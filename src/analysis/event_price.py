"""Estudo de evento de preço (H1, Fase 3).

Especificação (fixada antes dos resultados, ver docs/decisions.md):
- Retorno simples diário. O retorno do dia d vai do preço de ~00:00 UTC de d
  ao de ~00:00 UTC de d+1, então o dia 0 cobre o dia do hack.
- Modelo de mercado por MQO em [-120,-11], exigindo pelo menos 90% dos dias.
- Benchmarks: ETH (principal), moeda nativa da chain principal do evento e
  índice DeFi equal-weighted sem o próprio token (robustez). Um benchmark é
  pulado quando coincide com o token do evento.
- Janelas: [-1,+1], [0,+1], [0,+5], [0,+10], [0,+30].
- CAR (soma dos retornos anormais) e BHAR (buy-and-hold do token menos o
  buy-and-hold implícito no modelo de mercado).
- Testes: transversal t, BMP, Corrado multi-dia, bootstrap e Wilcoxon.

Saídas em data/processed/:
- price_car.parquet         um registro por evento x benchmark x janela
- price_ar_daily.parquet    retornos anormais diários em [-120,+30]
- price_event_study.csv     tabela resumo por benchmark x janela
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.analysis import stats as st
from src.collect.chain_names import CHAIN_GECKO_FALLBACK
from src.collect.prices import DEFI_INDEX
from src.config import PROCESSED_DIR

log = logging.getLogger(__name__)

EST = (-120, -11)
REL_MIN, REL_MAX = -120, 30
EST_MIN_SHARE = 0.9
WINDOWS = [(-1, 1), (0, 1), (0, 5), (0, 10), (0, 30)]
BENCHMARKS = ["eth", "native", "defi_index"]
MAIN_BENCHMARK = "eth"
MIN_INDEX_CONSTITUENTS = 5


SPIKE_FACTOR = 3.0
REVERT_TOL = 1.5
LEVEL_BREAK = 10.0  # alta diária acima deste fator indica quebra de nível na série


def remove_spikes(wide: pd.DataFrame) -> pd.DataFrame:
    """Remove erros de cotação de um dia só (pico que se reverte).

    Um ponto é tratado como erro da fonte quando difere por um fator maior que
    3 do dia anterior e do dia seguinte, na mesma direção, e os dois vizinhos
    estão a menos de um fator 1,5 um do outro (o preço volta ao nível prévio). Regra objetiva,
    aplicada a todas as séries, sem olhar para as datas dos eventos.
    """
    prev, nxt = wide.shift(1), wide.shift(-1)
    # o preço precisa voltar ao nível anterior: um crash real seguido de
    # recuperação parcial (ex.: Bunny 19/05/2021, 232 -> 11,6 -> 43,8) não é erro
    ratio = prev / nxt
    reverts = (ratio >= 1 / REVERT_TOL) & (ratio <= REVERT_TOL)
    up = (wide > SPIKE_FACTOR * prev) & (wide > SPIKE_FACTOR * nxt) & reverts
    down = (wide < prev / SPIKE_FACTOR) & (wide < nxt / SPIKE_FACTOR) & reverts
    n = int((up | down).sum().sum())
    if n:
        log.info("picos de cotação removidos: %d pontos", n)
    return wide.mask(up | down)


def load_returns() -> pd.DataFrame:
    """Matriz de retornos simples (datas x moedas), sem o último ponto intradiário."""
    px = pd.read_parquet(PROCESSED_DIR / "prices.parquet")
    px = px[px["price"] > 0]
    last_full = px["date"].max() - pd.Timedelta(days=1)
    px = px[px["date"] <= last_full]
    wide = px.pivot(index="date", columns="coin", values="price")
    wide = wide.reindex(pd.date_range(wide.index.min(), wide.index.max(), freq="D"))
    wide = remove_spikes(wide)
    # R_d = P_{d+1} / P_d - 1, indexado pelo dia d
    return wide.shift(-1) / wide - 1


def defi_index_returns(rets: pd.DataFrame, exclude: str | None) -> pd.Series:
    cols = [c for c in DEFI_INDEX if c in rets.columns and c != exclude]
    sub = rets[cols]
    idx = sub.mean(axis=1, skipna=True)
    return idx.where(sub.notna().sum(axis=1) >= MIN_INDEX_CONSTITUENTS)


def native_coin(chain: str | None, chains: pd.DataFrame) -> str | None:
    if not chain:
        return None
    m = chains.set_index("chain")["gecko_id"].dropna().to_dict()
    return m.get(chain) or CHAIN_GECKO_FALLBACK.get(chain)


def _market_model(ri: pd.Series, rm: pd.Series) -> dict | None:
    """Estima o modelo de mercado e devolve parâmetros e retornos anormais."""
    rel = ri.index
    est_mask = (rel >= EST[0]) & (rel <= EST[1])
    est = pd.concat([ri[est_mask], rm[est_mask]], axis=1, keys=["ri", "rm"]).dropna()
    n_est_days = EST[1] - EST[0] + 1
    if len(est) < EST_MIN_SHARE * n_est_days:
        return None
    x, y = est["rm"].to_numpy(), est["ri"].to_numpy()
    xm = x.mean()
    sxx = ((x - xm) ** 2).sum()
    beta = ((x - xm) * (y - y.mean())).sum() / sxx
    alpha = y.mean() - beta * xm
    resid = y - alpha - beta * x
    sigma = np.sqrt((resid**2).sum() / (len(y) - 2))
    expected = alpha + beta * rm
    return {
        "alpha": alpha,
        "beta": beta,
        "sigma": sigma,
        "T": len(y),
        "rm_mean": xm,
        "sxx": sxx,
        "ar": ri - expected,
        "expected": expected,
    }


def _rank_u(ar: pd.Series) -> pd.Series:
    """U = K/(1+M) - 0,5 sobre a série combinada estimação + evento."""
    valid = ar.dropna()
    k = valid.rank()
    return (k / (1 + len(valid)) - 0.5).reindex(ar.index)


def run(events: pd.DataFrame | None = None, save: bool = True, rets: pd.DataFrame | None = None,
        benchmarks: list[str] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Estudo de evento de preço. Sem argumentos, roda a especificação principal
    e grava os arquivos. Com `events`, roda sobre esses eventos (robustez)."""
    bench_list = benchmarks or BENCHMARKS
    chains = pd.read_parquet(PROCESSED_DIR / "chains.parquet")
    if events is None:
        ev = pd.read_parquet(PROCESSED_DIR / "events.parquet")
        ev = ev[ev["sample_price"]].copy()
    else:
        ev = events.copy()
    rets = load_returns() if rets is None else rets
    rel_days = np.arange(REL_MIN, REL_MAX + 1)

    car_rows, ar_rows, u_cols, excluded = [], [], {b: {} for b in bench_list}, []
    for e in ev.itertuples():
        dates = pd.DatetimeIndex([e.date + pd.Timedelta(days=int(k)) for k in rel_days])
        ri = pd.Series(rets[e.gecko_id].reindex(dates).to_numpy(), index=rel_days)
        if (ri > LEVEL_BREAK - 1).any():
            # alta de mais de 10x em um dia: quebra de nível na fonte (ex.: Rubic 2022)
            log.info("excluído por quebra de nível na série: %s %s", e.name, e.date.date())
            excluded.append(e.hack_id)
            continue
        nat = native_coin(e.main_chain, chains)
        bench = {
            "eth": "ethereum",
            "native": nat,
            "defi_index": None,  # construído abaixo
        }
        for b in bench_list:
            coin = bench[b]
            if b == "defi_index":
                rm_full = defi_index_returns(rets, exclude=e.gecko_id)
            else:
                if coin is None or coin == e.gecko_id or coin not in rets.columns:
                    continue
                rm_full = rets[coin]
            rm = pd.Series(rm_full.reindex(dates).to_numpy(), index=rel_days)
            mm = _market_model(ri, rm)
            if mm is None:
                continue
            ar = mm["ar"]
            u_cols[b][e.hack_id] = _rank_u(ar)
            for k in rel_days:
                ar_rows.append((e.hack_id, b, int(k), ar[k]))
            for w in WINDOWS:
                sl = (ar.index >= w[0]) & (ar.index <= w[1])
                L = int(sl.sum())
                car = ar[sl].sum()
                # robustez: CAR em log-retornos (evita o viés de somar retornos simples extremos)
                car_log = (np.log1p(ri[sl]) - np.log1p(mm["expected"][sl])).sum()
                bhar = (1 + ri[sl]).prod() - (1 + mm["expected"][sl]).prod()
                rm_w = rm[sl].sum()
                var_car = mm["sigma"] ** 2 * (
                    L + L**2 / mm["T"] + (rm_w - L * mm["rm_mean"]) ** 2 / mm["sxx"]
                )
                car_rows.append(
                    {
                        "hack_id": e.hack_id,
                        "benchmark": b,
                        "window": f"[{w[0]},{w[1]}]",
                        "car": car,
                        "bhar": bhar,
                        "car_log": car_log,
                        "scar": car / np.sqrt(var_car),
                        "alpha": mm["alpha"],
                        "beta": mm["beta"],
                        "sigma": mm["sigma"],
                        "T": mm["T"],
                    }
                )

    car = pd.DataFrame(car_rows)
    ar = pd.DataFrame(ar_rows, columns=["hack_id", "benchmark", "rel_day", "ar"])
    if save:
        car.to_parquet(PROCESSED_DIR / "price_car.parquet", index=False)
        ar.to_parquet(PROCESSED_DIR / "price_ar_daily.parquet", index=False)

    summary = []
    for b in bench_list:
        u = pd.DataFrame(u_cols[b])
        for w in WINDOWS:
            wl = f"[{w[0]},{w[1]}]"
            sub = car[(car["benchmark"] == b) & (car["window"] == wl)]
            if sub.empty:
                continue
            s_car = st.summarize(sub["car"].to_numpy(), sub["scar"].to_numpy())
            s_bh = st.summarize(sub["bhar"].to_numpy())
            s_lg = st.summarize(sub["car_log"].to_numpy())
            zc, pc = st.corrado_test(u, w)
            summary.append(
                {
                    "benchmark": b,
                    "window": wl,
                    **{f"car_{k}": v for k, v in s_car.items()},
                    "z_corrado": zc,
                    "p_corrado": pc,
                    "bhar_mean": s_bh["mean"],
                    "bhar_median": s_bh["median"],
                    "bhar_p_boot": s_bh["p_boot"],
                    "bhar_p_wilcoxon": s_bh["p_wilcoxon"],
                    "carlog_mean": s_lg["mean"],
                    "carlog_median": s_lg["median"],
                    "carlog_p_boot": s_lg["p_boot"],
                }
            )
    summary = pd.DataFrame(summary)
    if save:
        summary.to_csv(PROCESSED_DIR / "price_event_study.csv", index=False)
    return car, summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _, s = run()
    pd.set_option("display.width", 250)
    cols = ["benchmark", "window", "car_n", "car_mean", "car_median", "car_frac_neg",
            "p_csect", "car_p_bmp", "p_corrado", "car_p_boot", "car_p_wilcoxon", "bhar_mean", "bhar_median", "carlog_mean", "carlog_median"]
    s = s.rename(columns={"car_p_csect": "p_csect"})
    print(s[cols].round(4).to_string(index=False))

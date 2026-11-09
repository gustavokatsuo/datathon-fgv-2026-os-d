"""Nível da blockchain (H4, Fase 5).

1. Retorno anormal da moeda nativa da chain do hack (benchmark BTC).
2. Crescimento anormal da oferta de stablecoins na chain.
3. Perda de paridade de ativos wrapped em hacks de bridge (estudo de casos).

Especificação registrada em docs/decisions.md antes de rodar.

Uso: python -m src.analysis.chain_level
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from src.analysis import stats as st
from src.analysis.event_price import WINDOWS, _market_model, load_returns, native_coin
from src.config import PROCESSED_DIR

log = logging.getLogger(__name__)

EXCLUDED_TARGETS = {"CEX", "Wallet"}
MIN_CHAIN_TVL = 10e6
LARGE = [0.01, 0.05]
REL = np.arange(-120, 31)
SC_BASE = (-60, -11)
BRIDGE_ASSETS = Path(__file__).resolve().parents[1] / "build" / "bridge_assets.csv"


def chain_sample() -> pd.DataFrame:
    ev = pd.read_parquet(PROCESSED_DIR / "events.parquet")
    ct = pd.read_parquet(PROCESSED_DIR / "chain_tvl.parquet").set_index(["chain", "date"])["tvl"]
    s = ev[ev["in_base"] & (ev["n_chains"] == 1) & ~ev["is_chain_target"]
           & ~ev["target_type"].isin(EXCLUDED_TARGETS)].copy()
    s["chain_tvl"] = [ct.get((c, d), np.nan) for c, d in zip(s["main_chain"], s["date"])]
    s = s[s["chain_tvl"] >= MIN_CHAIN_TVL].copy()
    s["loss_chain"] = s["amount_usd"] / s["chain_tvl"]
    s["log_loss_chain"] = np.log(s["loss_chain"])
    return s


def native_study(s: pd.DataFrame) -> pd.DataFrame:
    chains = pd.read_parquet(PROCESSED_DIR / "chains.parquet")
    rets = load_returns()
    rows = []
    for e in s.itertuples():
        coin = native_coin(e.main_chain, chains)
        if coin is None or coin not in rets.columns:
            continue
        bench = "ethereum" if coin == "bitcoin" else "bitcoin"
        dates = pd.DatetimeIndex([e.date + pd.Timedelta(days=int(k)) for k in REL])
        ri = pd.Series(rets[coin].reindex(dates).to_numpy(), index=REL)
        if ri.loc[-1:30].isna().any():
            continue
        rm = pd.Series(rets[bench].reindex(dates).to_numpy(), index=REL)
        mm = _market_model(ri, rm)
        if mm is None:
            continue
        for w in WINDOWS:
            sl = (REL >= w[0]) & (REL <= w[1])
            L = int(sl.sum())
            car = mm["ar"][sl].sum()
            var = mm["sigma"] ** 2 * (L + L**2 / mm["T"] + (rm[sl].sum() - L * mm["rm_mean"]) ** 2 / mm["sxx"])
            rows.append({"hack_id": e.hack_id, "native": coin, "window": f"[{w[0]},{w[1]}]",
                         "car": car, "scar": car / np.sqrt(var)})
    return pd.DataFrame(rows)


def stablecoin_study(s: pd.DataFrame) -> pd.DataFrame:
    sc = pd.read_parquet(PROCESSED_DIR / "stablecoin_supply.parquet")
    by_chain = {c: g.set_index("date")["circulating_usd"] for c, g in sc.groupby("chain")}
    rows = []
    for e in s.itertuples():
        ser = by_chain.get(e.main_chain)
        if ser is None:
            continue
        days = pd.date_range(e.date + pd.Timedelta(days=SC_BASE[0]), e.date + pd.Timedelta(days=31))
        lvl = ser.reindex(days)
        lvl = lvl.where(lvl > 0)
        g = np.log(lvl).diff().shift(-1)  # g(t) = ln S(t+1) - ln S(t)
        g.index = np.arange(SC_BASE[0], 32)
        base = g.loc[SC_BASE[0]:SC_BASE[1]].dropna()
        if len(base) < 0.9 * (SC_BASE[1] - SC_BASE[0] + 1) or g.loc[-1:30].isna().any():
            continue
        mu, sd = base.mean(), base.std(ddof=1)
        for w in WINDOWS:
            sl = g.loc[w[0]:w[1]]
            ab = (sl - mu).sum()
            rows.append({"hack_id": e.hack_id, "window": f"[{w[0]},{w[1]}]", "abn_growth": ab,
                         "scaf": ab / (sd * np.sqrt(len(sl))) if sd > 0 else np.nan,
                         "supply_pre": lvl.iloc[-SC_BASE[0]] if len(lvl) > -SC_BASE[0] else np.nan})
    return pd.DataFrame(rows)


def _summ(df: pd.DataFrame, value: str, scar: str, s: pd.DataFrame, label: str) -> list[dict]:
    out = []
    d = df.merge(s[["hack_id", "loss_chain"]], on="hack_id")
    for subset, mask in [("todos", d["loss_chain"] > 0)] + [
        (f"perda >= {t:.0%} do TVL da chain", d["loss_chain"] >= t) for t in LARGE
    ]:
        for w in WINDOWS:
            sub = d[mask & (d["window"] == f"[{w[0]},{w[1]}]")]
            out.append({"medida": label, "amostra": subset, "window": f"[{w[0]},{w[1]}]",
                        **st.summarize(sub[value].to_numpy(), sub[scar].to_numpy())})
    return out


def dose_response(df: pd.DataFrame, value: str, s: pd.DataFrame, label: str) -> list[dict]:
    out = []
    d = df.merge(s[["hack_id", "log_loss_chain", "main_chain"]], on="hack_id")
    d["ethereum"] = (d["main_chain"] == "Ethereum").astype(int)
    for w in ["[0,1]", "[0,5]", "[0,30]"]:
        sub = d[d["window"] == w]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            m = smf.ols(f"{value} ~ log_loss_chain + ethereum", sub).fit(cov_type="HC3")
        out.append({"medida": label, "window": w, "n": int(m.nobs),
                    "b_log_loss_chain": m.params["log_loss_chain"],
                    "p_log_loss_chain": m.pvalues["log_loss_chain"]})
    return out


def bridge_cases() -> pd.DataFrame:
    spec = pd.read_csv(BRIDGE_ASSETS)
    px = pd.read_parquet(PROCESSED_DIR / "bridge_asset_prices.parquet")
    ev = pd.read_parquet(PROCESSED_DIR / "events.parquet").set_index("hack_id")
    rows = []
    for s in spec.itertuples():
        d0 = ev.at[s.hack_id, "date"]
        p = px[px["hack_id"] == s.hack_id].pivot(index="date", columns="coin", values="price")
        ratio = (p[s.asset_id] / p[s.reference_id]).dropna()
        rel = ((ratio.index - d0).days).astype(int)
        ratio.index = rel
        base = ratio.get(-1, np.nan)
        dev = ratio / base - 1
        w = dev.loc[0:30]
        rows.append({"caso": s.name, "ativo": s.asset_label, "data": d0.date(),
                     "desvio_d1": dev.get(1, np.nan), "desvio_d7": dev.get(7, np.nan),
                     "desvio_d30": dev.get(30, np.nan), "desvio_min_0_30": w.min(),
                     "dia_do_minimo": int(w.idxmin()) if len(w) else np.nan})
        for k, v in dev.loc[-10:30].items():
            rows.append({"caso": s.name, "rel_day": int(k), "desvio": v, "serie": True})
    df = pd.DataFrame(rows)
    df[df["serie"] != True].drop(columns=["serie", "rel_day", "desvio"]).to_csv(  # noqa: E712
        PROCESSED_DIR / "bridge_depeg_cases.csv", index=False)
    df[df["serie"] == True][["caso", "rel_day", "desvio"]].to_parquet(  # noqa: E712
        PROCESSED_DIR / "bridge_depeg_daily.parquet", index=False)
    return df[df["serie"] != True].drop(columns=["serie", "rel_day", "desvio"])  # noqa: E712


def run() -> None:
    s = chain_sample()
    nat = native_study(s)
    sc = stablecoin_study(s)
    nat.to_parquet(PROCESSED_DIR / "chain_native_car.parquet", index=False)
    sc.to_parquet(PROCESSED_DIR / "chain_stablecoin_flow.parquet", index=False)
    summary = pd.DataFrame(_summ(nat, "car", "scar", s, "CAR moeda nativa")
                           + _summ(sc, "abn_growth", "scaf", s, "crescimento anormal de stablecoins"))
    summary.to_csv(PROCESSED_DIR / "chain_level_study.csv", index=False)
    dose = pd.DataFrame(dose_response(nat, "car", s, "CAR moeda nativa")
                        + dose_response(sc, "abn_growth", s, "stablecoins"))
    dose.to_csv(PROCESSED_DIR / "chain_level_dose.csv", index=False)
    cases = bridge_cases()

    pd.set_option("display.width", 250)
    print(f"amostra de chain: {len(s)} eventos, {s['main_chain'].nunique()} chains")
    cols = ["medida", "amostra", "window", "n", "mean", "median", "frac_neg", "p_csect", "p_bmp", "p_boot", "p_wilcoxon"]
    print(summary[cols].round(4).to_string(index=False))
    print(dose.round(4).to_string(index=False))
    print(cases.round(4).to_string(index=False))


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    run()

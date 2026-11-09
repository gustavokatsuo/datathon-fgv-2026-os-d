"""Estudo de evento de TVL: corrida bancária on-chain (H1, Fase 3).

Decomposição token a token, com snapshots diários às 00:00 UTC. O fluxo do
dia t vai do snapshot de t ao de t+1, então o dia 0 cobre o dia do hack:

    TVL(t+1) - TVL(t) = Σ q(t)·[P(t+1) - P(t)]      efeito preço
                      + Σ P(t+1)·[q(t+1) - q(t)]    fluxo líquido

com P = usd/qty implícito na DefiLlama (último preço conhecido se faltar).

- f(t) = fluxo(t)/TVL(t), limitado a [-1,+1]. Fluxo normal = média de f em
  [-60,-11] (pelo menos 90% dos dias).
- Fluxo anormal acumulado AF[a,b] = soma de fluxo(t)/TVL_pre - normal, com
  TVL_pre = snapshot das 00:00 do dia 0 (fechamento do dia -1).
- Fluxo anormal líquido do roubo: AF + min(perda, TVL_pre)/TVL_pre.
  Conservador contra H1, pois nem todo valor roubado saía do TVL medido.

Saídas em data/processed/:
- tvl_flows.parquet       um registro por evento x janela
- tvl_flows_daily.parquet fluxo anormal diário em [-60,+30]
- tvl_event_study.csv     tabela resumo
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.analysis import stats as st
from src.config import PROCESSED_DIR

log = logging.getLogger(__name__)

BASE = (-60, -11)
REL_MIN, REL_MAX = -60, 30
BASE_MIN_SHARE = 0.9
WINDOWS = [(-1, 1), (0, 1), (0, 5), (0, 10), (0, 30)]
FLOW_CLIP = 1.0


def decompose(tok: pd.DataFrame) -> pd.DataFrame:
    """Recebe o painel (date, token, qty, usd) de um protocolo e devolve, por
    dia t, TVL(t), efeito preço e fluxo de t para t+1."""
    q = tok.pivot_table(index="date", columns="token", values="qty", aggfunc="last")
    u = tok.pivot_table(index="date", columns="token", values="usd", aggfunc="last")
    days = pd.date_range(q.index.min(), q.index.max(), freq="D")
    q = q.reindex(days)
    u = u.reindex(days)
    observed = q.notna().any(axis=1)  # dia com snapshot
    price = (u / q.where(q != 0)).replace([np.inf, -np.inf], np.nan).ffill()
    q = q.fillna(0.0)
    q_next, p_next = q.shift(-1), price.shift(-1).fillna(price)
    tvl = (q * price).sum(axis=1, min_count=1)
    price_eff = (q * (p_next - price)).sum(axis=1)
    flow = (p_next * (q_next - q)).sum(axis=1)
    out = pd.DataFrame({"tvl": tvl, "price_effect": price_eff, "flow": flow})
    # só vale quando há snapshot em t e em t+1
    valid = observed & observed.shift(-1, fill_value=False)
    return out.where(valid)


def _tvl_at(tok: pd.DataFrame, day: pd.Timestamp) -> float:
    snap = tok[tok["date"] == day]
    return float(snap["usd"].sum()) if len(snap) else np.nan


def run(events: pd.DataFrame | None = None, save: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Sem argumentos, roda a especificação principal e grava os arquivos."""
    if events is None:
        ev = pd.read_parquet(PROCESSED_DIR / "events.parquet")
        ev = ev[ev["sample_tvl"]].copy()
    else:
        ev = events.copy()
    tok = pd.read_parquet(
        PROCESSED_DIR / "tvl_tokens.parquet", filters=[("slug", "in", list(ev["slug"].unique()))]
    )
    tok_by_slug = {k: g for k, g in tok.groupby("slug")}
    rel_days = np.arange(REL_MIN, REL_MAX + 1)

    rows, daily = [], []
    for e in ev.itertuples():
        g = tok_by_slug[e.slug]
        lo, hi = e.date + pd.Timedelta(days=REL_MIN), e.date + pd.Timedelta(days=REL_MAX + 1)
        d = decompose(g[(g["date"] >= lo) & (g["date"] <= hi)])
        idx_days = np.arange(REL_MIN, REL_MAX + 2)  # inclui o snapshot do dia +31
        d = d.reindex(pd.DatetimeIndex([e.date + pd.Timedelta(days=int(k)) for k in idx_days]))
        d.index = idx_days
        # o snapshot do dia +31 só tem TVL (o fluxo dele sai da janela)
        d.loc[REL_MAX + 1, "tvl"] = _tvl_at(g, e.date + pd.Timedelta(days=REL_MAX + 1))

        tvl_pre = d.at[0, "tvl"]
        if not np.isfinite(tvl_pre) or tvl_pre <= 0:
            log.info("sem TVL_pre: %s", e.name)
            continue
        f = (d["flow"] / d["tvl"]).clip(-FLOW_CLIP, FLOW_CLIP)
        base = f.loc[BASE[0]:BASE[1]].dropna()
        if len(base) < BASE_MIN_SHARE * (BASE[1] - BASE[0] + 1):
            log.info("linha de base insuficiente: %s", e.name)
            continue
        mu, sd = base.mean(), base.std(ddof=1)
        f_evt = (d["flow"] / tvl_pre).clip(-FLOW_CLIP, FLOW_CLIP)
        af = f_evt - mu
        theft = min(e.amount_usd, tvl_pre) / tvl_pre
        for k in rel_days:
            daily.append((e.hack_id, int(k), f.get(k), af.get(k) if k >= 0 else f.get(k) - mu))
        for w in WINDOWS:
            sl = af.loc[w[0]:w[1]]
            if sl.isna().any():
                continue
            L = len(sl)
            cum_af = sl.sum()
            pe = (d["price_effect"].loc[w[0]:w[1]].sum()) / tvl_pre
            tvl_end = d["tvl"].get(w[1] + 1, np.nan)
            tvl_start = d["tvl"].get(w[0], np.nan)
            rows.append(
                {
                    "hack_id": e.hack_id,
                    "window": f"[{w[0]},{w[1]}]",
                    "abn_flow": cum_af,
                    "abn_flow_ex_theft": cum_af + theft,
                    "price_effect": pe,
                    "tvl_change": tvl_end / tvl_start - 1 if np.isfinite(tvl_end) and tvl_start > 0 else np.nan,
                    "scaf": cum_af / (sd * np.sqrt(L)) if sd > 0 else np.nan,
                    "scaf_ex_theft": (cum_af + theft) / (sd * np.sqrt(L)) if sd > 0 else np.nan,
                    "theft_share": theft,
                    "base_mean": mu,
                    "base_sd": sd,
                    "tvl_pre": tvl_pre,
                }
            )

    res = pd.DataFrame(rows)
    res = res.merge(ev[["hack_id", "name", "target_type", "category"]], on="hack_id", how="left")
    if save:
        res.to_parquet(PROCESSED_DIR / "tvl_flows.parquet", index=False)
    if save:
        pd.DataFrame(daily, columns=["hack_id", "rel_day", "flow_rate", "abn_flow"]).to_parquet(
            PROCESSED_DIR / "tvl_flows_daily.parquet", index=False
        )

    summary = []
    for subset, mask in [("todos", res["hack_id"].notna()), ("sem CEX", res["target_type"] != "CEX")]:
        r = res[mask]
        for w in WINDOWS:
            wl = f"[{w[0]},{w[1]}]"
            sub = r[r["window"] == wl]
            for measure, scar in [("abn_flow", "scaf"), ("abn_flow_ex_theft", "scaf_ex_theft"),
                                  ("tvl_change", None), ("price_effect", None)]:
                s = st.summarize(sub[measure].to_numpy(), sub[scar].to_numpy() if scar else None)
                summary.append({"amostra": subset, "window": wl, "measure": measure, **s})
    summary = pd.DataFrame(summary)
    if save:
        summary.to_csv(PROCESSED_DIR / "tvl_event_study.csv", index=False)
    return res, summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _, s = run()
    pd.set_option("display.width", 250)
    cols = ["amostra", "window", "measure", "n", "mean", "median", "frac_neg", "p_csect",
            "p_bmp", "p_boot", "p_wilcoxon"]
    print(s.reindex(columns=cols).round(4).to_string(index=False))

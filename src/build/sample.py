"""Construção da amostra de eventos (Fase 2).

Critérios fixados antes de ver qualquer resultado (ver docs/decisions.md):
- Período: hacks a partir de 01/01/2020 com janela [-1,+30] completa nos dados.
- Relevância: perda de pelo menos US$ 1 milhão.
- Amostra de preço: token com preço em >= 90% dos dias de [-120,-11] e em
  todos os dias de [-1,+30].
- Amostra de TVL: quantidades por token em >= 90% dos dias de [-60,-11] e em
  todos os dias de [-1,+30], e TVL(-1) >= US$ 1 milhão.
- Datas corrigidas manualmente em docs/date_validation.csv substituem a da
  DefiLlama.

Saída: data/processed/events.parquet (um registro por hack, com flags de
amostra) e tabela descritiva por categoria em data/processed/.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from src.build.taxonomy import CATEGORIES, apply_taxonomy
from src.collect.coverage import EVT, _covered
from src.config import DOCS_DIR, PROCESSED_DIR

log = logging.getLogger(__name__)

START = pd.Timestamp("2020-01-01")
MIN_LOSS = 1e6
PRICE_EST = (-120, -11)
TVL_BASE = (-60, -11)
MIN_TVL_PRE = 1e6
OVERLAP_WINDOW = (-120, 30)  # outro evento do mesmo token/protocolo nesta janela contamina
DATE_FIXES = DOCS_DIR / "date_validation.csv"
RECOVERY_CSV = Path(__file__).with_name("recovery_manual.csv")
RETURNED_MIN_SHARE = 0.5


def _load_date_fixes() -> pd.DataFrame:
    if not DATE_FIXES.exists():
        return pd.DataFrame(columns=["hack_id", "date_validated"])
    fx = pd.read_csv(DATE_FIXES, parse_dates=["date_defillama", "date_validated"])
    return fx[["hack_id", "date_validated"]]


def _overlap(events: pd.DataFrame, key: str) -> pd.Series:
    """True se outro evento com a mesma chave cai na janela de contaminação."""
    flag = pd.Series(False, index=events.index)
    for _, g in events.dropna(subset=[key]).groupby(key):
        if len(g) < 2:
            continue
        d = g["date"].to_numpy(dtype="datetime64[ns]")
        for idx, d0 in zip(g.index, d):  # d0 é numpy datetime64
            delta = (d - d0) / np.timedelta64(1, "D")
            others = (delta >= OVERLAP_WINDOW[0]) & (delta <= OVERLAP_WINDOW[1]) & (delta != 0)
            # mesmo dia com outra entrada também conta (registro duplicado ou ataque em série)
            same_day = (delta == 0).sum() > 1
            flag.loc[idx] = bool(others.any() or same_day)
    return flag


def build_events() -> pd.DataFrame:
    hacks = pd.read_parquet(PROCESSED_DIR / "hacks.parquet")
    cov = pd.read_parquet(PROCESSED_DIR / "coverage.parquet")
    protocols = pd.read_parquet(PROCESSED_DIR / "protocols.parquet")
    prices = pd.read_parquet(PROCESSED_DIR / "prices.parquet")
    tvl = pd.read_parquet(PROCESSED_DIR / "tvl_daily.parquet")
    tok = pd.read_parquet(PROCESSED_DIR / "tvl_tokens.parquet", columns=["slug", "date"])

    ev = apply_taxonomy(hacks)
    ev = ev.merge(
        cov[["hack_id", "slug", "gecko_id", "main_chain", "n_chains", "in_protocols"]],
        on="hack_id",
        how="left",
    )

    # datas validadas manualmente
    fx = _load_date_fixes()
    ev["date_defillama"] = ev["date"]
    ev = ev.merge(fx, on="hack_id", how="left")
    ev["date"] = ev["date_validated"].fillna(ev["date"])
    ev["date_fixed"] = ev["date"] != ev["date_defillama"]
    ev = ev.drop(columns="date_validated")

    meta = protocols.set_index("slug")[["category", "audits", "oracles", "forked_from_ids", "listed_at"]]
    meta = meta.rename(columns={"category": "protocol_category"})
    ev = ev.join(meta, on="slug")
    ev["audited"] = ev["audits"].fillna(0) > 0

    # devolução pelo atacante: a codificação manual (src/build/recovery_manual.csv)
    # tem precedência, pois o campo da DefiLlama mistura recuperação junto ao
    # atacante com ressarcimento de usuários pelo próprio protocolo
    ev["returned_usd"] = ev["returned_usd"].fillna(0.0)
    share_dl = pd.Series(
        np.where(ev["amount_usd"] > 0, (ev["returned_usd"] / ev["amount_usd"]).clip(upper=1), np.nan),
        index=ev.index,
    )
    rec = pd.read_csv(RECOVERY_CSV).set_index("hack_id")
    manual = ev["hack_id"].map(rec["recovered_share"])
    ev["recovered_share"] = manual.fillna(share_dl).fillna(0.0)
    ev["users_reimbursed"] = ev["hack_id"].map(rec["users_reimbursed"]).fillna(False).astype(bool)
    ev["funds_returned"] = ev["recovered_share"] >= RETURNED_MIN_SHARE

    # cobertura com as datas finais
    px = prices[prices["price"] > 0]
    last_full_day = px["date"].max() - pd.Timedelta(days=1)  # último ponto é intradiário
    px = px[px["date"] <= last_full_day]
    px_dates = {k: pd.DatetimeIndex(g["date"]) for k, g in px.groupby("coin")}
    tvl = tvl[tvl["tvl_usd"].notna()]
    tok_dates = {k: pd.DatetimeIndex(g["date"].unique()) for k, g in tok.groupby("slug")}
    tvl_dates = {k: pd.DatetimeIndex(g["date"]) for k, g in tvl.groupby("slug")}
    tvl_level = tvl.set_index(["slug", "date"])["tvl_usd"]

    def has(x) -> bool:
        return isinstance(x, str) and len(x) > 0

    ev["price_cov"] = [
        has(g) and _covered(px_dates, g, d, PRICE_EST, EVT) for g, d in zip(ev["gecko_id"], ev["date"])
    ]
    ev["tvl_tokens_cov"] = [
        has(s) and _covered(tok_dates, s, d, TVL_BASE, EVT) for s, d in zip(ev["slug"], ev["date"])
    ]
    ev["tvl_total_cov"] = [
        has(s) and _covered(tvl_dates, s, d, TVL_BASE, EVT) for s, d in zip(ev["slug"], ev["date"])
    ]
    ev["tvl_pre"] = [
        tvl_level.get((s, d - pd.Timedelta(days=1)), np.nan) if has(s) else np.nan
        for s, d in zip(ev["slug"], ev["date"])
    ]
    ev["loss_to_tvl"] = ev["amount_usd"] / ev["tvl_pre"]

    ev["overlap_token"] = _overlap(ev, "gecko_id")
    ev["overlap_protocol"] = _overlap(ev, "slug")

    base = (ev["date"] >= START) & (ev["amount_usd"].fillna(0) >= MIN_LOSS)
    ev["in_base"] = base
    ev["sample_price"] = base & ev["price_cov"]
    ev["sample_tvl"] = base & ev["tvl_tokens_cov"] & (ev["tvl_pre"] >= MIN_TVL_PRE)
    ev["sample_tvl_total"] = base & ev["tvl_total_cov"] & (ev["tvl_pre"] >= MIN_TVL_PRE)

    ev.to_parquet(PROCESSED_DIR / "events.parquet", index=False)
    return ev


def descriptive_table(ev: pd.DataFrame) -> pd.DataFrame:
    b = ev[ev["in_base"]]
    g = b.groupby("category")
    t = pd.DataFrame(
        {
            "n_eventos": g.size(),
            "perda_total_usd_bi": g["amount_usd"].sum() / 1e9,
            "perda_mediana_usd_mi": g["amount_usd"].median() / 1e6,
            "frac_bridge": g["bridge_hack"].mean(),
            "frac_devolucao": g["funds_returned"].mean(),
            "frac_ressarcido": g["users_reimbursed"].mean(),
            "frac_auditado": g["audited"].mean(),
            "n_amostra_preco": g["sample_price"].sum(),
            "n_amostra_tvl": g["sample_tvl"].sum(),
        }
    )
    t.loc["total"] = [
        len(b),
        b["amount_usd"].sum() / 1e9,
        b["amount_usd"].median() / 1e6,
        b["bridge_hack"].mean(),
        b["funds_returned"].mean(),
        b["users_reimbursed"].mean(),
        b["audited"].mean(),
        b["sample_price"].sum(),
        b["sample_tvl"].sum(),
    ]
    order = [c for c in CATEGORIES if c in t.index] + ["total"]
    t = t.loc[order]
    t.index = [CATEGORIES.get(c, "Total") for c in t.index]
    t.to_csv(PROCESSED_DIR / "table_categories.csv")
    return t


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    ev = build_events()
    b = ev[ev["in_base"]]
    print(f"base: {len(b)}  amostra de preço: {b['sample_price'].sum()}  amostra de TVL: {b['sample_tvl'].sum()}")
    print(descriptive_table(ev).round(2).to_string())


if __name__ == "__main__":
    main()

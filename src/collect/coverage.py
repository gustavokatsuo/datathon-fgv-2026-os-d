"""Relatório de cobertura da Fase 1.

Para cada hack, verifica se existem: protocolo na DefiLlama, histórico de TVL
nas janelas de estimação e evento, token com preço nessas janelas, preço da
moeda nativa da chain e série de stablecoins da chain.

Critério operacional (provisório, a ser fixado na Fase 2): uma janela está
coberta se tem observação em pelo menos 90% dos dias da estimação [-120,-11]
e em todos os dias de [-1,+30]. Para o TVL, valor zero conta como observado,
para não excluir os protocolos esvaziados pelo próprio hack.
"""

from __future__ import annotations

import pandas as pd

from src.collect.chain_names import CHAIN_GECKO_FALLBACK
from src.config import PROCESSED_DIR

EST = (-120, -11)
EVT = (-1, 30)
EST_MIN_SHARE = 0.9


def _covered(dates_by_key: dict, key, day0: pd.Timestamp, est=EST, evt=EVT) -> bool:
    dates = dates_by_key.get(key)
    if dates is None:
        return False
    e = pd.date_range(day0 + pd.Timedelta(days=est[0]), day0 + pd.Timedelta(days=est[1]))
    v = pd.date_range(day0 + pd.Timedelta(days=evt[0]), day0 + pd.Timedelta(days=evt[1]))
    return e.isin(dates).mean() >= EST_MIN_SHARE and v.isin(dates).all()


def build_coverage() -> pd.DataFrame:
    hacks = pd.read_parquet(PROCESSED_DIR / "hacks.parquet")
    protocols = pd.read_parquet(PROCESSED_DIR / "protocols.parquet")
    ptok = pd.read_parquet(PROCESSED_DIR / "protocol_tokens.parquet")
    tvl = pd.read_parquet(PROCESSED_DIR / "tvl_daily.parquet")
    tvl_tok = pd.read_parquet(PROCESSED_DIR / "tvl_tokens.parquet", columns=["slug", "date"])
    prices = pd.read_parquet(PROCESSED_DIR / "prices.parquet")
    chains = pd.read_parquet(PROCESSED_DIR / "chains.parquet")
    sc = pd.read_parquet(PROCESSED_DIR / "stablecoin_supply.parquet")

    # TVL zero é observação válida (protocolo esvaziado após o hack), não dado faltante
    tvl = tvl[tvl["tvl_usd"].notna()]
    tvl_dates = {k: pd.DatetimeIndex(g["date"]) for k, g in tvl.groupby("slug")}
    tok_dates = {k: pd.DatetimeIndex(g["date"].unique()) for k, g in tvl_tok.groupby("slug")}
    px = prices[prices["price"] > 0]
    px_dates = {k: pd.DatetimeIndex(g["date"]) for k, g in px.groupby("coin")}
    sc_dates = {k: pd.DatetimeIndex(g["date"]) for k, g in sc.groupby("chain")}

    by_id = protocols.set_index("protocol_id")
    tok_by_id = ptok.set_index("protocol_id")
    chain_gecko = chains.set_index("chain")["gecko_id"].dropna().to_dict()
    chain_gecko.update({k: v for k, v in CHAIN_GECKO_FALLBACK.items() if k not in chain_gecko})

    def ok(x) -> bool:
        return x is not None and not (isinstance(x, float) and pd.isna(x)) and x is not pd.NA

    rows = []
    for h in hacks.itertuples():
        pid = h.defillama_id if ok(h.defillama_id) else None
        d0 = h.date
        chains_h = list(h.chains) if h.chains is not None else []
        in_proto = pid is not None and pid in by_id.index
        slug = by_id.at[pid, "slug"] if in_proto else None
        gecko = tok_by_id.at[pid, "gecko_id"] if in_proto and pid in tok_by_id.index else None
        if h.is_chain_target and chains_h:
            gecko = chain_gecko.get(chains_h[0])
        gecko = gecko if ok(gecko) else None
        main_chain = chains_h[0] if chains_h else None
        native = chain_gecko.get(main_chain) if main_chain else None
        rows.append(
            {
                "hack_id": h.hack_id,
                "date": d0,
                "name": h.name,
                "amount_usd": h.amount_usd,
                "target_type": h.target_type,
                "classification": h.classification,
                "main_chain": main_chain,
                "n_chains": len(chains_h),
                "has_defillama_id": pid is not None,
                "in_protocols": in_proto,
                "slug": slug,
                "gecko_id": gecko,
                "has_token": gecko is not None,
                "tvl_window": slug is not None and _covered(tvl_dates, slug, d0),
                "tvl_tokens_window": slug is not None and _covered(tok_dates, slug, d0),
                "price_window": gecko is not None and _covered(px_dates, gecko, d0),
                "native_price_window": native is not None and _covered(px_dates, native, d0),
                "stablecoin_window": main_chain is not None and _covered(sc_dates, main_chain, d0),
            }
        )
    cov = pd.DataFrame(rows)
    cov.to_parquet(PROCESSED_DIR / "coverage.parquet", index=False)
    return cov


def summarize(cov: pd.DataFrame) -> pd.DataFrame:
    flags = [
        "has_defillama_id",
        "in_protocols",
        "has_token",
        "tvl_window",
        "tvl_tokens_window",
        "price_window",
        "native_price_window",
        "stablecoin_window",
    ]
    cov = cov.assign(
        amount_ge_1m=cov["amount_usd"].fillna(0) >= 1e6,
        since_2020=cov["date"] >= "2020-01-01",
    )
    groups = {
        "todos": cov,
        "2020+": cov[cov.since_2020],
        "2020+ e perda >= 1M": cov[cov.since_2020 & cov.amount_ge_1m],
    }
    out = pd.DataFrame({k: [len(g)] + [int(g[f].sum()) for f in flags] for k, g in groups.items()},
                       index=["n_eventos", *flags])
    return out

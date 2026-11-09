"""Histórico de TVL dos protocolos atingidos por hacks.

Fonte: https://api.llama.fi/protocol/{slug}. Usa os campos de nível superior
`tvl`, `tokens` (quantidades) e `tokensInUsd`, que correspondem ao TVL padrão
da DefiLlama (sem borrowed, staking e pool2). Conferido na inspeção do schema.

Saídas em data/processed/:
- tvl_daily.parquet    slug, date, tvl_usd
- tvl_tokens.parquet   slug, date, token, qty, usd (apenas valores não nulos)
- protocol_tokens.parquet  slug -> gecko_id do próprio protocolo ou do pai
"""

from __future__ import annotations

import logging

import pandas as pd

from src.collect.http import HTTPFailure, cached_json, parallel_map
from src.config import PROCESSED_DIR, RAW_DIR

log = logging.getLogger(__name__)

PROTOCOL_URL = "https://api.llama.fi/protocol/{slug}"
TVL_RAW = RAW_DIR / "tvl"


def _day(ts) -> pd.Timestamp:
    return pd.to_datetime(int(float(ts)), unit="s").normalize()


def fetch_protocol(slug: str) -> dict | None:
    try:
        return cached_json(PROTOCOL_URL.format(slug=slug), TVL_RAW / f"{slug}.json.gz")
    except HTTPFailure as exc:
        log.warning("sem histórico para %s: %s", slug, exc)
        return None


def _tvl_frame(slug: str, data: dict) -> pd.DataFrame:
    tvl = pd.DataFrame(data.get("tvl") or [])
    if tvl.empty:
        return pd.DataFrame(columns=["slug", "date", "tvl_usd"])
    tvl["date"] = tvl["date"].map(_day)
    # o último ponto do dia corrente costuma ser intradiário: mantém o último do dia
    tvl = tvl.groupby("date", as_index=False)["totalLiquidityUSD"].last()
    return tvl.rename(columns={"totalLiquidityUSD": "tvl_usd"}).assign(slug=slug)[
        ["slug", "date", "tvl_usd"]
    ]


def _wide(snapshots: list[dict]) -> pd.DataFrame:
    """Lista de {date, tokens: {token: valor}} -> tabela longa (date, token, valor)."""
    if not snapshots:
        return pd.DataFrame(columns=["date", "token", "value"])
    wide = pd.DataFrame.from_records([x["tokens"] for x in snapshots])
    wide.index = pd.to_datetime([int(float(x["date"])) for x in snapshots], unit="s").normalize()
    wide.index.name = "date"
    # último snapshot de cada dia
    wide = wide[~wide.index.duplicated(keep="last")]
    long = wide.stack().rename("value").reset_index()
    return long.rename(columns={long.columns[1]: "token"})


def _tokens_frame(slug: str, data: dict) -> pd.DataFrame:
    qty = _wide(data.get("tokens") or []).rename(columns={"value": "qty"})
    usd = _wide(data.get("tokensInUsd") or []).rename(columns={"value": "usd"})
    df = qty.merge(usd, on=["date", "token"], how="outer")
    # a API mistura int (às vezes enormes), float e string: padroniza em float
    for col in ("qty", "usd"):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
    df = df[(df["qty"].fillna(0) != 0) | (df["usd"].fillna(0) != 0)]
    return df.assign(slug=slug)[["slug", "date", "token", "qty", "usd"]]


def collect_tvl(hacks: pd.DataFrame, protocols: pd.DataFrame) -> None:
    by_id = protocols.set_index("protocol_id")
    ids = hacks["defillama_id"].dropna()
    ids = ids[ids.isin(by_id.index)].unique()
    slugs = sorted(by_id.loc[ids, "slug"].unique())
    parents = sorted(by_id.loc[ids, "parent_slug"].dropna().unique())
    log.info("TVL: %d protocolos e %d protocolos pais", len(slugs), len(parents))

    # 1) download em paralelo (só grava o cache, rede é o gargalo)
    def _download(slug: str) -> bool:
        if (TVL_RAW / f"{slug}.json.gz").exists():
            return True
        return fetch_protocol(slug) is not None

    parallel_map(_download, slugs + parents, "TVL download")

    # 2) processamento sequencial a partir do cache (CPU é o gargalo)
    tvl_parts, tok_parts = [], []
    for i, slug in enumerate(slugs, 1):
        data = fetch_protocol(slug)
        if data is not None:
            tvl_parts.append(_tvl_frame(slug, data))
            tok_parts.append(_tokens_frame(slug, data))
        if i % 100 == 0:
            log.info("TVL processamento %d/%d", i, len(slugs))
    parent_gecko = {}
    for slug in parents:
        data = fetch_protocol(slug)
        if data is not None:
            parent_gecko[slug] = data.get("gecko_id")

    token_map = []
    for pid in ids:
        p = by_id.loc[pid]
        own = p["gecko_id"] if pd.notna(p["gecko_id"]) else None
        par = parent_gecko.get(p["parent_slug"]) if pd.notna(p["parent_slug"]) else None
        token_map.append(
            {
                "protocol_id": pid,
                "slug": p["slug"],
                "parent_slug": p["parent_slug"],
                "gecko_id": own or par,
                "gecko_source": "own" if own else ("parent" if par else None),
            }
        )

    pd.concat(tvl_parts, ignore_index=True).to_parquet(
        PROCESSED_DIR / "tvl_daily.parquet", index=False
    )
    pd.concat(tok_parts, ignore_index=True).to_parquet(
        PROCESSED_DIR / "tvl_tokens.parquet", index=False
    )
    pd.DataFrame(token_map).to_parquet(PROCESSED_DIR / "protocol_tokens.parquet", index=False)

"""Coleta de hacks, protocolos e chains (DefiLlama).

Saídas em data/processed/:
- hacks.parquet       um registro por incidente da base de hacks
- protocols.parquet   metadados de todos os protocolos listados
- chains.parquet      chains com o id da moeda nativa no CoinGecko
"""

from __future__ import annotations

import hashlib
import logging

import pandas as pd

from src.collect.chain_names import canonical_chain
from src.collect.http import cached_json
from src.config import PROCESSED_DIR, RAW_DIR

log = logging.getLogger(__name__)

HACKS_URL = "https://api.llama.fi/hacks"
PROTOCOLS_URL = "https://api.llama.fi/protocols"
CHAINS_URL = "https://api.llama.fi/v2/chains"
STABLE_CHAINS_URL = "https://stablecoins.llama.fi/stablecoinchains"


def _hack_id(rec: dict) -> str:
    key = f"{rec['date']}|{rec['name']}|{rec.get('defillamaId')}|{rec.get('amount')}"
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def collect_hacks() -> pd.DataFrame:
    raw = cached_json(HACKS_URL, RAW_DIR / "hacks.json.gz")
    rows = []
    for r in raw:
        chains_raw = r.get("chain") or []
        chains = [c for c in (canonical_chain(x) for x in chains_raw) if c]
        did = r.get("defillamaId")
        did = str(did) if did is not None else None
        rows.append(
            {
                "hack_id": _hack_id(r),
                "date": pd.to_datetime(r["date"], unit="s", utc=True).tz_localize(None).normalize(),
                "name": r["name"],
                "classification": r.get("classification"),
                "technique": r.get("technique"),
                "amount_usd": r.get("amount"),
                "returned_usd": r.get("returnedFunds"),
                "chains_raw": list(chains_raw),
                "chains": chains,
                "bridge_hack": bool(r.get("bridgeHack")),
                "target_type": r.get("targetType"),
                "language": r.get("language"),
                "defillama_id": did,
                "is_chain_target": bool(did and did.startswith("chain#")),
                "parent_protocol_id": r.get("parentProtocolId"),
                "source": r.get("source") or None,
                "description": r.get("description"),
            }
        )
    df = pd.DataFrame(rows).sort_values(["date", "name"]).reset_index(drop=True)
    dup = df["hack_id"].duplicated().sum()
    if dup:
        raise ValueError(f"{dup} hack_id duplicados")
    df.to_parquet(PROCESSED_DIR / "hacks.parquet", index=False)
    log.info("hacks: %d registros", len(df))
    return df


def _oracle_names(p: dict) -> list[str]:
    names = set(p.get("oracles") or [])
    for o in p.get("oraclesBreakdown") or []:
        if o.get("name"):
            names.add(o["name"])
    return sorted(names)


def collect_protocols() -> pd.DataFrame:
    raw = cached_json(PROTOCOLS_URL, RAW_DIR / "protocols.json.gz")
    rows = []
    for p in raw:
        listed = p.get("listedAt")
        rows.append(
            {
                "protocol_id": str(p["id"]),
                "slug": p["slug"],
                "name": p["name"],
                "symbol": p.get("symbol"),
                "gecko_id": p.get("gecko_id"),
                "category": p.get("category"),
                "chains": [canonical_chain(c) for c in (p.get("chains") or [])],
                "oracles": _oracle_names(p),
                "oracles_breakdown": [
                    {"name": o.get("name"), "type": o.get("type")}
                    for o in (p.get("oraclesBreakdown") or [])
                ],
                "forked_from_ids": [str(x) for x in (p.get("forkedFromIds") or [])],
                "forked_from": list(p.get("forkedFrom") or []),
                "audits": pd.to_numeric(p.get("audits"), errors="coerce"),
                "audit_links": list(p.get("audit_links") or []),
                "listed_at": pd.to_datetime(listed, unit="s") if listed else pd.NaT,
                "parent_protocol": p.get("parentProtocol"),
                "parent_slug": p.get("parentProtocolSlug"),
                "deprecated": bool(p.get("deprecated")),
                "rugged": bool(p.get("rugged")),
                "language": p.get("language"),
                "tvl_now": p.get("tvl"),
                "mcap_now": p.get("mcap"),
            }
        )
    df = pd.DataFrame(rows)
    df.to_parquet(PROCESSED_DIR / "protocols.parquet", index=False)
    log.info("protocols: %d registros", len(df))
    return df


def collect_chains() -> pd.DataFrame:
    raw = cached_json(CHAINS_URL, RAW_DIR / "chains.json.gz")
    stable = cached_json(STABLE_CHAINS_URL, RAW_DIR / "stablecoin_chains.json.gz")
    stable_names = {c["name"] for c in stable}
    df = pd.DataFrame(
        [
            {
                "chain": c["name"],
                "gecko_id": c.get("gecko_id"),
                "gas_token_gecko_id": c.get("gasTokenGeckoId"),
                "token_symbol": c.get("tokenSymbol"),
                "chain_id": str(c["chainId"]) if c.get("chainId") is not None else None,
                "tvl_now": c.get("tvl"),
                "has_stablecoin_data": c["name"] in stable_names,
            }
            for c in raw
        ]
    )
    df.to_parquet(PROCESSED_DIR / "chains.parquet", index=False)
    log.info("chains: %d registros", len(df))
    return df

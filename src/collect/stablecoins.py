"""Oferta de stablecoins por chain via https://stablecoins.llama.fi.

Baixa a série agregada de cada chain que aparece na base de hacks e tem
cobertura de stablecoins, mais o total de todas as chains.

Saída: data/processed/stablecoin_supply.parquet com chain, date,
circulating_usd (soma de todas as âncoras, em USD) e circulating_pegged_usd
(apenas stablecoins atreladas ao dólar, em unidades).
"""

from __future__ import annotations

import logging
from urllib.parse import quote

import pandas as pd

from src.collect.http import HTTPFailure, cached_json
from src.config import PROCESSED_DIR, RAW_DIR

log = logging.getLogger(__name__)

CHART_URL = "https://stablecoins.llama.fi/stablecoincharts/{chain}"
SC_RAW = RAW_DIR / "stablecoins"


def _frame(chain: str, data: list) -> pd.DataFrame:
    rows = []
    for x in data:
        usd = x.get("totalCirculatingUSD") or {}
        circ = x.get("totalCirculating") or {}
        rows.append(
            {
                "chain": chain,
                "date": pd.to_datetime(int(x["date"]), unit="s").normalize(),
                "circulating_usd": float(sum(v for v in usd.values() if v is not None)),
                "circulating_pegged_usd": circ.get("peggedUSD"),
            }
        )
    return pd.DataFrame(rows).groupby(["chain", "date"], as_index=False).last()


def collect_stablecoins(hacks: pd.DataFrame, chains: pd.DataFrame) -> pd.DataFrame:
    covered = set(chains.loc[chains["has_stablecoin_data"], "chain"])
    targets = sorted({c for cs in hacks["chains"] for c in cs} & covered)
    log.info("stablecoins: %d chains + total", len(targets))
    parts = []
    for chain in ["all", *targets]:
        safe = chain.replace("/", "_").replace(" ", "_")
        try:
            data = cached_json(CHART_URL.format(chain=quote(chain)), SC_RAW / f"{safe}.json.gz")
        except HTTPFailure as exc:
            log.warning("sem stablecoins para %s: %s", chain, exc)
            continue
        if data:
            parts.append(_frame(chain, data))
    df = pd.concat(parts, ignore_index=True)
    df.to_parquet(PROCESSED_DIR / "stablecoin_supply.parquet", index=False)
    return df

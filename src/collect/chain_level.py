"""Coleta para o nível da blockchain (Fase 5, H4).

- TVL DeFi histórico de cada chain da base de hacks (/v2/historicalChainTvl).
- Preços dos ativos bridged dos casos de bridge com ativo negociado
  (src/build/bridge_assets.csv), via coins.llama.fi por id ou endereço.

Saídas: data/processed/chain_tvl.parquet e bridge_asset_prices.parquet
"""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import quote

import pandas as pd

from src.collect.http import HTTPFailure, cached_json, parallel_map
from src.config import PROCESSED_DIR, RAW_DIR

log = logging.getLogger(__name__)

CHAIN_TVL_URL = "https://api.llama.fi/v2/historicalChainTvl/{chain}"
CHART_URL = "https://coins.llama.fi/chart/{coin}"
BRIDGE_ASSETS = Path(__file__).resolve().parents[1] / "build" / "bridge_assets.csv"
WINDOW = (-130, 40)


def collect_chain_tvl(hacks: pd.DataFrame, chains: pd.DataFrame) -> pd.DataFrame:
    known = set(chains["chain"])
    targets = sorted({c for cs in hacks["chains"] for c in cs} & known)

    def fetch(chain: str):
        safe = chain.replace("/", "_").replace(" ", "_")
        try:
            data = cached_json(CHAIN_TVL_URL.format(chain=quote(chain)), RAW_DIR / "chain_tvl" / f"{safe}.json.gz")
        except HTTPFailure as exc:
            log.warning("sem TVL de chain para %s: %s", chain, exc)
            return None
        df = pd.DataFrame(data)
        if df.empty:
            return None
        df["date"] = pd.to_datetime(df["date"], unit="s").dt.normalize()
        return df.groupby("date", as_index=False)["tvl"].last().assign(chain=chain)

    parts = [p for p in parallel_map(fetch, targets, "TVL de chain") if p is not None]
    out = pd.concat(parts, ignore_index=True)[["chain", "date", "tvl"]]
    out.to_parquet(PROCESSED_DIR / "chain_tvl.parquet", index=False)
    return out


def collect_bridge_assets(hacks: pd.DataFrame) -> pd.DataFrame:
    spec = pd.read_csv(BRIDGE_ASSETS)
    dates = hacks.set_index("hack_id")["date"]
    rows = []
    for s in spec.itertuples():
        d0 = dates[s.hack_id]
        start = d0 + pd.Timedelta(days=WINDOW[0])
        span = WINDOW[1] - WINDOW[0]
        for coin in (s.asset_id, s.reference_id):
            safe = coin.replace(":", "_")
            data = cached_json(
                CHART_URL.format(coin=coin),
                RAW_DIR / "bridge_assets" / f"{safe}_{d0:%Y%m%d}.json.gz",
                params={"start": int(start.timestamp()), "span": span, "period": "1d"},
            )
            series = data.get("coins", {}).get(coin)
            for p in (series or {}).get("prices", []):
                rows.append((s.hack_id, coin, pd.to_datetime(p["timestamp"], unit="s").round("D"), p["price"]))
    out = pd.DataFrame(rows, columns=["hack_id", "coin", "date", "price"])
    out = out.groupby(["hack_id", "coin", "date"], as_index=False)["price"].last()
    out.to_parquet(PROCESSED_DIR / "bridge_asset_prices.parquet", index=False)
    return out

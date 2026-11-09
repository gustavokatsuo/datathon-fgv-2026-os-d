"""Preços diários históricos via https://coins.llama.fi/chart.

A API limita cada requisição a 500 pontos, então o histórico de cada moeda é
baixado em blocos de 499 dias a partir de 2019-01-01. A resposta traz só
preço (sem volume nem market cap).

Convenção de data: os timestamps vêm perto de 00:00 UTC (por exemplo 23:57 ou
00:02). Cada ponto é atribuído ao dia UTC mais próximo, de modo que o preço
do dia d é o preço por volta de 00:00 UTC de d.

Saída: data/processed/prices.parquet com coin, date, price.
"""

from __future__ import annotations

import logging

import pandas as pd

from src.collect.chain_names import CHAIN_GECKO_FALLBACK
from src.collect.http import cached_json, parallel_map
from src.config import PROCESSED_DIR, RAW_DIR

log = logging.getLogger(__name__)

CHART_URL = "https://coins.llama.fi/chart/coingecko:{coin}"
PRICES_RAW = RAW_DIR / "prices"
START = pd.Timestamp("2019-01-01")
CHUNK_DAYS = 499

# Benchmarks de mercado
MARKET_BENCHMARKS = ["ethereum", "bitcoin"]

# Índice DeFi equal-weighted: tokens de governança DeFi de primeira geração,
# baseados nos constituintes do DeFi Pulse Index (set/2020) mais grandes
# protocolos DeFi da mesma época. Lista fixada antes de ver resultados para
# evitar viés de sobrevivência por seleção ex post. O próprio DPI entra como
# benchmark alternativo.
DEFI_INDEX = [
    "uniswap",
    "aave",
    "maker",
    "compound-governance-token",
    "curve-dao-token",
    "havven",
    "yearn-finance",
    "sushi",
    "balancer",
    "loopring",
    "republic-protocol",
    "kyber-network-crystal",
    "bancor",
    "uma",
    "0x",
    "1inch",
    "pancakeswap-token",
    "thorchain",
]
ALT_BENCHMARKS = ["defipulse-index"]


def _chunks(end: pd.Timestamp):
    start = START
    while start <= end:
        yield start
        start = start + pd.Timedelta(days=CHUNK_DAYS)


def fetch_coin(coin: str, end: pd.Timestamp) -> pd.DataFrame:
    rows = []
    for start in _chunks(end):
        ts = int(start.timestamp())
        path = PRICES_RAW / coin / f"{start:%Y%m%d}.json.gz"
        data = cached_json(
            CHART_URL.format(coin=coin),
            path,
            params={"start": ts, "span": CHUNK_DAYS, "period": "1d"},
        )
        series = data.get("coins", {}).get(f"coingecko:{coin}")
        if series:
            rows.extend((p["timestamp"], p["price"]) for p in series["prices"])
    if not rows:
        return pd.DataFrame(columns=["coin", "date", "price"])
    df = pd.DataFrame(rows, columns=["ts", "price"])
    df["date"] = pd.to_datetime(df["ts"], unit="s").dt.round("D")
    df = df.groupby("date", as_index=False)["price"].last().assign(coin=coin)
    return df[["coin", "date", "price"]]


def coin_universe(protocol_tokens: pd.DataFrame, hacks: pd.DataFrame, chains: pd.DataFrame) -> pd.DataFrame:
    """Lista de moedas a baixar, com o papel de cada uma."""
    items: list[tuple[str, str]] = []
    items += [(c, "protocol_token") for c in protocol_tokens["gecko_id"].dropna().unique()]

    chain_gecko = chains.set_index("chain")["gecko_id"].dropna().to_dict()
    chain_gecko.update({k: v for k, v in CHAIN_GECKO_FALLBACK.items() if k not in chain_gecko})
    hack_chains = {c for cs in hacks["chains"] for c in cs}
    items += [(chain_gecko[c], "chain_native") for c in hack_chains if c in chain_gecko]
    items += [(c, "benchmark_market") for c in MARKET_BENCHMARKS]
    items += [(c, "benchmark_defi_index") for c in DEFI_INDEX]
    items += [(c, "benchmark_alt") for c in ALT_BENCHMARKS]
    df = pd.DataFrame(items, columns=["coin", "role"])
    return df.groupby("coin", as_index=False)["role"].agg(lambda s: sorted(set(s)))


def collect_prices(universe: pd.DataFrame, end: pd.Timestamp | None = None) -> pd.DataFrame:
    end = end or pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    coins = universe["coin"].tolist()
    log.info("preços: %d moedas", len(coins))
    parts = parallel_map(lambda c: fetch_coin(c, end), coins, "preços")
    df = pd.concat(parts, ignore_index=True)
    df.to_parquet(PROCESSED_DIR / "prices.parquet", index=False)
    universe.to_parquet(PROCESSED_DIR / "coin_universe.parquet", index=False)
    return df

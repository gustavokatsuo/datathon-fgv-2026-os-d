"""Executa toda a coleta da Fase 1 e imprime o relatório de cobertura.

Uso (na raiz do repositório):
    python -m src.collect.run
"""

from __future__ import annotations

import logging

import pandas as pd

from src.collect.coverage import build_coverage, summarize
from src.collect.metadata import collect_chains, collect_hacks, collect_protocols
from src.collect.prices import coin_universe, collect_prices
from src.collect.stablecoins import collect_stablecoins
from src.collect.tvl import collect_tvl
from src.config import PROCESSED_DIR


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    hacks = collect_hacks()
    protocols = collect_protocols()
    chains = collect_chains()
    collect_tvl(hacks, protocols)
    ptok = pd.read_parquet(PROCESSED_DIR / "protocol_tokens.parquet")
    collect_prices(coin_universe(ptok, hacks, chains))
    collect_stablecoins(hacks, chains)

    cov = build_coverage()
    print(summarize(cov).to_string())


if __name__ == "__main__":
    main()

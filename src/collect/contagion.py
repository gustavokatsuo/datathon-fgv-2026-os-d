"""Coleta do TVL histórico dos protocolos expostos e de controle (Fase 6).

Reaproveita o cache de data/raw/tvl/. Saída: data/processed/contagion_tvl.parquet
com slug, date, tvl_usd (série total, sem decomposição por token).

Uso: python -m src.collect.contagion
"""

from __future__ import annotations

import logging

import pandas as pd

from src.collect.http import parallel_map
from src.collect.tvl import TVL_RAW, _tvl_frame, fetch_protocol
from src.config import PROCESSED_DIR


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    sets = pd.read_parquet(PROCESSED_DIR / "contagion_sets.parquet")
    slugs = sorted(sets["slug"].unique())

    def download(slug: str) -> bool:
        return (TVL_RAW / f"{slug}.json.gz").exists() or fetch_protocol(slug) is not None

    parallel_map(download, slugs, "TVL contágio")
    parts = []
    for slug in slugs:
        data = fetch_protocol(slug)
        if data is not None:
            parts.append(_tvl_frame(slug, data))
    pd.concat(parts, ignore_index=True).to_parquet(PROCESSED_DIR / "contagion_tvl.parquet", index=False)


if __name__ == "__main__":
    main()

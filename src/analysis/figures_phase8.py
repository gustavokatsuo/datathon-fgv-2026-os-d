"""Gráfico da Fase 8: concentração do TVL nas maiores chains.

Uso: python -m src.analysis.figures_phase8
"""

from __future__ import annotations

import pandas as pd
from matplotlib.ticker import PercentFormatter

from src.analysis import plotstyle as ps
from src.analysis.exposure_ranking import THRESHOLD
from src.config import PROCESSED_DIR

N = 12


def main() -> None:
    ps.setup()
    c = pd.read_csv(PROCESSED_DIR / "exposure_chain_concentration.csv").head(N).iloc[::-1]
    fig, ax = ps.plt.subplots(figsize=(10, 5.5))
    y = range(len(c))
    ax.barh(y, c["maior_share"], height=0.6, color=ps.SERIES[0])
    for i, r in enumerate(c.itertuples()):
        ax.annotate(f"{r.maior_protocolo} {r.maior_share:.0%}", (r.maior_share, i), xytext=(6, 0),
                    textcoords="offset points", va="center", fontsize=11, color=ps.TEXT)
    ax.axvline(THRESHOLD, color=ps.SERIES[1], linewidth=2, linestyle=(0, (4, 2)))
    ax.annotate("5%: a partir daqui a moeda nativa reagiu ao hack (H4)", (THRESHOLD, -0.75),
                xytext=(6, 0), textcoords="offset points", fontsize=10.5, color=ps.TEXT_2, va="center")
    ax.set_ylim(-1.1, len(c) - 0.5)
    ax.set_yticks(list(y), [f"{r.chain} (US$ {r.chain_tvl / 1e9:.1f} bi)" for r in c.itertuples()])
    ax.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.set_xlim(0, 1.15)
    ax.grid(axis="x", color=ps.GRID)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Participação do maior protocolo no TVL DeFi da chain")
    ax.set_title("Um único protocolo concentra boa parte do TVL de cada chain")
    ps.save(fig, "fig8_chain_concentration")


if __name__ == "__main__":
    main()

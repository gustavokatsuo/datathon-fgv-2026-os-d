"""Padrão visual único dos gráficos (legíveis em slide, PDF e PNG).

Paleta categórica de referência validada para daltonismo: os três primeiros
slots passam em todos os pares, então nenhum gráfico usa mais de três séries
coloridas. Texto sempre em tons de cinza, nunca na cor da série.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src.config import FIGURES_DIR  # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]  # azul, laranja, verde-água
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
GRID = "#e4e3df"
SURFACE = "#ffffff"


def setup() -> None:
    plt.rcParams.update(
        {
            "figure.figsize": (8, 4.5),
            "figure.dpi": 100,
            "savefig.dpi": 200,
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "font.family": "DejaVu Sans",
            "font.size": 13,
            "axes.titlesize": 15,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.labelsize": 13,
            "axes.labelcolor": TEXT_2,
            "axes.edgecolor": GRID,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.grid.axis": "y",
            "grid.color": GRID,
            "grid.linewidth": 0.8,
            "xtick.color": TEXT_2,
            "ytick.color": TEXT_2,
            "text.color": TEXT,
            "lines.linewidth": 2.0,
            "legend.frameon": False,
            "legend.fontsize": 12,
        }
    )


def save(fig, name: str) -> None:
    FIGURES_DIR.mkdir(exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(FIGURES_DIR / f"{name}.{ext}", bbox_inches="tight")
    plt.close(fig)

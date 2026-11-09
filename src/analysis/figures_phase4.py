"""Gráfico da Fase 4: reação do token por tipo de falha (H2).

Média do CAR com IC 95% bootstrap e mediana, sem controles. Os coeficientes
com controles estão em data/processed/cross_section_main.csv.

Uso: python -m src.analysis.figures_phase4
"""

from __future__ import annotations

import numpy as np
from matplotlib.ticker import PercentFormatter

from src.analysis import plotstyle as ps
from src.analysis.cross_section import build_frames
from src.analysis.stats import bootstrap_mean

LABELS = {
    "code": "Bug de código\n(contrato, bridge)",
    "economic": "Oráculo ou preço",
    "operational": "Operacional\n(chave, infra, governança)",
}
ORDER = ["code", "economic", "operational"]


def main() -> None:
    ps.setup()
    price, _ = build_frames()
    fig, axes = ps.plt.subplots(1, 2, figsize=(10, 4.5), sharey=True)
    for ax, (y, title) in zip(axes, [("car_0_1", "CAR [0,+1]"), ("car_0_30", "CAR [0,+30]")]):
        for i, g in enumerate(ORDER):
            x = price.loc[price["group"] == g, y].dropna().to_numpy()
            lo, hi, _ = bootstrap_mean(x)
            ax.plot([lo, hi], [i, i], color=ps.SERIES[0], linewidth=2, solid_capstyle="round")
            ax.plot(x.mean(), i, "o", color=ps.SERIES[0], markersize=9)
            ax.plot(np.median(x), i, "D", color=ps.SERIES[1], markersize=7)
        ax.axvline(0, color=ps.TEXT_2, linewidth=0.8)
        ax.set_title(title)
        ax.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
        ax.grid(axis="x", color=ps.GRID)
        ax.grid(axis="y", visible=False)
        ax.set_ylim(-0.6, len(ORDER) - 0.4)
    counts = price.groupby("group")["car_0_1"].count()
    axes[0].set_yticks(range(len(ORDER)), [f"{LABELS[g]}\nn = {counts[g]}" for g in ORDER])
    axes[0].plot([], [], "o", color=ps.SERIES[0], label="Média (IC 95% bootstrap)")
    axes[0].plot([], [], "D", color=ps.SERIES[1], label="Mediana")
    fig.legend(loc="lower center", ncol=2, bbox_to_anchor=(0.5, -0.06))
    fig.suptitle("Reação do token por tipo de falha", x=0.01, ha="left", fontweight="bold", fontsize=15)
    fig.tight_layout()
    ps.save(fig, "fig4_car_by_failure_type")


if __name__ == "__main__":
    main()

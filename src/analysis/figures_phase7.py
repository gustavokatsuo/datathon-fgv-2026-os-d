"""Gráfico da Fase 7: H1 sob as variações da amostra, contra a faixa placebo.

Uso: python -m src.analysis.figures_phase7
"""

from __future__ import annotations

import pandas as pd
from matplotlib.ticker import PercentFormatter

from src.analysis import plotstyle as ps
from src.config import PROCESSED_DIR

ORDER = ["principal", "datas originais DefiLlama", "sem sobreposição", "sem crises",
         "sem sobreposição e sem crises", "perda >= US$ 5 mi", "perda >= US$ 10 mi", "winsorizado 1/99"]
LABELS = {"perda >= US$ 5 mi": "perda ≥ US$ 5 mi", "perda >= US$ 10 mi": "perda ≥ US$ 10 mi",
          "winsorizado 1/99": "winsorizado 1% e 99%", "datas originais DefiLlama": "datas originais da DefiLlama"}


def main() -> None:
    ps.setup()
    rb = pd.read_csv(PROCESSED_DIR / "robustness_h1.csv")
    pl = pd.read_csv(PROCESSED_DIR / "placebo_summary.csv")
    panels = [
        ("CAR preço", "[0,1]", ("preço", "média CAR", "[0,1]"), "Token: CAR [0,+1]"),
        ("fluxo líquido do roubo", "[0,30]", ("TVL", "média fluxo bruto", "[0,30]"),
         "TVL: fluxo líquido do roubo [0,+30]"),
    ]
    fig, axes = ps.plt.subplots(1, 2, figsize=(11, 5), sharey=True)
    for ax, (medida, w, (pt, pe, pw), title) in zip(axes, panels):
        sub = rb[(rb["medida"] == medida) & (rb["window"] == w)].set_index("spec").reindex(ORDER)
        p = pl[(pl["teste"] == pt) & (pl["estatística"] == pe) & (pl["window"] == pw)].iloc[0]
        ax.axvspan(p["placebo_p2_5"], p["placebo_p97_5"], color=ps.GRID, alpha=0.9, linewidth=0,
                   label="Faixa placebo (95%, datas sem hack)")
        for i, (spec, r) in enumerate(sub.iterrows()):
            y = len(ORDER) - 1 - i
            ax.plot([r["boot_lo"], r["boot_hi"]], [y, y], color=ps.SERIES[0], linewidth=2,
                    solid_capstyle="round")
            ax.plot(r["mean"], y, "o", color=ps.SERIES[0], markersize=8)
            ax.plot(r["median"], y, "D", color=ps.SERIES[1], markersize=6)
        ax.axvline(0, color=ps.TEXT_2, linewidth=0.8)
        ax.set_title(title)
        ax.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
        ax.grid(axis="x", color=ps.GRID)
        ax.grid(axis="y", visible=False)
    n = rb[(rb["medida"] == "CAR preço") & (rb["window"] == "[0,1]")].set_index("spec")["n"]
    nt = rb[(rb["medida"] == "fluxo líquido do roubo") & (rb["window"] == "[0,30]")].set_index("spec")["n"]
    axes[0].set_yticks(range(len(ORDER)),
                       [f"{LABELS.get(s, s)} ({int(n[s])} / {int(nt[s])})" for s in reversed(ORDER)])
    axes[0].plot([], [], "o", color=ps.SERIES[0], label="Média (IC 95% bootstrap)")
    axes[0].plot([], [], "D", color=ps.SERIES[1], label="Mediana")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center", ncol=3, bbox_to_anchor=(0.55, -0.07))
    fig.suptitle("Robustez do H1 (n de preço / n de TVL entre parênteses)", x=0.01, ha="left",
                 fontweight="bold", fontsize=15)
    fig.tight_layout()
    ps.save(fig, "fig7_robustness")


if __name__ == "__main__":
    main()

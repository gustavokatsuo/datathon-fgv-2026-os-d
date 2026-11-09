"""Gráfico da Fase 6: trajetória do TVL de protocolos expostos (fork) e controles.

Média por evento dentro de cada grupo, depois média entre eventos, com IC 95%
por bootstrap de eventos (a unidade independente é o evento).

Uso: python -m src.analysis.figures_phase6
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.ticker import PercentFormatter

from src.analysis import plotstyle as ps
from src.analysis.stats import SEED
from src.config import PROCESSED_DIR

N_BOOT = 2000


def main() -> None:
    ps.setup()
    d = pd.read_parquet(PROCESSED_DIR / "contagion_daily.parquet").sort_values("rel_day")
    d["cum"] = d.groupby(["hack_id", "slug"])["abn"].cumsum()
    ev_mean = d.groupby(["group", "hack_id", "rel_day"])["cum"].mean().unstack("rel_day")

    fig, ax = ps.plt.subplots()
    rng = np.random.default_rng(SEED)
    for grp, color, label, dy in [("exposed", ps.SERIES[1], "Forks da vítima (expostos)", -9),
                                  ("control", ps.SERIES[0], "Mesma categoria e chain, sem fork (controle)", 9)]:
        m = ev_mean.loc[grp]
        x = m.to_numpy()
        idx = rng.integers(0, x.shape[0], size=(N_BOOT, x.shape[0]))
        boots = np.nanmean(x[idx], axis=1)
        lo, hi = np.percentile(boots, [2.5, 97.5], axis=0)
        mean = np.nanmean(x, axis=0)
        ax.fill_between(m.columns, lo, hi, color=color, alpha=0.15, linewidth=0)
        ax.plot(m.columns, mean, color=color, label=f"{label}")
        ax.plot(m.columns[-1], mean[-1], "o", color=color, markersize=6)
        ax.annotate(f"{mean[-1]:.0%}", (m.columns[-1], mean[-1]), xytext=(8, dy),
                    textcoords="offset points", va="center", fontsize=12)
    ax.axvline(0, color=ps.TEXT_2, linewidth=1, linestyle=(0, (3, 3)))
    ax.axhline(0, color=ps.TEXT_2, linewidth=0.8)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.set_xlim(-10, 36)
    ax.set_xlabel("Dias em relação ao hack da vítima")
    ax.set_ylabel("Variação anormal do log do TVL\n(acumulada desde o dia -10)")
    n = d["hack_id"].nunique()
    ax.set_title(f"Contágio por código compartilhado ({n} hacks)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2))
    ps.save(fig, "fig6_fork_contagion")


if __name__ == "__main__":
    main()

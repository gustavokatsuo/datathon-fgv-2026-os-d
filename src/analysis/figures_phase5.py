"""Gráfico da Fase 5: moeda nativa por tamanho relativo e paridade de wrapped.

Uso: python -m src.analysis.figures_phase5
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.ticker import PercentFormatter

from src.analysis import plotstyle as ps
from src.analysis.chain_level import chain_sample
from src.analysis.stats import bootstrap_mean
from src.config import PROCESSED_DIR

BUCKETS = [(0, 0.01, "< 1%"), (0.01, 0.05, "1% a 5%"), (0.05, np.inf, "≥ 5%")]
# 4 casos em linhas: paleta categórica na ordem fixa (pares adjacentes validados)
CASE_COLORS = ["#111111", "#D9A400", "#8C8C8C", "#7A5C00"]


def main() -> None:
    ps.setup()
    s = chain_sample()
    nat = pd.read_parquet(PROCESSED_DIR / "chain_native_car.parquet").merge(s[["hack_id", "loss_chain"]])
    nat = nat[nat["window"] == "[0,5]"]
    dep = pd.read_parquet(PROCESSED_DIR / "bridge_depeg_daily.parquet")

    fig, (a1, a2) = ps.plt.subplots(1, 2, figsize=(11, 4.6), gridspec_kw={"width_ratios": [1, 1.25]})

    for i, (lo, hi, lab) in enumerate(BUCKETS):
        x = nat.loc[(nat["loss_chain"] >= lo) & (nat["loss_chain"] < hi), "car"].to_numpy()
        blo, bhi, _ = bootstrap_mean(x)
        a1.plot([i, i], [blo, bhi], color=ps.SERIES[0], linewidth=2, solid_capstyle="round")
        a1.plot(i, x.mean(), "o", color=ps.SERIES[0], markersize=9)
        a1.plot(i, np.median(x), "D", color=ps.SERIES[1], markersize=7)
    counts = [((nat["loss_chain"] >= lo) & (nat["loss_chain"] < hi)).sum() for lo, hi, _ in BUCKETS]
    a1.set_xticks(range(3), [f"{lab}\nn = {n}" for (_, _, lab), n in zip(BUCKETS, counts)])
    a1.set_xlabel("Perda / TVL DeFi da chain")
    a1.axhline(0, color=ps.TEXT_2, linewidth=0.8)
    a1.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    a1.set_title("Moeda nativa da chain, CAR [0,+5]")
    a1.plot([], [], "o", color=ps.SERIES[0], label="Média (IC 95%)")
    a1.plot([], [], "D", color=ps.SERIES[1], label="Mediana")
    a1.legend(loc="lower left")
    a1.set_xlim(-0.5, 2.5)

    cases = pd.read_csv(PROCESSED_DIR / "bridge_depeg_cases.csv").set_index("caso")
    for color, (case, g) in zip(CASE_COLORS, dep.groupby("caso", sort=False)):
        g = g.sort_values("rel_day").dropna()
        c = cases.loc[case]
        note = " (série acaba no dia +1)" if g["rel_day"].max() < 5 else ""
        a2.plot(g["rel_day"], g["desvio"], color=color,
                label=f"{case}, {c['ativo']}: mínimo {c['desvio_min_0_30']:.0%}{note}")
    a2.axvline(0, color=ps.TEXT_2, linewidth=1, linestyle=(0, (3, 3)))
    a2.axhline(0, color=ps.TEXT_2, linewidth=0.8)
    a2.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    a2.set_xlim(-10, 31)
    a2.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), fontsize=10.5)
    a2.set_xlabel("Dias em relação ao hack")
    a2.set_ylabel("Preço wrapped / original\n(relativo ao dia -1)")
    a2.set_title("Paridade de ativos em hacks de bridge")
    fig.tight_layout()
    ps.save(fig, "fig5_chain_level")


if __name__ == "__main__":
    main()

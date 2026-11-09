"""Gráficos da Fase 3: trajetória do retorno anormal e do fluxo anormal.

Uso: python -m src.analysis.figures_phase3
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.ticker import PercentFormatter

from src.analysis import plotstyle as ps
from src.analysis.stats import SEED
from src.config import PROCESSED_DIR

START, END = -10, 30
N_BOOT = 2000


def _paths(daily: pd.DataFrame, value: str, add_at_zero: pd.Series | None = None) -> pd.DataFrame:
    """Caminho acumulado por evento a partir do dia START (zero no início)."""
    w = daily[daily["rel_day"].between(START, END)].pivot(index="rel_day", columns="hack_id", values=value)
    w = w.fillna(0.0)  # dia sem observação conta como retorno/fluxo anormal zero
    if add_at_zero is not None:
        w.loc[0] = w.loc[0] + add_at_zero.reindex(w.columns).fillna(0).to_numpy()
    return w.cumsum()


def _band(paths: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    rng = np.random.default_rng(SEED)
    x = paths.to_numpy()
    idx = rng.integers(0, x.shape[1], size=(N_BOOT, x.shape[1]))
    means = x[:, idx].mean(axis=2)  # dias x reamostragens
    lo, hi = np.percentile(means, [2.5, 97.5], axis=1)
    return pd.Series(lo, index=paths.index), pd.Series(hi, index=paths.index)


def _decorate(ax, ylabel: str) -> None:
    ax.axvline(0, color=ps.TEXT_2, linewidth=1, linestyle=(0, (3, 3)))
    ax.axhline(0, color=ps.TEXT_2, linewidth=0.8)
    ax.set_xlabel("Dias em relação ao hack")
    ax.set_ylabel(ylabel + "\n(acumulado desde o dia -10)")
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.set_xlim(START, END + 6)


def _label(ax, y: float, text: str, color: str) -> None:
    ax.plot([END], [y], "o", color=color, markersize=6)
    ax.annotate(text, (END, y), xytext=(8, 0), textcoords="offset points", va="center",
                fontsize=12, color=ps.TEXT)


def price_figure() -> None:
    ar = pd.read_parquet(PROCESSED_DIR / "price_ar_daily.parquet")
    ar = ar[ar["benchmark"] == "eth"]
    paths = _paths(ar, "ar")
    mean, med = paths.mean(axis=1), paths.median(axis=1)
    lo, hi = _band(paths)

    fig, ax = ps.plt.subplots()
    ax.fill_between(paths.index, lo, hi, color=ps.SERIES[0], alpha=0.15, linewidth=0)
    ax.plot(paths.index, mean, color=ps.SERIES[0], label="Média (IC 95% bootstrap)")
    ax.plot(paths.index, med, color=ps.SERIES[1], label="Mediana")
    _label(ax, mean.iloc[-1], f"{mean.iloc[-1]:.0%}", ps.SERIES[0])
    _label(ax, med.iloc[-1], f"{med.iloc[-1]:.0%}", ps.SERIES[1])
    _decorate(ax, "Retorno anormal acumulado")
    ax.set_title(f"Token do protocolo após o hack (n = {paths.shape[1]})")
    ax.legend(loc="lower left")
    ps.save(fig, "fig3_price_car_path")


def tvl_figure() -> None:
    daily = pd.read_parquet(PROCESSED_DIR / "tvl_flows_daily.parquet")
    flows = pd.read_parquet(PROCESSED_DIR / "tvl_flows.parquet")
    theft = flows.drop_duplicates("hack_id").set_index("hack_id")["theft_share"]
    raw = _paths(daily, "abn_flow")
    ex = _paths(daily, "abn_flow", add_at_zero=theft)

    fig, ax = ps.plt.subplots()
    for paths, color, name in [(raw, ps.SERIES[1], "Fluxo bruto (inclui o roubo)"),
                               (ex, ps.SERIES[0], "Fluxo descontado o roubo")]:
        med = paths.median(axis=1)
        lo, hi = _band(paths)
        mean = paths.mean(axis=1)
        ax.fill_between(paths.index, lo, hi, color=color, alpha=0.15, linewidth=0)
        ax.plot(paths.index, mean, color=color, label=f"{name}: média (IC 95%)")
        ax.plot(paths.index, med, color=color, linestyle=(0, (4, 2)), linewidth=1.5)
        _label(ax, mean.iloc[-1], f"{mean.iloc[-1]:.0%}", color)
    ax.plot([], [], color=ps.TEXT_2, linestyle=(0, (4, 2)), linewidth=1.5, label="Mediana (tracejado)")
    _decorate(ax, "Fluxo anormal acumulado / TVL")
    ax.set_title(f"Saída de criptoativos depositados (n = {raw.shape[1]})")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=1)
    ps.save(fig, "fig3_tvl_flow_path")


if __name__ == "__main__":
    ps.setup()
    price_figure()
    tvl_figure()
    print("figuras salvas em figures/")

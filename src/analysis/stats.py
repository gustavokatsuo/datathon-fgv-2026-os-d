"""Testes de significância para estudos de evento.

- BMP: Boehmer, Musumeci e Poulsen (1991). Teste t sobre os CARs
  padronizados, robusto a aumento de variância no evento.
- Corrado multi-dia: Corrado (1989) com a extensão de Campbell e Wasley
  (1993) para janelas de vários dias. Não paramétrico, baseado em postos.
- Bootstrap: reamostragem de eventos com reposição para a média do CAR.
  Intervalo percentil e p-valor sob a nula (distribuição centrada).
- Wilcoxon (posto sinalizado) para a mediana, como complemento.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

SEED = 20261108
N_BOOT = 10_000


def bmp_test(scar: np.ndarray) -> tuple[float, float]:
    """Estatística BMP a partir dos CARs padronizados (SCAR) de cada evento."""
    scar = np.asarray(scar, dtype=float)
    scar = scar[np.isfinite(scar)]
    n = len(scar)
    if n < 3:
        return np.nan, np.nan
    z = scar.mean() * np.sqrt(n) / scar.std(ddof=1)
    p = 2 * stats.t.sf(abs(z), df=n - 1)
    return float(z), float(p)


def corrado_test(ranks_u: pd.DataFrame, window: tuple[int, int]) -> tuple[float, float]:
    """Corrado multi-dia (Campbell e Wasley 1993).

    ranks_u: DataFrame (dias relativos x eventos) com U = K/(1+M) - 0,5, em
    que K é o posto do retorno anormal do evento na série combinada
    (estimação + evento) e M o número de observações não nulas.
    """
    ubar = ranks_u.mean(axis=1, skipna=True)
    s_u = np.sqrt((ubar**2).mean())
    days = [d for d in range(window[0], window[1] + 1) if d in ubar.index]
    L = len(days)
    if L == 0 or s_u == 0:
        return np.nan, np.nan
    t = ubar.loc[days].sum() / (np.sqrt(L) * s_u)
    p = 2 * stats.norm.sf(abs(t))
    return float(t), float(p)


def bootstrap_mean(x: np.ndarray, n_boot: int = N_BOOT, seed: int = SEED) -> tuple[float, float, float]:
    """IC percentil 95% da média e p-valor bilateral sob H0: média = 0."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 3:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(n_boot, len(x)))
    means = x[idx].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    centered = means - x.mean()
    p = (np.abs(centered) >= abs(x.mean())).mean()
    return float(lo), float(hi), float(p)


def wilcoxon_median(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 3:
        return np.nan
    return float(stats.wilcoxon(x).pvalue)


def summarize(values: np.ndarray, scar: np.ndarray | None = None) -> dict:
    """Resumo de uma janela: média, mediana, fração negativa e testes."""
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    out = {
        "n": len(v),
        "mean": v.mean() if len(v) else np.nan,
        "median": np.median(v) if len(v) else np.nan,
        "frac_neg": (v < 0).mean() if len(v) else np.nan,
    }
    t, p = stats.ttest_1samp(v, 0.0) if len(v) >= 3 else (np.nan, np.nan)
    out["t_csect"], out["p_csect"] = float(t), float(p)
    if scar is not None:
        out["z_bmp"], out["p_bmp"] = bmp_test(scar)
    lo, hi, pb = bootstrap_mean(v)
    out["boot_lo"], out["boot_hi"], out["p_boot"] = lo, hi, pb
    out["p_wilcoxon"] = wilcoxon_median(v)
    return out

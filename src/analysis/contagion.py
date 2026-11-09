"""Contágio por código compartilhado (H5, Fase 6): diferenças em diferenças.

Para cada par (evento, protocolo), variação anormal do log do TVL na janela,
descontada a tendência média em [-60,-11]. Regressão com efeito fixo de evento:

    y = α_evento + β·exposto + γ·log TVL(-1) + ε,  erros agrupados por evento

Especificação registrada em docs/decisions.md antes de rodar.

Uso: python -m src.analysis.contagion
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from src.config import PROCESSED_DIR

BASE = (-60, -11)
REL = np.arange(-60, 31)
WINDOWS = [(0, 1), (0, 5), (0, 10), (0, 30)]
MIN_TVL_PRE = 1e6
OWN_HACK_WINDOW = (-120, 30)
CLIP = 1.0


def build_panel() -> tuple[pd.DataFrame, pd.DataFrame]:
    sets = pd.read_parquet(PROCESSED_DIR / "contagion_sets.parquet")
    tvl = pd.read_parquet(PROCESSED_DIR / "contagion_tvl.parquet")
    ev = pd.read_parquet(PROCESSED_DIR / "events.parquet")
    dates = ev.set_index("hack_id")["date"]
    own = ev.dropna(subset=["slug"])[["slug", "date"]]  # qualquer hack registrado, de qualquer valor
    own_by_slug = own.groupby("slug")["date"].apply(list).to_dict()
    series = {k: g.set_index("date")["tvl_usd"] for k, g in tvl.groupby("slug")}

    rows, daily = [], []
    for r in sets.itertuples():
        d0 = dates[r.hack_id]
        hacked = any(OWN_HACK_WINDOW[0] <= (d - d0).days <= OWN_HACK_WINDOW[1] for d in own_by_slug.get(r.slug, []))
        if hacked or r.slug not in series:
            continue
        days = pd.DatetimeIndex([d0 + pd.Timedelta(days=int(k)) for k in REL])
        lvl = series[r.slug].reindex(days.append(pd.DatetimeIndex([days[-1] + pd.Timedelta(days=1)])))
        pre = lvl.get(d0, np.nan)
        if not (pre >= MIN_TVL_PRE):
            continue
        lv = np.log(lvl.where(lvl > 0))
        g = (lv.shift(-1) - lv).iloc[:-1].clip(-CLIP, CLIP)
        g.index = REL
        base = g.loc[BASE[0]:BASE[1]].dropna()
        if len(base) < 0.9 * (BASE[1] - BASE[0] + 1) or g.loc[-1:30].isna().any():
            continue
        ab = g - base.mean()
        for k in range(-10, 31):
            daily.append((r.hack_id, r.slug, r.group, k, ab[k]))
        rec = {"hack_id": r.hack_id, "slug": r.slug, "group": r.group, "log_tvl_pre": np.log(pre)}
        for w in WINDOWS:
            rec[f"y_{w[0]}_{w[1]}"] = ab.loc[w[0]:w[1]].sum()
        rows.append(rec)
    panel = pd.DataFrame(rows)
    # mantém só eventos com os dois grupos (o efeito fixo de evento exige comparação)
    both = panel.groupby("hack_id")["group"].nunique()
    panel = panel[panel["hack_id"].isin(both[both == 2].index)]
    panel["exposed"] = (panel["group"] == "exposed").astype(int)
    daily = pd.DataFrame(daily, columns=["hack_id", "slug", "group", "rel_day", "abn"])
    daily = daily[daily["hack_id"].isin(panel["hack_id"].unique())]
    return panel, daily


def did(panel: pd.DataFrame) -> pd.DataFrame:
    out = []
    for w in WINDOWS:
        y = f"y_{w[0]}_{w[1]}"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            m = smf.ols(f"{y} ~ exposed + log_tvl_pre + C(hack_id)", panel).fit(
                cov_type="cluster", cov_kwds={"groups": pd.factorize(panel["hack_id"])[0]})
        b, se = m.params["exposed"], m.bse["exposed"]
        out.append({"window": f"[{w[0]},{w[1]}]", "beta_exposed": b, "se": se, "p": m.pvalues["exposed"],
                    "ci_lo": b - 1.96 * se, "ci_hi": b + 1.96 * se, "n_obs": int(m.nobs),
                    "n_eventos": panel["hack_id"].nunique(),
                    "mean_exposed": panel.loc[panel["exposed"] == 1, y].mean(),
                    "mean_control": panel.loc[panel["exposed"] == 0, y].mean()})
    return pd.DataFrame(out)


def run() -> None:
    panel, daily = build_panel()
    panel.to_parquet(PROCESSED_DIR / "contagion_panel.parquet", index=False)
    daily.to_parquet(PROCESSED_DIR / "contagion_daily.parquet", index=False)
    res = did(panel)
    res.to_csv(PROCESSED_DIR / "contagion_did.csv", index=False)

    # robustez: winsorização 1/99 por janela e mediana por evento
    pw = panel.copy()
    for c in [c for c in pw if c.startswith("y_")]:
        lo, hi = pw[c].quantile([0.01, 0.99])
        pw[c] = pw[c].clip(lo, hi)
    rw = did(pw).assign(spec="winsor 1/99")
    rw.to_csv(PROCESSED_DIR / "contagion_did_winsor.csv", index=False)

    pd.set_option("display.width", 200)
    print(panel.groupby("group").agg(pares=("slug", "size"), protocolos=("slug", "nunique"), eventos=("hack_id", "nunique")))
    print(res.round(4).to_string(index=False))
    print("winsor:\n", rw[["window", "beta_exposed", "p"]].round(4).to_string(index=False))


if __name__ == "__main__":
    run()

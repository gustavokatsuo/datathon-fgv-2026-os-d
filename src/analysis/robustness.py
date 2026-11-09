"""Robustez (Fase 7): placebos e variações da amostra para H1, e placebo da
deriva do teste de contágio (H5).

Especificação registrada em docs/decisions.md antes de rodar.

Uso: python -m src.analysis.robustness
Saídas em data/processed/: robustness_h1.csv, placebo_summary.csv,
placebo_draws.parquet
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.analysis import event_price, event_tvl
from src.analysis import stats as st
from src.analysis.event_tvl import decompose
from src.config import PROCESSED_DIR

log = logging.getLogger(__name__)

CRISES = [
    ("Terra/Luna", "2022-05-07", "2022-05-31"),
    ("FTX", "2022-11-06", "2022-11-30"),
    ("Liquidações out/2025", "2025-10-10", "2025-10-20"),
    ("Liquidações out/2026", "2026-10-01", "2026-10-31"),
]
START = pd.Timestamp("2020-01-01")
EXCL = (-150, 60)  # sem hack real do mesmo ativo em torno da data falsa
N_PLACEBO = 1000
N_PLACEBO_CONTAGION = 500
PRICE_WINDOWS = ["[0,1]", "[0,30]"]
TVL_WINDOWS = ["[0,10]", "[0,30]"]


# ---------------------------------------------------------------- variações

def in_crisis(dates: pd.Series) -> pd.Series:
    hit = pd.Series(False, index=dates.index)
    for _, a, b in CRISES:
        a, b = pd.Timestamp(a), pd.Timestamp(b)
        hit |= (dates + pd.Timedelta(days=30) >= a) & (dates - pd.Timedelta(days=1) <= b)
    return hit


def _original_dates(ev: pd.DataFrame, rets: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Eventos com a data original da DefiLlama e cobertura recalculada."""
    tok = pd.read_parquet(PROCESSED_DIR / "tvl_tokens.parquet", columns=["slug", "date"])
    tvl = pd.read_parquet(PROCESSED_DIR / "tvl_daily.parquet")
    tok_dates = {k: pd.DatetimeIndex(g["date"].unique()) for k, g in tok.groupby("slug")}
    level = tvl.set_index(["slug", "date"])["tvl_usd"]
    o = ev.copy()
    o["date"] = o["date_defillama"]
    base = (o["date"] >= START) & (o["amount_usd"].fillna(0) >= 1e6) & ~o["is_duplicate"]

    def price_ok(g, d):
        if not isinstance(g, str) or g not in rets.columns:
            return False
        r = rets[g]
        est = r.reindex(pd.date_range(d - pd.Timedelta(days=120), d - pd.Timedelta(days=11)))
        evt = r.reindex(pd.date_range(d - pd.Timedelta(days=1), d + pd.Timedelta(days=30)))
        return est.notna().mean() >= 0.9 and evt.notna().all()

    def tvl_ok(s, d):
        if not isinstance(s, str) or s not in tok_dates:
            return False
        D = tok_dates[s]
        b = pd.date_range(d - pd.Timedelta(days=60), d - pd.Timedelta(days=11)).isin(D).mean()
        v = pd.date_range(d - pd.Timedelta(days=1), d + pd.Timedelta(days=30)).isin(D).all()
        return b >= 0.9 and v and level.get((s, d), 0) >= 1e6

    o = o[base]
    p = o[np.array([price_ok(g, d) for g, d in zip(o["gecko_id"], o["date"])], dtype=bool)]
    t = o[np.array([tvl_ok(s, d) for s, d in zip(o["slug"], o["date"])], dtype=bool)]
    return p, t


def _price_stats(spec: str, car: pd.DataFrame) -> list[dict]:
    out = []
    for w in PRICE_WINDOWS:
        sub = car[(car["benchmark"] == "eth") & (car["window"] == w)]
        s = st.summarize(sub["car"].to_numpy(), sub["scar"].to_numpy())
        out.append({"spec": spec, "medida": "CAR preço", "window": w, **s})
    return out


def _tvl_stats(spec: str, res: pd.DataFrame) -> list[dict]:
    out = []
    for w in TVL_WINDOWS:
        sub = res[res["window"] == w]
        s = st.summarize(sub["abn_flow_ex_theft"].to_numpy(), sub["scaf_ex_theft"].to_numpy())
        out.append({"spec": spec, "medida": "fluxo líquido do roubo", "window": w, **s})
    return out


def variations(rets: pd.DataFrame) -> pd.DataFrame:
    ev = pd.read_parquet(PROCESSED_DIR / "events.parquet")
    crisis = in_crisis(ev["date"])
    P, T = ev[ev["sample_price"]], ev[ev["sample_tvl"]]
    specs = {
        "principal": (P, T),
        "sem sobreposição": (P[~P["overlap_token"]], T[~T["overlap_protocol"]]),
        "sem crises": (P[~crisis[P.index]], T[~crisis[T.index]]),
        "sem sobreposição e sem crises": (P[~P["overlap_token"] & ~crisis[P.index]],
                                          T[~T["overlap_protocol"] & ~crisis[T.index]]),
        "perda >= US$ 5 mi": (P[P["amount_usd"] >= 5e6], T[T["amount_usd"] >= 5e6]),
        "perda >= US$ 10 mi": (P[P["amount_usd"] >= 10e6], T[T["amount_usd"] >= 10e6]),
        "datas originais DefiLlama": _original_dates(ev, rets),
    }
    rows = []
    for name, (p, t) in specs.items():
        log.info("variação: %s (preço %d, TVL %d)", name, len(p), len(t))
        car, _ = event_price.run(events=p, save=False, rets=rets, benchmarks=["eth"])
        res, _ = event_tvl.run(events=t, save=False)
        rows += _price_stats(name, car) + _tvl_stats(name, res)
        if name == "principal":
            # média winsorizada 1/99 sobre a amostra principal
            for w in PRICE_WINDOWS:
                x = car[(car["benchmark"] == "eth") & (car["window"] == w)]["car"]
                x = x.clip(*x.quantile([0.01, 0.99]))
                rows.append({"spec": "winsorizado 1/99", "medida": "CAR preço", "window": w,
                             **st.summarize(x.to_numpy())})
            for w in TVL_WINDOWS:
                x = res[res["window"] == w]["abn_flow_ex_theft"]
                x = x.clip(*x.quantile([0.01, 0.99]))
                rows.append({"spec": "winsorizado 1/99", "medida": "fluxo líquido do roubo", "window": w,
                             **st.summarize(x.to_numpy())})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- placebos

def _valid_mask(ok: pd.Series, est: tuple[int, int], est_share: float, last: int = 30) -> pd.Series:
    """Datas d em que `ok` tem cobertura de est_share em est e completa em [-1,last]."""
    x = ok.astype(float)
    L = est[1] - est[0] + 1
    est_cnt = x.rolling(L).sum().shift(-est[1])          # soma de d+est0 .. d+est1
    evt_all = x.rolling(last + 2).min().shift(-last)     # mínimo de d-1 .. d+last
    return (est_cnt >= est_share * L) & (evt_all == 1)


def _exclusion(index: pd.DatetimeIndex, hack_dates: list) -> np.ndarray:
    bad = np.zeros(len(index), dtype=bool)
    for h in hack_dates:
        bad |= (index >= h + pd.Timedelta(days=EXCL[0])) & (index <= h + pd.Timedelta(days=EXCL[1]))
    return bad


def placebo_price(rets: pd.DataFrame, rng: np.random.Generator) -> tuple[np.ndarray, dict]:
    car = pd.read_parquet(PROCESSED_DIR / "price_car.parquet")
    car = car[car["benchmark"] == "eth"]
    ev = pd.read_parquet(PROCESSED_DIR / "events.parquet")
    ids = car["hack_id"].unique()
    tokens = ev.set_index("hack_id").loc[ids, "gecko_id"].tolist()
    hacks_by_token = ev.dropna(subset=["gecko_id"]).groupby("gecko_id")["date"].apply(list).to_dict()
    last_full = rets.index.max() - pd.Timedelta(days=32)
    eth = rets["ethereum"]
    cases = []
    for g in tokens:
        ri = rets[g]
        ok = ri.notna() & eth.notna()
        mask = _valid_mask(ok, (-120, -11), 0.9) & ri.notna().rolling(32).min().shift(-30).eq(1)
        mask &= (rets.index >= START) & (rets.index <= last_full)
        mask &= ~_exclusion(rets.index, hacks_by_token.get(g, []))
        pos = np.flatnonzero(mask.to_numpy())
        if len(pos):
            cases.append((ri.to_numpy(), eth.to_numpy(), pos))
    draws = np.empty((N_PLACEBO, 6))
    for r in range(N_PLACEBO):
        c1, c30, l1, l30 = [], [], [], []
        for ri, rm, pos in cases:
            i = rng.choice(pos)
            e_ri, e_rm = ri[i - 120:i - 10], rm[i - 120:i - 10]
            m = np.isfinite(e_ri) & np.isfinite(e_rm)
            x, y = e_rm[m], e_ri[m]
            beta = np.cov(x, y, ddof=1)[0, 1] / np.var(x, ddof=1)
            alpha = y.mean() - beta * x.mean()
            ar = ri[i:i + 31] - alpha - beta * rm[i:i + 31]
            exp = alpha + beta * rm[i:i + 31]
            lar = np.log1p(ri[i:i + 31]) - np.log1p(exp)
            c1.append(np.nansum(ar[:2]))
            c30.append(np.nansum(ar))
            l1.append(np.nansum(lar[:2]))
            l30.append(np.nansum(lar))
        draws[r] = [np.mean(c1), np.mean(c30), np.median(c1), np.median(c30), np.mean(l1), np.mean(l30)]
    actual = {}
    for w in PRICE_WINDOWS:
        sub = car[car["window"] == w]
        actual[("média CAR", w)] = sub["car"].mean()
        actual[("mediana CAR", w)] = sub["car"].median()
        actual[("média log-CAR", w)] = sub["car_log"].mean()
    return draws, {"n": len(cases), "actual": actual}


def placebo_tvl(rng: np.random.Generator) -> tuple[np.ndarray, dict]:
    flows = pd.read_parquet(PROCESSED_DIR / "tvl_flows.parquet")
    ev = pd.read_parquet(PROCESSED_DIR / "events.parquet")
    slugs = ev.set_index("hack_id").loc[flows["hack_id"].unique(), "slug"].tolist()
    hacks_by_slug = ev.dropna(subset=["slug"]).groupby("slug")["date"].apply(list).to_dict()
    tok = pd.read_parquet(PROCESSED_DIR / "tvl_tokens.parquet", filters=[("slug", "in", list(set(slugs)))])
    cases = []
    for s in slugs:
        d = decompose(tok[tok["slug"] == s])
        d = d[d.index >= START - pd.Timedelta(days=60)]
        f = (d["flow"] / d["tvl"]).clip(-1, 1)
        ok = f.notna()
        mask = _valid_mask(ok, (-60, -11), 0.9) & (d["tvl"] >= 1e6)
        mask &= (d.index >= START) & (d.index <= d.index.max() - pd.Timedelta(days=31))
        mask &= ~_exclusion(d.index, hacks_by_slug.get(s, []))
        pos = np.flatnonzero(mask.to_numpy())
        if len(pos):
            cases.append((f.to_numpy(), d["flow"].to_numpy(), d["tvl"].to_numpy(), pos))
    draws = np.empty((N_PLACEBO, 2))
    for r in range(N_PLACEBO):
        a10, a30 = [], []
        for f, flow, tvl, pos in cases:
            i = rng.choice(pos)
            mu = np.nanmean(f[i - 60:i - 10])
            evt = np.clip(flow[i:i + 31] / tvl[i], -1, 1) - mu
            a10.append(evt[:11].sum())
            a30.append(evt.sum())
        draws[r] = [np.mean(a10), np.mean(a30)]
    actual = {}
    for w in TVL_WINDOWS:
        sub = flows[flows["window"] == w]
        actual[("média fluxo bruto", w)] = sub["abn_flow"].mean()
        actual[("média fluxo líquido do roubo", w)] = sub["abn_flow_ex_theft"].mean()
    return draws, {"n": len(cases), "actual": actual}


def placebo_contagion(rng: np.random.Generator) -> tuple[np.ndarray, dict]:
    panel = pd.read_parquet(PROCESSED_DIR / "contagion_panel.parquet")
    tvl = pd.read_parquet(PROCESSED_DIR / "contagion_tvl.parquet")
    ev = pd.read_parquet(PROCESSED_DIR / "events.parquet")
    hacks_by_slug = ev.dropna(subset=["slug"]).groupby("slug")["date"].apply(list).to_dict()
    cases = []
    for s, g in tvl[tvl["slug"].isin(panel["slug"].unique())].groupby("slug"):
        lvl = g.set_index("date")["tvl_usd"]
        lvl = lvl.reindex(pd.date_range(lvl.index.min(), lvl.index.max()))
        lv = np.log(lvl.where(lvl > 0))
        dl = (lv.shift(-1) - lv).clip(-1, 1)
        mask = _valid_mask(dl.notna(), (-60, -11), 0.9) & (lvl >= 1e6)
        mask &= (lvl.index >= START) & (lvl.index <= lvl.index.max() - pd.Timedelta(days=31))
        mask &= ~_exclusion(lvl.index, hacks_by_slug.get(s, []))
        pos = np.flatnonzero(mask.to_numpy())
        if len(pos):
            cases.append((dl.to_numpy(), pos))
    draws = np.empty((N_PLACEBO_CONTAGION, 1))
    for r in range(N_PLACEBO_CONTAGION):
        vals = []
        for dl, pos in cases:
            i = rng.choice(pos)
            vals.append((dl[i:i + 31] - np.nanmean(dl[i - 60:i - 10])).sum())
        draws[r] = [np.mean(vals)]
    return draws, {"n": len(cases), "actual": {("média Δln TVL", "[0,30]"): panel["y_0_30"].mean()}}


# coluna da matriz de réplicas correspondente a cada estatística
PRICE_COLS = {("média CAR", "[0,1]"): 0, ("média CAR", "[0,30]"): 1, ("mediana CAR", "[0,1]"): 2,
              ("mediana CAR", "[0,30]"): 3, ("média log-CAR", "[0,1]"): 4, ("média log-CAR", "[0,30]"): 5}
TVL_COLS = {"[0,10]": 0, "[0,30]": 1}
# estatísticas acrescentadas depois de ver as caudas pesadas do placebo da média (não pré-registradas)
POST_HOC = {"mediana CAR", "média log-CAR"}


def placebo_all(rets: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(st.SEED)
    rows, draws_out = [], []
    tests = [
        ("preço", lambda: placebo_price(rets, rng), lambda k: PRICE_COLS[k]),
        ("TVL", lambda: placebo_tvl(rng), lambda k: TVL_COLS[k[1]]),
        ("contágio", lambda: placebo_contagion(rng), lambda k: 0),
    ]
    for name, fn, col in tests:
        draws, info = fn()
        for key, actual in info["actual"].items():
            d = draws[:, col(key)]
            rows.append({
                "teste": name, "estatística": key[0], "window": key[1], "real": actual,
                "placebo_media": d.mean(), "placebo_p2_5": np.percentile(d, 2.5),
                "placebo_p97_5": np.percentile(d, 97.5),
                "p_unilateral": (d <= actual).mean(),
                "p_bilateral": (np.abs(d - d.mean()) >= abs(actual - d.mean())).mean(),
                "excesso_sobre_placebo": actual - d.mean(),
                "pre_registrado": key[0] not in POST_HOC, "n_unidades": info["n"],
            })
            draws_out.append(pd.DataFrame({"teste": name, "estatística": key[0], "window": key[1],
                                           "valor_placebo": d}))
    pd.concat(draws_out).to_parquet(PROCESSED_DIR / "placebo_draws.parquet", index=False)
    return pd.DataFrame(rows)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for name in ["src.analysis.event_price", "src.analysis.event_tvl", "src.collect.http"]:
        logging.getLogger(name).setLevel(logging.WARNING)
    rets = event_price.load_returns()
    pl = placebo_all(rets)
    pl.to_csv(PROCESSED_DIR / "placebo_summary.csv", index=False)
    var = variations(rets)
    var.to_csv(PROCESSED_DIR / "robustness_h1.csv", index=False)
    pd.set_option("display.width", 250)
    print(pl.drop(columns=["n_unidades"]).round(4).to_string(index=False))
    cols = ["spec", "medida", "window", "n", "mean", "median", "frac_neg", "p_bmp", "p_boot", "p_wilcoxon"]
    print(var[cols].round(4).to_string(index=False))


if __name__ == "__main__":
    main()

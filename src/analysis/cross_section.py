"""Regressões em corte transversal (H2 e H3, Fase 4).

Especificação registrada em docs/decisions.md antes de rodar. MQO com erros
HC3. Robustez: winsorização 1/99, regressão mediana, BHAR, CAR em
log-retornos, categoria pela regra automática e TVL sem CEX.

Uso: python -m src.analysis.cross_section
Saídas: data/processed/cross_section_main.csv e cross_section_robust.csv
"""

from __future__ import annotations

import logging
import warnings

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from src.analysis.event_price import load_returns
from src.build.taxonomy import GROUP
from src.config import PROCESSED_DIR

log = logging.getLogger(__name__)

MAIN_CHAINS = ["Ethereum", "BSC", "Arbitrum", "Solana"]
BULL_WINDOW = (-120, -11)

H2 = "C(group, Treatment('code'))"
H2_CAT = "C(category, Treatment('contract_logic'))"
CONTROLS = "audited + bridge_hack + bull + C(chain_fe, Treatment('Ethereum'))"


def _bull(dates: pd.Series) -> pd.Series:
    eth = load_returns()["ethereum"]
    out = []
    for d in dates:
        w = eth.loc[d + pd.Timedelta(days=BULL_WINDOW[0]): d + pd.Timedelta(days=BULL_WINDOW[1])]
        out.append(bool((1 + w.dropna()).prod() > 1))
    return pd.Series(out, index=dates.index)


def build_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    ev = pd.read_parquet(PROCESSED_DIR / "events.parquet")
    ev = ev.assign(
        group=ev["failure_group"],
        group_rule=ev["category_rule"].map(GROUP),
        chain_fe=ev["main_chain"].where(ev["main_chain"].isin(MAIN_CHAINS), "Other"),
        log_loss=np.log(ev["amount_usd"]),
        log_loss_tvl=np.log(ev["amount_usd"] / ev["tvl_pre"].where(ev["tvl_pre"] > 0)),
        cex=ev["target_type"].eq("CEX"),
    )
    for c in ["audited", "bridge_hack", "funds_returned", "cex"]:
        ev[c] = ev[c].astype(int)

    car = pd.read_parquet(PROCESSED_DIR / "price_car.parquet")
    car = car[car["benchmark"] == "eth"]
    price = car.pivot(index="hack_id", columns="window", values=["car", "bhar", "car_log"])
    price.columns = [f"{m}_{w.strip('[]').replace(',', '_').replace('-', 'm').replace('+', '')}"
                     for m, w in price.columns]
    price = ev.set_index("hack_id").join(price, how="inner").reset_index()

    fl = pd.read_parquet(PROCESSED_DIR / "tvl_flows.parquet")
    tvl = fl.pivot(index="hack_id", columns="window", values="abn_flow_ex_theft")
    tvl.columns = [f"flow_{w.strip('[]').replace(',', '_').replace('-', 'm')}" for w in tvl.columns]
    tvl = ev.set_index("hack_id").join(tvl, how="inner").reset_index()

    bull = _bull(pd.concat([price["date"], tvl["date"]]).drop_duplicates())
    bmap = dict(zip(pd.concat([price["date"], tvl["date"]]).drop_duplicates(), bull))
    price["bull"] = price["date"].map(bmap).astype(int)
    tvl["bull"] = tvl["date"].map(bmap).astype(int)
    # categoria 'other' tem 1 evento no TVL: agrupada com code para não gerar dummy singular
    tvl["group"] = tvl["group"].replace("other", "code")
    tvl["group_rule"] = tvl["group_rule"].replace("other", "code")
    tvl["category"] = tvl["category"].replace("other", "contract_logic")
    return price, tvl


def _fit(df: pd.DataFrame, y: str, rhs: str, method: str = "ols") -> dict:
    d = df.dropna(subset=[y]).copy()
    formula = f"{y} ~ {rhs}"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if method == "ols":
            m = smf.ols(formula, d).fit(cov_type="HC3")
        elif method == "winsor":
            lo, hi = d[y].quantile([0.01, 0.99])
            d[y] = d[y].clip(lo, hi)
            m = smf.ols(formula, d).fit(cov_type="HC3")
        elif method == "median":
            m = smf.quantreg(formula, d).fit(q=0.5)
        else:
            raise ValueError(method)
    out = {"n": int(m.nobs), "r2": getattr(m, "rsquared", np.nan)}
    for k in m.params.index:
        out[f"b[{k}]"] = m.params[k]
        out[f"p[{k}]"] = m.pvalues[k]
    return out


def _rhs(size: str, group: str = H2, returned: bool = False, cex: bool = False) -> str:
    parts = [group, size, CONTROLS]
    if returned:
        parts.append("funds_returned")
    if cex:
        parts.append("cex")
    return " + ".join(parts)


def run() -> tuple[pd.DataFrame, pd.DataFrame]:
    price, tvl = build_frames()
    main, robust = [], []

    def add(rows, label, df, y, rhs, method="ols"):
        rows.append({"modelo": label, "y": y, "metodo": method, **_fit(df, y, rhs, method)})

    # principais
    add(main, "preço, perda/TVL", price, "car_0_1", _rhs("log_loss_tvl"))
    add(main, "preço, perda", price, "car_0_1", _rhs("log_loss"))
    add(main, "preço, perda/TVL", price, "car_0_30", _rhs("log_loss_tvl", returned=True))
    add(main, "preço, perda", price, "car_0_30", _rhs("log_loss", returned=True))
    add(main, "TVL", tvl, "flow_0_30", _rhs("log_loss_tvl", returned=True, cex=True))
    add(main, "TVL", tvl, "flow_0_10", _rhs("log_loss_tvl", returned=True, cex=True))
    add(main, "preço, 6 categorias", price, "car_0_1", _rhs("log_loss", group=H2_CAT))
    add(main, "TVL, 6 categorias", tvl, "flow_0_30", _rhs("log_loss_tvl", group=H2_CAT, returned=True, cex=True))

    # robustez
    for y in ["car_0_1", "car_0_30"]:
        ret = y == "car_0_30"
        for method in ["winsor", "median"]:
            add(robust, f"preço {method}", price, y, _rhs("log_loss", returned=ret), method)
        alt = y.replace("car_", "bhar_")
        add(robust, "preço BHAR", price, alt, _rhs("log_loss", returned=ret))
        add(robust, "preço CAR log", price, y.replace("car_", "car_log_"), _rhs("log_loss", returned=ret))
        add(robust, "preço regra automática", price, y,
            _rhs("log_loss", group="C(group_rule, Treatment('code'))", returned=ret))
    for method in ["winsor", "median"]:
        add(robust, f"TVL {method}", tvl, "flow_0_30", _rhs("log_loss_tvl", returned=True, cex=True), method)
    add(robust, "TVL sem CEX", tvl[tvl["cex"] == 0], "flow_0_30", _rhs("log_loss_tvl", returned=True))
    add(robust, "TVL regra automática", tvl, "flow_0_30",
        _rhs("log_loss_tvl", group="C(group_rule, Treatment('code'))", returned=True, cex=True))

    main, robust = pd.DataFrame(main), pd.DataFrame(robust)
    main.to_csv(PROCESSED_DIR / "cross_section_main.csv", index=False)
    robust.to_csv(PROCESSED_DIR / "cross_section_robust.csv", index=False)
    return main, robust


KEY = ["operational", "economic", "log_loss_tvl", "log_loss", "audited", "funds_returned",
       "bridge_hack", "bull", "cex", "key_infra", "governance", "oracle_price", "bridge]"]


def show(df: pd.DataFrame) -> None:
    for _, r in df.iterrows():
        terms = []
        for k, v in r.items():
            if k.startswith("b[") and pd.notna(v) and any(s in k for s in KEY) and "chain_fe" not in k:
                name = k[2:-1].replace("C(group, Treatment('code'))[T.", "").replace(
                    "C(group_rule, Treatment('code'))[T.", "").replace(
                    "C(category, Treatment('contract_logic'))[T.", "").rstrip("]")
                terms.append(f"{name}={v:+.3f} (p={r['p' + k[1:]]:.3f})")
        print(f"[{r['modelo']} | {r['y']} | {r['metodo']} | n={r['n']}]\n   " + "\n   ".join(terms))


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    m, rb = run()
    print("==== PRINCIPAIS ====")
    show(m)
    print("\n==== ROBUSTEZ ====")
    show(rb)

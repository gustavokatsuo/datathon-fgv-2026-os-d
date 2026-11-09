"""Ranking atual de exposição (Fase 8).

Medida principal: participação de cada protocolo no TVL DeFi oficial de cada
chain onde opera (canal com evidência no H4). Contexto descritivo: TVL
atendido por provedor de oráculo e TVL das famílias de fork.

Uso: python -m src.analysis.exposure_ranking
Saídas em data/processed/: exposure_protocol_chain.csv, exposure_ranking.csv,
exposure_chain_concentration.csv, exposure_oracles.csv, exposure_fork_bases.csv
"""

from __future__ import annotations

import gzip
import json

import numpy as np
import pandas as pd

from src.build.network import fork_graph
from src.collect.chain_names import canonical_chain
from src.config import PROCESSED_DIR, RAW_DIR

MIN_PROTOCOL_TVL = 10e6
MIN_CHAIN_TVL = 10e6
THRESHOLD = 0.05
EXCLUDED_CATEGORIES = {"CEX", "Bridge", "Canonical Bridge", "Chain"}
EXTRA_KEYS = {"borrowed", "staking", "pool2", "vesting", "treasury", "offers", "doublecounted",
              "liquidstaking", "dcAndLsOverlap"}


def protocol_chain_shares() -> pd.DataFrame:
    with gzip.open(RAW_DIR / "protocols.json.gz", "rt") as f:
        raw = json.load(f)
    chains = pd.read_parquet(PROCESSED_DIR / "chains.parquet").set_index("chain")["tvl_now"]
    rows = []
    for p in raw:
        if (p.get("tvl") or 0) < MIN_PROTOCOL_TVL or p.get("category") in EXCLUDED_CATEGORIES:
            continue
        for key, v in (p.get("chainTvls") or {}).items():
            if "-" in key or key in EXTRA_KEYS or not v:
                continue
            c = canonical_chain(key)
            ctvl = chains.get(c, np.nan)
            if not (ctvl >= MIN_CHAIN_TVL):
                continue
            rows.append({"slug": p["slug"], "name": p["name"], "category": p.get("category"),
                         "parent": p.get("parentProtocolSlug"), "chain": c, "tvl_on_chain": v,
                         "chain_tvl": ctvl, "share": v / ctvl})
    return pd.DataFrame(rows)


def main() -> None:
    d = protocol_chain_shares()
    # participação acima de 100%: TVL do protocolo fora do escopo do TVL oficial da chain
    d["escopo_inconsistente"] = d["share"] > 1
    d.to_csv(PROCESSED_DIR / "exposure_protocol_chain.csv", index=False)
    n_bad = int(d["escopo_inconsistente"].sum())
    d = d[~d["escopo_inconsistente"]]

    above = d[d["share"] >= THRESHOLD]
    ranking = (above.sort_values("share", ascending=False)
               .groupby("slug")
               .agg(name=("name", "first"), category=("category", "first"),
                    chains_acima_5pct=("chain", lambda s: ", ".join(s)),
                    n_chains_acima_5pct=("chain", "size"),
                    share_max=("share", "max"),
                    tvl_total_nessas_chains=("tvl_on_chain", "sum"))
               .sort_values(["tvl_total_nessas_chains"], ascending=False))
    ranking.to_csv(PROCESSED_DIR / "exposure_ranking.csv")

    conc = (d.sort_values("share", ascending=False).groupby("chain")
            .agg(chain_tvl=("chain_tvl", "first"), maior_protocolo=("name", "first"),
                 maior_share=("share", "first"),
                 n_protocolos_acima_5pct=("share", lambda s: int((s >= THRESHOLD).sum())))
            .sort_values("chain_tvl", ascending=False))
    conc.to_csv(PROCESSED_DIR / "exposure_chain_concentration.csv")

    # contexto descritivo: oráculos (provedor principal) e famílias de fork
    pr = pd.read_parquet(PROCESSED_DIR / "protocols.parquet")
    live = pr[(pr["tvl_now"] >= MIN_PROTOCOL_TVL) & ~pr["category"].isin(EXCLUDED_CATEGORIES)]
    orc = live.explode("oracles").dropna(subset=["oracles"])
    oracles = (orc.groupby("oracles").agg(n_protocolos=("slug", "size"), tvl_atendido=("tvl_now", "sum"))
               .sort_values("tvl_atendido", ascending=False))
    oracles.to_csv(PROCESSED_DIR / "exposure_oracles.csv")

    g = fork_graph(pr)
    P = pr.set_index("protocol_id")
    rows = []
    for pid in P.index:
        children = [c for c in g.neighbors(pid) if pid in [str(x) for x in P.at[c, "forked_from_ids"]]]
        if children:
            tvl_forks = P.loc[children, "tvl_now"].fillna(0).sum()
            rows.append({"codigo_base": P.at[pid, "name"], "n_forks": len(children), "tvl_forks": tvl_forks,
                         "tvl_original": P.at[pid, "tvl_now"]})
    forks = pd.DataFrame(rows).sort_values("tvl_forks", ascending=False)
    forks.to_csv(PROCESSED_DIR / "exposure_fork_bases.csv", index=False)

    pd.set_option("display.width", 220)
    print(f"pares excluídos por escopo inconsistente (participação > 100%): {n_bad}")
    print(f"pares protocolo-chain: {len(d)}, acima de 5%: {len(above)}, protocolos: {above['slug'].nunique()}, "
          f"chains: {above['chain'].nunique()}")
    print("\nTop 15 por TVL nas chains em que passam de 5%:")
    print(ranking.head(15).assign(share_max=lambda x: x["share_max"].round(3),
                                  tvl_total_nessas_chains=lambda x: (x["tvl_total_nessas_chains"] / 1e9).round(2))
          .to_string())
    print("\nConcentração nas 15 maiores chains:")
    print(conc.head(15).assign(chain_tvl=lambda x: (x["chain_tvl"] / 1e9).round(1),
                               maior_share=lambda x: x["maior_share"].round(3)).to_string())
    print("\nOráculos:", (oracles.head(6)["tvl_atendido"] / 1e9).round(1).to_dict())
    print("Códigos-base:", forks.head(6)[["codigo_base", "n_forks", "tvl_forks"]]
          .assign(tvl_forks=lambda x: (x["tvl_forks"] / 1e9).round(2)).to_dict("records"))


if __name__ == "__main__":
    main()

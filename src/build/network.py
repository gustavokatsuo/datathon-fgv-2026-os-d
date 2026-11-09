"""Rede de dependências entre protocolos (Fase 6).

- Grafo de forks: aresta entre protocolo e cada id em forkedFromIds.
- Família de fork de uma vítima: vizinhos de até dois passos (pai, filhos e
  irmãos), excluindo protocolos do mesmo projeto (mesmo parent_slug).
- Para cada evento elegível, monta o grupo exposto (família) e o grupo de
  controle (mesma categoria, chain em comum, fora da família).

Saída: data/processed/contagion_sets.parquet (hack_id, slug, grupo)
"""

from __future__ import annotations

import networkx as nx
import pandas as pd

from src.config import PROCESSED_DIR

CATEGORIES = {"contract_logic", "oracle_price"}
LAST_DATE = pd.Timestamp("2026-10-07")
CAP = 25


def fork_graph(protocols: pd.DataFrame) -> nx.Graph:
    g = nx.Graph()
    g.add_nodes_from(protocols["protocol_id"])
    known = set(protocols["protocol_id"])
    for p in protocols.itertuples():
        for f in p.forked_from_ids:
            if str(f) in known:
                g.add_edge(p.protocol_id, str(f))
    return g


def fork_family(g: nx.Graph, pid: str) -> set[str]:
    if pid not in g:
        return set()
    first = set(g.neighbors(pid))
    fam = set(first)
    for q in first:
        fam |= set(g.neighbors(q))
    fam.discard(pid)
    return fam


def _project(p: pd.Series) -> str:
    return p["parent_slug"] if isinstance(p["parent_slug"], str) else p["slug"]


def build_sets() -> pd.DataFrame:
    pr = pd.read_parquet(PROCESSED_DIR / "protocols.parquet")
    ev = pd.read_parquet(PROCESSED_DIR / "events.parquet")
    P = pr.set_index("protocol_id")
    P["project"] = [_project(r) for _, r in P.iterrows()]
    slug_to_id = pr.set_index("slug")["protocol_id"]
    g = fork_graph(pr)

    elig = ev[ev["in_base"] & ev["slug"].notna() & ev["category"].isin(CATEGORIES) & (ev["date"] <= LAST_DATE)]
    rows = []
    for e in elig.itertuples():
        pid = slug_to_id.get(e.slug)
        if pid is None:
            continue
        proj = P.at[pid, "project"]
        listed = P["listed_at"].lt(e.date)
        fam = [f for f in fork_family(g, pid) if P.at[f, "project"] != proj and listed.get(f, False)]
        if not fam:
            continue
        exposed = P.loc[fam].sort_values("tvl_now", ascending=False).head(CAP)
        vchains = set(P.at[pid, "chains"])
        cand = P[(P["category"] == P.at[pid, "category"]) & listed & (P["project"] != proj)
                 & ~P.index.isin(fam) & (P.index != pid)]
        cand = cand[cand["chains"].map(lambda c: len(vchains & set(c)) > 0)]
        control = cand.sort_values("tvl_now", ascending=False).head(CAP)
        for grp, df in [("exposed", exposed), ("control", control)]:
            for s in df["slug"]:
                rows.append({"hack_id": e.hack_id, "victim_slug": e.slug, "slug": s, "group": grp})
    out = pd.DataFrame(rows)
    out.to_parquet(PROCESSED_DIR / "contagion_sets.parquet", index=False)
    return out


if __name__ == "__main__":
    s = build_sets()
    print(s.groupby("group").agg(eventos=("hack_id", "nunique"), pares=("slug", "size"), protocolos=("slug", "nunique")))

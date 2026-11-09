"""Taxonomia de falhas de segurança.

Mapeia a classificação e a técnica brutas da DefiLlama para seis categorias
fundamentadas no vetor de ataque (mecanismo da falha):

1. contract_logic  Lógica de contrato (reentrância, validação, aritmética,
                   controle de acesso no código, lógica de negócio)
2. key_infra       Comprometimento de chave ou infraestrutura (chave privada,
                   frontend, DNS, servidores, engenharia social)
3. oracle_price    Manipulação de oráculo ou de preço
4. bridge          Falha de verificação cross-chain (prova, mensagem, mint
                   sem lastro em bridge)
5. governance      Proposta maliciosa ou ataque de votação
6. other           Rugpull, alvos não protocolares e não classificáveis

Regras gerais (justificativas em docs/decisions.md):
- A categoria segue o mecanismo, não o tipo de alvo. Um bridge drenado por
  chave comprometida é key_infra. Ser bridge é a dummy separada bridge_hack.
- Rugpull é fraude interna, não falha de segurança: fica em other e recebe a
  flag is_rugpull para poder ser excluído.
- "Access Control" em exchange centralizada (CEX) é invasão de sistema, não
  bug de contrato: vai para key_infra.
- Revisões manuais por evento, quando a descrição da própria DefiLlama
  contradiz a classificação, ficam em taxonomy_overrides.csv com justificativa.
  A coluna category_rule guarda a categoria pela regra automática (robustez).

Também define um agrupamento grosso para H2:
- operational: key_infra e governance (falhas de processo e de gestão)
- code:        contract_logic e bridge (bugs de software)
- economic:    oracle_price (desenho econômico explorável)
- other
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

OVERRIDES_CSV = Path(__file__).with_name("taxonomy_overrides.csv")

CATEGORIES = {
    "contract_logic": "Lógica de contrato",
    "key_infra": "Chave ou infraestrutura",
    "oracle_price": "Oráculo ou preço",
    "bridge": "Bridge cross-chain",
    "governance": "Governança",
    "other": "Outros",
}

GROUP = {
    "contract_logic": "code",
    "bridge": "code",
    "key_infra": "operational",
    "governance": "operational",
    "oracle_price": "economic",
    "other": "other",
}

# categoria padrão por classificação da DefiLlama
BY_CLASSIFICATION = {
    "Access Control": "contract_logic",
    "Input Validation": "contract_logic",
    "Protocol Logic": "contract_logic",
    "Reentrancy": "contract_logic",
    "Token & Share Accounting": "contract_logic",
    "Key Compromise": "key_infra",
    "Frontend & Infrastructure": "key_infra",
    "Social Engineering": "key_infra",
    "Oracle Manipulation": "oracle_price",
    "Market Manipulation": "oracle_price",
    "Bridge & Cross-Chain": "bridge",
    "Governance": "governance",
    "Rugpull": "other",
}

# exceções por (classificação, técnica)
BY_TECHNIQUE = {
    # o alvo é um bot de trading do próprio atacado, não manipulação de preço de protocolo
    ("Market Manipulation", "MEV Bot Drained"): "other",
    ("Market Manipulation", "Market Maker Bot Exploited"): "other",
}

# tipos de alvo sem contrato inteligente próprio
CUSTODIAL_TARGETS = {"CEX"}


def categorize(classification, technique, target_type) -> str:
    if classification is None or pd.isna(classification):
        return "other"
    key = (classification, technique)
    if key in BY_TECHNIQUE:
        return BY_TECHNIQUE[key]
    if classification == "Access Control" and target_type in CUSTODIAL_TARGETS:
        return "key_infra"
    return BY_CLASSIFICATION.get(classification, "other")


def apply_taxonomy(hacks: pd.DataFrame) -> pd.DataFrame:
    out = hacks.copy()
    out["category"] = [
        categorize(c, t, tt)
        for c, t, tt in zip(out["classification"], out["technique"], out["target_type"])
    ]
    out["category_rule"] = out["category"]
    ov = pd.read_csv(OVERRIDES_CSV)
    bad = set(ov["category"]) - set(CATEGORIES)
    if bad:
        raise ValueError(f"categorias inválidas em overrides: {bad}")
    ov_map = ov.set_index("hack_id")["category"]
    hit = out["hack_id"].isin(ov_map.index)
    out.loc[hit, "category"] = out.loc[hit, "hack_id"].map(ov_map)
    out["category_overridden"] = hit
    out["failure_group"] = out["category"].map(GROUP)
    out["is_rugpull"] = out["classification"].eq("Rugpull") & ~hit
    unknown = set(out["classification"].dropna()) - set(BY_CLASSIFICATION)
    if unknown:
        raise ValueError(f"classificações sem mapeamento: {sorted(unknown)}")
    return out


def mapping_table(hacks: pd.DataFrame) -> pd.DataFrame:
    """Tabela completa (classificação, técnica, tipo de alvo) -> categoria, para revisão."""
    t = apply_taxonomy(hacks)
    return (
        t.groupby(["classification", "technique", "category", "failure_group"], dropna=False)
        .size()
        .rename("n")
        .reset_index()
        .sort_values(["category", "classification", "technique"])
    )

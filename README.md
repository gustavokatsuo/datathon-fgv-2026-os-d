# Nem todo hack é igual

Como o mercado de criptoativos precifica falhas de segurança em blockchain.

Equipe **Os D** no 7º Desafio de Dados (Datathon) de Moedas Digitais FGV, realizado pela FGV EESP Digital Finance com patrocínio da Ripple (University Blockchain Research Initiative).

**Integrantes:** Yoonsik Hur, Carolina Thomaz Ferreira Curraladas, Miguel Absy Freire de Oliveira, Murilo Santos de Castro e Gustavo Katsuo Tsutsui.

## Tese

O mercado de moedas digitais não reage a um exploit apenas pelo valor roubado. Ele lê o incidente como um sinal sobre a qualidade de quem administra o protocolo, e o dano se propaga pelas dependências técnicas compartilhadas na blockchain.

## Estrutura

```
data/raw/         respostas brutas das APIs (cache local, fora do git)
data/processed/   tabelas limpas
src/collect/      coletores, um módulo por fonte
src/build/        amostra, taxonomia e rede de dependências
src/analysis/     estudo de evento, regressões, contágio e robustez
figures/          gráficos em PDF e PNG
slides/           apresentação em Beamer
docs/decisions.md log de decisões metodológicas
```

## Como reproduzir

Requer Python 3.11 ou superior.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 1. Coleta

```bash
python -m src.collect.run
```

Baixa hacks, metadados de protocolos e chains, histórico de TVL dos protocolos atingidos, preços diários (tokens, moedas nativas e benchmarks) e oferta de stablecoins por chain. As respostas brutas ficam em cache em `data/raw/` (JSON com gzip) e nunca são baixadas de novo. As tabelas limpas vão para `data/processed/` em Parquet, e o script termina imprimindo o relatório de cobertura.

### 2. Amostra e taxonomia

```bash
python -m src.build.sample
```

Aplica a taxonomia de falhas (`src/build/taxonomy.py`, com revisões manuais em `src/build/taxonomy_overrides.csv`), as datas validadas (`docs/date_validation.csv`) e a codificação de devolução de fundos (`src/build/recovery_manual.csv`). Gera `data/processed/events.parquet`, com as flags de amostra, e a tabela descritiva por categoria em `data/processed/table_categories.csv`.

### 3. Estudo de evento (H1)

```bash
python -m src.analysis.event_price     # retorno anormal do token (CAR, BHAR, BMP, Corrado, bootstrap)
python -m src.analysis.event_tvl       # decomposição do TVL em preço e fluxo, fluxo anormal
python -m src.analysis.figures_phase3  # figuras em figures/
```

Tabelas resumo em `data/processed/price_event_study.csv` e `data/processed/tvl_event_study.csv`.

### 4. Regressões em corte transversal (H2, H3)

```bash
python -m src.analysis.cross_section   # MQO com HC3 e robustez
python -m src.analysis.figures_phase4  # CAR por tipo de falha
```

Coeficientes em `data/processed/cross_section_main.csv` e `data/processed/cross_section_robust.csv`.

### 5. Nível da blockchain (H4)

```bash
python -m src.analysis.chain_level     # moeda nativa, stablecoins e paridade de wrapped
python -m src.analysis.figures_phase5
```

O TVL histórico das chains e os preços dos ativos bridged são coletados por `python -m src.collect.run` (a lista de ativos está em `src/build/bridge_assets.csv`). Resultados em `data/processed/chain_level_study.csv`, `chain_level_dose.csv` e `bridge_depeg_cases.csv`.

### 6. Rede de dependências e contágio (H5)

```bash
python -m src.build.network            # famílias de fork, expostos e controles
python -m src.collect.contagion        # TVL histórico dos expostos e controles
python -m src.analysis.contagion       # diferenças em diferenças com efeito fixo de evento
python -m src.analysis.figures_phase6
```

Resultados em `data/processed/contagion_did.csv`.

### 7. Robustez

```bash
python -m src.analysis.robustness      # placebos e variações da amostra
python -m src.analysis.figures_phase7
```

Resultados em `data/processed/placebo_summary.csv` e `data/processed/robustness_h1.csv`.

### 8. Ranking de exposição atual

```bash
python -m src.analysis.exposure_ranking
python -m src.analysis.figures_phase8
```

Resultados em `data/processed/exposure_ranking.csv` (protocolos acima de 5% do TVL de alguma chain), `exposure_chain_concentration.csv`, `exposure_oracles.csv` e `exposure_fork_bases.csv`.

### 9. Slides

```bash
cd slides && latexmk -pdf main.tex
```

A apresentação final é `slides/main.pdf` (10 slides, Beamer com tema metropolis).

## Principais resultados

| Hipótese | Resultado |
|---|---|
| H1. Retorno anormal negativo e corrida on-chain | **Confirmada.** CAR[0,+1] de -17,4% (mediana -14,2%, n = 132), fora da faixa placebo (-2,4% a +3,1%). Corrida de depósitos além do roubo de cerca de 10% do TVL em 30 dias acima do placebo (p = 0,01, n = 125). |
| H2. Falhas operacionais punidas mais que bugs de código | **Não confirmada**, com pouco poder. Diferença de -6 p.p. na especificação principal (IC 95% de -23 a +10, n = 101) e de -7 p.p. com a amostra completa (IC de -19 a +5, n = 132). O tamanho da perda é o que explica a reação. |
| H3. Auditoria e devolução atenuam | **Não confirmada.** Sem efeito em nenhuma especificação (9 devoluções na amostra). |
| H4. Efeito na chain | **Moeda nativa confirmada** para hacks de pelo menos 5% do TVL da chain (-13% em [0,+5], n = 27). Stablecoins *saem* da chain, ao contrário do previsto. Perda de paridade de até 56% em ativos bridged (Orbit). |
| H5. Contágio por dependência técnica | **Não confirmada.** Forks da vítima não perdem mais TVL que controles (+0,3 p.p. em [0,+1], IC de -2,0 a +2,6). Sinal fraco de contágio setorial. |

Ranking atual: nas 12 maiores chains, um único protocolo tem de 28% a 78% do TVL DeFi (Lido 49% no Ethereum, Morpho Blue 74% na Base). Morpho Blue e Aave V3 passam de 5% do TVL em 17 e 15 chains.

Todas as decisões metodológicas, especificações registradas antes dos resultados, correções de dados e resultados por fase estão em `docs/decisions.md`.

## Fontes de dados

Todas públicas e gratuitas: DefiLlama (hacks, protocolos, TVL por protocolo e por chain, preços e stablecoins), coletadas em 08/11/2026. O cache bruto (cerca de 600 MB) não é versionado e é recriado por `python -m src.collect.run`. As tabelas processadas são versionadas, exceto `tvl_tokens.parquet` (acima do limite do GitHub).

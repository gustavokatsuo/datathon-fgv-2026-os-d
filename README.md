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

Os passos seguintes serão documentados aqui conforme forem implementados.

## Fontes de dados

Todas públicas e gratuitas: DefiLlama (hacks, protocolos, TVL, preços e stablecoins).

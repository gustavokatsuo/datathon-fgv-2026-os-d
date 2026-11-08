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

Os passos de coleta e análise serão documentados aqui conforme forem implementados.

## Fontes de dados

Todas públicas e gratuitas: DefiLlama (hacks, protocolos, TVL, preços e stablecoins).

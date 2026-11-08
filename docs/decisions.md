# Log de decisões metodológicas

Cada decisão relevante ou ambígua fica registrada aqui com data, contexto e justificativa.

## Fase 0. Setup

**2026-11-08. Cache bruto fora do controle de versão.** As respostas das APIs ficam em `data/raw/` e não são versionadas, pois podem ser regeneradas pelos coletores. As tabelas de `data/processed/` serão versionadas se o tamanho permitir, para facilitar a conferência dos resultados.

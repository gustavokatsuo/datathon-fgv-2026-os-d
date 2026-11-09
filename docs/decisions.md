# Log de decisões metodológicas

Cada decisão relevante ou ambígua fica registrada aqui com data, contexto e justificativa.

## Fase 0. Setup

**2026-11-08. Cache bruto fora do controle de versão.** As respostas das APIs ficam em `data/raw/` e não são versionadas, pois podem ser regeneradas pelos coletores. As tabelas de `data/processed/` serão versionadas se o tamanho permitir, para facilitar a conferência dos resultados.

## Fase 1. Coleta

**2026-11-08. Schema real das fontes.** Antes de escrever os coletores, cada endpoint foi inspecionado com uma requisição de teste. Principais achados:
- `/hacks` (1.341 registros, 2011 a 06/11/2026) traz `classification` (13 classes) e `technique` (81 técnicas), `amount`, `returnedFunds`, `chain` (lista), `bridgeHack`, `targetType`, `defillamaId` e `language`. Não traz informação de auditoria, que vem de `/protocols`. O campo `source` vem vazio.
- `/protocols` traz oráculos em `oraclesBreakdown` (o campo `oracles` está quase sempre vazio) e forks em `forkedFromIds` (o campo `forkedFrom` existe em apenas 7 protocolos). O `gecko_id` muitas vezes está só no protocolo pai (por exemplo Aave V3 não tem, o pai `aave` tem).
- `/protocol/{slug}`: os campos de nível superior `tvl`, `tokens` e `tokensInUsd` batem com o TVL padrão da DefiLlama (sem borrowed, staking e pool2). Conferido no Euler V1.
- `coins.llama.fi/chart` aceita no máximo 500 pontos por requisição e retorna só preço, sem volume nem market cap.

**2026-11-08. Token do protocolo.** O token de um protocolo hackeado é o `gecko_id` do próprio protocolo ou, na ausência, o do protocolo pai. Para alvos que são a própria chain (`defillamaId` começando com `chain#`), o token é a moeda nativa da chain. A origem fica registrada em `protocol_tokens.parquet` (coluna `gecko_source`).

**2026-11-08. Harmonização de nomes de chain.** A base de hacks usa grafias livres ("Binance Smart Chain", "Optimism", "Ripple"). Adotamos como canônico o nome de `/v2/chains`, que é o mesmo usado na API de stablecoins. O mapa de aliases e os ids CoinGecko das chains ausentes de `/v2/chains` (EOS, Polkadot, Monero etc.) estão em `src/collect/chain_names.py`. Os rótulos "Multiple" e "Multi-Chain" são tratados como chain desconhecida.

**2026-11-08. Convenção de data dos preços.** Os timestamps da API de preços ficam perto de 00:00 UTC (por exemplo 23:57 ou 00:02). Cada ponto é atribuído ao dia UTC mais próximo, então o preço do dia d é o preço por volta de 00:00 UTC de d. Como a data do hack também está em dia UTC, o retorno do dia 0 é p(d+1)/p(d), que cobre o dia do incidente.

**2026-11-08. Índice DeFi equal-weighted.** Para evitar viés de sobrevivência por escolha ex post, a lista de constituintes foi fixada antes de ver qualquer resultado: tokens DeFi de primeira geração inspirados no DeFi Pulse Index de 2020 (UNI, AAVE, MKR, COMP, CRV, SNX, YFI, SUSHI, BAL, LRC, REN, KNC, BNT, UMA, ZRX, 1INCH, CAKE, RUNE). O próprio DPI (`defipulse-index`) entra como benchmark alternativo. Quando o token do evento faz parte do índice, ele será excluído do benchmark daquele evento (Fase 3).

**2026-11-08. Escopo da coleta.** A coleta não aplica filtro de perda nem de período. Os filtros da amostra são definidos na Fase 2. O histórico de preços começa em 01/01/2019 para cobrir a janela de estimação de eventos de 2020. Os dados refletem o estado das APIs em 08/11/2026, e o cache em `data/raw/` congela essa versão.

**2026-11-08. Critério provisório de cobertura.** No relatório de cobertura, uma série cobre um evento se tem observação em pelo menos 90% dos dias de [-120,-11] e em todos os dias de [-1,+30]. O critério definitivo, incluindo liquidez, será fixado na Fase 2. Como a API não fornece volume, a liquidez terá de ser aproximada (por exemplo pela fração de dias com retorno zero).

**2026-11-08. TVL zero conta como observado.** Na primeira versão do relatório de cobertura, exigir TVL positivo até +30 excluía 17 eventos (2020+, perda de pelo menos US$ 1 milhão) em que o protocolo foi esvaziado pelo próprio hack. Como esses são os casos de corrida mais extremos, excluí-los enviesaria H1 contra o efeito. TVL zero passou a contar como observação válida.

**2026-11-08. Pontos de atenção para a Fase 2.**
- 82 eventos com protocolo na DefiLlama têm TVL começando depois de -120 (protocolo jovem ou listado depois). Para o TVL a janela de estimação longa talvez não seja necessária, pois o fluxo anormal pode usar uma linha de base mais curta. A decisão será tomada e justificada na Fase 2, antes de olhar resultados.
- O token herdado do protocolo pai pode ter sido lançado depois do hack (por exemplo Portal/Wormhole em 2022 recebe o token W, lançado em 2024). Esses eventos já caem fora por falta de preço na janela, mas a atribuição de token será validada manualmente nos maiores eventos.
- 6 eventos perdem a cobertura de preço porque o token deixou de ser cotado antes de +30 (provável morte do token). É um viés de sobrevivência a reportar como limitação.
- O último ponto de preço (09/11/2026) é intradiário e será descartado.

**2026-11-08. Tabelas versionadas.** Todas as tabelas de `data/processed/` são versionadas, exceto `tvl_tokens.parquet` (219 MB, acima do limite de 100 MB por arquivo do GitHub), que é regenerada a partir do cache por `python -m src.collect.run`.

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

## Fase 2. Amostra e taxonomia

**2026-11-08. Taxonomia pelo mecanismo do ataque.** As 81 técnicas da DefiLlama foram mapeadas em seis categorias (`src/build/taxonomy.py`): lógica de contrato, chave ou infraestrutura, oráculo ou preço, bridge cross-chain, governança e outros. A categoria segue o vetor do ataque e não o tipo de alvo. Um bridge drenado por chave comprometida (Ronin, Harmony) é chave ou infraestrutura, e ser bridge é a dummy separada `bridge_hack`. Assim H2 (operacional contra código) e H4 (bridge) não se confundem. Agrupamento grosso para H2: operacional (chave ou infraestrutura e governança), código (lógica de contrato e bridge), econômico (oráculo ou preço) e outros.

**2026-11-08. Casos de fronteira da taxonomia.**
- Engenharia social (phishing, malware, falso recrutador) entra em chave ou infraestrutura, pois a falha é operacional.
- "Access Control" em exchange centralizada vai para chave ou infraestrutura, porque CEX não tem contrato com bug: é invasão de sistema.
- "Donation Attack" fica em lógica de contrato (falha de contabilidade de cotas), embora envolva mover um preço interno.
- "Flashloan Governance Attack" fica em governança, conforme a definição da categoria.
- "MEV Bot Drained" e "Market Maker Bot Exploited" vão para outros, pois o alvo é um robô de negociação e não um protocolo.
- Rugpull é fraude interna e não falha de segurança: fica em outros com a flag `is_rugpull`.
- Kelp DAO (abr/2026) foi mantido como bridge. O vetor imediato foi comprometer nós RPC da LayerZero, mas o que permitiu o ataque foi a configuração de verificador único (1 de 1 DVN). É ambíguo e será testado em robustez.

**2026-11-08. Revisões manuais da categoria.** Quando a descrição da própria DefiLlama contradiz a classificação, a categoria foi revista evento a evento em `src/build/taxonomy_overrides.csv`, com justificativa. Para encontrar os casos, todos os 193 eventos da amostra de análise passaram por busca de termos (chave privada, multisig, phishing, malware, pré-assinatura) e os resultados foram lidos um a um. Cinco revisões: Orbit Bridge, Drift, Purrlend, Taiko Bridge e DxSale, todos para chave ou infraestrutura. A categoria pela regra automática fica em `category_rule` para teste de robustez.

**2026-11-08. Validação de datas.** Os 35 maiores eventos da amostra de análise foram conferidos (`docs/date_validation.csv`, com método e fonte). Convenção: dia 0 é o dia UTC em que o incidente começou ou, se ficou oculto, o dia em que foi divulgado. Oito datas foram corrigidas: Multichain, Qubit, Rari Capital, SwissBorg e Humanity (um dia de diferença, confirmado em fontes externas), BingX (horário de Singapura convertido para UTC), DxSale (descrição) e Mirror (exploit de outubro de 2021 só divulgado em maio de 2022, data de divulgação ambígua entre 26 e 31/05, e dentro da crise Terra).

**2026-11-08. Critérios da amostra.** Fixados antes de qualquer resultado:
- Base: hacks a partir de 01/01/2020 com perda de pelo menos US$ 1 milhão (584 eventos).
- Amostra de preço: preço em pelo menos 90% dos dias de [-120,-11] e em todos os dias de [-1,+30].
- Amostra de TVL: quantidades por token em pelo menos 90% dos dias de [-60,-11] e em todos os dias de [-1,+30], e TVL(-1) de pelo menos US$ 1 milhão. A linha de base do TVL é mais curta que a do preço porque o fluxo anormal é medido contra a média de fluxo pré-evento, sem modelo de mercado. TVL(-1) mínimo evita eventos em que a perda supera o próprio TVL medido.
- Sem filtro de liquidez: a API de preços não fornece volume, e a fração de retornos zero na janela de estimação não discrimina (mediana 0, máximo 5,5%), pois os preços são agregados. Fica como limitação.
- Flags `overlap_token` e `overlap_protocol` marcam eventos com outro hack do mesmo token ou protocolo em [-120,+30], para exclusão na robustez.

**2026-11-08. Devolução de fundos.** O campo `returnedFunds` da DefiLlama só está preenchido em 28 dos 1.341 registros e omite casos conhecidos (Curve 2023, ThalaSwap). A fração recuperada foi codificada manualmente a partir das descrições dos eventos da amostra de análise (`src/build/recovery_manual.csv`). O campo da DefiLlama também mistura duas coisas: recuperação junto ao atacante (Euler, GMX) e ressarcimento de usuários com caixa do protocolo ou de terceiros (Bybit, Wormhole pela Jump, Ankr). São economicamente diferentes, pois no ressarcimento a perda continua e passa para o protocolo. Todos os registros da DefiLlama na base foram recodificados à mão em duas variáveis: `recovered_share` (fração devolvida pelo atacante ou interceptada) e `users_reimbursed`. A codificação manual tem precedência sobre o campo da DefiLlama. A variável binária principal é `funds_returned` = fração recuperada de pelo menos 50%. A devolução costuma ocorrer dias ou semanas depois do hack, então a Fase 4 deve testar H3 em janelas compatíveis com a data da devolução.

**2026-11-08. Auditoria.** O campo `audits` de `/protocols` reflete o estado atual e não a data do hack. Um protocolo auditado depois do incidente aparece como auditado. É uma limitação para H3, a reportar. Não há fonte pública gratuita com a data das auditorias.

## Fase 3. Estudo de evento (H1)

**2026-11-08. Especificação registrada antes de rodar.** Escrita e versionada antes de qualquer resultado.

Preço:
- Retorno simples diário. O retorno do dia d vai do preço de ~00:00 UTC de d ao de ~00:00 UTC de d+1, então o dia 0 cobre o dia do hack.
- Modelo de mercado por MQO em [-120,-11], com pelo menos 90% dos dias. Benchmark principal: ETH (ativo mais líquido do ecossistema de contratos inteligentes). Robustez: moeda nativa da chain principal do evento e índice DeFi equal-weighted (mínimo de 5 constituintes no dia, sem o próprio token). Benchmark que coincide com o token do evento é pulado.
- Janelas [-1,+1], [0,+1], [0,+5], [0,+10] e [0,+30]. CAR e BHAR (buy-and-hold do token menos o buy-and-hold implícito no modelo de mercado).
- Testes: t transversal, BMP com correção do erro de previsão na variância do CAR, Corrado multi-dia (Campbell e Wasley 1993) com postos sobre [-120,+30], bootstrap de eventos (10 mil reamostragens, semente 20261108) e Wilcoxon para a mediana.
- Sem winsorização na especificação principal. Média e mediana são reportadas lado a lado.

TVL:
- A variação diária do TVL é decomposta, token a token, em efeito preço Σ q(t-1)·[P(t)-P(t-1)] e fluxo Σ P(t)·[q(t)-q(t-1)], com P = usd/qty implícito na DefiLlama (último preço conhecido quando falta).
- Taxa de fluxo diária f(t) = fluxo(t)/TVL(t-1), limitada a [-1,+1] para conter erros de preço da fonte. Fluxo normal = média de f em [-60,-11]. Fluxo anormal acumulado na janela = soma de [f(t) - normal], com f do período do evento medido sobre TVL(-1).
- Fluxo líquido do roubo: soma de volta min(perda, TVL(-1))/TVL(-1). É conservador contra H1, pois nem todo valor roubado saía do TVL medido (tesouraria, tokens cunhados). Reporto os dois.
- Mesmas janelas e testes (t, bootstrap, Wilcoxon). A padronização tipo BMP usa o desvio-padrão de f na linha de base.

**2026-11-08. Correções de dados feitas durante a Fase 3 (antes de qualquer regressão).** Ao inspecionar os retornos anormais diários, três problemas de dados apareceram. Registro aqui o que foi visto e o que foi feito, para que fique claro o que veio dos dados e o que veio de regra.
- *Datas.* Alguns tokens caíam fortemente no dia -1 (Humanity -86%, Growth DeFi, Spartan). Isso motivou uma checagem sistemática, só textual, em todos os 193 eventos da amostra de análise: quando a descrição da DefiLlama informa explicitamente a data de início e ela difere do campo de data, vale a descrição. Exceção: exploit gradual descoberto depois (Levana), em que vale a data de descoberta. 13 datas foram corrigidas por essa regra, inclusive para datas posteriores (THORChain, Lazy Summer, Allbridge), então a regra não escolhe a direção que favorece H1. Datas nunca foram escolhidas pela série de preços. Ambiguidades de fuso de um dia permanecem (THORChain de julho de 2021 e Defrost mostram queda no dia -1 mesmo após a regra), e por isso a janela [-1,+1] é reportada. A Fase 7 roda o estudo também com as datas originais da DefiLlama.
- *Humanity.* A correção para 09/06/2026 feita na Fase 2 estava errada: baseou-se no horário dos mints (02:09 UTC de 09/06), mas o token já valia US$ 0,105 às 00:00 de 09/06 contra US$ 0,71 em 08/06. O mint não foi o primeiro passo do ataque e a data do protocolo provavelmente está no horário da Ásia. Revertido para a data da DefiLlama.
- *Duplicatas.* Três registros duplicados foram excluídos (`src/build/duplicates.csv`): DEUS 2021 (mesmo ataque de 2022 com ano errado), Gamma 2021 (mesmo incidente da Visor registrado duas vezes) e BasketDAO 2024 (mesmo exploit de 2022).
- *Erros de cotação.* Regra aplicada a todas as séries: um ponto é removido quando difere por fator maior que 3 dos dois vizinhos, na mesma direção, e os vizinhos estão a menos de fator 1,5 um do outro (o preço volta ao nível anterior). A primeira versão da regra não exigia a volta ao nível e apagava o crash real do Bunny em 19/05/2021 (232, 11,6, 43,8): foi corrigida antes de seguir. 187 pontos removidos no total.
- *Quebra de nível.* Eventos com alta diária de mais de 10 vezes em [-120,+30] são excluídos da amostra de preço por erro de escala na fonte. Só o Rubic (dez/2022, salto de 27 vezes que não reverte) é afetado.
- *CAR em log-retornos.* Somar retornos simples distorce casos extremos: no Bunny, -95% seguido de +277% daria CAR de +182%, enquanto o log-retorno dá -167%. O CAR simples e o BHAR continuam como pré-registrados, e o CAR em log-retornos entra como robustez.

**2026-11-08. Convenção de horário do TVL.** O snapshot diário de TVL datado de d corresponde às 00:00 UTC de d (antes do hack do dia d). Verificado em 13 eventos com horário conhecido: em 12 (Euler, CREAM, Radiant, Balancer, GMX, Bybit, Drift, Curve, Nomad, Orbit, Qubit, Kelp) o valor de d é anterior ao hack e a queda aparece em d+1. Exceção: Cetus (Sui), cujo snapshot de 22/05/2025 já reflete o hack das 10:30 UTC. O Nemo (também Sui) parece ter o mesmo desvio, sugerindo que o adaptador da Sui na DefiLlama usa outro horário. Não deslocamos eventos individualmente com base no fluxo, pois isso seria escolher datas pelo resultado. Consequência: parte da saída média no dia -1 vem desses casos, e a janela [-1,+1] os absorve. Também corrigimos `tvl_pre` em `sample.py`, que usava o snapshot de d-1 (fechamento do dia -2) em vez do de d (fechamento do dia -1): a amostra de TVL passou de 129 para 127 eventos.

**2026-11-08. Resultados da Fase 3 (H1).**
- Preço (n = 132, benchmark ETH): CAR médio de -17,4% em [0,+1] (mediana -14,2%, 87% dos eventos negativos) e de -28,1% em [0,+30] (mediana -19,2%). Significativo em todos os testes (t, BMP, Corrado, bootstrap, Wilcoxon) e nos três benchmarks. BHAR e CAR em log-retornos são ainda mais negativos. A queda se concentra no dia 0 (AAR de -16%) e continua lentamente até +30.
- TVL (n = 125): fluxo anormal bruto de -36% do TVL em [0,+1] e -51% em [0,+30]. Descontado o roubo, o fluxo é próximo de zero nos primeiros dias (-0,4% em [0,+1], p = 0,88) e fica negativo e significativo em [0,+10] (-7,2%, p = 0,03) e em [0,+30] (-15,9%, mediana -9,0%, p < 0,01 em t, bootstrap e Wilcoxon). O BMP não rejeita para o fluxo líquido do roubo (p = 0,56 em [0,+30]), porque a padronização pelo desvio da linha de base dá peso extremo a protocolos de fluxo muito estável. Resultado igual sem as 10 exchanges centralizadas.
- Leitura: a corrida bancária on-chain além do valor roubado existe, mas é gradual (semanas) e não imediata. O efeito preço no TVL é pequeno (cerca de -2%), então a queda do TVL é fluxo e não reprecificação dos ativos depositados.

## Fase 4. Regressões em corte transversal (H2, H3)

**2026-11-08. Especificação registrada antes de rodar.**

Variáveis dependentes:
- Preço: CAR[0,+1] (reação imediata, que é onde o sinal sobre o tipo de falha deve aparecer) e CAR[0,+30], benchmark ETH.
- TVL: fluxo anormal descontado o roubo em [0,+30] (principal) e [0,+10].

Regressores:
- Tipo de falha (H2): dummies `operational` (chave ou infraestrutura e governança) e `economic` (oráculo ou preço), com base `code` (lógica de contrato e bridge). Versão secundária com as seis categorias (base: lógica de contrato), lembrando que governança tem 2 eventos e bridge 6.
- Tamanho: log(perda/TVL(-1)) na especificação principal (n menor, só eventos com TVL) e log(perda) na alternativa (amostra completa de preço).
- H3: `audited` (auditoria atual, limitação já registrada) e `funds_returned` (devolução pelo atacante de pelo menos 50%). Como a devolução costuma vir dias ou semanas depois, a interpretação de `funds_returned` só vale para CAR[0,+30] e fluxo [0,+30]. Ressarcimento de usuários tem 3 casos na amostra de preço e 2 na de TVL e não entra na regressão.
- Controles: `bridge_hack`, estado do mercado (`bull` = retorno do ETH em [-120,-11] positivo, janela sem contaminação do evento), efeitos fixos de chain (Ethereum como base, BSC, Arbitrum, Solana e demais agrupadas) e, no TVL, dummy de exchange centralizada.
- Inferência: MQO com erros robustos HC3 (amostra pequena).

Robustez desta fase: variável dependente winsorizada em 1% e 99%, regressão mediana (quantílica), BHAR e CAR em log-retornos no lugar do CAR, categoria pela regra automática (`category_rule`, sem as revisões manuais), e TVL sem exchanges centralizadas. Com três hipóteses e várias janelas, um p-valor isolado próximo de 0,05 deve ser lido com cautela.

**2026-11-08. Resultados da Fase 4.**
- H2 não confirmada, e o teste tem pouco poder. Sem controles, falhas operacionais têm CAR[0,+1] médio de -24,9% (mediana -17,6%, n = 31) contra -15,8% (mediana -10,3%, n = 78) em bugs de código, na direção prevista. Com controles, a diferença operacional menos código é -7,2 p.p. (IC 95% de -19,3 a +4,9, p = 0,24). Efeito mínimo detectável com 80% de poder: cerca de 17 p.p. em [0,+1] e 38 p.p. em [0,+30]. Conclusão honesta: os dados descartam que falhas operacionais sejam punidas mais de cerca de 19 p.p. além de bugs de código, mas não conseguem detectar diferenças menores. Em [0,+30] não há diferença (-1,4 p.p.). Mesmo resultado em todas as robustezes (winsorização, mediana, BHAR, CAR em log, regra automática da taxonomia) e com as seis categorias.
- H3 não confirmada. Auditoria (status atual) e devolução de fundos não têm coeficiente significativo em nenhuma especificação. Só 9 eventos com devolução na amostra de preço, então o teste também tem pouco poder.
- Tamanho da perda: log(perda) entra negativo e significativo em CAR[0,+30] (-8,4 p.p. por log, p = 0,03, e mediana p = 0,04) e em CAR[0,+1] nas especificações robustas a outliers (mediana p = 0,007, BHAR p = 0,01, CAR em log p = 0,02). Perdas maiores, reação maior.
- Efeito do tamanho no TVL não é identificável neste desenho: a parcela do roubo somada de volta tem correlação de 0,85 com log(perda/TVL), o que gera coeficiente positivo mecânico no fluxo líquido do roubo e negativo mecânico no fluxo bruto. Não interpretamos esse coeficiente.
- Estado do mercado, bridge e exchange centralizada não são significativos.

## Fase 5. Nível da blockchain (H4)

**2026-11-08. Especificação registrada antes de rodar.**
- Amostra: eventos da base em uma única chain, excluindo alvos custodiais (CEX, carteira), alvos que são a própria chain (cuja moeda nativa já é o token do H1) e chains com TVL DeFi abaixo de US$ 10 milhões na data. O TVL da chain vem de `/v2/historicalChainTvl` (snapshot das 00:00 UTC da data do hack).
- Tamanho relativo: perda / TVL DeFi da chain. "Hack grande" = perda de pelo menos 1% do TVL da chain (principal), com 5% como robustez, e versão contínua log(perda/TVL da chain).
- Moeda nativa: mesmo estudo de evento da Fase 3 (modelo de mercado em [-120,-11], mesmas janelas e testes), com BTC como benchmark de mercado (ETH quando a moeda nativa é o próprio BTC). Dose-resposta: regressão MQO-HC3 do CAR da moeda nativa em log(perda/TVL da chain).
- Stablecoins: crescimento diário g(t) = Δln(oferta de stablecoins na chain). Crescimento anormal acumulado = soma de [g(t) - média de g em [-60,-11]], com cobertura de 90% na linha de base e completa em [-1,+30]. H4 prevê crescimento positivo (fuga para stablecoins dentro da rede). Teste bilateral, pois saída de capital da rede daria sinal negativo.
- Ativos wrapped: só existe preço para 4 casos de bridge (Orbit oUSDT, Nomad USDC, Heco ETH, Kelp rsETH). A Multichain tem página na CoinGecko, mas sem histórico disponível na fonte gratuita. Wormhole e Harmony não foram encontrados. Medida: razão preço do wrapped / preço do original, normalizada pelo dia -1, em [0,+30]. Estudo de casos, sem inferência estatística.
- Limitação: muitos eventos dividem a mesma chain e datas próximas (sobretudo Ethereum e BSC), então os retornos anormais da moeda nativa são correlacionados entre eventos. A amostra de "hacks grandes" é dominada por chains pequenas, onde isso pesa menos.

**2026-11-08. Resultados da Fase 5 (H4).**
- Amostra: 393 eventos em 48 chains. 336 com preço da moeda nativa e 360 com série de stablecoins.
- Moeda nativa: hacks grandes em relação à chain derrubam a moeda nativa. Com perda de pelo menos 5% do TVL DeFi da chain (n = 27), CAR de -7,5% em [0,+1] e -13,1% em [0,+5] (medianas -3,5% e -5,0%), significativo em t, BMP, bootstrap, Wilcoxon e com erros agrupados por chain e mês (p = 0,003 e 0,001). Some em [0,+30] (p = 0,15). Na faixa de 1% a 5%, não há efeito. Dose-resposta contínua: log(perda/TVL da chain) com coeficiente negativo em [0,+1] (p = 0,04) e [0,+5] (p = 0,01). Em todos os eventos, o efeito é pequeno (-0,8% em [0,+1]) mas significativo mesmo com erros agrupados.
- Stablecoins: resultado contrário à previsão de migração para stablecoins na mesma rede. A oferta de stablecoins na chain cresce menos que o normal depois do hack (-0,6% em [0,+1], -1,3% em [0,+5], -6,3% em [0,+30], medianas menores), significativo com erros agrupados. A leitura é saída de capital da rede, e não fuga para stablecoins dentro dela. Nos hacks grandes (5% ou mais) não há efeito (n = 21). O BMP não rejeita por causa de caudas pesadas.
- Ativos wrapped (4 casos): o oUSDT da Orbit na Klaytn perdeu até 56% da paridade e seguia 46% abaixo no dia +30 (perda de lastro sem reposição). O rsETH da Kelp chegou a -20% no dia +4 e voltou à paridade em cerca de 4 semanas. O ETH da HECO caiu até -12%. A série do madUSDC da Nomad acaba no dia +1 (-2%), provavelmente por deslistagem. Sem inferência, apenas casos.

## Fase 6. Rede de dependências e contágio (H5)

**2026-11-08. Escopo das dependências.** A DefiLlama permite medir três tipos de dependência: fork (`forkedFromIds`), oráculo (`oraclesBreakdown`) e chain. Mesma chain já é tratada no H4. Mesma bridge não tem dado na fonte e fica como limitação. Oráculo compartilhado não identifica dependência relevante: a Chainlink atende 562 protocolos e a Pyth 346, e a maioria dos hacks de oráculo da base manipula preço spot em AMM, não o provedor listado. Por isso oráculo entra só na rede descritiva (Fase 8) e não no teste de contágio. O teste de H5 é contágio por código compartilhado.

**2026-11-08. Especificação do teste de contágio por fork, registrada antes de rodar.**
- Eventos: amostra base com protocolo identificado, categoria lógica de contrato ou oráculo/preço (falhas de código, que é o que um fork compartilha) e data até 07/10/2026 (janela de +30 completa).
- Família de fork da vítima: protocolos de quem ela é fork, forks dela e forks do mesmo pai (vizinhos de até dois passos no grafo de forks). Excluídos: a própria vítima e protocolos do mesmo projeto (`parent_slug` igual), pois versões do mesmo projeto não são dependência técnica externa.
- Expostos: membros da família listados na DefiLlama antes do hack. Controles: mesma categoria DefiLlama da vítima, ao menos uma chain em comum, fora da família, listados antes do hack. Em famílias grandes (clones de Uniswap e Compound), no máximo 25 expostos e 25 controles por evento, escolhidos pela mesma regra nos dois grupos (maior TVL atual), para que o viés de seleção seja simétrico.
- Exclusões: protocolos com hack próprio em [-120,+30] e protocolos com TVL(-1) abaixo de US$ 1 milhão.
- Variável: variação anormal do log do TVL total, Σ[Δln TVL(t) - média de Δln TVL em [-60,-11]], com Δln diário limitado a [-1,+1] e cobertura de 90% na linha de base e completa em [-1,+30]. Usa o TVL total (inclui efeito preço, que na Fase 3 foi de cerca de 2%), porque decompor por token para centenas de protocolos não muda a comparação entre grupos expostos à mesma data.
- Diferenças em diferenças: y = α_evento + β·exposto + γ·log TVL(-1) + ε, com efeitos fixos de evento (compara expostos e controles na mesma data) e erros agrupados por evento. A subtração da linha de base de cada protocolo faz o papel da primeira diferença. Janelas [0,+1], [0,+5], [0,+10] e [0,+30]. Tendências paralelas checadas pela trajetória diária em [-10,+30].

**2026-11-08. Resultados da Fase 6 (H5).**
- Amostra efetiva: 38 hacks com expostos e controles válidos, 382 pares exposto-evento (131 protocolos) e 430 pares controle-evento (184 protocolos).
- Sem contágio específico por código compartilhado. β(exposto) = +0,3 p.p. em [0,+1] (IC 95% de -2,0 a +2,6), +2,0 em [0,+5], +2,5 em [0,+10] e +4,3 em [0,+30] (IC de -7,6 a +16,2), nenhum significativo, igual com winsorização. Os dados descartam uma perda extra de TVL dos forks maior que cerca de 2 p.p. nos dois primeiros dias.
- Tendências paralelas: as trajetórias de expostos e controles coincidem em [-10,0] e seguem juntas depois. Os dois grupos têm deriva negativa de cerca de -25% até +30 que já começa antes do hack no mesmo ritmo. É um deslocamento da linha de base que afeta os dois grupos igualmente, não um efeito do hack, e por isso só a diferença entre grupos é interpretada.
- Leitura: H5 não confirmada no canal de fork. Nos dados, o dano do hack fica na vítima (Fase 3) e, quando o hack é grande em relação à chain, na moeda nativa (Fase 5), mas não se propaga por código copiado.

## Fase 7. Robustez

**2026-11-08. Janelas de crise sistêmica.** Terra/Luna: 07/05/2022 a 31/05/2022. FTX: 06/11/2022 a 30/11/2022. Liquidações de outubro de 2025: 10/10/2025 a 20/10/2025 (dia recorde de cerca de US$ 19 bilhões em 10/10). Liquidações de outubro de 2026: mês inteiro, 01/10/2026 a 31/10/2026, porque não houve um único dia de colapso (cerca de US$ 12,5 bilhões no mês, com pico em 14 e 15/10 segundo a imprensa especializada). Um evento é excluído quando a janela [-1,+30] toca uma crise.

**2026-11-08. Especificação registrada antes de rodar.**
- Placebo de preço: para cada token da amostra de preço, uma data falsa sorteada entre as datas com cobertura completa ([-120,-11] com 90% e [-1,+30] completo), a partir de 2020, sem nenhum hack registrado do mesmo token em [-150,+60] da data falsa. Mesmo modelo de mercado (ETH). 1.000 réplicas com uma data falsa por token. Compara o CAR médio real com a distribuição dos CARs médios placebo.
- Placebo de TVL: mesma lógica para os protocolos da amostra de TVL, com o fluxo anormal bruto (sem somar o roubo, pois não há roubo). 1.000 réplicas.
- Placebo de contágio: datas falsas para os protocolos expostos e de controle da Fase 6, com a variação anormal do log do TVL em [0,+30]. Testa se a deriva de cerca de -25% dos dois grupos é artefato da linha de base. 500 réplicas.
- Variações do H1 (CAR[0,+1] e CAR[0,+30] de preço, fluxo líquido do roubo em [0,+10] e [0,+30]): (a) datas originais da DefiLlama, com cobertura recalculada, (b) sem eventos sobrepostos (mesmo token ou protocolo em [-120,+30]), (c) sem crises, (d) (b) e (c) juntos, (e) perda mínima de US$ 5 milhões e (f) de US$ 10 milhões, (g) média winsorizada em 1% e 99%.
- Benchmarks alternativos (moeda nativa e índice DeFi) e CAR em log-retornos já foram reportados na Fase 3.

**2026-11-08. Resultados da Fase 7.**
- Placebo de preço, CAR[0,+1]: média placebo de +1,1% (95% entre -2,4% e +3,1%) contra -17,4% real. Nenhuma das 1.000 réplicas chega ao valor real (p unilateral < 0,001). Efeito do dia do hack robusto.
- Placebo de preço, CAR[0,+30]: a distribuição placebo da média é muito larga e deslocada para cima (média +9,3%, 95% entre -26% e +82%), porque somar 31 retornos simples de tokens muito voláteis gera caudas pesadas e viés positivo. O CAR médio real (-28%) tem p unilateral de 0,019 e p bilateral de 0,185. Conclusão: os testes paramétricos (t, BMP) superestimavam a significância da média em [0,+30]. Depois de ver isso, acrescentamos ao placebo a mediana do CAR e a média do CAR em log-retornos (não pré-registrados, marcados como tal no arquivo): mediana real -19,2% contra placebo -1,5% (95% entre -7,3% e +4,4%) e log-CAR real -52,7% contra placebo -11,3% (95% entre -29,1% e -1,8%), ambos com p < 0,001. A queda de 30 dias existe, mas a média aritmética não é a estatística adequada para mostrá-la.
- Placebo de TVL: sem hack, o fluxo anormal tem deriva negativa (-2,0% em [0,+10] e -5,7% em [0,+30]), provável reversão à média depois de linhas de base de crescimento. O fluxo líquido do roubo fica abaixo do placebo: excesso de -5,2 p.p. em [0,+10] (p unilateral 0,006) e -10,2 p.p. em [0,+30] (p unilateral 0,011). A estimativa honesta da corrida bancária além do valor roubado é de cerca de 10% do TVL em 30 dias, e não os 16% da Fase 3. A mediana (-9%) fica dentro da faixa placebo da média, então o efeito vem de parte dos protocolos e não de todos.
- Placebo do contágio: cerca de dois terços da queda conjunta de expostos e controles na Fase 6 (-12,2 de -17,7 p.p.) aparecem também em datas sem hack, o que confirma o artefato de linha de base. Sobra um excesso de -5,5 p.p. comum aos dois grupos (p unilateral 0,042, bilateral 0,086): sinal fraco de contágio setorial (mesma categoria e chain), não por fork. O teste de diferenças em diferenças não é afetado.
- Variações da amostra: CAR[0,+1] médio entre -16,3% e -22,9% e fluxo líquido do roubo [0,+30] entre -12,7% e -15,9% em todas as especificações (datas originais da DefiLlama, sem sobreposição, sem crises, as duas exclusões juntas, perda mínima de 5 e 10 milhões, winsorização), com bootstrap e Wilcoxon significativos em todas. O fluxo em [0,+10] perde significância no bootstrap ao excluir crises (p = 0,29), mantendo o Wilcoxon (p = 0,02).

# Cache persistente de feature text no sugeridor de aliases (v0.50.3)

**Concluído em 2026-07-25.** Origem: bug report do usuário — "clico em aprovar ou
dispensar e as sugestões não somem mais depois da ação".

## Diagnóstico (cadeia factual completa)

1. Backend estava CORRETO: aprovações/dispensas persistiam (profile v108, termos
   excluídos do GET) — só a UI não refletia.
2. Rede do browser: o refetch DISPARAVA após cada ação... e ficava pendurado
   (request sem resposta por minutos).
3. Medição do endpoint: `GET alias-suggestions` do *080 = **61,8s** vs 0,66s no
   e2e_v0200 — lentidão por projeto, não deadlock.
4. Causa raiz: `alias_suggester._doc_text` chama `extract_feature_text(path)` —
   **re-extração completa de cada doc resolvido, a cada GET, sem cache**. Design
   pré-existente (v0.37.0) que era tolerável com resolvidos leves; nesse dia o
   **PDF escaneado de 46 páginas** entrou no triage_resolved do projeto (teste
   da aura) e cada GET passou a re-OCRizar 46 páginas (~60s — bate com a
   estimativa medida de 1,3s/página). Não foi regressão do fluxo de aliases.

## Fix

Cache persistente do EXCERPT por **sha256** (identidade de conteúdo, já presente
no meta resolvido — rename não invalida, edição gera sha novo) em
`<projeto>/_PROFILE/feature_text_cache/{sha}.txt`. A linha do nome é recomposta
por chamada (mesmo conteúdo re-resolvido sob outro nome não herda o nome antigo
do cache — teste cobre). Falha de leitura/escrita do cache degrada para
extração ao vivo, nunca derruba a análise. Meta sem sha (testes antigos,
registros legados) segue o caminho sem cache.

## Validações

- Backend 683/683 (2 novos: segunda análise com zero re-extração + cache não
  contamina nome de outro resolvido).
- Medição viva na stack dev: 1ª GET (aquece) 62,5s → **2ª GET 35ms** (1.780×);
  18 arquivos de cache criados.
- E2E do sintoma exato no browser real: aprovar "cartorio" no projeto → linha
  some da lista em ~1s (antes: congelada até reload). Nota: na validação foram
  consumidas 2 sugestões reais com escopo projeto ("escritura publica" e
  "cartorio" — mesma direção que o usuário vinha aprovando; reversível no
  editor de taxonomia).

## Follow-up consciente

`classifier_cycle` (datasets/benchmark) também re-extrai sem cache — são jobs
batch, fora do caminho interativo; avaliar reuso do cache se o ciclo pesar.

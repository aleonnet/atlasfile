# Tier 1 UX — aprendizado por projeto, scoring honesto, reconcile explícito, cookie por instalação (v0.44.0)

**Concluído em 2026-07-24.** Origem: priorização do roadmap por ganho de UX com benchmarks reais
(Paperless-ngx, regras Gmail/Outlook, BM25/Lucene, heurísticas NN/g). Quatro itens executados
na ordem W4 → W3 → W1 → W2.

## W1 — Aliases por projeto (escopo na aprovação)

**Problema**: aprovar alias propagava ao template default e a TODOS os projetos; o usuário
esperava aprendizado local (registrado no E2E de 2026-07-23). Benchmark: Paperless-ngx e regras
de e-mail aprendem por instância/conta — "o que ensino aqui vale aqui".

**Entregue**:
- `POST /api/taxonomy/aliases` com `scope: global|project` (default `global`, compat retro) e
  `project_ref` (obrigatório em `project`, com `enforce_project_scope`).
- `add_project_aliases` (`taxonomy.py`): merge só no profile do projeto; template intacto;
  idempotente; entrada inexistente → 400. Semântica documentada: projetos novos não herdam.
- UI: dois botões por termo — "Aprovar no projeto" (default recomendado) e "Global" — com
  tooltips e toasts distintos; texto de introdução do card atualizado (PT/EN).
- Coerência de graça: a mineração e o filtro de "já existentes" leem o profile do projeto,
  então a sugestão some do projeto que aprendeu e permanece nos demais.

**Testes**: `test_taxonomy.py` +2 (escopo project não toca template nem outro projeto;
validações); `IngestTriageCard.test.tsx` reescrito para os 2 botões + payloads.

## W2 — Scoring: diagnóstico refutou o √N; correção real foi outra

**Item do roadmap dizia**: "score = hits/√N do domínio dilui termos novos". **Fato verificado**:
o √N só existe no caminho de alias de *document_type*; domínio usa pesos lineares
(filename×3, texto×2, entidades×2, doc_type×2) + `0.18 + 0.08·min(score,7) + 0.06·min(margem,3)`.

**Diagnóstico** (novo `backend/scripts/trace_classification.py`, rodado nos arquivos reais do
kit marítimo da instância):
- `notificacao_demurrage_v99.pdf` → `operacoes` 46% com **zero** hits de conteúdo: os 2 pontos
  vinham só do overlap "status report" ∈ `relatorio.aliases` ∩ `operacoes.aliases`. Todo doc
  tipado `relatorio` nascia "operacoes".
- `juridico` score 0 legítimo: os 4 aliases aprovados vieram dos OUTROS docs do kit; o
  vocabulário deste ("demurrage", "sobreestadia") nunca foi aprovado — o sugeridor o rejeitou
  corretamente (support 1 < MIN_SUPPORT 2 entre corrigidos).
- Controle positivo: `lavratura_matricula_4483.docx` → `juridico` 0.92 com 17 pontos de hits
  reais — o aprendizado já funcionava para vocabulário aprendido.

**Correção**: overlap tipo↔domínio é desempate, não evidência primária — só pontua com hit de
conteúdo. Sem evidência: best-effort 0.05 → triagem (honesto), em vez de falsa certeza 46%.

**Validação**: teste novo falha no código antigo e passa no novo (+ controle positivo);
benchmark bootstrap no split de validação (62 docs): **idêntico antes/depois** — domínio 87.1%,
tipo 93.6%, exact 82.3% — zero regressão; `auto_route_min`/`triage_min` mantidos com base em
dados (a distribuição de scores com evidência não mudou).

## W3 — Escopo do reconcile explícito

**Fato verificado**: `POST /api/reconcile/{id}` roda `cleanup_orphans=False`; `POST
/api/reconcile` (todos) roda a limpeza global. O botão era idêntico nos dois modos.

**Entregue**: label dinâmico "Reconciliar INDEX — {{projeto}}" / "— todos os projetos" +
tooltips explicando a diferença (PT/EN). Testes no `App.test.tsx` (2 casos, independentes de
ordem — o mock compartilhado do reconcile é resetado explicitamente).

## W4 — Cookie password do Dashboards por instalação

**Problema** (diagnóstico de campo 2026-07-23): a chave default de encriptação do cookie é
igual entre instâncias — cookie de instalação anterior decripta mas a sessão não existe → 500.

**Mecanismo verificado na imagem 2.17.1**: a allowlist de env do entrypoint NÃO cobre
`opensearch_security.*`; o entrypoint repassa argumentos CLI ao binário (prefixa
`opensearch-dashboards` quando o 1º arg começa com `-`). Logo:
- `docker-compose.yml`: `command: ["--opensearch_security.cookie.password=${DASHBOARDS_COOKIE_PASSWORD:?...}"]`.
- `install.sh`: gera 48 chars só quando ausente/placeholder (re-run não desloga ninguém).
- `make docker-up`/`docker-update`: guard `ensure-dashboards-cookie` para upgrade via git pull.
- `.env.example` documentada; INSTALL.md com nota de upgrade.

**Validação**: flag verificada dentro do container (`docker inspect` Args) e boot sem erro de
cookie; `bash -n` + suite do instalador verdes. **Pendente usuário**: E2E vivo do replay de
cookie velho (bloqueado no ambiente da sessão — senha do volume dev divergente do `.env` e
permissões de container; roteiro no fechamento do ciclo).

## Fora de escopo (mantidos no roadmap)

Órfão físico em `_TRIAGE_REVIEW/pending`; alerting/heatmap/reporting do Dashboards; blackhole
como indicador de contexto; cortes do sugeridor (MIN_SUPPORT etc. — comportamento correto no
caso analisado).

## Validações do ciclo

`make test` completo verde (backend 645, frontend 239 em 32 arquivos, installer com shellcheck);
`tsc --noEmit` limpo; benchmark antes/depois idêntico; trace real nos 2 documentos do kit.

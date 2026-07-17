# Plano: RAG Híbrido + Permissões Mínimas + UI v2 "Mind-Blowing" (AtlasFile)

**Nome único do plano:** `rag_hibrido_permissoes_ui_v2`
**Branch:** `feature/rag-hibrido-ui-v2` (criar a partir de `main`)
**Execução:** sessão limpa (após `/clear`) — este plano é autocontido.

---

## Contexto

### Por quê
A expectativa do produto AtlasFile: documento via drag'n'drop → inbox do projeto → classificação **leve** → ingestão RAG com busca **híbrida** (literal + lexical + semântica) + fuzzy + filtros de metadados **e permissões** + reranking, exposta via MCP tools para o LLM responder sobre documentos. E uma UI "to blow people's mind" — nível "como ele conseguiu fazer isso?" — com logo animado reescrito em WebGL.

### Estado atual (verificado no código, 2026-07-16)
- **Classificação**: 4 modos (`bootstrap`, `sparse_logreg`, `setfit`, `llm`). O `setfit` perde do `sparse_logreg` no benchmark (domain 38,7%), **nunca é servido em ingestão por padrão** (llm também é benchmark-only), e é o único usuário de torch/transformers/setfit/sentence-transformers (~545 MB no venv; potencialmente 1,5-2,5 GB na imagem Docker com wheels CUDA). → **Remover setfit.**
- **Busca**: `GET /api/search` (backend/app/main.py:3031) já faz BM25 `bool.should` com `multi_match` fuzzy (`fuzziness: AUTO`), `match_phrase` literais com boost alto, query `nested` sobre `content_chunks` (chunking existe: document_extractor.py:36, 1200 chars/overlap 150), filtros `bool.filter` (project_id, business_domain, tags, document_type, doc_kind, datas) e re-sort heurístico Python (`_search_hit_sort_key`, main.py:568). **Não existe**: embeddings/k-NN, fusão híbrida, rerank por modelo, auth/ACL (zero auth; só CORS).
- **MCP/chat**: tools em backend/app/mcp/server.py (`search_documents`:49, `get_document_chunks`:104 etc.); orchestrator (backend/app/orchestrator.py:184, OpenAI+Anthropic) injeta `project_id` em tools project-scoped; chamado por `POST /api/chat` (main.py:1922).
- **Upload por projeto já funciona**: `POST /api/ingest/upload/{project_id}` (main.py:1549) → `_INBOX_DROP` do projeto → ingestion.py:286.
- **Frontend**: App.tsx god-component (1.366 linhas, ~40 useState, PainelView recebe 24 props), sem router; styles.css 2.384 linhas + 8 CSS globais (~5.500 linhas em namespace global compartilhado — alterar `.card`/`.btn` numa tela pode quebrar outra silenciosamente); tokens parciais em `:root` (cores/radius/shadow/easing; **falta** escala `--space-*` e tipográfica); 82 inline styles, 50 hex hardcoded em .tsx; navegação = 3 abas topbar + sub-abas pill + `<select>` de projeto; feedback de erro via footer `.status`; estados loading/empty/erro inconsistentes. Identidade existente boa: accent laranja `#ff5a36`, dark profundo `#0e0d10`, fontes DM Sans (display) + Fragment Mono (body/mono), tema dark/light via `data-theme`.
- **Orb atual** (CompanionOrb.tsx, 315 linhas): SVG 40px com órbitas keplerianas reais (Newton-Raphson), aurora, cometas, estados idle/thinking/success/error/alive, respeita `prefers-reduced-motion`. SVG tem teto de realismo → **reescrever em WebGL com fallback para este SVG**.
- **Infra**: OpenSearch **2.17.1** (docker-compose.yml:3) — tem k-NN e hybrid query, mas **RRF nativo só em ≥2.19** → fusão RRF manual em Python. `ATLASFILE_API_TOKEN` já é injetado no serviço `mcp` e `backend/app/mcp/api_client.py` já envia `Authorization: Bearer` — o backend só não valida ainda.
- **Custos LLM**: app/usage_costs.py + config/usage_costs.json ($/1M por provider/model); padrão de gravação em índices `atlasfile_classification_usage`/`atlasfile_training_usage`.

### Decisões fechadas pelo usuário (não reabrir)
1. **Embeddings**: provider configurável — OpenAI `text-embedding-3-small` default + local leve (fastembed/ONNX, sem torch) opcional. Custos no usage_costs.
2. **Permissões**: fundação mínima — API key + enforcement de escopo por projeto (API e MCP). Sem usuários/RBAC.
3. **UI**: **shadcn/ui + Tailwind CSS** com tema 100% customizado desde o dia 1 (nunca o default cinza). Motivos: estilo co-localizado elimina o risco de regressão do CSS global ao iterar; primitivas Radix (Dialog/Popover/Toast/Tabs com a11y resolvida) e `cmdk` (command palette padrão Linear/Vercel) liberam esforço para a camada que impressiona. Migração gradual tela a tela; CSS legado convive até o fim da Fase 6.
4. **Navegação**: sidebar colapsável + command palette (Cmd+K). Sem react-router (hash sync barato).
5. **Logo**: **orb novo em WebGL** (salto de realismo estilo Siri/Apple Intelligence), com fallback para o SVG atual (WebGL indisponível / `prefers-reduced-motion`).
6. **Direção de arte**: carta branca do usuário ("me surpreenda, o melhor do melhor"). A direção especificada na Fase 6 é vinculante para a execução não se perder em vagueza.

### Regra de execução (pedido explícito do usuário)
- **A arte é feita diretamente pelo modelo principal (Fable 5), sem delegar a subagentes**: direção de arte, tema shadcn custom, motion design (Framer Motion), shader do orb WebGL e wordmark — tudo das Fases 5.2, 6 e 7 que define o visual é trabalho da sessão principal. Subagentes apenas para trabalho mecânico (substituição de fetches pelo wrapper, ajustes repetitivos de testes, varreduras de inline styles/hex).

### Regras do projeto (CLAUDE.md)
- Commits sem trailers de ferramenta. Nunca commitar sem instrução explícita do usuário.
- Skill `safe-exec` antes de qualquer Bash.
- Ao concluir: salvar plano em `docs/planos_concluidos/rag_hibrido_permissoes_ui_v2.plan.md`, atualizar `docs/planos_concluidos/README.md`, bump SemVer em `frontend/package.json`+lock, atualizar `CHANGELOG.md`, revisar `README.md`/`INSTALL.md`, staging + proposta de commit.
- Testes: `make test` (backend pytest + frontend vitest); `make docker-update` para smoke da stack.

---

## Fases (1 branch, commits por fase, `make test` verde antes de cada commit)

Ordem de dependência: 1 → 2 → 3; 4 independente; 5 → 6 → 7.

### Fase 1 — Remoção do setfit
**Objetivo:** eliminar modo `setfit` e ~545 MB de deps, mantendo `bootstrap`/`sparse_logreg`/`llm`.

Backend:
- `classifier_registry.py`: `SUPPORTED_CLASSIFIER_MODES = ("bootstrap", "sparse_logreg", "llm")` (linha 13); remover branch setfit em `classifier_model_path` (:184-186). **Saneamento na carga do `_ATLASFILE/classifier/registry.json`**: antes da validação Pydantic, filtrar entradas `setfit` e rebaixar `champion_mode: "setfit"` → `sparse_logreg` (se houver artifact) ou `bootstrap`, com warning. Sem isso, registries persistidos quebram na validação.
- `classifier_runtime.py`: remover import (:13) e branches (:73-74, :87-98).
- `classifier_cycle.py`: remover imports (:21-28), `benchmark_setfit_candidate` (:757-870), `setfit_enabled` (:933) e chamadas na orquestração (~:1000+).
- Deletar `backend/app/classifier_setfit.py` e `backend/tests/unit/test_classifier_setfit.py`.
- `scripts/run_classifier_cycle.py:56`: remover setfit do help.
- `requirements.txt`: remover linhas 23-25 (`setfit`, `sentence-transformers`, `transformers`). **Manter** `scikit-learn` (sparse_logreg).
- Ajustar testes: `test_classifier_runtime.py:58-72`, `test_classifier_registry.py:50-59,69-74`, `test_classifier_cycle.py:69-105`. Novo teste: registry com setfit é saneado sem erro.

Frontend: `src/types.ts:470` (tipo), `src/features/ingest/IngestTriageCard.tsx:65-66,747-748,816` (labels/listas).
Docs: `CLAUDE.md:108`, `README.md` (menções). Histórico em docs/planos_concluidos/ fica intocado.

**Validação:** `make test`; `make docker-build` (imagem encolhe); ciclo de classificação com registry antigo contendo setfit (teste unitário). Não deletar `_ATLASFILE/classifier/models/setfit/` (dado do usuário; apenas ignorar).

### Fase 2 — Camada semântica: embeddings + índice de vetores
**Decisão de arquitetura:** **NÃO** adicionar `knn_vector` ao índice principal (`index.knn` é setting estático → exigiria reindex; k-NN nested é limitado no 2.17; granularidade RAG é o chunk). **Criar índice separado `atlasfile_chunk_vectors`** (1 doc por chunk, flat):
- Campos: `doc_id`, `project_id`, `business_domain`, `document_type`, `doc_kind`, `tags`, `ingested_at`, `location`, `chunk_index`, `text`, `sha256`, `embedding_provider`, `embedding_model`, `embedding` (`knn_vector`, dimension do provider, hnsw/cosinesimil/engine **lucene** — suporta filtered k-NN eficiente no 2.17).
- Vantagens: zero reindex do índice principal; filtros duplicados no chunk permitem k-NN com `filter`; re-embed = recriar só este índice.

Mudanças:
1. **Novo `backend/app/embeddings.py`**: protocol `EmbeddingProvider` (`embed_texts`, `embed_query`, `provider_name`, `model_name`, `dimension`); `OpenAIEmbeddingProvider` (default `text-embedding-3-small`, dim 1536, batch ~100, cliente `openai` já existente, captura `usage.total_tokens`); `FastEmbedProvider` opcional (lazy import, modelo `intfloat/multilingual-e5-small` dim 384 — corpus pt-BR; prefixos "query: "/"passage: "); factory `get_embedding_provider()` por settings.
2. `requirements.txt`: **não** adicionar fastembed no principal — criar `backend/requirements-local-embeddings.txt`; lazy import com erro claro.
3. `config.py`: `embedding_enabled=True`, `embedding_provider="openai"`, `embedding_model`, `embedding_dimension=1536`, `embedding_batch_size=100`, `opensearch_chunk_vectors_index="atlasfile_chunk_vectors"`.
4. `opensearch_client.py`: `ensure_chunk_vectors_index(client)` com `_meta` (provider/model/dimension); se `_meta` divergir das settings → log de alerta instruindo re-embed (não recriar automaticamente).
5. `indexer.py`: `index_document_chunks_embeddings(client, payload, provider)` — delete-by-doc_id + bulk dos chunks com embeddings; skip incremental por sha256+model; **falha de embedding não quebra ingestão** (try/except + log + flag no doc).
6. `reconcile.py` (`rebuild_search_index`:400, `sync_search_index_for_project`:514): backfill de embeddings; limpeza de órfãos também no índice de vetores.
7. **Novo `backend/scripts/backfill_embeddings.py`**: scroll no índice principal, embeda `content_chunks`, indexa; idempotente (sha256+model); flags `--project`, `--force`. Esta é a migração do corpus existente.
8. **Custos**: `config/usage_costs.json` + `"text-embedding-3-small": {"input": 0.02, "output": 0}`; gravar uso no padrão existente (`training_usage`) com `script_name: "embeddings_ingest"|"embeddings_backfill"|"embeddings_query"` (validar assinatura do recorder na implementação). fastembed → custo 0, registrar contagem mesmo assim.

**Testes:** unit embeddings.py (mock OpenAI, factory, fastembed ausente), ensure_chunk_vectors_index, indexer com embedding mockado (falha não quebra), custo em test_usage_costs.
**Validação manual:** `make docker-update`; upload de PDF; `GET atlasfile_chunk_vectors/_count`; backfill do corpus; custos no UsageView.
**Riscos:** troca de provider/dimension exige recriar índice (documentar); rate limit no backfill (batch + retry/backoff).

### Fase 3 — Busca híbrida (BM25 + kNN) + rerank
**Decisão de fusão:** **RRF manual em Python** (OpenSearch 2.17 sem RRF nativo; `hybrid query` não convive com a query BM25 atual com inner_hits/highlights e os índices são distintos). Duas buscas paralelas + fusão preserva o pipeline atual de evidências.

Mudanças:
1. **Novo `backend/app/search_hybrid.py`**:
   - `semantic_search(query, filters, k=50)`: embed da query + `knn` no `atlasfile_chunk_vectors` com `filter` (mesmos filtros da busca atual); agrega por `doc_id` (max score) e guarda top chunks (evidências semânticas).
   - `rrf_fuse(bm25_ranked_ids, knn_ranked_ids, k=60)`: `score = Σ 1/(k + rank)`.
2. `main.py` `GET /api/search`: param `mode = "hybrid"|"lexical"|"semantic"` (default hybrid). Hybrid: BM25 atual (size ~50) + semantic → RRF → reordena e anexa docs achados só via kNN (`mget` no índice principal; evidências com `match_type: "semantic"`); paginação após fusão. `_search_hit_sort_key` vira tie-breaker. **Fallback degrade silencioso para lexical** se embedding indisponível + campo `search_mode_effective` na resposta.
3. **Rerank (ajustado 2026-07-16, aprovado pelo usuário após verificação SOTA):** heurístico atual como default + **cross-encoder ONNX opcional via fastembed** (`search_rerank_enabled=False`, `search_rerank_model` configurável, multilíngue para pt-BR): rerank do top-20 fundido usando `TextCrossEncoder` do fastembed (mesma dependência opcional da Fase 2, sem torch, custo zero de API). Rerank LLM listwise descartado (custo/latência piores que cross-encoder segundo literatura 2025-2026). Lazy import com erro claro se fastembed ausente.
3b. **Golden set de retrieval (novo, aprovado 2026-07-16):** `backend/scripts/benchmark_retrieval.py` — mede Recall@5/MRR/NDCG@10 em `lexical` vs `hybrid` vs `hybrid+rerank` contra um golden set de queries pt-BR (`_ATLASFILE/retrieval_golden_set.jsonl`, fora do git; template versionado em `config/retrieval_golden_set.example.jsonl`). Decisões de k do RRF/top-N do rerank passam a ser validáveis com dados do corpus real.
4. `models.py` SearchResponse: `search_mode_effective`, `match_type` por evidência (aditivo).
5. MCP `server.py`: `search_documents` ganha `mode` (default hybrid) + docstring; **nova tool `semantic_search_chunks(query, project_id, k)`** retornando chunks crus com `location` para RAG com citações.
6. `config.py`: `search_hybrid_enabled=True`, `search_knn_k=50`, `search_rrf_rank_constant=60`, `search_rerank_llm_enabled/model`.
7. Frontend mínimo: badge "semântico" nas evidências `match_type: "semantic"` (UI completa na Fase 6).

**Testes:** rrf_fuse determinístico; fallback com braço semântico vazio; mock semantic_search; MCP tool com mode; snapshot da query knn com filtros; testes atuais de search continuam verdes.
**Validação manual:** query parafraseada ("contrato de aluguel" acha doc que diz "locação"); comparar `mode=lexical` vs `hybrid`; latência (embed ~50-100ms + knn ~10ms).
**Riscos:** paginação pós-fusão (fundir top-N fixo, documentar); consistência de metadados nos chunks quando tags/metadata mudam → hook em `set_metadata`/`apply_tags` ou eventual consistency até reconcile (decidir na implementação e documentar); docs sem embedding aparecem só no braço lexical (aceitável).

### Fase 4 — Permissões mínimas: API key + escopo de projeto
1. `config.py`: `api_auth_enabled=False` (default off = backward compat), `api_keys_config_path`. Formato `config/api_keys.json` (real fora do git; versionar `api_keys.example.json`):
   `{"keys": [{"key": "atlas_sk_...", "name": "mcp-server", "projects": ["*"]}, {"key": "...", "name": "cliente-x", "projects": ["projeto-a"]}]}`
2. **Novo `backend/app/auth.py`**: dependency `require_auth` — `Authorization: Bearer` ou `X-API-Key`; off → escopo `["*"]`; `secrets.compare_digest`; retorna `AuthContext(name, allowed_projects)`.
3. Dependency **global** do app (exceto `/health` e preflight CORS). Helper `enforce_project_scope(auth, project_id)` → 403; listagens sem project_id filtram por `allowed_projects` (search: `terms` no bool.filter; `/api/projects`: filtra lista).
4. MCP: `api_client.py` já envia Bearer; compose já injeta `ATLASFILE_API_TOKEN` no serviço `mcp`. Adicionar `API_AUTH_ENABLED` + montar `api_keys.json` no serviço `api`. Porta 8001 permanece interna (documentar risco).
5. Frontend: wrapper `apiFetch` em `src/api.ts` injetando key de `localStorage("atlasfile_api_key")`; substituir fetches diretos (~60, mecânico); campo de API key em ConfigView; 401/403 → toast.
6. `docker-compose.yml`, `.env.example`, `INSTALL.md`.

**Testes:** auth unit (off passa; on sem key 401; key errada 401; escopo 403; wildcard); search com escopo; extensão de test_mcp_client (header); wrapper frontend.
**Riscos:** endpoint esquecido sem enforcement (mitigar: dependency global + grep `project_id` nos handlers no PR); watcher/reconcile são internos (sem HTTP, sem impacto).

### Fase 5 — UI Foundation: Tailwind + shadcn + tema custom + quebra do App.tsx
**Objetivo:** fundação técnica e de tema. Sem redesign visual ainda — as telas continuam funcionando com o CSS legado enquanto a base entra.

1. **Setup Tailwind + shadcn**: instalar Tailwind (com `corePlugins.preflight` avaliado/ajustado para não quebrar o CSS global legado durante a convivência — se necessário, preflight escopado), `components.json` do shadcn, `class` dark mode integrado ao mecanismo `data-theme` existente.
2. **Tema custom desde o dia 1** (`src/styles/theme.css` + `tailwind.config`): mapear a identidade existente para os tokens shadcn — accent `#ff5a36` (+ `--accent-light/soft/purple`), superfícies dark (`#0e0d10`/`#171519`), borda `#2a2630`, `--danger/--ok`, radius/shadows/easings atuais; fontes DM Sans/Fragment Mono; escala de spacing/tipografia via Tailwind (resolve a ausência de `--space-*`); paleta de gráficos `--chart-1..8` na marca (mata os hex do UsageView/recharts). **Proibido** o tema default do shadcn aparecer em qualquer tela.
3. **Componentes shadcn a adotar** (copy-in, customizados): Button, Card, Dialog, DropdownMenu, Popover, Tooltip, Tabs, Input/Select/Textarea, Toast (sonner ou radix-toast), Command (`cmdk`), Skeleton, Badge, Separator, ScrollArea. + próprios: `EmptyState`, `ErrorState` (retry) sobre os mesmos tokens.
4. **Quebra do App.tsx**: `contexts/ProjectContext` (mata prop-drilling — PainelView recebe 24 props hoje), `contexts/SettingsContext` (tema + API key da Fase 4), `hooks/useSearch`, `useDocuments`, `useChatSession`; App.tsx vira providers + shell + switch. Sem react-router: `NavigationContext` com sync de `location.hash` (deep-link barato).
5. Migrar 1 tela piloto (ConfigView, a mais simples) para Tailwind+shadcn como prova do tema.

**Testes:** vitest dos componentes ui custom e do render das primitivas temadas; `renderWithProviders` para adaptar testes existentes; build Vite ok (tamanho de bundle monitorado).
**Riscos:** preflight do Tailwind vs CSS legado (mitigar: avaliar preflight escopado/desligado até Fase 6 concluir); dois sistemas de estilo convivendo é dívida temporária — encerra na Fase 6.

### Fase 6 — UI Reformulação "mind-blowing": sidebar, palette, telas, upload
**Direção de arte (vinculante):** *"instrumento de precisão vivo"* — o rigor espacial do **Linear** + a materialidade do **Arc/Raycast** + luz viva própria (o orb como fonte de luz da interface). Concretamente:
- **Superfície**: dark profundo em camadas com elevação real (não bordas cinzas: luz). Painéis com micro-gradiente radial sutilíssimo respondendo à posição do orb/estado do sistema; grain/noise a 1-2% de opacidade para matar o "flat plástico"; glass (backdrop-blur) apenas em overlays (palette, modais, drop overlay) — nunca em superfícies de trabalho.
- **Luz laranja como linguagem de estado**: o accent `#ff5a36` não é decoração — é semântica de "vida": glow no que está ativo/processando (documento sendo ingerido pulsa; citação referenciada no chat acende; resultado semântico tem aura levemente distinta do lexical). Em light mode a mesma linguagem com sombras coloridas suaves.
- **Motion coreografado** (Framer Motion, única dependência de animação): entradas com stagger de 20-40ms por item; transições de rota com continuidade espacial (o card clicado expande, não "pisca tela nova"); springs físicos em micro-interações (hover elástico sutil, press com escala 0.98); números que contam (stats do painel); tudo com `prefers-reduced-motion` matando animação não-essencial.
- **Tipografia com hierarquia dramática**: DM Sans display em pesos altos e tamanhos generosos para títulos de seção; Fragment Mono para metadados/paths/hashes (identidade técnica); nunca mais 7 tamanhos mágicos.
- **Detalhes "impossíveis"** (o que faz alguém perguntar "como?"): cursor-glow sutil nos cards do painel (radial gradient seguindo o mouse via CSS vars); bordas com gradiente animado no elemento em foco do palette; o overlay global de drop escurece a UI e projeta um "portal" com o nome do projeto e partículas convergindo ao centro; skeleton com shimmer na direção de leitura.

Mockups:

**AS-IS:**
```
┌────────────────────────────────────────────────────────────┐
│ ◉ AtlasFile   [Painel][Assistente][Config]  [projeto ▾] ☾ │  ← topbar 64px
├────────────────────────────────────────────────────────────┤
│  (view única com cards empilhados; sub-abas pill dentro)   │
│  [Painel de controle] [UploadZone] [Scan] [Triage] [Hist.] │
├────────────────────────────────────────────────────────────┤
│ status: "Falha ao reconciliar índice..." (footer textual)  │
└────────────────────────────────────────────────────────────┘
```

**TO-BE:**
```
┌──────────┬─────────────────────────────────────────────────┐
│ ◉≈Atlas  │  Seção / breadcrumb                   ⌘K  ☾ ○  │
│ ┌──────┐ │ ┌─────────────────────────────────────────────┐ │
│ │Proj ▾│ │ │  Grid de cards com elevação/luz; tiles de   │ │
│ └──────┘ │ │  busca com aura lexical/semântica; chat com │ │
│ ▸ Painel │ │  citações que acendem → abrem doc no chunk  │ │
│ ▸ Docs   │ │                                             │ │
│ ▸ Assist.│ │  EmptyState/ErrorState/Skeleton unificados  │ │
│ ▸ Config │ └─────────────────────────────────────────────┘ │
│ ⟨ colaps.│  toasts (sonner); footer de status morre        │
└──────────┴─────────────────────────────────────────────────┘
  + drop global: UI escurece, "portal" com nome do projeto,
    partículas convergindo; fila com progresso por arquivo
  + ⌘K (cmdk): navegar, trocar projeto, tema, upload,
    pular para documento via /api/search/suggest
```

Entregas (3 commits):
1. **Shell**: `layouts/Sidebar.tsx` (seções Painel/Documentos/Assistente/Config, colapso persistido com animação spring, project switcher rico no topo — avatar/cor por projeto, contagem, busca inline — substitui o `<select>`), CommandPalette com `cmdk` (absorve `layouts/SearchModal.tsx`), Topbar reduzida a breadcrumb + ações. Framer Motion entra aqui.
2. **Telas**: redesign com shadcn temado — PainelView (grid de stats com números animados), resultados de busca (tiles com aura por match_type, filtros como chips), ChatPanel (citações clicáveis → doc na location), UsageView (`--chart-*`), triagem. Quebrar IngestTriageCard (1.014 linhas) em subcomponentes conforme tocado. Estados unificados (EmptyState/ErrorState/Skeleton/toasts; footer `.status` morre). Remoção progressiva do CSS legado por tela migrada.
3. **Upload**: drop **global** (overlay "portal" com projeto; sem projeto selecionado, o palette pede), fila com progresso por arquivo (XHR progress), preview por doc_kind, estado por item (enviando/classificando/erro) via ingest history.

**Testes:** Sidebar (colapso/seleção), CommandPalette (filtro/teclado), UploadZone (fila), smoke por tela migrada.
**Validação:** navegação 100% por teclado; tema dark/light; `prefers-reduced-motion`; ao final, `styles.css` legado reduzido a resíduo mínimo ou removido.
**Riscos:** fase grande — os 3 commits são checkpoints; Topbar antiga convive até o commit 1 estabilizar; bundle (Framer Motion ~30kb gzip — aceitável, monitorar no build).

### Fase 7 — Orb WebGL: o logo "impossível"
**Objetivo:** reescrever o orb como esfera viva em WebGL — nível Siri/Apple Intelligence — mantendo o SVG atual como fallback integral.

1. **Novo `components/OrbGL/`** — WebGL cru (sem three.js: um quad + fragment shader é suficiente e evita ~150kb de dependência; decisão validável na implementação — se a complexidade explodir, three.js é aceitável):
   - Fragment shader: esfera com **FBM noise 3D animado** (aurora fluida interna em 2-3 camadas de cor — laranja/coral/púrpura dos tokens), **fresnel rim light** (borda luminosa), refração fake do fundo, **bloom/glow volumétrico** (blur multi-pass ou glow analítico no shader), leve dispersão cromática na borda.
   - **Estados dirigem uniforms** (não trocam shader): `idle` (fluxo lento, respiração), `thinking` (turbulência acelerada + pulso), `ingesting` (novo estado — partículas espiralando para dentro), `success` (flash quente expandindo), `error` (shake + vermelho), `alive` (cometas — portar do SVG).
   - **Portar a mecânica kepleriana**: as duas luas (Newton-Raphson já implementado em CompanionOrb.tsx:118-177) viram pontos de luz orbitando a esfera no shader/overlay — a assinatura matemática do orb sobrevive à reescrita.
   - Tamanhos: 24px (sidebar colapsada) → 48px (sidebar) → 160px+ (hero no boot/onboarding, com wordmark).
2. **Fallback e acessibilidade**: sem WebGL ou com `prefers-reduced-motion` → renderiza o CompanionOrb SVG atual (mantido no repo); detecção via `canvas.getContext("webgl2")`; pausar render loop quando aba oculta (`visibilitychange`) e quando fora do viewport (IntersectionObserver) — zero GPU idle.
3. **Wordmark animado** "AtlasFile": SVG stroke draw-on no boot (uma vez, ~800ms), micro-interação no hover; compõe com o orb no hero e na sidebar expandida.
4. **Integração de estados reais** via `useCompanionState` estendido: `thinking` no streaming do chat, `ingesting` na fila de upload/ingest ativo, `success/error` nas conclusões.

**Testes:** mapeamento estado→uniforms (lógica pura testável), fallback sem WebGL (mock), pausa por visibilidade; validação visual manual em dark/light e nos 3 tamanhos.
**Riscos:** performance em GPU fraca (mitigar: resolução do canvas capada a 2x, FPS cap 60/30 adaptativo, kill-switch para o fallback SVG via setting); shader dev é iterativo — validar visual cedo com o usuário antes de polir.

---

## Verificação end-to-end (ao final)
1. `make test` (pytest + vitest) verde.
2. `make docker-update` — stack sobe, smoke ok, imagem backend menor (sem torch).
3. Fluxo completo: drag'n'drop global de um PDF → overlay portal → inbox do projeto → classificado (bootstrap/sparse_logreg) → indexado + embeddings no `atlasfile_chunk_vectors`.
4. Busca: `mode=lexical` vs `hybrid` com query parafraseada; aura semântica nas evidências; fallback com `embedding_enabled=false`.
5. Chat: pergunta sobre conteúdo de doc → orchestrator usa `search_documents`/`semantic_search_chunks` → resposta com citações clicáveis abrindo o chunk.
6. Auth: `api_auth_enabled=true` → curl sem key 401, com key 200, escopo de projeto 403; MCP funcionando via `ATLASFILE_API_TOKEN`.
7. UI: navegação completa por teclado, Cmd+K, tema dark/light, `prefers-reduced-motion`, orb WebGL com fallback SVG verificado (desabilitar WebGL no browser).
8. Custos: embeddings e rerank aparecendo no UsageView.

## Checklist de conclusão (CLAUDE.md)
1. Salvar este plano em `docs/planos_concluidos/rag_hibrido_permissoes_ui_v2.plan.md`.
2. Atualizar `docs/planos_concluidos/README.md`.
3. Bump SemVer **minor por fase concluída** em `frontend/package.json`+lock (Fase 1 → 0.14.0; … Fase 7 → 0.20.0), com `CHANGELOG.md` por versão.
4. Revisar `README.md` e `INSTALL.md` (embeddings, auth, novos envs, requirements-local-embeddings, Tailwind/shadcn no build).
5. Staging + proposta de commit por fase (sem trailers; commit só com autorização explícita do usuário).

## Riscos globais
- **Reindex evitado por design** (índice de vetores separado + put_mapping aditivo). Únicas migrações: backfill de embeddings (script idempotente) e saneamento do registry.json.
- OpenSearch 2.17.1 sem RRF nativo — `search_hybrid.py` isola o ponto de troca se subir para ≥2.19.
- Fases 2-3 introduzem chamadas OpenAI novas (embeddings, rerank opcional) — todas rastreadas em usage_costs.
- Convivência Tailwind/shadcn + CSS legado (Fases 5-6): preflight controlado, remoção progressiva por tela, encerra na Fase 6.
- Fase 6/7 têm forte componente visual — **checkpoints de validação visual com o usuário** antes de polir (especialmente o shader do orb).

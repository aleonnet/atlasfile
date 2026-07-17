# Changelog

Todas as mudanças relevantes do AtlasFile são documentadas neste arquivo.

---

## Não versionado — Ferramental

### PoC: MarkItDown vs Extrator AtlasFile (`extractor-benchmark_mdxaf`)

- **Nova pasta de benchmark** comparando MarkItDown (vanilla) vs o extrator de produção do AtlasFile, lado a lado, sobre 6 contratos reais (PDF/DOCX/XLSX/PPTX)
- **Comparação determinística** (sem LLM-judge, sem custo de API): métricas objetivas (tamanho, linhas de tabela markdown, densidade numérica, latência, memória) + outputs lado a lado para inspeção humana
- **Achado principal**: extrator do AtlasFile superior em PDF nativo (preserva espaçamento; MarkItDown mangla) e escaneado (OCR; MarkItDown sai vazio após ~24 min). MarkItDown só agrega como gerador de Markdown estruturado de Office
- **Não toca** backend, frontend nem o `extractor-benchmark/` existente. `corpus/` e `results/` fora do git (contratos sensíveis). Detalhes em `extractor-benchmark_mdxaf/ACHADOS.md`

---

## [0.22.0] -- 2026-07-17

### UI de conflitos de rótulo + criação governada de taxonomia

- **Card "Conflitos de rótulo"** no Painel (junto à Triagem): pendências da reconciliação com fontes divergentes em chips, proposta do LLM em painel púrpura (confiança + justificativa) e arbitragem em um clique — Aceitar proposta ou Corrigir (fontes/proposta/personalizado). Endpoints `GET /api/classifier/label-conflicts` e `POST .../{sha}/resolve`; a resolução propaga o canônico por SHA às fontes (validation/training, nota `reconciled:ui`) e derivados (corpus/splits), com proveniência `human`/`human_confirmed_llm`
- **Criação governada de taxonomia** (`app/taxonomy.py` + `POST /api/taxonomy/create` + `GET /api/taxonomy`): quando a sugestão aprovada usa um `document_type`/`business_domain` inexistente, a UI avisa ("usa taxonomia nova") e oferece **"Criar no template e aplicar"** — diálogo com label/aliases editáveis; a criação atualiza o template `default` (persistido em `_ATLASFILE/templates/`, com proveniência no `template_meta`) e propaga aos profiles de todos os projetos. **Só aprovação humana cria** (chave `outro` bloqueada). Efeito imediato: `bootstrap` e `llm` leem a taxonomia em runtime — o tipo novo com aliases classifica na próxima ingestão; `sparse_logreg` aprende no ciclo seguinte
- Rehome aplicado: 20/20 arquivos dos projetos realinhados ao canônico (dataset ↔ filesystem sem descasamento); reconcile preserva resoluções prévias em re-execuções
- Testes: 495 backend (+8) e 140 frontend (+5)

---

## [0.21.0] -- 2026-07-17

### Instalador one-liner + reconciliação de rótulos por consenso

- **`install.sh`** — instalação em um comando (`curl -fsSL .../install.sh | bash`): verifica pré-requisitos (Docker/Compose v2/git, daemon, portas), clona/atualiza em `~/AtlasFile`, cria `.env` perguntando só a pasta de projetos, sobe a stack, aguarda `/health` e abre a UI — o onboarding guia o primeiro projeto. Idempotente; flags `--dir/--projects-root/--yes/--no-open`. **`install.ps1`** (Windows) verifica WSL2 + Docker Desktop e delega ao instalador Linux dentro do WSL. Seção "Instalação rápida" no README e INSTALL
- **`backend/scripts/reconcile_labels.py`** — reconciliação de rótulos por SHA256 com proveniência: agrupa training_pool + validation_set + árvores `02_AREAS` dos projetos (observacional), detecta conflitos (antes resolvidos silenciosamente por "último ganha"), resolve por unanimidade (`consensus`), LLM forte como **proponente** com justificativa (`llm_consensus` quando concorda com uma fonte; default `gpt-5.1`) e arbitragem humana só no resíduo (`label_conflicts_report.md` editável + `--apply`); `--rehome-projects` (dry-run) e `--rehome-apply` realinham os arquivos dos projetos ao canônico via API de move
- **Guardrail permanente**: `compute_dataset_integrity` agora reporta `label_conflicts` (divergência de rótulo por SHA) como warning no relatório do ciclo
- Execução real: 24 SHAs, 9 conflitos detectados — 4 resolvidos por consenso-LLM, 4 pendentes de arbitragem, 1 por fonte autoritativa única
- Primeiro push do repositório para `github.com/aleonnet/atlasfile`
- Testes: +8 unit (núcleo de consenso + guardrail) — 487 backend

---

## [0.20.0] -- 2026-07-17

### Orb WebGL: o logo vivo (Fase 7 do plano rag_hibrido_permissoes_ui_v2 — encerra o plano)

- **Novo `components/OrbGL/`** — WebGL2 cru (um quad + fragment shader, sem three.js): esfera com **aurora FBM domain-warped** (4 oitavas de value noise 3D nas cores da marca), **iluminação direcional real** (difuso + specular Blinn-Phong), **fresnel com dispersão cromática** tingido coral→púrpura, glow volumétrico analítico (sem multipass) e **anti-aliasing proporcional ao pixel** em todas as bordas
- **Estados dirigem uniforms, nunca trocam shader** (`orbStates.ts`, puro e testado): idle respira; thinking acelera fluxo/pulso e luas 4×; **ingesting (novo)** — espiral de partículas convergindo ao núcleo, conectado de verdade ao portal de upload via evento `atlas:ingest-active`; success flash verde; error treme (no espaço do shader) e avermelha; transições sempre por lerp
- **Mecânica kepleriana preservada**: Newton-Raphson extraído puro (`kepler.ts`) — a CPU resolve as órbitas e o shader desenha as luas com brilho de proximidade e oclusão atrás da esfera; testes de periapsis/apoapsis, convergência e fechamento de órbita
- **Fallback integral**: sem WebGL2, prefers-reduced-motion ou queda do contexto GL → CompanionOrb SVG intacto; render loop pausa com aba oculta e fora do viewport (zero GPU idle); DPR ≤ 2
- **Wordmark "AtlasFile"** com stroke draw-on (~1.5s) e fill emergindo no hero do onboarding (orb 112px), micro-interação de glow no hover
- **Chat: fim das URLs fabricadas** — regra no system prompt do orchestrator (nunca inventar links; citar `original_filename` entre backticks) + safety net no renderer (links placeholder viram chip clicável quando o texto é um arquivo, ou texto puro) — validado E2E com resposta real
- Testes: 135 frontend (9 novos do OrbGL) + 479 backend

---

## [0.19.0] -- 2026-07-17

### UI reformulada "instrumento de precisão vivo" — 100% das telas, zero CSS legado (Fase 6 do plano rag_hibrido_permissoes_ui_v2)

- **Shell**: sidebar colapsável com spring (Framer Motion), project switcher rico (avatar/cor determinística, busca inline), luz do orb, indicador ativo deslizante; CommandPalette ⌘K (cmdk) absorve o SearchModal — docs com trecho/location, navegação, projetos, tema, ações; Topbar reduzida a breadcrumb
- **Painel**: stat tiles com números que contam e cursor-glow; resultados de busca como tiles com aura por match_type (púrpura semântico/laranja lexical) e stagger; filtros como chips com contagem; barra de progresso com glow
- **Assistente**: chips de citação clicáveis sob as respostas (resolve via suggest e abre o doc); gráficos (ChartBlock + UsageView) na paleta da marca --chart-1..8 por tema
- **Triagem**: fila redesenhada (badge pulsante, tiles com barra accent, contexto do classificador em painel mono, ações Aprovar/Corrigir/Rejeitar temadas)
- **Upload portal global**: drop em qualquer lugar escurece a UI e projeta o portal (anel conic girando + partículas convergindo); sem projeto ativo, dialog de escolha; fila com progresso XHR por arquivo e scan automático único por lote
- **Toasts (sonner)** substituem o footer .status (toast único auto-atualizável; falhas de ingest com motivo por arquivo)
- **Zero CSS legado**: `styles.css` 2.416 → ~150 linhas (só design tokens dark/light); `ChatPanel.css` (~780) e `ingestTriageCard.css` (818) **eliminados** — conversão integral para Tailwind com reuso das primitivas (CollapsibleSection com badge rico, Badge, DataTable, selects padrão); restam apenas 8 linhas de override do recharts e o fallback SVG do orb (Fase 7)
- **Preflight-lite** em `@layer base`: reset de `button` (buttonface/borda nativos vazavam sem o preflight) e margens UA de headings/parágrafos — headers das 4 abas de Config **medidos idênticos (31px topo / 21px esquerda)** via getBoundingClientRect; `color-scheme` por tema (scrollbars e date pickers nativos acompanham dark/light)
- **Uso e custo**: StatTiles com ícones e cursor-glow (mesmos do Painel), **DateRangePicker pt-BR** (react-day-picker v10 + date-fns, calendário duplo com presets) substituindo o input nativo que exibia datas em formato US, **granularidade Dia/Semana/Mês** com default calculado do tamanho do range (≤31d dia, ≤26sem semana, senão mês) e barras animando do eixo
- **Chat**: empty state hero com starter prompts ancorados nas tools MCP; **aura Apple-Intelligence** (conic-gradient girando via @property) no compose durante streaming; "Pensando..." com shimmer de gradiente; compose reestruturado como container único (textarea + barra de ações interna, Enviar↔Parar contextuais); **órbita de contexto** — medidor na linguagem do orb (lua percorre órbita tracejada com rastro em gradiente, núcleo respira e esquenta accent→âmbar→vermelho, ≥90% pulsa e clique inicia nova sessão); popover de histórico redesenhado; markdown do assistente com tipografia completa via seletores arbitrários; **echo otimista corrigido** (refresh da sessão não engole mais a mensagem recém-enviada)
- **Onboarding**: fundo AuroraField (canvas 2D, blobs da marca com mola seguindo o pointer; `multiply` no light / `lighter` no dark — contraste correto nos dois temas)
- **Tabs com ícones** (Assistente e Config) e headers de card padronizados (CardTitle + ícone accent, min-h uniforme)
- Cascade layers: CSS legado em @layer legacy (legacy < theme < base < utilities) durante a migração — camada legacy hoje contém apenas tokens
- **Correções achadas em teste E2E real**: download de arquivos acentuados (RFC 6266), keyframes × propriedade translate do Tailwind v4, tokens @theme circulares, scan em loop na fila de upload, buttonface/borda nativos de button, scrollbar clara no dark, contraste light (--text-tertiary 3.4:1 → 4.55:1 AA)
- prefers-reduced-motion respeitado em todas as animações; navegação 100% por teclado no shell
- Novas deps frontend: react-day-picker, date-fns
- Testes: 126 frontend (15 novos na fase) + 479 backend

---

## [0.18.0] -- 2026-07-16

### UI Foundation: Tailwind + primitivas temadas + quebra do App.tsx (Fase 5 do plano rag_hibrido_permissoes_ui_v2)

- **Tailwind v4 (CSS-first)** via `@tailwindcss/vite`, **sem preflight** — o CSS legado convive intacto até o fim da Fase 6; só utilities + tokens
- **Tema 100% custom desde o dia 1** (`src/styles/theme.css`): `@theme inline` referencia os CSS vars existentes (accent `#ff5a36`, superfícies dark, DM Sans/Fragment Mono, radius/easings) — fonte única de verdade, dark/light automático via `data-theme`; nova paleta de gráficos `--chart-1..8` na marca (dark + light)
- **14 primitivas `components/ui/`** (copy-in estilo shadcn, temadas, zero cinza default): Button (cva, 6 variantes), Card, Dialog (glass overlay), DropdownMenu, Popover, Tooltip, Tabs (pill com accent), Input/Textarea, Select, Badge (inclui variante púrpura p/ semântico), Separator, Skeleton (shimmer na direção de leitura), ScrollArea, Command (cmdk) + Toaster (sonner) + `EmptyState`/`ErrorState` próprios
- **Quebra do App.tsx** (1.379 → shell): `SettingsContext` (tema, modelos, LLM keys, persistência), `NavigationContext` (view + hash sync `#/painel` — deep-link sem react-router), `ProjectContext` (projects/selected/labels — mata prop-drilling), hooks `useSearch` (⌘K + busca completa) e `useChatSession` (mensagens, sessões, usage, SSE); App virou providers + AppShell
- **Piloto migrado**: ConfigView agora em Tabs/Card/Input/Button temados (prova do tema); aba Acesso com a API key
- Testes: +7 das primitivas ui; 111 frontend verdes; build Vite ok

---

## [0.17.0] -- 2026-07-16

### Permissões mínimas: API key + escopo de projeto (Fase 4 do plano rag_hibrido_permissoes_ui_v2)

- **Novo `app/auth.py`**: `require_auth` como dependency global do app (Bearer/`X-API-Key`/query `api_key` para SSE e links de download), comparação em tempo constante (`secrets.compare_digest`, sem early-return), `AuthContext(name, allowed_projects)` e `enforce_project_scope` → 403
- **`API_AUTH_ENABLED=false` por default** — backward compat total; `/health` e preflight CORS nunca exigem key
- **Escopo por projeto aplicado** em: search (filtro `terms` quando a key é restrita), `/api/search/chunks`, `/api/projects` (lista filtrada), `/api/stats`, `/api/documents` (lista + get/chunks por doc), download (1º segmento do path), upload/inbox/scan/history, triagem, reconcile por projeto, move, chat (project_id do body), classifier override, initialize
- **Keys em `config/api_keys.json`** (fora do git; template `config/api_keys.example.json`; cache por mtime); MCP usa `ATLASFILE_API_TOKEN` (api_client já enviava Bearer); porta 8001 do MCP não valida key — manter interna
- **Frontend**: wrapper `apiFetch` injeta `Authorization: Bearer` de `localStorage("atlasfile_api_key")` (52 chamadas migradas); URLs de SSE/download anexam `api_key`; nova aba **Config → Acesso** para gravar a key; 401/403 exibem aviso via handler global
- Validação live: sem key 401, key errada 401, key ok 200, projeto fora do escopo 403, busca sem projeto filtrada ao escopo da key
- Testes: 8 novos de auth + 3 de triagem ajustados (AuthContext explícito)

---

## [0.16.0] -- 2026-07-16

### Busca híbrida BM25 + kNN + RRF com rerank opcional (Fase 3 do plano rag_hibrido_permissoes_ui_v2)

- **Novo `app/search_hybrid.py`**: braço semântico (kNN filtrado no `atlasfile_chunk_vectors`, agregado por documento com top-3 chunks como evidências), fusão RRF manual determinística (OpenSearch 2.17 sem RRF nativo; módulo isola o ponto de troca para ≥2.19), rerank opcional por **cross-encoder ONNX via fastembed** (sem torch; decisão ajustada após verificação SOTA — cross-encoder supera LLM listwise em custo/latência)
- **`GET /api/search` ganha `mode`**: `hybrid` (default), `lexical`, `semantic`; fallback silencioso para lexical quando embeddings indisponíveis, com `search_mode_effective` na resposta; docs achados só via kNN entram com evidências `match_type: "semantic"`; paginação pós-fusão sobre o top-N fundido
- **Novo `GET /api/search/chunks`** + **tool MCP `semantic_search_chunks`**: chunks crus com location/filename para RAG com citações; `search_documents` (MCP) ganha `mode`
- **Novo `scripts/benchmark_retrieval.py`**: Recall@5/MRR/NDCG@10 por modo contra golden set de queries pt-BR (`_ATLASFILE/retrieval_golden_set.jsonl`; template em `config/retrieval_golden_set.example.jsonl`) — decisões de RRF k e rerank passam a ser mensuráveis no corpus real
- **Frontend**: badge "semântico" (aura púrpura) em evidências vindas do braço vetorial; tipos atualizados
- **Settings novos**: `SEARCH_HYBRID_ENABLED`, `SEARCH_KNN_K`, `SEARCH_RRF_RANK_CONSTANT`, `SEARCH_RERANK_ENABLED`, `SEARCH_RERANK_MODEL`, `SEARCH_RERANK_TOP_N`
- Testes: 16 novos (RRF, filtros, braço semântico, rerank, integração do endpoint)

---

## [0.15.0] -- 2026-07-16

### Camada semântica: embeddings + índice de vetores (Fase 2 do plano rag_hibrido_permissoes_ui_v2)

- **Novo `app/embeddings.py`**: providers plugáveis — `openai` (text-embedding-3-small, dim 1536, batching, tokens rastreados) e `fastembed` (local/ONNX, `intfloat/multilingual-e5-small` dim 384 com prefixos query/passage; lazy import com erro claro; dependência opcional em `requirements-local-embeddings.txt`)
- **Novo índice `atlasfile_chunk_vectors`** (1 doc por chunk, knn_vector hnsw/cosinesimil/engine lucene — filtered k-NN no OpenSearch 2.17): metadados duplicados por chunk (project_id, business_domain, document_type, doc_kind, tags, datas) para k-NN filtrado; `_meta` com provider/modelo/dimensão e alerta em divergência (nunca recria sozinho). Zero reindex do índice principal
- **Ingestão e reconcile geram embeddings**: `index_document_chunks_embeddings` com skip incremental por sha256+provider+modelo; falha de embedding nunca quebra ingestão (doc flagado com `embedding_status`); reconcile faz backfill de docs sem vetores e remove vetores órfãos (doc removido e projeto órfão)
- **Novo `scripts/backfill_embeddings.py`**: migração do corpus já indexado; idempotente, flags `--project` e `--force`
- **Custos**: `text-embedding-3-small` ($0.02/1M input) em `config/usage_costs.json`; uso gravado no índice de training usage com `script_name: embeddings_ingest|embeddings_backfill`
- **Settings novos**: `EMBEDDING_ENABLED`, `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION`, `EMBEDDING_BATCH_SIZE` (documentados em `.env.example`/INSTALL.md)
- Testes: 15 novos (providers/factory, ensure do índice, indexação/skip/falha, custo)

---

## [0.14.0] -- 2026-07-16

### Remoção do modo de classificação `setfit`

- **Modos suportados agora são 3**: `bootstrap`, `sparse_logreg` e `llm`. O `setfit` perdia do `sparse_logreg` no benchmark, nunca era servido em ingestão por padrão e era o único usuário de torch/transformers/setfit/sentence-transformers (~545 MB no venv)
- **Dependências removidas** de `requirements.txt`: `setfit`, `sentence-transformers`, `transformers` (imagem Docker do backend encolhe)
- **Saneamento automático de registry legado**: `registry.json` persistido com `champion_mode`/`fallback_mode: "setfit"` é rebaixado na carga para `sparse_logreg` (se houver artefato) ou `bootstrap`, com warning; entradas `setfit` em `benchmark_enabled_modes` e `champion_summary` são removidas e o registry saneado é persistido
- **Arquivos deletados**: `backend/app/classifier_setfit.py`, `backend/tests/unit/test_classifier_setfit.py`
- **Frontend**: `setfit` removido de `OperationalClassifierMode` e das listas/labels do IngestTriageCard
- **Dados preservados**: `_ATLASFILE/classifier/models/setfit/` não é deletado — apenas ignorado
- Parte da Fase 1 do plano `rag_hibrido_permissoes_ui_v2`

---

## [0.13.0] -- 2026-04-08

### Upload de arquivos via frontend

- **Drag-and-drop + file picker**: zona de upload no Painel envia multiplos arquivos para `_INBOX_DROP/` via HTTP
- **Lista de arquivos enviados**: estado done mostra cada arquivo com botao × para remover da inbox
- **Persistencia**: inbox carregada do backend ao montar — arquivos permanecem visiveis entre trocas de aba
- **Endpoints**: `POST /api/ingest/upload`, `GET /api/ingest/inbox`, `DELETE /api/ingest/upload/{filename}`

### Move de documentos

- **Endpoint move**: `POST /api/documents/{project_id}/{doc_id}/move` com integracao training pool
- **MoveDocumentModal**: modal compartilhado com seletores bd/dt, confirmacao e erro inline
- **Dois pontos de entrada**: botao [Mover] nos resultados de busca + icone na tabela Processamentos
- **Todas as decisoes**: move habilitado para AUTO, TRIAGEM, aprovados e corrigidos (exceto DUP e error)
- **Ingest history**: triage approve/correct/reject e move atualizam `ingest_history.json`

### Refatoracao e componentizacao

- **`_relocate_document()`**: funcao extraida do triage para reuso pelo move
- **`PainelView`**: extraido do App.tsx (~280 linhas removidas)
- **`IngestHistoryCard`**: tabela Processamentos extraida do IngestTriageCard, movida para o Painel
- **`FileUploadZone`**: componente de upload com estados idle/dragover/uploading/done/error

### Fixes

- **Reconcile incremental**: comparacao de skip agora inclui `path` — detecta renomeacoes de arquivo
- **`build_corpus.py`**: `_load_existing_labels` usa ultimo registro por SHA256 (correcoes sobrescrevem)
- **`.gitignore`**: `_ATLASFILE/` adicionado para evitar artefatos de runtime no repo
- **Teste isolado**: `test_build_corpus_last_label_wins` usa `tmp_path` em vez de poluir o repo

---

## [0.12.0] -- 2026-04-06

### Evolucao UI — arquitetura de informacao e refinamento visual

- **Navegacao reestruturada**: 3 views por frequencia de uso — Painel (diario), Assistente (consulta), Configuracao (setup)
- **Painel**: KPIs com contagem de triagem pendente, TriageQueue em destaque, InboxScanCard + Reconciliar INDEX, atividade recente
- **Configuracao**: sub-tabs Perfil do projeto, Classificador, Templates (antes view isolada)
- **Templates integrado**: deixa de ser view top-level, agora sub-tab contextualizada junto ao perfil

### Decomposicao de componentes

- **IngestTriageCard**: triage queue extraida (TriageQueue.tsx), scan extraido (InboxScanCard.tsx), hooks SSE (useIngestMonitor, useClassifierCycleMonitor)
- **App.tsx**: Topbar, SearchModal, AssistenteView extraidos como componentes independentes
- **Novos componentes**: Skeleton (loading shimmer), EmptyState, ToastContext (notificacoes)

### Refinamentos visuais

- **Tipografia**: DM Sans como body font (15px), Fragment Mono reservado para dados numericos (KPIs, tabelas, badges)
- **Espacamento**: content/cards com padding e gap aumentados para sensacao editorial
- **Motion**: hover elevation em cards, button active scale(0.97), entrance animation com reduced-motion support
- **Charts**: animacoes Recharts ativadas (600ms), container com gradient background, titulo DM Sans
- **Tabelas**: row hover, header uppercase normalizado, zebra striping, total row com background
- **Chat compose**: textarea harmonizado com tema dark, focus ring accent, botoes alinhados
- **Modal overlay**: fix position:fixed quebrado por transform residual de animation fill-mode
- **CompanionOrb**: tamanho aumentado de 40px para 48px no topbar

### Testes

- 94 testes passam (vitest)
- Build TypeScript limpo
- Smoke test visual em Docker

---

## [0.11.0] -- 2026-04-03

### Uso e custo — precisao e visibilidade

- **Fix custo truncado**: `formatUsd` trocado de `Math.floor` para `Math.round` — $0.0567 agora mostra $0.06 (antes: $0.05)
- **Contagem de chamadas API**: novo campo `api_call_count` rastreado no orchestrator (OpenAI e Anthropic), persistido por sessao, exposto no endpoint `/api/usage/summary`
- **Treinamento: chamadas reais**: `records_processed` exposto como `total_api_calls` e `api_call_count` no endpoint `/api/usage/training` — benchmark_llm agora mostra 62 chamadas (antes: 1)
- **Card "Chamadas API"**: novo card no dashboard somando chamadas de todos os processos (assistente + classificacao + treinamento)
- **Colunas renomeadas**: "Chamadas" → "Chamadas API" nas tabelas de treinamento e classificacao

### Grafico diario — todos os processos

- **by_day nos endpoints**: `GET /api/usage/training` e `GET /api/usage/classification` agora retornam `by_day` via `date_histogram` do OpenSearch
- **Aba "Por tipo"** (default): barras empilhadas Input/Output/Cache Read/Cache Write somando todos os processos
- **Aba "Por processo"** (nova): barras empilhadas Assistente/Classificacao/Treinamento com cores dedicadas
- **Aba "Total" removida**: redundante (total ja exibido acima de cada barra)
- **Legenda lateral sincronizada**: "Tokens por tipo" / "Tokens por processo" alterna com a aba selecionada

### Cache tokens da OpenAI

- Captura de `prompt_tokens_details.cached_tokens` (cache read) em `_run_chat_openai`, `_classify_openai` e `benchmark_llm_candidate`
- Antes: campo ignorado, sempre 0 para OpenAI

### Testes

- Novo: `test_orchestrator_api_call_count.py` (6 testes)
- Novo: `UsageView.test.tsx` (12 testes — formatUsd, formatUsd4, formatTokens)
- Atualizados: testes de integracao para endpoints training e classification com by_day e api_call_count

---

## [0.10.0] -- 2026-04-02

### Gráficos no chat

- **ChartBlock** (Recharts): 8 tipos de gráfico renderizados inline no chat — bar, stacked_bar, horizontal_bar, pie, line, area, composed, treemap
- **Renderer server-side** (matplotlib): gráficos enviados como PNG via `send_photo` no Telegram e no mirror web→Telegram
- **System prompt** com instruções de geração de gráficos e guia para cruzamento de dimensões (stacked_bar)
- Fix flicker: `MARKDOWN_COMPONENTS` como constante de módulo + `React.memo` + `isAnimationActive={false}`

### Custos de treinamento / pipeline

- Novo índice OpenSearch `atlasfile_training_usage` com helper `persist_training_usage()`
- Instrumentação de custos em: `benchmark_llm_candidate` (ciclo via UI), `label_corpus_llm.py`, `classifier_augmentation.py`, `run_augmentation.py`
- Endpoint `GET /api/usage/training` com agregação por modelo e por script
- UsageView: card "Treinamento", tabelas de 5 colunas alinhadas, total tokens consolidado (assistente + classificação + treinamento)

### CompanionOrb

- Orb animado com mecânica orbital Kepleriana substituindo avatar estático do assistente no chat

### Correções

- `config/usage_costs.json` atualizado com preços corretos de abril/2026 (OpenAI e Anthropic)
- Opus 4.6: $15/$75 → $5/$25; gpt-4.1: $2.50/$10 → $2/$8; gpt-5.1: $5/$15 → $1.25/$10; Haiku 4.5: $0.80/$4 → $1/$5
- Cache read/write adicionados para OpenAI; cache write Anthropic ajustado para tier 5min (1.25x input)

---

## [0.9.0] -- 2026-04-02

### Pipeline de dados

- Corpus unificado com dedup SHA256: ~363 documentos únicos (de 401 arquivos), 14 tipos, 11 domínios
- Splits estratificados 70/15/15 (`build_corpus.py`, `build_splits.py`, `label_corpus_llm.py`, `inject_training_records.py`)
- Data leakage eliminado: 24 SHA256 duplicados entre treino e validação removidos
- `evaluation_dataset.py`: `splits_available()`, `load_split_as_training_records()`, `load_split_as_validation_entries()`

### Classificação — expansão para 4 modos

- **SetFit/ModernBERT** (`classifier_setfit.py`, 489 linhas): two-phase training em subprocesses isolados (spawn), OOM fix com truncagem em 2000 chars para encode/predict
- **LLM Classifier** integrado ao ciclo via `benchmark_llm_candidate()` (OpenAI/Anthropic, texto integral 20k chars)
- **sparse_logreg** melhorado: FeatureUnion char n-grams (3-5) + word n-grams (1-2), gate graduado (≥2 amostras com warning), `LinearSVC` removido
- **Bootstrap** como campeão: 87.1% domain / 93.5% type / 82.3% exact match
- Modos de benchmark configuráveis e persistidos via `benchmark_enabled_modes` no registry
- Bootstrap pode ser desmarcado — cada modo é opcional
- Herança de métricas: modos pulados preservam valores do ciclo anterior no relatório (`inherited_from_report_id`)

### Ciclo ML

- `_MAX_EXTRACT_CHARS`: 50.000 → 20.000 (alinhado ao "Lost in the Middle" ACL 2024)
- `extract_feature_text`: truncamento arbitrário `[:4000]` removido — texto completo ao modelo
- `_cross_validate_sparse()` com `StratifiedKFold(n_splits=5)`
- Progresso dinâmico por modo habilitado com phases granulares (`extracting`, `baseline:{mode}`, `benchmark:{mode}`)
- Cancelamento de ciclo: `DELETE /api/classifier/cycle` com `threading.Event` e `InterruptedError`

### API

- `PUT /api/classifier/benchmark-modes` — configurar modos habilitados
- `DELETE /api/classifier/cycle` — cancelar ciclo em andamento (202)
- `DELETE /api/classifier/reports/{report_id}` — excluir relatório (protege campeão ativo, 409)
- `GET /api/classifier/status` inclui `benchmark_enabled_modes`

### Frontend

- Barras de progresso SSE para scan INBOX e ciclo do classificador (mesmo padrão visual de Reconciliar INDEX)
- "Evolução recente" em tabela compacta com data formatada, campeão, exact, bd F1 e botão de delete por relatório
- Cancelar ciclo: botão com popover de confirmação e estado "Cancelando..."
- Modos pulados esmaecidos (opacity 0.45) com métricas reais do ciclo anterior
- Sync bidirecional do combobox "Modelo triagem" entre card Ingestão e modal Configurações
- Cabeçalho simplificado: removidos campos técnicos (Versão/Última), adicionado contador de pendentes
- Badges accent pill em "Classificador operacional" e "Processamentos"
- Card renomeado para "Perfil e Organização" com empty state alinhado ao estilo ITC
- Espaçamentos dos colapsáveis alinhados entre cards ITC e Perfil e Organização

### Augmentation (feature flag desabilitada)

- `classifier_augmentation.py` (453 linhas): augmentação sintética via LLM para classes sub-representadas
- `AugmentationConfig` no profile schema e template default

### System prompt de classificação

- Instrução explícita para analisar conteúdo (não apenas nome do arquivo)
- `document_types` do projeto injetados no contexto do LLM
- `explanation` obrigatória em todos os casos

### Testes

- 4 novos arquivos: `test_classifier_augmentation.py`, `test_classifier_setfit.py`, `test_corpus_splits.py`, `test_inject_training_records.py`
- **Total: 403 backend + 71 frontend = 474 testes**

### Docs

- Benchmark card completo com dados do ciclo `cycle_20260401_194500_343482` (4 modos, accuracy + F1-macro por eixo)
- Fundamentação SOTA: F1-macro vs accuracy, exact_match como critério de promoção, StratifiedKFold
- Justificativa sparse_logreg vs LinearSVC, XGBoost, BERT, SetFit

### Removido

- `frontend/mockup-chat-ui.html` (protótipo HTML não usado)
- `sparse_linear_svc` dos modos suportados

---

## [0.8.1] -- 2026-03-28

### Extração de PDF

- Migração do motor de extração PDF de `pypdf` para `pymupdf` com parsing espacial via bounding boxes
- Nova função `_spatial_extract_page`: agrupa spans por proximidade vertical (Y), ordena por X dentro de cada linha e reconstrói colunas com padding espacial
- Benchmark em 10 PDFs reais (216 QA pairs): qualidade equivalente (~76%), 3.5x mais rápido, 4.2x menos memória; em PDFs grandes (244p) pymupdf foi 64x mais rápido
- OCR fallback (pdf2image + Tesseract) inalterado — acionado quando texto nativo < 50 chars
- Interface `ExtractionResult` inalterada — zero impacto em consumidores (indexer, classifier)

### Testes

- 5 testes novos de PDF: multipage, metadata pages, max_chars early stop, empty page skipped, OCR fallback
- **Total: 365 backend + 71 frontend = 436 testes**

### Docs

- Projeto de benchmark independente em `extractor-benchmark/` com corpus, providers, ground truth e scripts de avaliação
- Sessão de decisão registrada em `docs/claude_chats/`
- Planos concluídos renomeados com nomes descritivos em `docs/planos_concluidos/`

---

## [0.8.0] -- 2026-03-20

### Ciclo operacional do classificador

- registry persistido em `_ATLASFILE/classifier` com `champion_mode`, ultimo report, gates de promocao e override por projeto
- novo fluxo de `benchmark + retreino` pela API/UI, com reports versionados, artefatos sparse persistidos e politica `auto_best_with_ui_override`
- ingestao passa a servir o modo efetivo do classificador (`bootstrap`, `sparse_logreg`, `sparse_linear_svc`) com fallback explicito para `bootstrap` quando o artefato supervisionado estiver ausente ou falhar
- datasets operacionais consolidados em `_ATLASFILE/classifier/datasets` como fonte fisica unica; o runtime nao copia mais `validation_set`/`training_pool` a partir do repo
- status em tempo real do ciclo do classificador e do processamento da INBOX corrigidos no frontend, sem reload manual
- scorecards por documento, override manual e estado operacional exibidos na UI sem expor `baseline` como modo publico

### Naming, triagem e indice

- corte do contrato publico legado `area_key` / `{area}` para `business_domain` nas superficies ativas, hints de UI, template/profile e validacao de schema
- `decide_triage()` agora recomputa `canonical_filename` em `correct`, preserva data de ingestao e versao e regrava o metadata resolvido
- `_INDEX.md` passa a ser atualizado por `doc_id`, mantendo `corrected` / `rejected` consistentes com filesystem e OpenSearch
- runtime do profile passa a incluir `naming`, evitando divergencia entre profile salvo e nome canonico aplicado na ingestao

### Docs e validacao

- `docs/plano_teste_e2e_v0.8.0.md` registrado como delta do `0.7.0`, com rerun usando o mesmo lote real de arquivos e evidencia do fix de streaming
- fixture mínima de `validation_set` mantida em `backend/tests/fixtures/classifier_datasets` apenas para um teste de integração, sem versionar cópia completa dos datasets operacionais
- `README.md` e docs tecnicos atualizados para o contrato `business_domain`, ciclo do classificador, fonte unica em `_ATLASFILE` e fixture mínima de teste dedicada
- novas regressions backend/frontend para naming, triagem, `_INDEX.md` e streaming de INBOX/ciclo

---

## [0.7.0] -- 2026-03-18

### Classificação e benchmark

- `bootstrap` consolidado como classificador operacional atual em `business_domain` + `document_type`
- refatoração config-driven do bootstrap: `classification.*` e `default.json` passam a ser a fonte de verdade da política de negócio; remoção de `DEFAULT_*` e fallback silencioso
- taxonomia expandida com `suprimentos` em `business_domain` e `edital` / `plano` em `document_type`
- `config/validation_set` e `config/training_pool` operacionalizados como artefatos distintos
- decisões de triagem `approve` / `correct` alimentam `config/training_pool/records.jsonl`
- benchmark oficial (`backend/scripts/benchmark_classification.py`) endurecido com:
  - checagem de integridade entre `validation_set` e `training_pool`
  - gates de elegibilidade do supervisionado
  - accuracy, macro-F1, recall por classe e matriz de confusão por eixo
- `sparse_logreg` e `sparse_linear_svc` seguem como candidatos de benchmark; promoção automática não foi introduzida neste release

### Busca, índice e assistente

- busca prioriza nome de arquivo e título exatos acima de ruído de score/evidências
- chat web passa `project_id` explicitamente ao orquestrador e às tools MCP compatíveis
- Telegram ganha `/projeto <project_id>` para fixar ou limpar o escopo de projeto no chat
- `/api/search`, `/api/stats`, triagem e UI operam de forma consistente com `business_domain` / `document_type`

### Operação e datasets

- `training_pool` desacoplado dos projetos físicos para benchmark reproduzível a partir de `config/training_pool/files`
- limpeza do estado operacional para manter apenas projetos úteis de validação do fluxo
- `validation_set` ampliado para cobrir classes antes sub-representadas sem sobreposição com o `training_pool`

### Docs

- novo roteiro `docs/plano_teste_e2e_v0.7.0.md`, orientado a teste via frontend e fiel ao estado implementado
- planos concluídos do ciclo arquivados em `docs/planos_concluidos/`
- `README.md` atualizado para refletir bootstrap operacional, datasets de benchmark e layout por `business_domain/document_type`

---

## [0.6.0] -- 2026-03-12

### Canais transparentes

- Telegram (e futuros canais) opera como pipe transparente: sessões, histórico e usage/custo compartilhados com o chat web
- Session manager para canais: busca sessão ativa por `(channel, chat_id)` no OpenSearch, timeout configurável (`channel_session_timeout_minutes`, default 30min)
- Comando `/novo` no Telegram para forçar nova sessão
- Concorrência por `asyncio.Lock` per `chat_id` (single-instance)
- Campo `channel` e `channel_chat_id` em `ChatSession`; campo `channel` per-message em `StoredChatMessage`
- Migração automática no startup: sessões existentes sem `channel` recebem `channel='web'` via `update_by_query`
- Campo `channel` opcional nos modelos (sem fallback mascarado; UI exibe "—" quando ausente)

### Rastreamento de uso LLM na classificação

- Novo índice OpenSearch `classification_usage` com mapping dedicado (doc_id, filename, project_id, provider, model, tokens, custo)
- `_classify_openai` e `_classify_anthropic` capturam `resp.usage` (input/output/cache tokens + custo estimado)
- `_persist_classification_usage` persiste uso no OpenSearch após cada classificação na ingestão
- Novo endpoint `GET /api/usage/classification` com agregação por período, projeto e modelo
- Card "Classificações" e seção "Classificação (uso LLM na ingestão)" no UsageView
- Custo total na aba "Uso e custo" agrega sessões do assistente + classificação

### Gestão de janela de contexto

- `_trim_history_to_context`: truncamento FIFO automático a 60% da janela do modelo (reserva 20% para tools, 20% para resposta)
- `_estimate_context_pressure`: estimativa de pressão de contexto retornada em cada resposta do `POST /api/chat`
- `get_context_tokens` no `llm_catalog.py`: lookup da janela de contexto por provider/modelo a partir do `LLM_MODEL_CATALOG`
- Modelo `ContextPressure` (context_tokens_estimate, context_tokens_limit, context_pressure_ratio)
- Componente `ContextRing` no footer do ChatPanel: indicador circular de pressão de contexto
  - 0-50%: neutro (cinza), 50-75%: atenção (amarelo), 75-100%: alerta (vermelho)
  - Tooltip a 90%: "Contexto quase cheio. Considere iniciar nova sessão."

### UsageView

- Filtro "Canal" (Todos / Web / Telegram) nos endpoints e na UI
- Coluna "Canal" na tabela de sessões
- Filtro de projeto unificado com o seletor global do header (removido filtro duplicado local)

### Sincronização cross-channel e espelhamento

- Append atômico de mensagens via `append_messages` no PATCH — elimina overwrite destrutivo quando web e Telegram operam na mesma sessão
- Refresh automático antes de enviar: frontend busca mensagens frescas do backend (`getChatSession`) antes de montar contexto para o LLM
- Espelhamento configurável: respostas enviadas via web em sessões originadas no Telegram são encaminhadas ao Telegram (mensagem do usuário com prefixo 🌐, resposta do assistente com conversão Markdown→HTML)
- Toggle "Espelhar respostas para o Telegram" na configuração de canais (default: off)
- `send_message` do Telegram aplica `_md_to_tg_html()` para conversão automática de Markdown para HTML do Telegram
- Proteção anti-loop: `source_channel` no PATCH impede espelhamento quando a origem é o próprio canal

### Atualização em tempo real (SSE)

- Event bus in-memory via `asyncio.Event` por sessão — notifica clientes SSE quando a sessão é modificada por outro canal
- Endpoint SSE `GET /api/chat/sessions/{id}/events` com keepalive a cada 25s
- `_notify_session_update` disparado no PATCH (web) e no `_handle_channel_message` (Telegram)
- Frontend abre `EventSource` quando uma sessão está ativa; atualiza mensagens, usage e by-model em tempo real
- Cleanup automático do Event ao desconectar

### Bug fixes

- Responsividade da tabela Sessões na aba "Uso e custo": `nowrap` em Data/Modelo, `text-overflow: ellipsis` no Título
- Remoção de fallback que mascarava sessões sem canal como "web" — exibe "—" quando `channel` é nulo

### Testes

- 4 novos arquivos de teste: `test_api_channel_features.py`, `test_context_management.py`, `test_llm_catalog_context.py`, `test_persist_classification_usage.py`
- 3 novos arquivos: `test_mirror_channel.py` (6 testes — mirror fires/skip/disabled/user-only/no-content), `test_session_events.py` (4 testes — event bus), `test_api_session_sse.py` (3 testes — SSE generator)
- 2 novos testes em `test_api_chat_sessions.py`: append atômico e conflito messages+append_messages (400)
- **Total: 339 backend + 69 frontend = 408 testes**

### Docs

- `docs/planos_concluidos/`: 5 planos movidos (canais_transparentes, fix_cross-channel_session_sync, fix_usage_cost_tracking, search_ui_mintlify_redesign, docx_pagina-paragrafo)
- `docs/07_rollout_kpis.md`: fases 2 e 3 marcadas como concluídas; nova fase 4 (Canais e observabilidade) adicionada

---

## [0.5.0] -- 2026-03-09

### Uso e custo do Assistente

- Nova aba "Uso e custo" no Assistente com visão consolidada de tokens e custo estimado por período, projeto e modelo
- Tabela "Por modelo" com breakdown de input/output tokens e custo (4 casas) por modelo, linha de totais
- Tabela "Sessões" com tokens e custo por sessão, paginação de 10 em 10
- Gráficos "Uso diário de tokens" (barras empilhadas por tipo) e "Tokens por tipo" (barra horizontal proporcional)
- Datas no formato brasileiro (dd/mm/aaaa) nos filtros de período
- Coluna Modelo nas sessões exibe modelos sem prefixo de provider; sessões multi-modelo listam todos (ex: "gpt-4.1, gpt-5.1")

### Rastreamento de uso por sessão

- Cada resposta do LLM retorna `usage` (input/output/cache tokens + custo estimado) ao frontend
- `usage_totals` e `usage_by_model` acumulados e persistidos por sessão no OpenSearch
- Sessões multi-modelo rastreiam tokens e custo separadamente por modelo usado
- Tokens de geração de título (background) acumulados na sessão correspondente
- Backend `GET /api/usage/summary` agrega tokens por tipo (input, output, cache_read, cache_write) por dia e por modelo

### Custo configurável por modelo

- Arquivo `config/usage_costs.json` com preços $/1M tokens por provider/modelo (input, output, cache_read, cache_write)
- Módulo `backend/app/usage_costs.py`: `get_cost_per_1m()` e `estimate_usage_cost()` — zero hardcoded
- Preços incluem cache read/write para Anthropic (prompt caching)

### Autosave de sessão

- Sessão criada automaticamente após a 1ª resposta do LLM (sem necessidade de clicar "+")
- Título derivado da primeira mensagem do usuário; título LLM gerado em background (se habilitado)
- Botão "+" sempre inicia nova conversa (sessão atual já salva)

### Identificação de modelo por mensagem

- Cada mensagem do assistente armazena o modelo que a gerou (`model` field)
- Footer do chat exibe "Assistente (gpt-4.1)" ao invés de apenas "Assistente"
- Retrocompatível: mensagens antigas sem `model` exibem "Assistente"

### UI/UX

- Abas "Chat" / "Uso e custo" em estilo segmented control (pill)
- Formatação de custo: totais com 2 casas decimais (truncado), componentes input/output com 4 casas
- Estilos do UsageView alinhados com o design system do App (sem CSS customizado conflitante)

---

## [0.4.0] -- 2026-03-06

### Canais de comunicação (Telegram)

- Camada nativa de channels no backend: módulo plugável `backend/app/channels/` com protocol `Channel`, `ChannelManager` e `TelegramChannel`
- Canal Telegram via **aiogram 3.x** (long-polling async), rodando dentro do mesmo processo FastAPI (zero containers novos)
- Mensagens inbound do Telegram despachadas diretamente para `run_chat_loop()` (zero hop HTTP, latência mínima)
- Endpoints REST: `GET/PUT /api/channels/config`, `GET /api/channels/status`, `POST /api/channels/test`
- UI: seção "Canais de comunicação" no modal de configuração do assistente com toggle, bot token (mascarado) e indicador de status em tempo real
- Placeholders visuais para Discord e Slack ("Em breve")
- Configuração via env vars (`CHANNELS_ENABLED`, `TELEGRAM_ENABLED`, `TELEGRAM_BOT_TOKEN`) e via API (PUT com restart automático)
- Falha no channel startup não impede o backend de subir (canais são opcionais)
- Testes unitários e de integração para o módulo channels e endpoints

### Formato canônico configurável

- Pattern de nomeação canônica configurável via `naming.canonical_pattern` no template/profile
- Nome original do arquivo preservado intacto (case, acentos, underscores) — apenas chars inválidos de filesystem removidos
- Campos disponíveis: `{date}`, `{project}`, `{area}`, `{original_name}`, `{document_type}`
- Sufixo `__v{version}{ext}` sempre adicionado automaticamente
- Pattern default simplificado: `{date}__{project}__{original_name}` (removido `area_key` do nome)
- Migração automática: arquivos no formato antigo (`__proj__area__title__`) renomeados para novo formato durante reconciliação
- `extract_original_name_from_canonical()`: parsing reverso robusto do nome original a partir do formato canônico

### Listagem de documentos e ferramentas MCP

- Novo endpoint `GET /api/documents`: listagem/browse de documentos com filtros (`project_id`, `doc_kind`, `document_type`, `area_key`) sem necessidade de query textual, com paginação
- Nova tool MCP `list_documents`: equivalente ao endpoint, usada pelo assistente para enumerar documentos de um projeto
- Guard `min_length` no MCP `search_documents`: retorna erro orientativo se query < 2 caracteres, direcionando para `list_documents`
- Modelos Pydantic: `ListDocumentItem` e `ListDocumentsResponse`

### Normalização de `project_id`

- `project_id` normalizado (sem acentos, lowercase) na criação de perfis (`profile_store.py`)
- `_resolve_project_root`: matching fuzzy com normalização de acentos, case e espaço↔underscore
- `_project_scope_filter`: aliases expandidos com variantes normalizadas para busca tolerante a acentos/case
- Agregação `by_project_id` adicionada ao endpoint `GET /api/stats`

### Arquitetura de indexação de conteúdo (Pure Nested)

- Campos flat de conteúdo removidos do mapping OpenSearch: `content`, `content_normalized`, `content_chunks_text`, `content_chunks_normalized`
- Todo o conteúdo textual agora armazenado exclusivamente em `content_chunks` (nested, ~1200 chars/chunk)
- Busca full-text migrada para nested queries com `inner_hits` e highlight por chunk
- Highlight via `inner_hits` elimina estruturalmente o erro `max_analyzed_offset` em documentos grandes (PDFs de qualquer tamanho)
- `GET /api/documents/{doc_id}`: campo `content` computado on-the-fly a partir da concatenação dos chunks
- Armazenamento reduzido ~60-70% por eliminação de 4 campos flat redundantes

### Highlighting de busca

- Dual highlight nativo do OpenSearch: `content_chunks.text` (preserva acentos) + `content_chunks.text_normalized` (fallback para queries sem acentos)
- Todas as ocorrências do termo destacadas nos snippets (antes: apenas a primeira)
- Funções de highlight manual eliminadas (`_build_evidence_snippet`, `_rehighlight_snippet`) em favor do highlight nativo do OpenSearch
- `_trim_highlight` reescrito para preservar todos os `<em>` tags dentro da janela de contexto
- Tamanho do snippet ampliado de 80 para 120 caracteres (melhor contexto sem poluir a UI)
- `number_of_fragments` aumentado de 1 para 2 nos inner_hits (cobre termos em partes distantes do mesmo chunk)
- Ordenação híbrida de evidências: trecho mais relevante (mais matches) no topo, demais em ordem sequencial do documento
- Chunks sem highlight nativo são pulados (sem snippets de texto puro sem destaque)
- Scoring passa de document-level para passage-level (melhor relevância em busca documental)
- Safety net: `max_analyzer_offset: 1_000_000` adicionado nas queries de highlight + `highlight.max_analyzed_offset: 10_000_000` nos index settings
- **Requer `RESET_INDEX=1` na atualização** (`make docker-update RESET_INDEX=1`)

### Reconciliação

- Scan de todas as roots PARA (`01_PROJECTS`, `02_AREAS`, `03_RESOURCES`, `04_ARCHIVE`): documentos em qualquer root são indexados no `_INDEX.md` e OpenSearch
- `area_key` para roots não-areas usa a categoria PARA (ex: `projects`, `resources`, `archive`); `02_AREAS` continua inferindo da subpasta
- Removido fallback legado `_WORK/`
- `cleanup_orphan_projects` integrado ao fluxo `run_reconcile` — executa automaticamente ao final
- Reconciliação default alterada para modo `incremental` (era `full`)
- Relatório de orphans (`orphan_projects_found`, `orphan_docs_deleted`) incluído no summary

### Assistente LLM

- System prompt atualizado: instruções para usar `list_documents`, obter `project_id` exato via `get_stats`, apresentar `original_filename` (não o título canônico), escopo e limites do assistente

### Onboarding

- Novo `OnboardingWizard`: wizard de primeira execução com detecção automática via `GET /api/setup/status`
- Endpoint `GET /api/setup/status`: retorna estado da instalação (`projects_root`, contagem de projetos, flag `onboarding_suggested`)

### Sessões de chat

- Save instantâneo: título gerado a partir da primeira mensagem do usuário (sem chamada LLM bloqueante); reduz latência de ~3-6s para ~200ms
- Flag `autoTitleLLM` (default desativado): se ativado, gera título via LLM em background após o save, sem bloquear a UI
- Sessão carregada do histórico não é duplicada ao clicar "Nova conversa" — apenas limpa o chat (mensagens já salvas automaticamente a cada resposta)
- Backend: PATCH `/api/chat/sessions` otimizado com `_update` parcial (em vez de GET + full INDEX)
- Configuração no modal do Assistente (checkbox "Gerar título da sessão via LLM")

### UI/UX

- Controle operacional redesenhado: layout compacto com métricas (total docs, tipos, extensões), mini-table de projetos e footer de reconciliação
- Dashboard stats carregado automaticamente na inicialização e pós-reconciliação
- Mensagem de reconciliação inclui contagem de órfãos removidos
- Classe CSS global `checkbox-inline`: fix para `flex: 1` global que distorcia checkboxes em modais

### Infraestrutura

- `make docker-update RESET_CHAT=1`: reseta índice de sessões de chat independente do índice de documentos
- `make docker-update RESET_INDEX=1 RESET_CHAT=1`: reseta ambos os índices
- `make reset-chat`: target standalone para resetar apenas sessões de chat
- Script `reset-opensearch-index.sh` refatorado com modos (`docs`, `chat`, `all`)

### Bug fixes

- Sync incremental: `project_id` agora comparado além de SHA256 — mudanças de metadados forçam reindexação
- `original_filename`: reconstruído corretamente via `extract_original_name_from_canonical()` quando `_INDEX.md` é recriado
- `cleanup_orphan_projects`: normalização de `project_id` (acentos, case, espaços/underscores) evita exclusão acidental de documentos legítimos

### Schema

- Nova seção `naming` no template e profile: `canonical_pattern`, `date_format`
- `NamingConfig` adicionado ao `profile_schema_v2.py` com validação de `{original_name}` obrigatório

### Testes

- 64+ novos testes: `fs_safe`, `build_canonical_filename`, `extract_original_name_from_canonical`, migração old→new, reconstrução de `original_filename`, normalização de orphans, `list_documents` endpoint, `project_id` normalization (14 cenários), `setup/status`, MCP `list_documents` tool, `OnboardingWizard` (14 cenários)

### Docs

- `docs/roadmap/plan_one_line_installer.md`: plano para instalador one-liner estilo OpenClaw

---

## [0.3.0] -- 2026-03-05

### Classificador

- Word boundary matching (`\b`) substituindo substring match em alias scoring e routing rules, eliminando falsos positivos (ex: "ativo" não casa mais com "interativo")
- Normalização sqrt: `hits / sqrt(len(aliases))` com cap em 1.0, inspirado no Lucene fieldNorm
- Helper `_match_normalize`: underscores e hífens convertidos em espaços para word boundary funcionar em nomes compostos (`Contrato_Servicos.pdf`)
- Routing rules completas para todas as 9 áreas (`juridica`, `financeiro`, `sistemas_migracao`, `processos_tsa`)

### LLM Visibility

- Campos `rule_area_key`, `rule_confidence`, `llm_explanation`, `llm_proposed_area` preservados na classificação
- Contexto de projeto (áreas, aliases, topics) injetado no prompt de classificação (`system_prompt_classify.md`)
- Prompt de chat enriquecido com contexto do projeto (`system_prompt_chat.md`)

### Template Management (CRUD)

- Novo `template_store.py`: store backend com templates `builtin` e `user`, CRUD completo
- API endpoints: `GET/POST/PUT/DELETE /api/templates`, `POST /api/templates/initialize`
- Novo `TemplateEditorView.tsx`: editor visual de templates (áreas, routing rules, confiança, LLM policy, indexação)
- Novo `TemplateSelectModal.tsx`: seleção de template na inicialização de projetos com opção de criar novo
- Removido `profile_v2_default.json` duplicado, consolidado em `config/templates/default.json`

### Busca e Estatísticas

- Novo endpoint `GET /api/stats`: agregações por `doc_kind`, `area_key`, `document_type`
- Filtros `doc_kind` e `area_key` adicionados à API de search

### UI/UX

- Hook `useEscapeKey`: todos os modais fecham com `Escape`
- Seções colapsáveis no editor de perfil (default: todos colapsados)
- Header harmonizado: alturas padronizadas de botões, selectors e combos
- Mobile responsiveness: largura mínima ajustada, scroll horizontal controlado
- Correção de radio buttons: override do `flex: 1` global para `input[type="radio"]`
- Modal overflow corrigido com flexbox scrollável
- `_ATLASFILE` e `.DS_Store` ocultos da listagem de projetos

### Infraestrutura

- `PROJECTS_HOST_ROOT` configurável via env var (default: `$HOME/Documents/Projects`), diretório criado se inexistente
- `.env.example` atualizado com todas as variáveis de ambiente
- `docker-compose.yml` ajustado para volume mount do `PROJECTS_HOST_ROOT`

### Testes

- 37 testes de classificador (word boundary, routing rules, sqrt scoring, aliases compostos)
- 6 testes de LLM visibility (preservação de campos rule/llm)
- 5 testes de classify context (briefing de projeto ao LLM)
- 6 testes de auto area creation (criação automática de área pelo LLM)
- 3 testes de stats endpoint (agregações)
- 10 testes de template store (CRUD, proteção default, merge builtin/user)
- **Total: 200 backend + 49 frontend = 249 testes**

---

## [0.2.0] -- 2026-03-05

### Profile V2

- Schema V2 de perfil com áreas de trabalho, routing rules, confidence thresholds, LLM policy e indexação
- `profile_store.py` e `profile_runtime.py`: gerenciamento e validação de perfis por projeto
- `profile_schema_v2.py`: validação estrutural do schema
- `area_resolver.py`: resolução de áreas com suporte a JD numbering

### Layout de Projeto

- `layout_service.py`: simulação (dry-run) e aplicação de layouts com rename, move e remoção de pastas
- `ProfileLayoutWorkspace.tsx`: workspace visual para editar estrutura de diretórios
- `ProfileLayoutEditor.tsx` e `LayoutPlanPreview.tsx`: editor e preview de plano de migração
- API endpoints `GET/PUT /api/profile`, `POST /api/profile/layout/plan`, `POST /api/profile/layout/apply`

### Ingestão e Triagem

- LLM toggle no card de ingestão: ativar/desativar LLM com seleção de modo e modelo
- `ingest_history.py`: histórico persistente em `_PROFILE/ingest_history.json` (FIFO, cap 50)
- Paginação de histórico: últimos 10 visíveis, paginado de 10 em 10
- Dedup precoce: SHA256 check antes do fluxo completo, sem cópias `_dup_*`
- `IngestTriageCard.tsx`: card completo com scan, histórico e LLM controls
- `CorrectDecisionModal.tsx`: modal para corrigir decisões de classificação

### Extração de Documentos

- Suporte a `.docx` com detecção de page breaks (explicit, last-rendered, estimated)
- Suporte a `.xlsx`, `.pptx`, `.msg`, `.zip`, `.rar` (listagem de conteúdo)
- Chunking com localização (`page:N`, `sheet:Name`, `slide:N`)
- Modo de extração `all` vs `excerpt` com `extraction_max_chars` configurável

### Topics e Enriquecimento

- `topics.py`: matching semântico de tópicos via `config/topics_v1.yaml`
- Campos `topics`, `topics_source`, `document_type`, `correspondent` derivados
- `doc_kind` inferido a partir de extensão do arquivo

### Reconciliação

- `reconcile_service.py`: reconciliação entre filesystem, index e profile
- Detecção de documentos órfãos, duplicados e ausentes

### UI/UX

- `AssistantSettingsModal.tsx`: modal de configuração do assistente (API key, modelo)
- Colapsáveis com chevrons em seções do perfil
- Responsividade mobile para header e cards
- Formatadores de busca (`searchFormatters.ts`)

### Testes

- 163 testes backend (profile layout, search, document extractor, ingest history, dedup, LLM policy, layout service, topics, reconcile)
- 49 testes frontend (App, API, IngestTriageCard, ProfileLayout, TemplateEditor)
- Scripts: `e2e_layout_scenarios.py`, `smoke-project-init.sh`

---

## [0.1.0] -- 2026-03-03

### Core

- Pipeline de ingestão: inbox drop → classificação por aliases → renomeação canônica → movimentação para área
- Classificação baseada em aliases com normalize_text (lowercase, remoção de acentos)
- Naming convention: `YYYYMMDD__proj__area__title__vNN.ext` (ver 0.4.0 para formato configurável)
- Versionamento automático de documentos duplicados (`_v01`, `_v02`, ...)

### MCP Server

- `mcp/server.py`: servidor MCP com tools `search_documents`, `get_document_chunks`, `list_projects`
- `mcp_client/client.py`: cliente MCP para integração com ferramentas externas

### Chat / Assistente

- `orchestrator.py`: orquestrador de chat com suporte a multi-modelos (OpenAI, Anthropic, Google)
- `llm_catalog.py`: catálogo de modelos com limites por provider
- Sessões de chat persistentes com histórico (`GET/POST/PUT/DELETE /api/chat/sessions`)
- `ChatPanel.tsx`: painel de chat com reasoning, markdown rendering e topbar
- System prompts configuráveis (`system_prompt_chat.md`, `system_prompt_classify.md`)

### Indexação (OpenSearch)

- `opensearch_client.py`: cliente com mapping completo (35+ campos)
- `indexer.py`: indexação de documentos com chunking e enriquecimento
- Busca full-text com highlight e suggest (autocomplete)
- API: `GET /api/search`, `GET /api/suggest`, `GET /api/documents/{id}`, `POST /api/documents/{id}/tags`

### Frontend

- SPA React + TypeScript + Vite
- Cards: Ingestão, Busca (modal + resultados completos), Chat/Assistente
- Tema claro/escuro com variáveis CSS
- Header com seletor de projeto, health check e theme toggle

### Infraestrutura

- Docker Compose: backend (FastAPI), frontend (Nginx), OpenSearch, OpenSearch Dashboards
- `atlasfile_install.sh`: instalador one-liner
- Makefile com targets: `build`, `up`, `test`, `docker-update`
- Dashboard Kibana importável (`dashboards/atlasfile.ndjson`)
- Scripts: `bootstrap_project.py`, `reset-opensearch-index.sh`, `import-dashboards.sh`

### Testes

- Pytest (backend): API health, chat models, document tags/chunks, MCP server/client
- Vitest (frontend): setup inicial

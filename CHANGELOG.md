# Changelog

Todas as mudanças relevantes do AtlasFile são documentadas neste arquivo.

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

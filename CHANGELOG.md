# Changelog

Todas as mudanças relevantes do AtlasFile são documentadas neste arquivo.

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

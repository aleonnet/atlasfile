# AtlasFile

Sistema local de organização documental por projeto, com classificação por `business_domain` + `document_type`, triagem humana, indexação full-text, benchmark supervisionado e assistente conversacional.

## Visão geral

- **Ingestão automática** via pasta `_INBOX_DROP` por projeto
- **Classificação operacional** via `bootstrap`, produzindo `business_domain` + `document_type`
- **Triagem humana** no frontend para documentos pendentes (`Aprovar`, `Corrigir`, `Rejeitar`)
- **Dedup precoce** por SHA256 antes do fluxo completo
- **Indexação** de conteúdo e metadados em OpenSearch com busca, suggest e highlight
- **Busca por nome exato** priorizada para `original_filename` e `title`
- **Assistente LLM** com escopo por projeto, sessões persistentes e rastreamento de uso/custo
- **Canais** com Telegram opcional e comando `/projeto` para fixar escopo do chat
- **Templates, profiles e layout** editáveis pela UI
- **Benchmark supervisionado** com `validation_set` e `training_pool` disjuntos
- **Rastreabilidade** completa: nome original → nome canônico → triagem → índice → benchmark

## Stack

| Camada | Tecnologia |
|--------|------------|
| Backend | FastAPI (Python 3.12) |
| Busca | OpenSearch 2.17 (BM25) |
| Frontend | Vite + React + TypeScript |
| LLM | OpenAI / Anthropic (multi-modelo) |
| MCP | FastMCP server (tools de busca, tags, stats) |
| Runtime | Docker Compose (5 serviços) |

## Estrutura do monorepo

```
AtlasFile/
├── backend/                 # API FastAPI, classificador, indexador, MCP server
│   ├── app/                 # Código principal (main, ingestion, orchestrator, ...)
│   │   ├── api/             # Routers (profile, layout, channels)
│   │   ├── channels/        # Camada de canais (Telegram, Discord, Slack)
│   │   ├── mcp/             # MCP server (tools)
│   │   ├── mcp_client/      # Cliente MCP (chat/orchestrator)
│   │   └── prompts/         # System prompts (classify, chat)
│   └── tests/               # Unit + integration (pytest)
├── frontend/                # SPA React + TypeScript
│   └── src/
│       ├── components/      # ChatPanel
│       ├── features/        # ingest, profile-layout, search, settings, templates, triage, usage
│       └── hooks/           # useEscapeKey
├── config/
│   ├── templates/           # Templates de projeto (default.json, user templates)
│   ├── validation_set/      # Conjunto de avaliação humana do classificador
│   ├── training_pool/       # Rótulos revisados para benchmark supervisionado
│   └── usage_costs.json     # Preços $/1M tokens por provider/modelo
├── docs/                    # Documentação de referência (benchmarking, conventions, KPIs)
├── scripts/                 # Bootstrap, smoke test, CI, reset index
├── docker-compose.yml
├── Makefile
└── CHANGELOG.md
```

## Estrutura de um projeto

```
/<PROJETO>/
├── _INBOX_DROP/                    # Ponto de entrada de documentos
├── _TRIAGE_REVIEW/
│   ├── pending/                    # Aguardando decisão humana
│   ├── resolved/                   # Aprovados/corrigidos
│   └── rejected/                   # Rejeitados
├── _PROFILE/
│   ├── profile.json                # Profile V2
│   ├── ingest_history.json         # Histórico de ingestões (FIFO, cap 50)
│   └── history/                    # Versões anteriores do profile
├── 01_PROJECTS/
├── 02_AREAS/
│   └── <business_domain>/
│       └── <document_type>/
├── 03_RESOURCES/
├── 04_ARCHIVE/
└── _INDEX.md                       # Registro local de documentos ingeridos
```

## Datasets do classificador

```text
config/
  validation_set/
    files/
    expected.json
  training_pool/
    files/
    records.jsonl
```

- `validation_set`: conjunto humano-curado para benchmark e aceite
- `training_pool`: documentos revisados via triagem que alimentam os candidatos supervisionados
- `backend/scripts/benchmark_classification.py`: compara `baseline`, `bootstrap`, `sparse_logreg` e `sparse_linear_svc`

## Execução local

### Pré-requisitos

- Docker Desktop ([Mac](https://www.docker.com/products/docker-desktop/) / [Windows](https://www.docker.com/products/docker-desktop/))
- (Opcional) Chaves de API: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`

### Setup

```bash
# 1. Copie e configure o .env
cp .env.example .env
# Edite PROJECTS_HOST_ROOT com o path absoluto dos seus projetos
# Default recomendado: $HOME/Documents/Projects

# 2. Suba o stack
make docker-update
```

### Serviços

| Serviço | URL | Descrição |
|---------|-----|-----------|
| Frontend | http://localhost:5173 | Interface web (tema claro/escuro) |
| API | http://localhost:8000 | FastAPI (REST + SSE) |
| MCP Server | http://localhost:8001 | Tools para chat/classificação |
| OpenSearch | https://localhost:9200 | Motor de busca (admin/Kaid0Search!2026X) |
| Dashboards | http://localhost:5601 | OpenSearch Dashboards |

### Makefile

| Target | O que faz |
|--------|-----------|
| `make test` | Roda todos os testes (backend + frontend) |
| `make docker-update` | Testa + rebuild + sobe stack + smoke test |
| `make docker-update RESET_INDEX=1` | Idem + reseta índice de documentos |
| `make docker-update RESET_CHAT=1` | Idem + reseta índice de sessões de chat |
| `make docker-up` | Sobe stack sem rodar testes |
| `make reset-index` | Remove índice de documentos |
| `make reset-chat` | Remove índice de sessões de chat |

## Fluxo de classificação

```text
Arquivo entra em _INBOX_DROP
         │
         ▼
   Dedup por SHA256
         │
         ▼
   Extração de texto + metadados
         │
         ├─ detect_document_type(...)
         └─ classify_bootstrap(...)
                 │
                 ▼
   Confiança alta?
   ├─ Sim → move para 02_AREAS/{business_domain}/{document_type} e indexa
   └─ Não → move para _TRIAGE_REVIEW/pending
                  │
                  ▼
          Humano: Aprovar / Corrigir / Rejeitar
                  │
                  └─ Aprovar/Corrigir → grava em config/training_pool/records.jsonl
```

- `bootstrap` é o classificador operacional atual
- `sparse_*` são candidatos medidos em benchmark, não promovidos automaticamente
- o LLM de ingestão é opcional e não é o classificador principal

## Convenção de nomes (canonical)

Formato configurável via `naming.canonical_pattern` no template/profile. Default:

```
{date}__{project}__{original_name}__v{version}{ext}
```

Exemplo: `20260301__kaido__Contrato_Migracao_Clientes__v01.xlsx`

O nome original do arquivo é preservado intacto (case, acentos, underscores). Veja `docs/04_naming_convention.md` para detalhes.

## Variáveis de ambiente

| Variável | Descrição | Default |
|----------|-----------|---------|
| `PROJECTS_HOST_ROOT` | Path absoluto dos projetos no host | (obrigatório) |
| `OPENAI_API_KEY` | Chave OpenAI (chat + classificação) | — |
| `ANTHROPIC_API_KEY` | Chave Anthropic (chat) | — |
| `CLASSIFICATION_LLM_ENABLED` | Habilitar LLM no fluxo de ingestão | `false` |
| `DEFAULT_LLM_PROVIDER` | Provider padrão | `openai` |
| `DEFAULT_LLM_MODEL` | Modelo padrão | `gpt-4o-mini` |
| `AUTO_RECONCILE_INTERVAL_SECONDS` | Intervalo de reconciliação automática | `600` |

Veja `.env.example` para a lista completa.

## MCP Tools (para LLM e integrações)

| Tool | Descrição |
|------|-----------|
| `list_documents` | Listagem/browse de documentos com filtros por projeto, `business_domain` e `document_type` |
| `search_documents` | Busca full-text com filtros por projeto, `business_domain`, `document_type`, tags e datas |
| `get_stats` | Estatísticas agregadas por `doc_kind`, `business_domain`, `document_type` e `project_id` |
| `get_document` | Metadados + chunks de um documento |
| `get_document_chunks` | Chunks específicos por localização (page:N, sheet:Name) |
| `apply_tags` | Adiciona/remove tags |
| `set_metadata` | Atualiza `document_type`, `business_domain`, `correspondent` e `review_status` |
| `submit_classification` | Suporte a classificação/revisão via LLM quando o fluxo configurado exigir |

## Testes

```bash
make test              # Backend (pytest) + Frontend (vitest)
make test-backend      # Apenas backend
make test-frontend     # Apenas frontend
```

As suítes cobrem bootstrap, benchmark, datasets, ingestão, triagem, busca, templates, profile/layout, channels, usage/custo, API e frontend.

## Documentação

- `CHANGELOG.md` — histórico de versões
- `INSTALL.md` — guia de instalação detalhado (Mac/Windows)

### Referência técnica (`docs/`)

| Doc | Conteúdo |
|-----|----------|
| `01_benchmarking.md` | Referências (NARA, ISO 15489, FAIR, Johnny.Decimal, BM25) |
| `02_gap_analysis.md` | Análise de gaps que motivou o projeto |
| `03_framework_template.md` | Estrutura de projeto e ciclo de ingestão |
| `04_naming_convention.md` | Convenção canônica de nomes |
| `05_index_models.md` | Modelo de índice (_INDEX.md + OpenSearch, 35+ campos) |
| `06_retention_policy.md` | Política de retenção (roadmap) |
| `07_rollout_kpis.md` | Fases de rollout e KPIs |
| `08_project_profile_template.md` | Template de profile V2 (JSON) com exemplo completo |
| `09_field_mapping.md` | Mapeamento completo de campos: origem, derivação, uso pelo LLM |
| `10_classifier_design.md` | Design do classificador: benchmarks, fundamentação, comparativos |
| `plano_teste_e2e_v0.7.0.md` | Roteiro E2E atual, orientado a teste pelo frontend |
| `agent-tools-flow.md` | Fluxo MCP → LLM → tools (como o agente recebe e usa ferramentas) |

Planos de implementação concluídos ficam em `docs/planos_concluidos/` como registro de decisões.

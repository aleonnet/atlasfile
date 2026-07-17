# AtlasFile

Sistema local de organização documental por projeto, com ciclo operacional de classificador, classificação por `business_domain` + `document_type`, triagem humana, indexação full-text, benchmark supervisionado e assistente conversacional.

## Instalação rápida

Pré-requisito: [Docker Desktop](https://docs.docker.com/get-docker/) rodando.

**macOS / Linux:**

```bash
curl -fsSL https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.sh | bash
```

**Windows (via WSL2):**

```powershell
irm https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.ps1 | iex
```

O instalador clona o projeto, configura o `.env`, sobe a stack Docker e abre `http://localhost:5173` — o assistente de primeiros passos guia a criação do primeiro projeto. Instalação manual e detalhes: [INSTALL.md](INSTALL.md).

## Visão geral

- **Ingestão automática** via pasta `_INBOX_DROP` por projeto
- **Classificação operacional** via modo efetivo do runtime (`bootstrap`, `sparse_logreg` ou `llm`)
- **Ciclo do classificador** com benchmark + retreino, campeão global, override por projeto e reports persistidos
- **Triagem humana** no frontend para documentos pendentes (`Aprovar`, `Corrigir`, `Rejeitar`)
- **Dedup precoce** por SHA256 antes do fluxo completo
- **Indexação** de conteúdo e metadados em OpenSearch com busca, suggest e highlight
- **Embeddings por chunk** (OpenAI text-embedding-3-small ou fastembed local) em índice de vetores separado (`atlasfile_chunk_vectors`), base da busca semântica/RAG
- **Busca híbrida** (BM25 + kNN com fusão RRF, default do `/api/search`) com fallback automático para lexical, rerank opcional por cross-encoder local e benchmark de retrieval contra golden set (`scripts/benchmark_retrieval.py`)
- **Autenticação opcional por API key** (`API_AUTH_ENABLED`) com escopo por projeto — keys em `config/api_keys.json`, enforcement na API e no MCP via `ATLASFILE_API_TOKEN`
- **Busca por nome exato** priorizada para `original_filename` e `title`
- **Assistente LLM** com escopo por projeto, sessões persistentes, gráficos inline (8 tipos) e rastreamento de uso/custo
- **Canais** com Telegram opcional e comando `/projeto` para fixar escopo do chat
- **Templates, profiles e layout** editáveis pela UI
- **Benchmark supervisionado** com 3 modos (bootstrap, sparse_logreg, llm), corpus unificado e splits estratificados
- **Status em tempo real** para reconcile, INBOX e ciclo do classificador
- **Rastreabilidade** completa: nome original → nome canônico → triagem → índice → benchmark

## Stack

| Camada | Tecnologia |
|--------|------------|
| Backend | FastAPI (Python 3.12) |
| Busca | OpenSearch 2.17 (BM25 + kNN, fusão RRF manual) |
| Frontend | Vite + React + TypeScript |
| UI | Tailwind v4 (CSS-first) + primitivas próprias estilo shadcn (copy-in sobre Radix UI + cva + cmdk + sonner) — tokens da marca em `src/styles.css`/`src/styles/theme.css`, sem tema default; orb WebGL (`components/OrbGL/`) com fallback SVG |
| LLM | OpenAI / Anthropic (multi-modelo) |
| MCP | FastMCP server (tools de busca, tags, stats) |
| Runtime | Docker Compose (5 serviços) |

O workflow completo de um documento (drop → dedup → extração → classificação → roteamento → indexação → embeddings → busca → chat), com os pontos de observação de cada etapa, está descrito em [`docs/workflow_documento.md`](docs/workflow_documento.md). O roteiro de validação com score por etapa está em [`docs/plano_teste_e2e_v0.20.0.md`](docs/plano_teste_e2e_v0.20.0.md).

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
│   ├── scripts/             # Benchmark, ciclo ML, datasets operacionais, status
│   └── tests/               # Unit + integration (pytest)
├── frontend/                # SPA React + TypeScript
│   └── src/
│       ├── components/      # ChatPanel, ChartBlock, CompanionOrb
│       ├── features/        # ingest, profile-layout, search, settings, templates, triage, usage
│       └── hooks/           # useEscapeKey, useCompanionState
├── config/
│   ├── templates/           # Templates de projeto (default.json, user templates)
│   ├── topics_v1.yaml       # Catálogo de topics derivado no runtime
│   └── usage_costs.json     # Preços $/1M tokens por provider/modelo
├── docs/                    # Documentação de referência (benchmarking, conventions, KPIs)
├── scripts/                 # Bootstrap, smoke test, CI, reset index, dashboards
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
_ATLASFILE/
  classifier/
    datasets/
      corpus.jsonl                 ← fonte única de verdade
      corpus_files/                ← arquivos com nomes normalizados
      splits/
        train.jsonl                ← 70%
        validation.jsonl           ← 15%
        test.jsonl                 ← 15%
      validation_set/
        files/
        expected.json
      training_pool/
        files/
        records.jsonl
```

- `corpus.jsonl` + `splits/`: corpus consolidado (~363 docs, dedup SHA256) com splits estratificados 70/15/15
- `validation_set`: conjunto humano-curado para benchmark e aceite, persistido apenas no volume operacional
- `training_pool`: snapshots e `records.jsonl` vivos do classificador, persistidos apenas no volume operacional
- `backend/tests/fixtures/classifier_datasets/validation_set`: fixture mínima versionada usada por um teste de integração; não representa dataset operacional nem cópia completa dos datasets reais
- `backend/scripts/build_corpus.py`: consolida training_pool + validation_set, dedup SHA256, gera `corpus.jsonl`
- `backend/scripts/build_splits.py`: particionamento estratificado 70/15/15

## Ciclo operacional do classificador

- O registry global em `_ATLASFILE/classifier` persiste `champion_mode`, `benchmark_enabled_modes`, gates de promocao, ultimo ciclo e ultimo report.
- O root operacional dos datasets fica em `_ATLASFILE/classifier/datasets`, fora da imagem Docker, com corpus, splits, `validation_set` e `training_pool` persistidos no volume de projetos.
- O runtime nao faz bootstrap silencioso a partir do repo: se o dataset operacional estiver vazio, benchmark/ciclo refletem esse estado explicitamente.
- Cada projeto pode fixar `classification.operational.override_mode`; sem override, a ingestao usa o campeao atual.
- O runtime serve `bootstrap`, `sparse_logreg` ou `llm` e faz fallback explicito para `bootstrap` se o artefato supervisionado estiver ausente ou falhar.
- Modos de benchmark sao configuraveis pela UI; cada modo pode ser habilitado/desabilitado independentemente. Modos pulados herdam metricas do ciclo anterior.
- A triagem grava snapshots estaveis do training pool e pula documentos que colidam por SHA com o validation set.
- A UI expoe benchmark + retreino, scorecards por documento, campeao atual, cancelamento de ciclo e override manual sem reintroduzir `baseline` como modo publico.

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

Para a função de cada script operacional e técnico, veja `docs/11_scripts_and_operations.md`.

### Serviços

| Serviço | URL | Descrição |
|---------|-----|-----------|
| Frontend | http://localhost:5173 | Interface web (tema claro/escuro) |
| API | http://localhost:8000 | FastAPI (REST + SSE) |
| MCP Server | http://localhost:8001 | Tools para chat/classificação |
| OpenSearch | https://localhost:9200 | Motor de busca (admin / `OPENSEARCH_PASSWORD` do `.env`) |
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
         ▼
  Resolver modo operacional
         │
         ├─ champion do registry
         └─ override do projeto (opcional)
                 │
                 ▼
  Classificar `document_type` + `business_domain`
                 │
                 ▼
   Confiança alta?
   ├─ Sim → move para 02_AREAS/{business_domain}/{document_type} e indexa
   └─ Não → move para _TRIAGE_REVIEW/pending
                  │
                  ▼
          Humano: Aprovar / Corrigir / Rejeitar
                  │
                 └─ Aprovar/Corrigir → grava em _ATLASFILE/classifier/datasets/training_pool/records.jsonl
```

- `bootstrap` continua como fallback seguro do runtime (campeao atual: 87.1% domain, 82.3% exact match)
- `sparse_logreg` e `llm` sao candidatos de benchmark e podem virar modo efetivo apos o ciclo oficial
- o LLM de ingestão é opcional e não é o classificador principal

## Convenção de nomes (canonical)

Formato configurável via `naming.canonical_pattern` no template/profile. Default:

```
{date}__{project}__{original_name}__v{version}{ext}
```

Exemplo: `20260301__kaido__Contrato_Migracao_Clientes__v01.xlsx`

Os placeholders suportados no contrato ativo sao `date`, `project`, `business_domain`, `document_type` e `original_name`; `{area}` e rejeitado no schema. Em triagem `correct`, o sistema recompõe o nome canonico preservando a data de ingestao e a versao ja emitida. Veja `docs/04_naming_convention.md` para detalhes.

## Variáveis de ambiente

| Variável | Descrição | Default |
|----------|-----------|---------|
| `PROJECTS_HOST_ROOT` | Path absoluto dos projetos no host | (obrigatório) |
| `CLASSIFIER_DATASETS_ROOT` | Root operacional dos datasets do classificador | `/projects/_ATLASFILE/classifier/datasets` |
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

As suites cobrem lifecycle do classificador, benchmark, datasets, ingestao, triagem, busca, templates, profile/layout, channels, usage/custo, API e frontend.

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
| `10_classifier_design.md` | Design do classificador: runtime operacional, benchmark, promocao e fallback |
| `plano_teste_e2e_v0.8.0.md` | Roteiro E2E delta da 0.8.0, orientado a teste pelo frontend |
| `plano_teste_e2e_v0.7.0.md` | Baseline E2E registrada e reutilizada como referencia do lote real |
| `agent-tools-flow.md` | Fluxo MCP → LLM → tools (como o agente recebe e usa ferramentas) |

Planos de implementação concluídos ficam em `docs/planos_concluidos/` como registro de decisões.

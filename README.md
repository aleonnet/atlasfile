# AtlasFile

Local, per-project document organization system with a classifier operational cycle, classification by `business_domain` + `document_type`, human triage, full-text indexing, supervised benchmarking, and a conversational assistant.

**English** · [Português (Brasil)](README.pt-BR.md)

🌐 **Website:** https://aleonnet.github.io/atlasfile.ai/ — presentation and install guide

## Quick install

Prerequisite: [Docker Desktop](https://docs.docker.com/get-docker/) running.

**macOS / Linux:**

```bash
curl -fsSL https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.sh | bash
```

**Windows (via WSL2):**

```powershell
irm https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.ps1 | iex
```

The installer clones the project, configures the `.env`, brings up the Docker stack, and opens `http://localhost:5173` — the first-steps assistant guides you through creating your first project. Manual installation and details: [INSTALL.md](INSTALL.md).

## Overview

- **Automatic ingestion** via a per-project `_INBOX_DROP` folder
- **Operational classification** via the runtime's effective mode (`bootstrap`, `sparse_logreg`, or `llm`)
- **Classifier cycle** with benchmark + retraining, global champion, per-project override, and persisted reports
- **Human triage** in the frontend for pending documents (`Approve`, `Correct`, `Reject`)
- **Early dedup** by SHA256 before the full pipeline
- **Indexing** of content and metadata in OpenSearch with search, suggest, and highlight
- **Per-chunk embeddings** (OpenAI text-embedding-3-small or local fastembed) in a separate vector index (`atlasfile_chunk_vectors`), the foundation of semantic/RAG search
- **Hybrid search** (BM25 + kNN with RRF fusion, the default for `/api/search`) with automatic fallback to lexical, optional reranking via a local cross-encoder, and a retrieval benchmark against a golden set (`scripts/benchmark_retrieval.py`)
- **Optional API key authentication** (`API_AUTH_ENABLED`) with per-project scope — keys in `config/api_keys.json`, enforced in the API and in MCP via `ATLASFILE_API_TOKEN`
- **Exact-name search** prioritized for `original_filename` and `title`
- **LLM assistant** with per-project scope, persistent sessions, inline charts (8 types), and usage/cost tracking
- **Channels** with optional Telegram and a `/projeto` command to pin the chat scope
- **Templates, profiles, and layout** editable from the UI
- **Supervised benchmark** with 3 modes (bootstrap, sparse_logreg, llm), a unified corpus, and stratified splits
- **Real-time status** for reconcile, INBOX, and the classifier cycle
- **Bilingual interface (PT-BR / EN-US)** with automatic browser detection, a persisted selector in Settings → Preferences, and a switcher on the first-run screens; API errors use stable codes (`{code, params, message}`) translated by the UI; numbers, dates, and currency follow the active language
- **Full traceability**: original name → canonical name → triage → index → benchmark

## Stack

| Layer | Technology |
|--------|------------|
| Backend | FastAPI (Python 3.12) |
| Search | OpenSearch 2.17 (BM25 + kNN, manual RRF fusion) |
| Frontend | Vite + React + TypeScript |
| UI | Tailwind v4 (CSS-first) + in-house shadcn-style primitives (copy-in over Radix UI + cva + cmdk + sonner) — brand tokens in `src/styles.css`/`src/styles/theme.css`, no default theme; WebGL orb (`components/OrbGL/`) with SVG fallback |
| LLM | OpenAI / Anthropic (multi-model) |
| MCP | FastMCP server (search, tags, stats tools) |
| Runtime | Docker Compose (5 services) |

The full document workflow (drop → dedup → extraction → classification → routing → indexing → embeddings → search → chat), with the observation points for each stage, is described in [`docs/workflow_documento.md`](docs/workflow_documento.md). The validation script with per-stage scores is in [`docs/plano_teste_e2e_v0.20.0.md`](docs/plano_teste_e2e_v0.20.0.md).

## Monorepo structure

```
AtlasFile/
├── backend/                 # FastAPI API, classifier, indexer, MCP server
│   ├── app/                 # Main code (main, ingestion, orchestrator, ...)
│   │   ├── api/             # Routers (profile, layout, channels)
│   │   ├── channels/        # Channels layer (Telegram, Discord, Slack)
│   │   ├── mcp/             # MCP server (tools)
│   │   ├── mcp_client/      # MCP client (chat/orchestrator)
│   │   └── prompts/         # System prompts (classify, chat)
│   ├── scripts/             # Benchmark, ML cycle, operational datasets, status
│   └── tests/               # Unit + integration (pytest)
├── frontend/                # React + TypeScript SPA
│   └── src/
│       ├── components/      # ChatPanel, ChartBlock, CompanionOrb
│       ├── features/        # ingest, profile-layout, search, settings, templates, triage, usage
│       └── hooks/           # useEscapeKey, useCompanionState
├── config/
│   ├── templates/           # Project templates (default.json, user templates)
│   ├── topics_v1.yaml       # Topic catalog derived at runtime
│   └── usage_costs.json     # $/1M token prices per provider/model
├── docs/                    # Reference documentation (benchmarking, conventions, KPIs)
├── scripts/                 # Bootstrap, smoke test, CI, reset index, dashboards
├── docker-compose.yml
├── Makefile
└── CHANGELOG.md
```

## Structure of a project

```
/<PROJECT>/
├── _INBOX_DROP/                    # Document entry point
├── _TRIAGE_REVIEW/
│   ├── pending/                    # Awaiting a human decision
│   ├── resolved/                   # Approved/corrected
│   └── rejected/                   # Rejected
├── _PROFILE/
│   ├── profile.json                # Profile V2
│   ├── ingest_history.json         # Ingestion history (FIFO, cap 50)
│   └── history/                    # Previous profile versions
├── 01_PROJECTS/
├── 02_AREAS/
│   └── <business_domain>/
│       └── <document_type>/
├── 03_RESOURCES/
├── 04_ARCHIVE/
└── _INDEX.md                       # Local record of ingested documents
```

## Classifier datasets

```text
_ATLASFILE/
  classifier/
    datasets/
      corpus.jsonl                 ← single source of truth
      corpus_files/                ← files with normalized names
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

- `corpus.jsonl` + `splits/`: consolidated corpus (~363 docs, SHA256 dedup) with stratified 70/15/15 splits
- `validation_set`: human-curated set for benchmark and acceptance, persisted only in the operational volume
- `training_pool`: live classifier snapshots and `records.jsonl`, persisted only in the operational volume
- `backend/tests/fixtures/classifier_datasets/validation_set`: minimal versioned fixture used by one integration test; it is neither an operational dataset nor a full copy of the real datasets
- `backend/scripts/build_corpus.py`: consolidates training_pool + validation_set, SHA256 dedup, generates `corpus.jsonl`
- `backend/scripts/build_splits.py`: stratified 70/15/15 partitioning

## Classifier operational cycle

- The global registry in `_ATLASFILE/classifier` persists `champion_mode`, `benchmark_enabled_modes`, promotion gates, the last cycle, and the last report.
- The operational datasets root lives in `_ATLASFILE/classifier/datasets`, outside the Docker image, with corpus, splits, `validation_set`, and `training_pool` persisted in the projects volume.
- The runtime does no silent bootstrap from the repo: if the operational dataset is empty, benchmark/cycle explicitly reflect that state.
- Each project may pin `classification.operational.override_mode`; without an override, ingestion uses the current champion.
- The runtime serves `bootstrap`, `sparse_logreg`, or `llm` and falls back explicitly to `bootstrap` if the supervised artifact is missing or fails.
- Benchmark modes are configurable from the UI; each mode can be enabled/disabled independently. Skipped modes inherit metrics from the previous cycle.
- Triage writes stable training-pool snapshots and skips documents that collide by SHA with the validation set.
- The UI exposes benchmark + retraining, per-document scorecards, the current champion, cycle cancellation, and manual override without reintroducing `baseline` as a public mode.

## Running locally

### Prerequisites

- Docker Desktop ([Mac](https://www.docker.com/products/docker-desktop/) / [Windows](https://www.docker.com/products/docker-desktop/))
- (Optional) API keys: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`

### Setup

```bash
# 1. Copy and configure the .env
cp .env.example .env
# Set PROJECTS_HOST_ROOT to the absolute path of your projects
# Recommended default: $HOME/Documents/Projects

# 2. Bring up the stack
make docker-update
```

For what each operational and technical script does, see `docs/11_scripts_and_operations.md`.

### Services

| Service | URL | Description |
|---------|-----|-----------|
| Frontend | http://localhost:5173 | Web interface (light/dark theme) |
| API | http://localhost:8000 | FastAPI (REST + SSE) |
| MCP Server | http://localhost:8001 | Tools for chat/classification |
| OpenSearch | https://localhost:9200 | Search engine (admin / `OPENSEARCH_PASSWORD` from `.env`) |
| Dashboards | http://localhost:5601 | OpenSearch Dashboards |

### Makefile

| Target | What it does |
|--------|-----------|
| `make test` | Runs all tests (backend + frontend) |
| `make docker-update` | Tests + rebuilds + brings up the stack + smoke test |
| `make docker-update RESET_INDEX=1` | Same + resets the document index |
| `make docker-update RESET_CHAT=1` | Same + resets the chat sessions index |
| `make docker-up` | Brings up the stack without running tests |
| `make reset-index` | Removes the document index |
| `make reset-chat` | Removes the chat sessions index |

## Classification flow

```text
File lands in _INBOX_DROP
         │
         ▼
   SHA256 dedup
         │
         ▼
  Text + metadata extraction
         │
         ▼
  Resolve operational mode
         │
         ├─ registry champion
         └─ project override (optional)
                 │
                 ▼
  Classify `document_type` + `business_domain`
                 │
                 ▼
   High confidence?
   ├─ Yes → moves to 02_AREAS/{business_domain}/{document_type} and indexes
   └─ No → moves to _TRIAGE_REVIEW/pending
                  │
                  ▼
          Human: Approve / Correct / Reject
                  │
                 └─ Approve/Correct → writes to _ATLASFILE/classifier/datasets/training_pool/records.jsonl
```

- `bootstrap` remains the runtime's safe fallback (current champion: 87.1% domain, 82.3% exact match)
- `sparse_logreg` and `llm` are benchmark candidates and may become the effective mode after the official cycle
- the ingestion LLM is optional and is not the primary classifier

### Learning loop (alias suggester)

Human corrections in triage feed a contrastive n-gram miner: a term is only proposed as a taxonomy alias when it appears in ≥2 corrected documents of the target class with ≥80% precision, measured against at least 2 documents of other classes also decided in triage (no contrast, no signal). Suggestions appear in the Classifier with their evidence (support and precision), a toast announces newly mined terms right after the triage decision, and approving a term appends the alias to the default template and to every project profile — the next classification recognizes the vocabulary immediately. Everything is human-approved; nothing is auto-applied. To relabel an already-routed document without losing this learning, use the governed move (⇄) in the processing history — it relocates the file, reindexes and rewrites the training signal in one step (manual filesystem moves do none of that).

## Resilience and self-healing

The projects root (the `PROJECTS_HOST_ROOT` bind mount) is monitored by a health probe with three states exposed in `/api/setup/status`: `ok`, `unavailable` (broken mount / permission lost) and `emptied` (host folder deleted under a live bind mount — on macOS/VirtioFS the container keeps seeing a healthy-looking empty "ghost" directory whose writes would be silently lost). In both failure states the UI opens a recovery modal: one click restarts the app gracefully, the `restart: unless-stopped` policy brings the container back, Docker recreates the missing host folder and re-binds the mount, the orphaned index is cleaned by a global reconcile and the setup wizard reopens. While broken, uploads, inbox scans and project creation are blocked with stable error codes (`PROJECTS_ROOT_UNAVAILABLE`, `PROJECTS_ROOT_EMPTIED`), and the orphan cleanup is skipped — a transient mount failure can never wipe the index.

## Observability dashboard (OpenSearch Dashboards)

The stack ships a complete "AtlasFile — Operação" dashboard (18 panels over 3 index patterns): collection pulse (documents, projects, average confidence, LLM cost, chat sessions), catalog breakdowns (business domain, `doc_kind`, document type, per-project table), ingestion flow over time by decision, confidence distribution, classifier mode, extraction/embedding health, LLM cost per day and model, and a topic tag cloud. It is **imported automatically** when the API boots (background thread with retry; `DASHBOARDS_URL` / `DASHBOARDS_AUTO_IMPORT` control it) — open <http://localhost:5601> and log in with `admin` + your `OPENSEARCH_PASSWORD` from `.env`. The set is generated by `backend/scripts/build_dashboards_ndjson.py` (edit there, re-run, done); manual import file: `dashboards/atlasfile.ndjson`.

## Naming convention (canonical)

Format configurable via `naming.canonical_pattern` in the template/profile. Default:

```
{date}__{project}__{original_name}__v{version}{ext}
```

Example: `20260301__kaido__Contrato_Migracao_Clientes__v01.xlsx`

The placeholders supported by the active contract are `date`, `project`, `business_domain`, `document_type`, and `original_name`; `{area}` is rejected by the schema. On a `correct` triage, the system recomposes the canonical name preserving the ingestion date and the already-issued version. See `docs/04_naming_convention.md` for details.

## Environment variables

| Variable | Description | Default |
|----------|-----------|---------|
| `PROJECTS_HOST_ROOT` | Absolute path of the projects on the host | (required) |
| `CLASSIFIER_DATASETS_ROOT` | Operational root of the classifier datasets | `/projects/_ATLASFILE/classifier/datasets` |
| `OPENAI_API_KEY` | OpenAI key (chat + classification) | — |
| `ANTHROPIC_API_KEY` | Anthropic key (chat) | — |
| `MOONSHOT_API_KEY` | Moonshot (Kimi) key — OpenAI-compatible provider | — |
| `MOONSHOT_BASE_URL` | Moonshot endpoint | `https://api.moonshot.ai/v1` |
| `OLLAMA_BASE_URL` | Local Ollama endpoint (no key needed) | `http://host.docker.internal:11434/v1` in Docker |
| `CLASSIFICATION_LLM_ENABLED` | Enable the LLM in the ingestion flow | `false` |
| `DEFAULT_LLM_PROVIDER` | Default provider | `openai` |
| `DEFAULT_LLM_MODEL` | Default model | `gpt-4o-mini` |
| `AUTO_RECONCILE_INTERVAL_SECONDS` | Automatic reconciliation interval | `600` |

See `.env.example` for the full list.

### Custom models (Ollama / Moonshot)

Ollama models are not listed in the catalog on purpose — the models are whatever *you* pulled locally. To use one: open the assistant settings (gear in the chat), type `provider/model` in the model combobox — e.g. `ollama/gemma3:12b`, exactly as shown by `ollama list` — and the live validation checks it against your endpoint (no key needed for Ollama). Once validated, the model appears in the chat selector as "validated by you" and can also be set as the project's triage model. The same flow works for any Moonshot model id (`moonshot/…`, requires `MOONSHOT_API_KEY`). Note: small local models may not support tool calls — the chat then answers directly, without cited search.

## MCP Tools (for LLMs and integrations)

| Tool | Description |
|------|-----------|
| `list_documents` | Document listing/browsing with filters by project, `business_domain`, and `document_type` |
| `search_documents` | Full-text search with filters by project, `business_domain`, `document_type`, tags, and dates |
| `get_stats` | Aggregated statistics by `doc_kind`, `business_domain`, `document_type`, and `project_id` |
| `get_document` | Metadata + chunks of a document |
| `get_document_chunks` | Specific chunks by location (page:N, sheet:Name) |
| `spreadsheet_schema` | Sheets, columns, and a sample of a spreadsheet (xlsx/csv) for structured querying |
| `spreadsheet_query` | SELECT (DuckDB, read-only) directly against the original file — exact counts and aggregations |
| `apply_tags` | Adds/removes tags |
| `set_metadata` | Updates `document_type`, `business_domain`, `correspondent`, and `review_status` |
| `submit_classification` | Supports LLM-driven classification/review when the configured flow requires it |

## Tests

```bash
make test              # Backend (pytest) + Frontend (vitest)
make test-backend      # Backend only
make test-frontend     # Frontend only
```

The suites cover classifier lifecycle, benchmark, datasets, ingestion, triage, search, templates, profile/layout, channels, usage/cost, API, and frontend.

## Documentation

- `CHANGELOG.md` — version history
- `INSTALL.md` — detailed install guide (Mac/Windows)

### Technical reference (`docs/`)

| Doc | Contents |
|-----|----------|
| `01_benchmarking.md` | References (NARA, ISO 15489, FAIR, Johnny.Decimal, BM25) |
| `02_gap_analysis.md` | Gap analysis that motivated the project |
| `03_framework_template.md` | Project structure and ingestion cycle |
| `04_naming_convention.md` | Canonical naming convention |
| `05_index_models.md` | Index model (_INDEX.md + OpenSearch, 35+ fields) |
| `06_retention_policy.md` | Retention policy (roadmap) |
| `07_rollout_kpis.md` | Rollout phases and KPIs |
| `08_project_profile_template.md` | Profile V2 template (JSON) with a complete example |
| `09_field_mapping.md` | Complete field mapping: origin, derivation, LLM usage |
| `10_classifier_design.md` | Classifier design: operational runtime, benchmark, promotion, and fallback |
| `plano_teste_e2e_v0.8.0.md` | E2E delta script for 0.8.0, oriented to testing through the frontend |
| `plano_teste_e2e_v0.7.0.md` | Recorded E2E baseline reused as the reference for the real batch |
| `agent-tools-flow.md` | MCP → LLM → tools flow (how the agent receives and uses tools) |

Completed implementation plans live in `docs/planos_concluidos/` as a record of decisions. Future evolutions under evaluation (with an explicit execution trigger) live in `docs/ROADMAP.md`.

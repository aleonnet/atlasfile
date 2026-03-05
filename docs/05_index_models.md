# Modelo de índice

## `_INDEX.md` (por projeto)

Registro local em Markdown com campos mínimos por documento ingerido:

- `doc_id` — identificador único (UUID4)
- `project_id` — identificador do projeto
- `original_filename` — nome original do arquivo
- `canonical_filename` — nome canônico gerado
- `current_path` — path final do arquivo
- `area_key` — área de classificação
- `source_channel` — canal de origem
- `source_ref` — referência da fonte
- `sender` — remetente
- `received_at` — timestamp de recebimento
- `ingested_at` — timestamp de processamento
- `decision` — `auto`, `triage_pending`, `duplicate`
- `confidence_score` — confiança da classificação
- `sha256` — hash do arquivo

## OpenSearch mapping (`atlasfile_documents`)

Índice principal com 35+ campos, definido em `backend/app/opensearch_client.py`:

### Identificação

| Campo | Tipo | Origem |
|-------|------|--------|
| `doc_id` | keyword | UUID4 gerado na ingestão |
| `project_id` | keyword | Profile do projeto |
| `area_key` | keyword | Classificação (rules/aliases/LLM) |

### Título

| Campo | Tipo | Origem |
|-------|------|--------|
| `title` | text | `inbox_file.stem` |
| `title_normalized` | text | `normalize_text(title)` |
| `title_suggest` | search_as_you_type | Autocomplete |

### Conteúdo

| Campo | Tipo | Origem |
|-------|------|--------|
| `content` | text | `extract_document_content()` |
| `content_normalized` | text | `normalize_text(content)` |
| `content_chunks` | nested | `{location, text, text_normalized}` — chunking (1200 chars) |
| `content_chunks_text` | text | Chunks concatenados |
| `content_chunks_normalized` | text | Chunks normalizados |
| `chunk_locations` | keyword | IDs dos chunks (ex: `page:1`, `sheet:Plan1`) |

### Extração

| Campo | Tipo | Origem |
|-------|------|--------|
| `content_type` | keyword | MIME type da extração |
| `extraction_status` | keyword | `ok`, `partial`, `error` |
| `extraction_metadata` | object (disabled) | Metadados da extração |

### Nomes de arquivo

| Campo | Tipo | Origem |
|-------|------|--------|
| `original_filename` | keyword | Nome original |
| `original_filename_text` | text | Full-text search |
| `original_filename_normalized` | text | Normalizado |
| `original_filename_suggest` | search_as_you_type | Autocomplete |
| `canonical_filename` | keyword | `YYYYMMDD__proj__area__title__vNN.ext` |
| `canonical_filename_text` | text | Full-text search |
| `canonical_filename_normalized` | text | Normalizado |

### Localização e metadados

| Campo | Tipo | Origem |
|-------|------|--------|
| `path` | keyword | Path final do arquivo |
| `extension` | keyword | `.pdf`, `.docx`, etc. |
| `doc_kind` | keyword | `pdf`, `docx`, `plain_text`, etc. |
| `source_channel` | keyword | Canal de origem |
| `source_ref` | keyword | Referência |
| `sender` | keyword | Remetente |

### Timestamps

| Campo | Tipo | Origem |
|-------|------|--------|
| `received_at` | date | Timestamp de recebimento |
| `ingested_at` | date | Timestamp de processamento |
| `processed_at` | date | Timestamp de pós-processamento |

### Classificação e decisão

| Campo | Tipo | Origem |
|-------|------|--------|
| `decision` | keyword | `auto`, `triage_pending`, `duplicate` |
| `confidence_score` | float | Score do classificador |
| `sha256` | keyword | Hash do arquivo |
| `review_status` | keyword | `needs_review` se confiança < threshold |

### Enriquecimento (regras + LLM)

| Campo | Tipo | Origem |
|-------|------|--------|
| `tags` | keyword (array) | `[area_key]` + tags do LLM |
| `document_type` | keyword | Tipo do documento (LLM) |
| `correspondent` | keyword | Correspondente (LLM) |
| `topics` | keyword (array) | `match_topics()` ou LLM |
| `topics_source` | keyword | `synonym_match`, `llm_policy`, `none` |

## OpenSearch mapping (`atlasfile_chat_sessions`)

Índice separado para sessões de chat:

| Campo | Tipo |
|-------|------|
| `title` | text |
| `messages` | object |
| `model` | keyword |
| `createdAt` | date |
| `updatedAt` | date |

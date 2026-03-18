# Modelo de indice

## `_INDEX.md` por projeto

`_INDEX.md` continua sendo o registro local de rastreabilidade, mas no runtime atual ele ainda usa uma linha compacta em Markdown.

Colunas persistidas hoje:

- `doc_id`
- `project_id`
- `area`
- `original_filename`
- `canonical_filename`
- `decision`
- `confidence_score`
- `path`
- `naming_pattern`

Observacoes:

- a coluna `area` recebe o valor de `area_key`, que hoje espelha `business_domain`
- `document_type` e `sha256` ficam no indice OpenSearch e nos metadados do fluxo, nao em coluna dedicada do `_INDEX.md`
- por isso a rastreabilidade completa precisa considerar `_INDEX.md` + OpenSearch

## OpenSearch: `atlasfile_documents`

O mapping atual fica em `backend/app/opensearch_client.py`.

### Eixos canonicos

| Campo | Tipo | Observacao |
|-------|------|------------|
| `business_domain` | keyword | Eixo funcional principal |
| `document_type` | keyword | Eixo formal principal |
| `area_key` | keyword | Espelho de `business_domain` para compatibilidade |

### Busca por titulo e nomes

| Campo | Tipo | Observacao |
|-------|------|------------|
| `title` | text | Titulo derivado do nome do arquivo |
| `title_normalized` | text | Busca sem acentos |
| `title_ocr_folded` | text | Busca robusta a OCR |
| `title_suggest` | search_as_you_type | Suggest |
| `original_filename` | keyword | Nome original bruto |
| `original_filename_text` | text | Busca lexical |
| `original_filename_normalized` | text | Busca sem acentos |
| `original_filename_ocr_folded` | text | Busca robusta a OCR |
| `original_filename_suggest` | search_as_you_type | Suggest |
| `canonical_filename` | keyword | Nome canonico persistido |
| `canonical_filename_text` | text | Busca lexical |
| `canonical_filename_normalized` | text | Busca sem acentos |
| `canonical_filename_ocr_folded` | text | Busca robusta a OCR |

### Conteudo textual

Todo o conteudo indexado permanece em `content_chunks` no modelo `pure nested`.

| Campo | Tipo | Observacao |
|-------|------|------------|
| `chunk_locations` | keyword | `page:1`, `slide:2`, `sheet:Plan1` etc |
| `content_chunks.location` | keyword | Localidade do trecho |
| `content_chunks.text` | text | Busca full-text |
| `content_chunks.text_normalized` | text | Busca sem acentos |
| `content_chunks.text_ocr_folded` | text | Busca robusta a OCR |

Campos flat de conteudo continuam fora do indice.

### Extracao e metadados tecnicos

| Campo | Tipo | Observacao |
|-------|------|------------|
| `content_type` | keyword | MIME type |
| `extraction_status` | keyword | `ok`, `partial`, `error` |
| `extraction_metadata` | object disabled | Storage tecnico, sem indexacao |
| `doc_kind` | keyword | Categoria derivada da extensao |
| `extension` | keyword | Extensao do arquivo |

### Decisao, confianca e triagem

| Campo | Tipo | Observacao |
|-------|------|------------|
| `decision` | keyword | `auto`, `triage_pending`, `duplicate` |
| `confidence_score` | float | Gate geral de roteamento |
| `business_domain_confidence` | float | Confianca do eixo funcional |
| `document_type_confidence` | float | Confianca do eixo formal |
| `review_status` | keyword | `needs_review` quando aplicavel |
| `tags` | keyword | Tags leves de classificacao |
| `topics` | keyword | Topics detectados |
| `topics_source` | keyword | Origem dos topics |
| `entities` | object disabled | Entidades extraidas |
| `sha256` | keyword | Integridade e dedup |

### Proveniencia e datas

| Campo | Tipo | Observacao |
|-------|------|------------|
| `project_id` | keyword | Escopo por projeto |
| `path` | keyword | Path final do arquivo |
| `source_channel` | keyword | Canal de origem |
| `source_ref` | keyword | Referencia externa |
| `sender` | keyword | Remetente |
| `received_at` | date | Data recebida |
| `ingested_at` | date | Data de ingestao |
| `processed_at` | date | Data de processamento |
| `correspondent` | keyword | Metadado opcional |

## Indice de sessoes: `atlasfile_chat_sessions`

| Campo | Tipo |
|-------|------|
| `title` | text |
| `messages` | object |
| `model` | keyword |
| `createdAt` | date |
| `updatedAt` | date |
| `project_id` | keyword |
| `usage_totals` | object |
| `usage_by_model` | object disabled |
| `channel` | keyword |
| `channel_chat_id` | keyword |

## Indice de uso de classificacao: `atlasfile_classification_usage`

Indice separado para rastrear custo/uso de LLM na classificacao quando o LLM estiver habilitado.

| Campo | Tipo |
|-------|------|
| `doc_id` | keyword |
| `filename` | keyword |
| `project_id` | keyword |
| `provider` | keyword |
| `model` | keyword |
| `timestamp` | date |
| `input_tokens` | integer |
| `output_tokens` | integer |
| `cache_read_input_tokens` | integer |
| `cache_creation_input_tokens` | integer |
| `estimated_cost_usd` | float |

## Notas de arquitetura

- `mapping.nested_objects.limit` e configurado dinamicamente no indice de documentos.
- Busca e highlight usam `content_chunks`; a resposta de leitura pode recompor `content` on-the-fly, mas esse campo nao e persistido no mapping.
- Os campos `*_ocr_folded` foram adicionados para melhorar busca em documentos com OCR ruidoso.

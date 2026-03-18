# Mapeamento de campos -- origem, derivacao e uso

Este documento reflete o estado atual da 0.7.0. O eixo operacional do AtlasFile e `business_domain`; o campo `area_key` continua existindo como espelho do mesmo valor para compatibilidade de API e indice.

## 1) Indice principal: `atlasfile_documents`

### Identidade e nomes

| Campo | Tipo OS | Produzido por | Uso principal |
|-------|---------|---------------|---------------|
| `doc_id` | keyword | UUID gerado na ingestao | Chave primaria do documento |
| `project_id` | keyword | `profile.project_id` | Escopo por projeto |
| `business_domain` | keyword | Bootstrap ou decisao humana | Eixo funcional operacional |
| `area_key` | keyword | Mesmo valor de `business_domain` | Compatibilidade de payload e filtros antigos |
| `original_filename` | keyword | Nome original do arquivo | Exibicao e auditoria |
| `original_filename_text` | text | Enriquecimento de busca | Busca lexical por nome |
| `original_filename_normalized` | text | Enriquecimento de busca | Busca sem acentos |
| `original_filename_ocr_folded` | text | Enriquecimento de busca | Busca robusta a OCR com espacos espurios |
| `original_filename_suggest` | search_as_you_type | Enriquecimento de busca | Suggest/autocomplete |
| `canonical_filename` | keyword | `build_canonical_filename()` | Nome canonico persistido |
| `canonical_filename_text` | text | Enriquecimento de busca | Busca lexical por nome canonico |
| `canonical_filename_normalized` | text | Enriquecimento de busca | Busca sem acentos |
| `canonical_filename_ocr_folded` | text | Enriquecimento de busca | Busca robusta a OCR |
| `path` | keyword | Destino final no filesystem | Download e reconcile |
| `extension` | keyword | Extensao do arquivo | Filtros |
| `doc_kind` | keyword | Derivado da extensao | Filtros e UI |

### Conteudo e extração

Todo o texto indexado fica em `content_chunks`. Campos flat de conteudo nao existem no indice.

| Campo | Tipo OS | Produzido por | Uso principal |
|-------|---------|---------------|---------------|
| `title` | text | `inbox_file.stem` | Ranking por titulo |
| `title_normalized` | text | Enriquecimento de busca | Busca sem acentos |
| `title_ocr_folded` | text | Enriquecimento de busca | Busca robusta a OCR |
| `title_suggest` | search_as_you_type | Enriquecimento de busca | Suggest/autocomplete |
| `chunk_locations` | keyword | Extrator/indexer | Exibicao de pagina, slide ou sheet |
| `content_chunks.location` | keyword | Extrator/indexer | Localidade do trecho |
| `content_chunks.text` | text | Extrator/indexer | Busca full-text e highlight |
| `content_chunks.text_normalized` | text | Extrator/indexer | Busca sem acentos |
| `content_chunks.text_ocr_folded` | text | Extrator/indexer | Busca robusta a OCR |
| `content_type` | keyword | Extrator | MIME type |
| `extraction_status` | keyword | Extrator | `ok`, `partial`, `error` |
| `extraction_metadata` | object disabled | Extrator | Storage de metadados tecnicos |

### Classificacao, triagem e enriquecimento

| Campo | Tipo OS | Produzido por | Uso principal |
|-------|---------|---------------|---------------|
| `decision` | keyword | Ingestao | `auto`, `triage_pending`, `duplicate` |
| `confidence_score` | float | Ingestao | Gate geral de auto-route |
| `business_domain_confidence` | float | Bootstrap | Confianca do eixo funcional |
| `document_type_confidence` | float | Bootstrap | Confianca do eixo formal |
| `document_type` | keyword | Bootstrap ou decisao humana | Eixo formal operacional |
| `tags` | keyword | Ingestao e LLM opcional | Facetas leves e sinalizacao |
| `topics` | keyword | `match_topics()` ou LLM opcional | Contexto transversal |
| `topics_source` | keyword | Ingestao | `synonym_match`, `llm_policy` ou equivalente |
| `entities` | object disabled | Bootstrap | Entidades extraidas para auditoria e uso futuro |
| `review_status` | keyword | Ingestao | `needs_review` quando cai em triagem |
| `correspondent` | keyword | Metadado opcional | Filtro/exibicao |
| `sha256` | keyword | Ingestao | Dedup e integridade |

### Proveniencia e datas

| Campo | Tipo OS | Produzido por | Uso principal |
|-------|---------|---------------|---------------|
| `source_channel` | keyword | Ingestao/canais | Rastreabilidade |
| `source_ref` | keyword | Ingestao/canais | Rastreabilidade |
| `sender` | keyword | Ingestao/canais | Rastreabilidade |
| `received_at` | date | Ingestao/canais | Timeline do documento |
| `ingested_at` | date | Ingestao | Auditoria e filtros |
| `processed_at` | date | Ingestao | Auditoria e ordenacao |

## 2) Campos de pipeline/UI que nao estao no mapping do indice

Esses campos aparecem em payloads, historico ou UI, mas nao fazem parte do mapping persistido de `atlasfile_documents`.

| Campo | Onde nasce | Finalidade |
|-------|------------|------------|
| `content` | Ingestao / resposta de leitura | Excerpt temporario ou conteudo recomposto; nao e campo indexado |
| `rule_area_key` | Fluxo de classificacao com LLM | Mostrar a classificacao deterministica original antes de eventual revisao |
| `rule_confidence` | Fluxo de classificacao com LLM | Mostrar confianca anterior |
| `llm_explanation` | LLM opcional | Auditoria da revisao |
| `llm_proposed_area` | LLM opcional | Rastrear sugestao fora do catalogo |
| `classification_reason` | Bootstrap/ingestao | Motivo resumido da decisao |

## 3) Outros indices

### `atlasfile_chat_sessions`

| Campo | Tipo OS | Uso principal |
|-------|---------|---------------|
| `title` | text | Titulo da sessao |
| `messages` | object | Historico do chat |
| `model` | keyword | Modelo usado |
| `createdAt` | date | Auditoria |
| `updatedAt` | date | Auditoria |
| `project_id` | keyword | Escopo do assistente por projeto |
| `usage_totals` | object | Totais agregados de uso/custo |
| `usage_by_model` | object disabled | Breakdown tecnico |
| `channel` | keyword | Origem web/Telegram |
| `channel_chat_id` | keyword | Vinculo com o canal |

### `atlasfile_classification_usage`

Indice separado para custo/uso do LLM na classificacao documental quando o LLM estiver habilitado.

| Campo | Tipo OS |
|-------|---------|
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

## 4) Fluxo resumido

```mermaid
flowchart TD
    A[_INBOX_DROP] --> B[Bootstrap: document_type + entities + business_domain]
    B --> C[Thresholds: auto ou triage]
    C --> D[_INDEX.md]
    C --> E[atlasfile_documents]
    E --> F[/api/search e suggest]
    E --> G[MCP search_documents e list_documents]
    E --> H[Assistente web e Telegram]
```

## 5) Observacoes importantes

- `business_domain` e `document_type` sao os dois eixos canonicos da 0.7.0.
- `area_key` nao representa uma segunda taxonomia; hoje ele espelha `business_domain`.
- Os campos `*_ocr_folded` existem para mitigar ruido de OCR em nomes e conteudo.
- O indice continua em arquitetura `pure nested`: highlight e busca full-text operam sobre `content_chunks`.

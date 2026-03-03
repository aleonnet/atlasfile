# Modelo de indice

## `_INDEX.md` (por projeto)

Campos minimos por item:

- `doc_id`
- `project_id`
- `original_filename`
- `canonical_filename`
- `current_path`
- `area_key`
- `source_channel`
- `source_ref`
- `sender`
- `received_at`
- `ingested_at`
- `processed_at`
- `decision` (`auto`, `approved`, `corrected`, `rejected`)
- `confidence_score`
- `sha256`

## `_GLOBAL_INDEX.md` (opcional)

Agrega visao resumida por projeto:

- volume por area;
- pendencias de triagem;
- ultimas ingestoes;
- principais erros.

## OpenSearch mapping (resumo)

Campos principais:

- `doc_id` (keyword)
- `project_id` (keyword)
- `area_key` (keyword)
- `title` (text)
- `content` (text)
- `tags` (keyword)
- `path` (keyword)
- `source_channel` (keyword)
- `received_at` (date)
- `ingested_at` (date)
- `confidence_score` (float)
- `sha256` (keyword)

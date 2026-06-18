# PoC: MarkItDown vs Extrator AtlasFile (`extractor-benchmark_mdxaf`)

> Plano concluído em 2026-06-17. PoC de tooling — não altera backend, frontend nem o `extractor-benchmark/` existente.

## Context

O AtlasFile já tinha um benchmark de extração (`extractor-benchmark/`), porém **page-scoped e exclusivo de PDF** (QA pairs por página, ground truth via Claude Vision, LLM-as-judge). Isso não serve para comparar dois extratores **whole-document e multi-formato**:

- **MarkItDown** (Microsoft) — `MarkItDown().convert(path).text_content`, converte para Markdown.
- **Extrator do AtlasFile** — `extract_document_content(path, max_chars)` (`backend/app/document_extractor.py:639-681`), cobre PDF (pymupdf + OCR Tesseract), DOCX, XLSX, PPTX, MSG.

Corpus: pasta `…/Contrato` (3 PDF, 1 DOCX, 1 PPTX, 1 XLSX).

**Decisões validadas com o usuário:**
1. Métrica = **só lado-a-lado qualitativo** (sem LLM-judge, sem ground truth, sem custo de API).
2. MarkItDown = **vanilla** (sem LLM/Azure). Assimetria de OCR explicitada.
3. Corpus = **só os 6 arquivos da pasta Contrato**.

## Mudanças entregues

Nova pasta `extractor-benchmark_mdxaf/` (irmã de `extractor-benchmark/`):
- `extractors/base.py` — dataclass `ExtractResult` (whole-document).
- `extractors/atlasfile_extractor.py` — wrapper de `extract_document_content` (adiciona `backend/` ao `sys.path`).
- `extractors/markitdown_extractor.py` — wrapper de `MarkItDown(enable_plugins=False)` com fallback de construtor.
- `scripts/setup_corpus.py` — copia os 6 arquivos (pathlib/shutil; idempotente).
- `scripts/run_compare.py` — roda os dois extratores, mede latência (mediana de N + warmup, `tracemalloc`), grava outputs e métricas objetivas; produz `summary.json` + `summary.md`.
- `requirements.txt` (markitdown + libs de extração pinadas ao backend), `README.md`, `.gitignore` (corpus/, results/, .venv/, .env), `ACHADOS.md`.

Métricas objetivas (sem LLM): `char_count`, `word_count`, `nonblank_line_count`, `pipe_table_rows`, `md_table_blocks`, `numeric_density`, `latency_ms`, `peak_memory_mb`, `text_length_ratio`.

## Resultados (run1, 1 run por arquivo)

- **PDF escaneado (Anexo 28 MB)**: AtlasFile 228.677 chars via OCR (~4 min); **MarkItDown vazio (0 bytes) após ~24 min**. MarkItDown vanilla não faz OCR de PDF → inviável para escaneados.
- **PDF nativo (Contrato VTAL)**: MarkItDown extrai mais chars (421k vs 298k) **porém com pior qualidade** — perde espaçamento entre palavras e fabrica tabelas falsas. AtlasFile (extração espacial) preserva espaços e foi ~20x mais rápido.
- **XLSX**: trade-off — MarkItDown gera tabela Markdown compacta (mas lê header errado → `Unnamed`); AtlasFile gera coordenadas por célula (melhor p/ RAG). Sem gap de cobertura (1 sheet).
- **DOCX/PPTX**: empate em conteúdo; MarkItDown mais rico em formatação Markdown, AtlasFile mais rápido e com marcadores de localização.

**Conclusão**: o extrator do AtlasFile é superior nos casos que mais importam ao pipeline (PDF nativo e escaneado, fidelidade textual, localização p/ busca/RAG). MarkItDown só agregaria como gerador complementar de Markdown estruturado de Office, e ainda assim exigiria OCR habilitado. Detalhes em `extractor-benchmark_mdxaf/ACHADOS.md`.

## Verificação executada
- `setup_corpus.py` copiou 6 arquivos. `run_compare.py` terminou com exit 0; `results/run1/outputs/` com 12 arquivos.
- Imports dos dois extratores validados (smoke test). Anexo MarkItDown confirmado vazio (0 bytes); XLSX confirmado 1 sheet coberta por ambos.

## Pendência
- **Bump de versão frontend**: não aplicado — PoC não toca `frontend/`. Decisão de versionamento deixada para o usuário (entrada de CHANGELOG provisória em "Não versionado / Ferramental").

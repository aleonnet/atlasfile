# Sessao: Benchmark de extracao PDF e migracao pypdf -> pymupdf

**Data**: 2026-03-27/28
**Escopo**: Avaliar qualidade de extracao PDF (inspirado pelo LiteParse) e migrar de pypdf para pymupdf

## Contexto

O LiteParse (LlamaIndex) usa parsing espacial via PDF.js para extrair texto de PDFs preservando layout 2D. Investigamos se essa abordagem seria superior ao extrator atual do AtlasFile (pypdf).

## Analise: AtlasFile vs LiteParse

| Formato | Vantagem | Motivo |
|---------|----------|--------|
| PDF (layout complexo) | LiteParse | Parsing espacial preserva colunas e tabelas |
| DOCX | AtlasFile | XML direto com paginacao real vs conversao LibreOffice |
| XLSX | AtlasFile | Celula a celula com localizacao vs conversao para PDF |
| PPTX | AtlasFile | Shapes e tabelas nativos vs conversao para PDF |
| MSG/HTML/texto | AtlasFile | Suportados nativamente, LiteParse nao suporta |

**Decisao**: LiteParse introduziria Node.js + LibreOffice no stack Docker. Melhor replicar a abordagem de parsing espacial em Python puro com pymupdf.

## Benchmark criado: extractor-benchmark/

Projeto independente em `extractor-benchmark/` comparando 3 providers:
- `atlasfile_pypdf` (extrator atual)
- `pymupdf_spatial` (parsing espacial com bounding boxes)
- `pdfplumber` (layout preservado + deteccao de tabelas)

### Metodologia
- Ground truth: Claude Vision gera QA pairs a partir de screenshots (max 5 paginas/doc)
- Avaliacao: LLM responde QA usando texto extraido, LLM-as-judge avalia pass/fail
- Performance: latencia e pico de memoria (max 20 paginas/doc)

### Corpus
10 PDFs reais distribuidos em: simple (2), multicolumn (1), tables (2), scanned (2), mixed (3)

### Resultados de qualidade (216 QA pairs)

| Provider | Pass Rate |
|----------|----------|
| atlasfile_pypdf | 76.4% |
| pymupdf_spatial | 75.9% |
| pdfplumber | 76.9% |

**Conclusao**: qualidade equivalente entre os 3 providers (~76%).

### Resultados de performance (20 paginas max)

| Provider | Avg ms | Avg MB | ms/page |
|----------|--------|--------|---------|
| atlasfile_pypdf | 18,855 | 18.2 | 1,376 |
| pymupdf_spatial | 5,352 | 4.3 | 391 |
| pdfplumber | 23,399 | 124.5 | 1,708 |

**Conclusao**: pymupdf 3.5x mais rapido, 4.2x menos memoria. pdfplumber descartado.

Destaque: PDF de 244 paginas (Docusign) — pymupdf 1.2s vs pypdf 77.8s (64x mais rapido).

## Migracao executada

### Arquivos alterados
1. `backend/requirements.txt`: `pypdf==5.9.0` -> `pymupdf>=1.25.0`
2. `backend/app/document_extractor.py`: funcao `_extract_pdf` reescrita + nova `_spatial_extract_page`
3. `backend/tests/unit/test_document_extractor.py`: +5 testes novos + helper `_write_multipage_pdf`

### Testes novos
- `test_extract_pdf_multipage` — PDF com 3 paginas
- `test_extract_pdf_metadata_pages` — metadata["pages"] correto
- `test_extract_pdf_max_chars_early_stop` — early termination funciona
- `test_extract_pdf_empty_page_skipped` — pagina vazia ignorada
- `test_extract_pdf_ocr_fallback_called` — OCR chamado quando texto < 50 chars

### Resultado
- 365 testes passando (360 existentes + 5 novos), 0 falhas
- Interface `ExtractionResult` inalterada
- OCR fallback (pdf2image + Tesseract) inalterado
- Zero impacto em consumidores (indexer.py, classifier_cycle.py)

## Decisoes e aprendizados

- Scripts de benchmark devem ser incrementais com resultados parciais e resume (evitar reprocessamento apos erro)
- Performance benchmarks devem limitar paginas (max 20) para PDFs grandes
- A diretiva de planos unicos foi adicionada ao CLAUDE.md
- Resumos de sessao ficam em `docs/claude_chats/`

## Planos de implementacao

- `docs/planos_concluidos/benchmark_extracao_pdf_a1b2c3d4.plan.md` — benchmark de extracao PDF
- `docs/planos_concluidos/migracao_pypdf_para_pymupdf_e5f6g7h8.plan.md` — migracao pypdf -> pymupdf

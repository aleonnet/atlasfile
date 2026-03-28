# Plano: Migrar extração PDF de pypdf para pymupdf

## Contexto

O benchmark `extractor-benchmark` comparou 3 providers de extração PDF em 10 documentos reais (216 QA pairs):
- **Qualidade equivalente**: atlasfile_pypdf 76.4%, pymupdf_spatial 75.9%, pdfplumber 76.9%
- **Performance**: pymupdf é 3.5x mais rápido e usa 4.2x menos memória que pypdf
- Em PDFs escaneados grandes (244p), pymupdf foi **64x mais rápido** porque extrai texto nativo onde pypdf falha e cai no OCR

O objetivo é substituir `pypdf` por `pymupdf` na função `_extract_pdf` do AtlasFile, mantendo a interface `ExtractionResult` idêntica e todos os 360 testes passando.

## Arquivos a modificar

### 1. `backend/app/document_extractor.py` (linhas 200-238)

Substituir a função `_extract_pdf`. Mudanças:

**Antes (pypdf):**
```python
def _extract_pdf(path: Path, max_chars: int) -> ExtractionResult:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    pages = len(reader.pages)
    ...
    for idx, page in enumerate(reader.pages, start=1):
        page_text = (page.extract_text() or "").strip()
```

**Depois (pymupdf com extração espacial):**
```python
def _extract_pdf(path: Path, max_chars: int) -> ExtractionResult:
    import pymupdf
    doc = pymupdf.open(str(path))
    pages = len(doc)
    ...
    for idx in range(pages):
        page = doc[idx]
        page_text = _spatial_extract_page(page)
        # OCR fallback segue igual
    ...
    doc.close()
```

Adicionar a função `_spatial_extract_page` (portada do benchmark `extractor-benchmark/providers/pymupdf_spatial.py` linhas 49-117) antes de `_extract_pdf`. Esta função:
- Usa `page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)`
- Agrupa spans por proximidade vertical (Y) em linhas
- Ordena por X dentro de cada linha
- Reconstrói texto com padding espacial para preservar colunas

A função `_ocr_pdf_page` (linhas 178-197) **não muda** — usa `pdf2image` + `pytesseract`, independente da lib de leitura.

O restante da função (`_format_chunks`, chunking, early termination, `ExtractionResult`) permanece **idêntico**.

### 2. `backend/requirements.txt` (linha 9)

- Remover: `pypdf==5.9.0`
- Adicionar: `pymupdf>=1.25.0`

### 3. `backend/tests/unit/test_document_extractor.py`

O teste existente `test_extract_pdf_from_generated_real_file` (linha 241) **continua passando sem alteração** — já validei que `pymupdf` lê o PDF gerado pelo helper `_write_simple_pdf`.

Adicionar 5 testes novos **após** o teste existente (linha 252):

#### `test_extract_pdf_multipage`
- Cria PDF com 3 páginas via `pymupdf` (doc.new_page + insert_text)
- Valida: `chunk_locations` contém `page:1`, `page:2`, `page:3`
- Valida: texto de cada página presente no `text_excerpt`

#### `test_extract_pdf_metadata_pages`
- Cria PDF com 3 páginas
- Valida: `metadata["pages"] == 3`

#### `test_extract_pdf_max_chars_early_stop`
- Cria PDF com 5 páginas com texto longo (~3000 chars/página)
- Chama com `max_chars=3000`
- Valida: extração parou antes de processar todas as 5 páginas (verifica que nem todas as page locations estão presentes)

#### `test_extract_pdf_empty_page_skipped`
- Cria PDF com 3 páginas, sendo a 2a vazia
- Valida: `chunk_locations` contém `page:1` e `page:3` mas **não** `page:2`

#### `test_extract_pdf_ocr_fallback_called`
- Cria PDF com 1 página com texto < 50 chars
- Usa `monkeypatch` para mockar `_ocr_pdf_page` retornando texto OCR
- Valida: texto OCR mockado aparece no `text_excerpt`

Helper novo `_write_multipage_pdf(path, texts: list[str])`:
- Usa `pymupdf` para criar PDF com N páginas, cada uma com o texto correspondente
- Reutilizado por todos os testes novos

## Verificação

1. Rodar o teste existente isolado: `cd backend && .venv/bin/python -m pytest tests/unit/test_document_extractor.py::test_extract_pdf_from_generated_real_file -v`
2. Rodar todos os testes de extração: `cd backend && .venv/bin/python -m pytest tests/unit/test_document_extractor.py -v`
3. Rodar suite completa: `cd backend && .venv/bin/python -m pytest tests/ -v` — deve manter 360+ testes passando (360 existentes + 5 novos = 365)

## O que NÃO muda

- `ExtractionResult` dataclass
- `_format_chunks`, `_split_chunks`, `_safe_excerpt`, `_chunks_from_rows`
- `_ocr_pdf_page` (OCR fallback)
- `extract_document_content` (entry point)
- `config.py` (settings pdf_ocr_enabled, pdf_ocr_min_chars)
- `indexer.py`, `classifier_cycle.py` (consumidores)
- Todos os testes de outros formatos (DOCX, XLSX, PPTX, MSG, HTML, etc.)

## Ordem de execução

1. Ler `document_extractor.py` e `requirements.txt` (confirmar estado atual)
2. Editar `requirements.txt`: trocar pypdf por pymupdf
3. Editar `document_extractor.py`: adicionar `_spatial_extract_page`, reescrever `_extract_pdf`
4. Ler `test_document_extractor.py` (confirmar estado atual)
5. Editar `test_document_extractor.py`: adicionar helper e 5 testes novos
6. Rodar `pytest tests/unit/test_document_extractor.py -v` — validar 27 testes passando
7. Rodar `pytest tests/ -v` — validar 365 testes passando

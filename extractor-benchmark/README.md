# extractor-benchmark

Benchmark de qualidade e performance de extração de texto em PDFs. Compara o extrator atual do AtlasFile (`pypdf`) contra alternativas Python com parsing espacial (`pymupdf`, `pdfplumber`).

## Setup

```bash
cd extractor-benchmark
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-...
```

## Corpus

Coloque PDFs reais nas subpastas de `corpus/`, organizados por categoria:

```
corpus/
├── simple/          # Texto corrido, layout simples
├── multicolumn/     # Duas ou mais colunas
├── tables/          # Tabelas predominantes
├── scanned/         # Escaneados (dependem de OCR)
└── mixed/           # Combinação de layouts
```

Recomendado: 10-15 PDFs, 2-3 por categoria.

## Uso

### 1. Gerar ground truth (QA pairs via Claude Vision)

```bash
python scripts/generate_ground_truth.py \
  --corpus-dir corpus/ \
  --output-dir ground_truth/ \
  --max-pages 5
```

Custo estimado: ~$0.10 por documento (5 páginas).

### 2. Avaliar qualidade de extração

```bash
python scripts/run_evaluation.py \
  --ground-truth-dir ground_truth/ \
  --corpus-dir corpus/ \
  --providers atlasfile_pypdf,pymupdf_spatial,pdfplumber \
  --output-dir results/run1/
```

Produz `results/run1/quality.json` com pass rates por provider e categoria.

### 3. Benchmark de performance

```bash
python scripts/run_perf.py \
  --corpus-dir corpus/ \
  --providers atlasfile_pypdf,pymupdf_spatial,pdfplumber \
  --output-dir results/run1/
```

Produz `results/run1/perf.json` com latência e memória por provider.

## Providers

| Provider | Lib | Abordagem |
|----------|-----|-----------|
| `atlasfile_pypdf` | pypdf + Tesseract | Stream order (extrator atual do AtlasFile) |
| `pymupdf_spatial` | pymupdf | Bounding boxes + reconstrução espacial 2D |
| `pdfplumber` | pdfplumber | Layout preservado + detecção de tabelas |

Todos usam fallback OCR (pdf2image + Tesseract, por+eng, 150 DPI) para páginas escaneadas.

## KPIs

| KPI | Descrição | Decisão |
|-----|-----------|---------|
| `qa_pass_rate` | % de QA pairs respondidos corretamente | Métrica primária |
| `qa_pass_rate_delta` | Diferença vs atlasfile_pypdf | > 10pp = vantagem significativa |
| `text_length_ratio` | Comprimento relativo entre providers | Detecta truncamento |
| `avg_latency_ms` | Tempo médio de extração | Regressão > 2x = flag |
| `peak_memory_mb` | Pico de memória | Regressão > 2x = flag |

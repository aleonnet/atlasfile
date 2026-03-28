# Plano: Benchmark de qualidade de extração PDF

## Contexto

O `document_extractor.py` do AtlasFile usa `pypdf` para extração de texto em PDFs. O pypdf extrai texto na ordem do stream interno do PDF, o que pode misturar colunas em layouts multi-coluna e perder alinhamento de tabelas visuais. O LiteParse (LlamaIndex) usa parsing espacial via PDF.js — projetando texto numa grid 2D com base em coordenadas/bounding boxes — e obtém resultados melhores em layouts complexos.

**Objetivo**: criar um projeto de benchmark independente (fora do AtlasFile) que compare a extração atual (`pypdf`) contra implementações Python equivalentes ao parsing espacial do LiteParse (`pymupdf`, `pdfplumber`), usando um corpus real de PDFs do usuário com avaliação via LLM-as-judge.

**Restrição**: não modificar o AtlasFile. Se um provider vencer, a migração será planejada separadamente.

## Estrutura do projeto

```
extractor-benchmark/
├── corpus/                          # PDFs reais, organizados por categoria
│   ├── simple/                      # Texto corrido, layout simples
│   ├── multicolumn/                 # Duas ou mais colunas
│   ├── tables/                      # Tabelas predominantes
│   ├── scanned/                     # Escaneados (dependem de OCR)
│   └── mixed/                       # Combinação de layouts
│
├── ground_truth/                    # 1 JSON por documento (gerado pelo step 1)
│
├── providers/
│   ├── base.py                      # Interface abstrata + PageResult dataclass
│   ├── atlasfile_pypdf.py           # pypdf + Tesseract OCR (replica _extract_pdf atual)
│   ├── pymupdf_spatial.py           # pymupdf com reconstrução espacial por grid 2D
│   └── pdfplumber_provider.py       # pdfplumber com detecção de tabelas
│
├── scripts/
│   ├── generate_ground_truth.py     # PDF → screenshots (max 5 páginas) → Claude Vision → QA JSON
│   ├── run_evaluation.py            # Provider extrai → LLM responde QA → judge avalia → quality.json
│   └── run_perf.py                  # Latência + pico de memória por provider/documento
│
├── results/                         # Output (gitignored)
│
├── requirements.txt
└── README.md
```

## Arquivos a criar (8 arquivos)

### 1. `requirements.txt`

```
pypdf==5.9.0
pdf2image==1.17.0
pytesseract==0.3.10
pymupdf>=1.25.0
pdfplumber>=0.11.0
anthropic>=0.40.0
Pillow>=10.0.0
```

### 2. `providers/base.py` — Interface comum

```python
@dataclass
class PageResult:
    page_number: int
    text: str
    method: str         # "native" | "ocr" | "spatial" | "table_aware"

class BaseProvider(ABC):
    name: str

    @abstractmethod
    def extract(self, path: Path, max_pages: int | None = None) -> list[PageResult]:
        """Extrai texto por página. max_pages=None extrai todas."""
        ...
```

Cada provider retorna `list[PageResult]` — uma entrada por página com texto e método usado.

### 3. `providers/atlasfile_pypdf.py` — Replica extrator atual

Reimplementa a lógica de `_extract_pdf` + `_ocr_pdf_page` do AtlasFile:
- `pypdf.PdfReader` para texto nativo
- Fallback OCR via `pdf2image` + `pytesseract` quando `len(text) < 50`
- OCR: 150 DPI, lang="por+eng"
- Sem chunking (retorna texto cru por página para comparação justa)

### 4. `providers/pymupdf_spatial.py` — Parsing espacial (equivalente Python do PDF.js)

Usa `pymupdf` (fitz) que expõe bounding boxes de cada span de texto:
- `page.get_text("dict")` retorna blocos com coordenadas `(x0, y0, x1, y1)`
- Reconstrução espacial: ordena spans por coordenada Y (linhas), agrupa por proximidade vertical, ordena por X dentro de cada linha
- Preserva alinhamento de colunas via padding com espaços (similar à grid 2D do LiteParse/PDF.js)
- Fallback OCR via `pytesseract` quando página tem pouco texto nativo

### 5. `providers/pdfplumber_provider.py` — Extração com detecção de tabelas

Usa `pdfplumber`:
- `page.extract_text()` com layout preservado (`layout=True`)
- `page.extract_tables()` para tabelas estruturadas
- Combina texto + tabelas formatadas como texto
- Fallback OCR quando página é escaneada (mesmo mecanismo)

### 6. `scripts/generate_ground_truth.py` — Geração de QA pairs

Pipeline:
1. Percorre `corpus/` recursivamente buscando `*.pdf`
2. Para cada PDF, renderiza **max 5 primeiras páginas** como imagem (via `pymupdf` ou `pdf2image`, 150 DPI)
3. Envia cada imagem para Claude Vision (`claude-sonnet-4-5-20250514`) com prompt pedindo 3-5 QA pairs factuais sobre o conteúdo visível
4. Salva `ground_truth/{doc_id}.json` com estrutura:

```json
{
  "file": "corpus/tables/balanco_2024.pdf",
  "category": "tables",
  "total_pages": 47,
  "pages_processed": 5,
  "pages": [
    {
      "page": 1,
      "qa_pairs": [
        {"q": "Qual o valor total do ativo?", "a": "R$ 2.340.000,00"}
      ]
    }
  ]
}
```

**Controle de custo**: max 5 páginas × 3-5 QA pairs × ~$0.01/imagem. Para 15 docs ≈ $1.50/rodada.

CLI: `python scripts/generate_ground_truth.py --corpus-dir corpus/ --output-dir ground_truth/ --max-pages 5`

### 7. `scripts/run_evaluation.py` — Avaliação de qualidade

Pipeline por provider:
1. Extrai texto das mesmas páginas do ground truth (max 5)
2. Para cada QA pair: envia o texto extraído + pergunta ao Claude, pede a resposta
3. LLM-as-judge: envia (pergunta, resposta esperada, resposta dada) ao Claude, recebe pass/fail
4. Agrega resultados:

```json
{
  "provider": "pymupdf_spatial",
  "overall_pass_rate": 0.87,
  "by_category": {
    "simple": 0.95,
    "multicolumn": 0.82,
    "tables": 0.78,
    "scanned": 0.85,
    "mixed": 0.80
  },
  "by_document": [ ... ],
  "text_length_ratio": { ... }
}
```

CLI: `python scripts/run_evaluation.py --ground-truth-dir ground_truth/ --corpus-dir corpus/ --providers atlasfile_pypdf,pymupdf_spatial,pdfplumber --output-dir results/`

### 8. `scripts/run_perf.py` — Performance

Para cada provider × documento:
- 3 runs (1 warmup + 2 medições)
- Mede latência e pico de memória via `tracemalloc`
- Extrai o documento completo (todas as páginas) para medir performance real

CLI: `python scripts/run_perf.py --corpus-dir corpus/ --providers atlasfile_pypdf,pymupdf_spatial,pdfplumber --output-dir results/`

## KPIs

| KPI | Fonte | Decisão |
|-----|-------|---------|
| `qa_pass_rate` (por provider × categoria) | run_evaluation.py | Métrica primária de qualidade |
| `qa_pass_rate_delta` (vs atlasfile_pypdf) | derivado | Diferença > 10pp = vantagem significativa |
| `text_length_ratio` (provider / atlasfile) | run_evaluation.py | Detecta truncamento ou excesso de lixo |
| `avg_latency_ms` (por página) | run_perf.py | Regressão > 2x = flag |
| `peak_memory_mb` | run_perf.py | Regressão > 2x = flag |

## Corpus recomendado

10-15 PDFs reais do usuário, distribuídos:
- 3 simple (contratos, relatórios texto)
- 3 multicolumn (jornais, papers, relatórios anuais)
- 3 tables (balanços, planilhas exportadas)
- 3 scanned (documentos digitalizados)
- 2-3 mixed (combina layouts)

## Verificação

1. `python scripts/generate_ground_truth.py --corpus-dir corpus/ --output-dir ground_truth/ --max-pages 5` → verifica que JSONs foram gerados com QA pairs
2. `python scripts/run_evaluation.py --ground-truth-dir ground_truth/ --corpus-dir corpus/ --providers atlasfile_pypdf,pymupdf_spatial,pdfplumber --output-dir results/run1/` → verifica `quality.json` com pass rates
3. `python scripts/run_perf.py --corpus-dir corpus/ --providers atlasfile_pypdf,pymupdf_spatial,pdfplumber --output-dir results/run1/` → verifica `perf.json` com latência/memória
4. Análise manual do `results/run1/` para decidir se algum provider justifica migração

## Ordem de implementação

1. `providers/base.py`
2. `providers/atlasfile_pypdf.py`
3. `providers/pymupdf_spatial.py`
4. `providers/pdfplumber_provider.py`
5. `scripts/generate_ground_truth.py`
6. `scripts/run_evaluation.py`
7. `scripts/run_perf.py`
8. `requirements.txt` + `README.md`

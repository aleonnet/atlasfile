# extractor-benchmark_mdxaf

PoC de comparação **lado-a-lado** entre o [MarkItDown](https://github.com/microsoft/markitdown) (Microsoft) e o extrator de conteúdo de produção do AtlasFile (`backend/app/document_extractor.py`), sobre arquivos reais de contrato (PDF, DOCX, XLSX, PPTX).

Diferente do `../extractor-benchmark` (que é **page-scoped e só-PDF**, com ground truth via Claude Vision e LLM-as-judge), esta PoC é **whole-document, multi-formato e determinística**: extrai com as duas ferramentas, grava os outputs e calcula métricas objetivas. **Sem LLM-judge, sem ground truth, sem custo de API.** A avaliação de qualidade é por inspeção humana dos outputs lado a lado.

## Escopo e decisões

- **Métrica**: comparação qualitativa lado a lado + métricas objetivas (tamanho, linhas, linhas de tabela markdown, densidade numérica, latência, memória). Sem score automático.
- **MarkItDown**: modo **vanilla** — sem LLM captioning, sem Azure Document Intelligence, sem plugins. Compara o parsing base.
- **Corpus**: os arquivos da pasta `…/Contrato` (3 PDF, 1 DOCX, 1 PPTX, 1 XLSX).

## ⚠️ Assimetria de OCR (ler antes de interpretar resultados)

O **MarkItDown não faz OCR de PDF** por default (precisa do plugin `markitdown-ocr` ou Azure). O **extrator do AtlasFile faz OCR** (fallback Tesseract `por+eng`, 150 DPI) quando uma página rende menos de 50 caracteres de texto nativo.

Consequência: para **PDFs escaneados/imagem**, o MarkItDown tende a sair quase vazio enquanto o AtlasFile recupera o conteúdo. Isso **não é bug do MarkItDown** — é diferença de configuração. Ao comparar, separe PDFs nativos (texto embutido) de PDFs escaneados. A coluna `status` e `char_count` no `summary.md` evidenciam o caso.

## Setup

```bash
cd extractor-benchmark_mdxaf
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Dependências de sistema (já presentes via Homebrew neste ambiente): `tesseract`, `poppler` (`pdftoppm`) — usados pelo OCR do lado AtlasFile.

As versões das libs de extração em `requirements.txt` estão **pinadas iguais ao `backend/requirements.txt`**, para o lado AtlasFile rodar idêntico à produção. O extrator é importado de `../backend` via `sys.path` (mesmo padrão de `backend/scripts/label_corpus_llm.py`).

## Uso

```bash
# 1. Copiar o corpus (idempotente; corpus/ é gitignored — contratos reais)
python scripts/setup_corpus.py

# 2. Rodar a comparação
python scripts/run_compare.py --corpus-dir corpus/ --output-dir results/run1/ --runs 3
```

Flags de `run_compare.py`:

| Flag | Default | Descrição |
|------|---------|-----------|
| `--corpus-dir` | (obrigatório) | Pasta com os arquivos |
| `--output-dir` | (obrigatório) | Onde gravar `outputs/`, `summary.json`, `summary.md` |
| `--runs` | 3 | Nº de execuções por arquivo (latência = mediana) |
| `--warmup` | 1 | Execuções de aquecimento descartadas |
| `--atlas-max-chars` | None | Cap de caracteres no lado AtlasFile (escape hatch p/ PDFs gigantes). MarkItDown sempre processa o doc inteiro. |

## Saídas

```
results/run1/
├── outputs/<slug>__atlasfile.txt   # texto completo extraído pelo AtlasFile
├── outputs/<slug>__markitdown.md   # markdown completo extraído pelo MarkItDown
├── summary.json                    # métricas estruturadas + previews + razões
└── summary.md                      # tabela legível + previews lado a lado
```

## Métricas objetivas (sem LLM)

| Métrica | Significado |
|---------|-------------|
| `char_count`, `word_count`, `nonblank_line_count` | Volume de texto recuperado |
| `text_length_ratio_md_over_atlas` | Razão de tamanho (detecta truncamento/sobra de um lado) |
| `pipe_table_rows`, `md_table_blocks` | Tabelas em Markdown (forte do MarkItDown; AtlasFile produz texto plano) |
| `numeric_density`, `digit_count` | Captura de valores numéricos (relevante p/ XLSX/tabelas) |
| `latency_ms`, `peak_memory_mb` | Performance (memória = pico Python via `tracemalloc`; não inclui subprocessos de OCR) |

## Limitações

- `tracemalloc` mede apenas alocações Python; o OCR roda via `tesseract`/`pdftoppm` em subprocesso e não entra no pico de memória reportado.
- Métricas objetivas não capturam **correção semântica** nem fidelidade fina de tabela — isso é avaliado abrindo os `outputs/`.
- Comparação justa apenas dentro do mesmo formato; entre formatos os números não são diretamente comparáveis.

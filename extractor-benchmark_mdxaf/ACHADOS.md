# Achados — MarkItDown (vanilla) vs Extrator AtlasFile

Run de referência: `results/run1/` (1 run por arquivo, sem warmup). Corpus: 6 arquivos reais de contrato (3 PDF, 1 DOCX, 1 PPTX, 1 XLSX). Comparação determinística, sem LLM-judge. Os números de tamanho/latência são da PoC; o conteúdo extraído (em `results/run1/outputs/`, gitignored) foi inspecionado manualmente.

## Métricas (resumo)

| Arquivo | Fmt | Ferramenta | Status | Chars | Tab.MD | Densid.num | Latência |
|---|---|---|---|---:|---:|---:|---:|
| Lista fornecedores | xlsx | atlasfile | ok | 183.885 | 0 | 0,116 | 23,0 s |
| Lista fornecedores | xlsx | markitdown | ok | 89.645 | 159 | 0,136 | 5,7 s |
| Carta Anuência | pdf (nativo, 1 pg) | atlasfile | ok | 2.601 | 0 | 0,034 | 0,6 s |
| Carta Anuência | pdf (nativo, 1 pg) | markitdown | ok | 2.639 | 0 | 0,032 | 3,3 s |
| Anexo (28 MB) | pdf (escaneado, 46 pg) | atlasfile | ok | **228.677** | 0 | 0,248 | 251 s |
| Anexo (28 MB) | pdf (escaneado, 46 pg) | markitdown | **error** | **0** | 0 | 0,0 | **1.442 s** |
| Contrato VTAL | pdf (nativo) | atlasfile | ok | 298.353 | 0 | 0,069 | 4,1 s |
| Contrato VTAL | pdf (nativo) | markitdown | ok | 421.397 | 3.220 | 0,046 | 88,8 s |
| Fluxo TI | pptx | atlasfile | ok | 2.477 | 0 | 0,011 | 0,03 s |
| Fluxo TI | pptx | markitdown | ok | 2.466 | 0 | 0,009 | 0,05 s |
| Minuta SPA | docx | atlasfile | ok | 98.691 | 0 | 0,016 | 0,08 s |
| Minuta SPA | docx | markitdown | ok | 93.143 | 0 | 0,011 | 1,6 s |

## Conclusões por formato

### PDF escaneado (Anexo, 28 MB) — AtlasFile vence de forma absoluta
- **AtlasFile**: 228.677 chars via OCR Tesseract (46 páginas), em ~4 min. Conteúdo legível (com ruído típico de OCR: "Sao Paulo", "RECUPERACAO").
- **MarkItDown**: **saída vazia (0 bytes) e ainda gastou ~24 min** tentando parsear o PDF de imagem com pdfminer.
- **Causa**: MarkItDown vanilla não faz OCR de PDF. Sem camada de texto, retorna nada — e ainda é lentíssimo no arquivo grande.
- **Implicação**: para o fluxo do AtlasFile (que recebe documentos heterogêneos, incluindo escaneados), MarkItDown vanilla é **inviável** sem um plugin de OCR.

### PDF nativo (Contrato VTAL) — AtlasFile vence em legibilidade
- O MarkItDown extraiu **mais caracteres** (421k vs 298k) e "3.220 linhas de tabela", mas a inspeção mostra que **isso é pior, não melhor**:
  - **Perda de espaçamento entre palavras**: ex. `12.901,27ºandar,conjunto2701,TorreOeste,ChácaraItaim,inscritanoCNPJ/MEsob`.
  - **Tabelas falsas**: o layout em colunas vira pseudo-tabelas markdown sem sentido.
- O **AtlasFile** (extração espacial via pymupdf com reconstrução de espaços por bounding box) preservou: `12.901, 27º andar, conjunto 2701, Torre Oeste, Chácara Itaim, inscrita no CNPJ/ME sob`.
- **Lição**: `char_count` e `pipe_table_rows` **não** são proxy de qualidade aqui — o MarkItDown infla ambos com lixo. Além disso, AtlasFile foi ~20x mais rápido (4 s vs 89 s).

### PDF nativo curto (Carta Anuência) — empate
- Ambos ~2,6k chars, conteúdo equivalente. MarkItDown sem os marcadores `[page]`; AtlasFile ~6x mais rápido.

### XLSX (Lista de fornecedores) — depende do uso (trade-off real)
- **MarkItDown**: tabela Markdown limpa e compacta (89k chars, 159 linhas de tabela). **Porém** leu o cabeçalho errado: como a 1ª linha é título/mesclado, rotulou as colunas como `Unnamed: 0…23` e empurrou o header real para linha de dados.
- **AtlasFile**: formato verboso por célula `[sheet Base row N col X] valor` (184k chars). Excelente para **localização precisa/RAG** (cada célula endereçável), ruim para leitura humana direta.
- Ambos cobriram a única sheet (`Base`). Não há gap de cobertura — é diferença de filosofia: tabela estruturada (MarkItDown) vs coordenadas por célula (AtlasFile).

### DOCX (Minuta SPA) — empate em conteúdo, MarkItDown mais rico em formatação
- Conteúdo equivalente (~95k chars ambos). **MarkItDown** preserva Markdown semântico: **negrito**, *itálico*, sumário/TOC com âncoras. **AtlasFile** dá marcadores `[docx_page:P:paragraph:N]` (bons para RAG) e foi ~20x mais rápido (81 ms vs 1,6 s).

### PPTX (Fluxo TI) — empate, MarkItDown leve vantagem de estrutura
- Conteúdo idêntico (~2,5k chars). **MarkItDown** adiciona `<!-- Slide number: N -->` e headings `#`; **AtlasFile** dá `[slide N.M]`. Latência equivalente (dezenas de ms).

## Síntese

| Dimensão | Vencedor |
|---|---|
| PDF escaneado (OCR) | **AtlasFile** (MarkItDown vazio) |
| PDF nativo — fidelidade de texto | **AtlasFile** (MarkItDown perde espaços) |
| Robustez/latência em arquivo grande | **AtlasFile** (MarkItDown 24 min e falhou) |
| XLSX — tabela estruturada | MarkItDown (com ressalva do header `Unnamed`) |
| XLSX — endereçamento p/ RAG | AtlasFile |
| DOCX/PPTX — formatação Markdown | MarkItDown (leve) |
| DOCX/PPTX — conteúdo e velocidade | Empate / AtlasFile mais rápido |

**Recomendação factual:** para o pipeline do AtlasFile (documentos heterogêneos, com escaneados, exigindo fidelidade textual e localização para busca/RAG), o **extrator atual do AtlasFile é superior** nos casos que mais importam (PDF nativo e escaneado). O **MarkItDown só agrega** onde a estrutura Markdown nativa é desejável (XLSX/DOCX/PPTX bem comportados) e **mesmo assim exigiria** habilitar OCR (plugin/Azure) para não regredir em escaneados. Não há ganho que justifique troca; há, no máximo, uso complementar para gerar Markdown estruturado de Office.

## Como reproduzir
Ver `README.md`. Resumo:
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/setup_corpus.py
python scripts/run_compare.py --corpus-dir corpus/ --output-dir results/run1/ --runs 1 --warmup 0
```
> `--runs 1` é recomendado: o Anexo escaneado faz o MarkItDown gastar ~24 min por run.

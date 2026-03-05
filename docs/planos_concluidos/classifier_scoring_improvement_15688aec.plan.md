---
name: Classifier scoring improvement
overview: Melhorar o classificador do AtlasFile corrigindo 3 problemas concretos (scoring, word boundary, routing rules), fundamentado em benchmarks reais e com comparacao critica contra ferramentas prontas (Paperless-ngx, Docling).
todos:
  - id: routing-rules
    content: Adicionar routing rules para juridica, financeiro, sistemas_migracao, processos_tsa no default.json
    status: pending
  - id: word-boundary
    content: Trocar substring match (alias in text) por regex word boundary em _score_area e routing rules
    status: pending
  - id: sqrt-norm
    content: Trocar normalizacao hits/len por hits/sqrt(len) com cap em 1.0, inspirado em Lucene fieldNorm
    status: pending
  - id: tests-regression
    content: Rodar os 12 testes existentes + criar novos para word boundary, novas routing rules, scoring sqrt e aliases compostos
    status: pending
  - id: threshold-calibration
    content: Recalibrar confidence_thresholds (auto_route_min, triage_min) com base nos novos scores
    status: pending
isProject: false
---

# Melhoria do Classificador AtlasFile -- Plano com Benchmarks Validados

## 1. Benchmarks e Referencias Reais

### 1.1 Abordagens de classificacao documental em producao

| Ferramenta | Metodo | Stack | Resultado |
|---|---|---|---|
| **Paperless-ngx** | `CountVectorizer(ngram_range=(1,2), min_df=0.01)` + `MLPClassifier` (scikit-learn) | Neural network treinada nos docs existentes. Retrain automatico. | Nao publica F1/accuracy, mas e a referencia open-source mais usada (37k stars). Exige massa de treinamento. |
| **Visualyze Keyword Classifier** | Keywords/regex PCRE por classe, com inclusao e exclusao | Rule-based deterministico | Preciso para dominios com vocabulario bem definido. Usa word boundary nativo via PCRE. |
| **M-Files Extension Kit** | Regras condicionais (trigger + condicao + acao) + ML opcional | Enterprise DMS | Padrao: regras como primeira camada, AI como enriquecimento. |
| **Alfresco Intelligence Services** | Folder rules + Amazon AI renditions | Enterprise DMS + cloud AI | Layout detection via AI, routing via regras de pasta. |
| **CLARA (OpenReview 2025)** | LLM para identificar condicoes + engine de regras deterministica para decisao final | Hibrido neuro-simbolico | Melhor interpretabilidade e robustez vs LLM puro. Sem numeros absolutos de F1 publicados. |

**Fontes:**
- Paperless-ngx classifier.py: [Gitea mirror](https://git.labexposed.com/lgcosta/paperless-ngx/src/commit/83734c3bee86d1fb99853afa8498b138c07f91c2/src/documents/classifier.py)
- Visualyze Keyword Classifier: [docs.visualyze.ai](https://docs.visualyze.ai/getting-started/rpa-studio/document-ai/document-classifier/types/keyword-classifier)
- M-Files: [extensionkit.unitfly.com](https://extensionkit.unitfly.com/documentation/how-to-create-rules)
- Alfresco: [docs.alfresco.com](https://docs.alfresco.com/intelligence-services/latest/using/)
- CLARA: [OpenReview](https://openreview.net/forum?id=eAW6yuszK7)

### 1.2 Scoring e normalizacao -- o que diz a literatura real

**BM25 (Elasticsearch default desde v5.0/2016, Lucene 6.0+):**
- Saturacao via `k1` (default 1.2): 1o hit = 0.92, 5 hits = 2.73, 100 hits = 3.17 (apenas 16% a mais que 5). Ref: [Elastic Blog](https://elastic.co/blog/practical-bm25-part-2-the-bm25-algorithm-and-its-variables)
- Length normalization via `b` (default 0.75): documentos mais curtos recebem boost. Ref: [SystemOverflow](https://www.systemoverflow.com/learn/search-ranking/ranking-algorithms/how-bm25-improves-tf-idf-with-saturation-and-length-normalization)

**Lucene fieldNorm:**
- Formula: `norm = 1.0 / sqrt(numTerms)`. Ref: [Lucene 4.9.0 API](https://lucene.apache.org/core/4_9_0/core/org/apache/lucene/search/similarities/DefaultSimilarity.html), [Elastic Guide](https://elastic.co/guide/en/elasticsearch/guide/current/practical-scoring-function.html)
- Proposito: penalizar campos com muitos termos de forma sub-linear, nao linear.

**Procycons Long Document Classification Benchmark 2025 (27k docs):**
- XGBoost + TF-IDF: **86% F1**
- Logistic Regression + TF-IDF: **79% F1** (treino em <20s)
- BERT-base: **82% F1** (23min treino, 2GB GPU)
- RoBERTa-base: **57% F1** (surpreendentemente ruim)
- Ref: [procycons.com](https://procycons.com/en/blogs/long-document-classification-benchmark-2025/)

**scikit-learn benchmarks (20newsgroups):**
- CountVectorizer(1,2) + SGDClassifier: **94% accuracy** em subset 2-categorias
- CountVectorizer + TfidfTransformer e a abordagem classica. Ref: [scikit-learn docs](https://scikit-learn.org/stable/auto_examples/text/plot_document_classification_20newsgroups.html)

**LLM embeddings vs TF-IDF (MachineLearningMastery 2025):**
- LLM embeddings superam TF-IDF em media 12.7% em 5 datasets
- TF-IDF permanece "robusto, interpretavel" para ambientes com restricoes de recurso
- Ref: [MachineLearningMastery](https://machinelearningmastery.com/llm-embeddings-vs-tf-idf-vs-bag-of-words-which-works-better-in-scikit-learn/)

### 1.3 Sistemas cascata com fallback por confianca

**"Fail Fast, or Ask" (arXiv 2507.14406):**
- Modelo rapido na frente + modelo caro para baixa confianca + humano
- Resultado: erro cai de 3% para <1%, latencia -40%, custo -50%
- Ref: [arXiv](https://arxiv.org/abs/2507.14406)

**Cascaded LLM Frameworks (arXiv 2602.15391):**
- Double-threshold policy: tau_l (rejeitar) e tau_u (aceitar), faixa intermediaria vai para modelo superior
- Melhora em ARC-Easy, ARC-Challenge, MMLU, MedQA, MedMCQA vs single-model
- Ref: [arXiv](https://arxiv.org/abs/2602.15391)

**Conclusao para AtlasFile:** A arquitetura "regras -> alias scoring -> LLM fallback -> triage humano" esta **alinhada** com o padrao cascata da literatura. O gap nao e arquitetural, e de execucao nos detalhes.

### 1.4 Word boundary -- dados reais

Nao ha benchmark direto quantificando "substring vs \b" em classificacao documental. Os dados indiretos:
- NUPunkt (legal sentence boundaries): **+29-32% precisao** com deteccao correta de limites vs ferramentas genericas. Ref: [arXiv:2504.04131](https://arxiv.org/html/2504.04131v1)
- Python `re` module: `\b\w+nn\b` em 2MB de texto = **32ms**. Overhead negligivel. Ref: [Python speed mailing list](https://mail.python.org/pipermail/speed/2016-March/000312.html)
- Visualyze usa PCRE regex nativamente para keyword classification (word boundary implicito)

---

## 2. Comparacao: AtlasFile vs Ferramentas Prontas

### 2.1 AtlasFile vs Paperless-ngx

| Aspecto | AtlasFile | Paperless-ngx |
|---|---|---|
| **Classificacao** | Rule-based (routing rules + alias scoring) + LLM opcional | ML (CountVectorizer + MLPClassifier) + matching modes (exact, fuzzy, regex, any, all) |
| **Treinamento** | Zero -- funciona day-1 com regras predefinidas | Precisa de massa de docs classificados para treinar |
| **Flexibilidade** | Regras editaveis pelo usuario, areas customizaveis | Aprende padroes automaticamente, menos controle direto |
| **LLM** | Integrado com guardrails (mode: tag_only/review/full_override) | Sem LLM nativo (extensoes comunitarias via API) |
| **Extracao** | pypdf, docx direto (XML), openpyxl, pptx, OCR, msg, rar | OCR nativo, foco em PDF/imagem |
| **Dominio** | M and A / carve-out (vocabulario especializado) | Documentos pessoais/genericos |

**Veredicto:** Paperless-ngx resolve um problema diferente (DMS pessoal com aprendizado automatico). AtlasFile opera em dominio especializado (M and A) onde:
- **Nao ha massa de treinamento** no dia zero (poucos documentos por projeto)
- **Vocabulario e previsivel** (areas de M and A sao bem definidas)
- **Controle e auditabilidade** sao criticos (regras explicitas > black-box ML)

A abordagem rule-based do AtlasFile e **correta para o usecase**. O que Paperless-ngx faz de superior e ter **multiplos modos de matching** (exact, regex, fuzzy, any, all) em vez de apenas substring.

### 2.2 AtlasFile vs Docling

| Aspecto | AtlasFile (extrator atual) | Docling |
|---|---|---|
| **Funcao** | Extrai texto de PDF/DOCX/XLSX/PPTX/MSG/RAR/ZIP | Converte documentos em representacao estruturada (JSON/Markdown) |
| **Acuracia** | pypdf para PDF (text layer), XML direto para DOCX | 97.9% em tabelas complexas, dentro de 5pp de acuracia humana para layout |
| **Velocidade** | Rapido (leitura direta sem modelo) | 137s no primeiro PDF (CPU), 5s subsequentes com cache |
| **Recursos** | ~50MB deps | 1.74GB (CPU-only) a 9.74GB (GPU). Memory leaks reportados em producao |
| **Docker** | Cabe no container atual (~500MB total) | Adicionaria 1.7-9.7GB a imagem |
| **Formatos** | PDF, DOCX, XLSX, PPTX, MSG, RAR, ZIP, plain text | PDF, DOCX, PPTX, XLSX, HTML, imagens |
| **OCR** | pytesseract + pdf2image (fallback) | DocLayNet (vision model) |
| **Classificacao** | Nao -- Docling nao classifica por area/categoria | Nao -- Docling nao classifica por area/categoria |

**Fontes Docker/recursos:** [shekhargulati.com](https://shekhargulati.com/2025/02/05/reducing-size-of-docling-pytorch-docker-image/), [Docling GPU docs](https://docling-project.github.io/docling/usage/gpu/)
**Benchmark extracao:** [Procycons PDF Extraction Benchmark 2025](https://procycons.com/en/blogs/pdf-data-extraction-benchmark/)

**Veredicto:** Docling e um **extrator/parser**, nao um classificador. Nao substitui o classificador do AtlasFile. Poderia substituir o `document_extractor.py` para melhor qualidade de extracao (especialmente tabelas e layout complexo), mas com trade-offs serios:
- **+1.7GB** na imagem Docker (minimo, CPU-only)
- **137s** primeiro processamento vs instantaneo atual
- **Memory leaks** reportados em producao
- Para o usecase do AtlasFile (extrair texto para classificacao, nao preservar layout), pypdf + XML direto e **suficiente e muito mais eficiente**

**Recomendacao: NAO integrar Docling agora.** Considerar no futuro apenas se:
- A qualidade de extracao de tabelas/layout se tornar um gargalo real
- O pipeline precisar de representacao estruturada (Markdown, JSON com bounding boxes)
- O budget de recursos Docker permitir +2GB

---

## 3. O que Muda com as Novas Referencias

Comparando com minha analise anterior:

**Muda:**
- A formula de scoring proposta `min(1.0, hits * 0.15)` era uma heuristica arbitraria. A referencia formal correta e **Lucene fieldNorm: `hits / sqrt(len(aliases))`** -- documentada, testada em bilhoes de documentos.
- O Paperless-ngx mostra que ter **multiplos modos de matching** (exact, regex, fuzzy) e mais robusto que um unico modo. AtlasFile poderia se beneficiar de suporte a regex nos routing rules.
- Docling **nao resolve** o problema de classificacao. E irrelevante para esta tarefa.

**NAO muda:**
- A recomendacao de adicionar routing rules para as 4 areas descobertas continua sendo a acao de maior impacto e menor risco
- Word boundary com `\b` continua recomendado (overhead: 32ms/2MB, negligivel)
- LLM como fallback + triage humano continua sendo best practice (confirmado por CLARA, "Fail Fast or Ask", Cascaded LLM)
- A arquitetura cascata do AtlasFile esta correta

---

## 4. Plano de Implementacao

### 4.1 Adicionar routing rules para 4 areas descobertas

**Arquivo:** [config/templates/default.json](config/templates/default.json) linhas 221-265

Adicionar:
- `juridica`: `when_filename_contains: ["parecer", "litigio", "mandado", "procuracao"]`
- `financeiro`: `when_filename_contains: ["dre", "ebitda", "budget", "orcamento", "balanco", "pnl"]`
- `sistemas_migracao`: `when_filename_contains: ["migracao", "sap", "integracao"]`
- `processos_tsa`: `when_filename_contains: ["tsa", "sox", "fluxograma"]`

**Risco:** Zero. Regras adicionais nao afetam regras existentes.

### 4.2 Trocar substring match por word boundary em `_score_area`

**Arquivo:** [backend/app/ingestion.py](backend/app/ingestion.py) linhas 22-27

De:
```python
hits = sum(1 for alias in aliases if alias in text)
```
Para:
```python
import re
_wb_cache: dict[str, re.Pattern] = {}

def _word_boundary_pattern(alias: str) -> re.Pattern:
    if alias not in _wb_cache:
        _wb_cache[alias] = re.compile(rf'\b{re.escape(alias)}\b')
    return _wb_cache[alias]

hits = sum(1 for alias in aliases if _word_boundary_pattern(alias).search(text))
```

Cache dos patterns compilados para evitar recompilacao (custo: ~50 patterns em memoria, negligivel).

**Risco:** Baixo. Pode quebrar matches de aliases compostos como `fluxo_caixa` (underscore nao e word boundary). Mitigacao: testar todos os aliases atuais.

### 4.3 Trocar normalizacao de `hits/len` para `hits/sqrt(len)`

**Arquivo:** [backend/app/ingestion.py](backend/app/ingestion.py) linha 27

De:
```python
return hits / len(aliases)
```
Para:
```python
import math
return hits / max(1.0, math.sqrt(len(aliases)))
```

**Referencia formal:** Lucene DefaultSimilarity `norm = 1/sqrt(numTerms)` -- [Lucene API](https://lucene.apache.org/core/4_9_0/core/org/apache/lucene/search/similarities/DefaultSimilarity.html)

**Impacto quantificavel no AtlasFile:**
- `financeiro` (17 aliases, 5 hits): antes = 0.29, depois = 5/4.12 = **1.21** (cap em 1.0)
- `contratos_comunicacao` (9 aliases, 2 hits): antes = 0.22, depois = 2/3.0 = **0.67**
- Separacao muito mais clara entre areas com muitos vs poucos hits

**Risco:** Medio. Scores vao mudar significativamente. Os thresholds `auto_route_min: 0.85` e `triage_min: 0.5` precisam ser recalibrados. Implementar com cap em 1.0.

### 4.4 Tambem aplicar word boundary nos routing rules

**Arquivo:** [backend/app/ingestion.py](backend/app/ingestion.py) linhas 41-57

De:
```python
if normalize_text(token) in path_text:
```
Para:
```python
if re.search(rf'\b{re.escape(normalize_text(token))}\b', path_text):
```

Isso evita que `"sap"` case com `"terapia"` ou `"ativo"` case com `"interativo"` tambem nos routing rules.

**Risco:** Baixo. Routing rules usam tokens mais longos e especificos (ex: `"contrato"`, `"filiais"`, `"cnpj"`), reduzindo risco de falso positivo.

### 4.5 Testes

**Arquivo existente:** [backend/tests/unit/test_classifier_aliases.py](backend/tests/unit/test_classifier_aliases.py)

Novos testes necessarios:
- **Regressao:** rodar os 12 testes existentes para confirmar que todos passam com as mudancas
- **Word boundary:** teste que `"ativo"` NAO casa com `"interativo"`, `"sap"` NAO casa com `"terapia"`
- **Novas routing rules:** testes para as 4 areas que ganharam regras
- **Scoring sqrt:** teste que `financeiro` com 5 hits supera `contratos_comunicacao` com 2 hits (diferenca de score significativa)
- **Aliases compostos:** teste que `fluxo_caixa`, `migracao_sistemas`, `processo_operacional` continuam casando (underscore como word boundary)
- **Recalibracao de thresholds:** verificar se os thresholds atuais (0.85 auto, 0.5 triage) ainda fazem sentido com sqrt normalization

### 4.6 Recalibracao de thresholds

Com `sqrt(len)`, os scores sobem significativamente. E provavel que `auto_route_min: 0.85` precise ser ajustado. Passo:
1. Rodar os 12 cenarios de teste existentes com a nova formula
2. Registrar os novos scores
3. Ajustar thresholds se necessario no `default.json`

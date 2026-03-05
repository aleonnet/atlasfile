# Design do classificador -- fundamentação e benchmarks

## Arquitetura: cascata com fallback por confiança

O classificador do AtlasFile opera em 4 camadas sequenciais:

```
1. Routing rules  →  match por path/filename (word boundary)  →  confiança 0.95+
2. Alias scoring  →  word boundary + sqrt normalization        →  confiança variável
3. LLM (opcional) →  enriquece/override com guardrails         →  confiança do LLM
4. Triage humano  →  decisão final para baixa confiança        →  confiança 1.0
```

Esta arquitetura está alinhada com o padrão cascata da literatura (ver seção de referências abaixo).

## Decisões de design

### Word boundary matching (`\b`)

**Problema**: substring match gerava falsos positivos (`"ativo"` casava com `"interativo"`, `"sap"` com `"terapia"`).

**Solução**: regex `\b` com cache de patterns compilados. Helper `_match_normalize` converte underscores e hífens em espaços para que `\b` funcione em nomes compostos (`Contrato_Servicos.pdf`).

**Overhead**: ~32ms/2MB de texto (negligível). Cache em memória de ~50 patterns.

**Referências**:
- NUPunkt (legal sentence boundaries): +29-32% precisão com detecção correta de limites vs ferramentas genéricas. [arXiv:2504.04131](https://arxiv.org/html/2504.04131v1)
- Visualyze Keyword Classifier usa PCRE regex nativamente. [docs.visualyze.ai](https://docs.visualyze.ai/getting-started/rpa-studio/document-ai/document-classifier/types/keyword-classifier)

### Normalização sqrt (inspirada no Lucene fieldNorm)

**Problema**: `hits / len(aliases)` penalizava linearmente áreas com muitos aliases. `financeiro` (17 aliases, 5 hits) = 0.29 vs `contratos_comunicacao` (9 aliases, 2 hits) = 0.22 -- separação insuficiente.

**Solução**: `min(1.0, hits / sqrt(len(aliases)))`. Com sqrt: `financeiro` = 1.0, `contratos_comunicacao` = 0.67 -- separação clara.

**Referência formal**: Lucene DefaultSimilarity `norm = 1/sqrt(numTerms)` -- [Lucene 4.9 API](https://lucene.apache.org/core/4_9_0/core/org/apache/lucene/search/similarities/DefaultSimilarity.html), [Elastic Guide](https://elastic.co/guide/en/elasticsearch/guide/current/practical-scoring-function.html)

### LLM como fallback com guardrails

O LLM participa em 3 modos configuráveis:

| Modo | Comportamento |
|------|---------------|
| `tag_only` | Enriquece tags, document_type, topics. Não altera area_key. |
| `review` | Pode divergir da área, mas envia para triagem humana. |
| `full_override` | Pode alterar area_key se guardrails permitirem. |

Guardrails: confiança mínima para override, exigir explicação, limite de alterações de área.

## Benchmarks comparativos

### Abordagens de classificação documental em produção

| Ferramenta | Método | Stack | Resultado |
|-----------|--------|-------|-----------|
| **Paperless-ngx** | `CountVectorizer(ngram_range=(1,2))` + `MLPClassifier` (scikit-learn) | Neural network treinada nos docs existentes. Retrain automático. | Referência open-source mais usada (37k stars). Exige massa de treinamento. |
| **Visualyze** | Keywords/regex PCRE por classe, inclusão e exclusão | Rule-based determinístico | Preciso para domínios com vocabulário definido. Word boundary nativo. |
| **M-Files Extension Kit** | Regras condicionais (trigger + condição + ação) + ML opcional | Enterprise DMS | Padrão: regras como 1a camada, AI como enriquecimento. |
| **Alfresco Intelligence Services** | Folder rules + Amazon AI renditions | Enterprise DMS + cloud AI | Layout detection via AI, routing via regras de pasta. |
| **CLARA (OpenReview 2025)** | LLM para condições + engine de regras determinística | Híbrido neuro-simbólico | Melhor interpretabilidade e robustez vs LLM puro. |

**Fontes:**
- Paperless-ngx: [classifier.py](https://git.labexposed.com/lgcosta/paperless-ngx/src/commit/83734c3bee86d1fb99853afa8498b138c07f91c2/src/documents/classifier.py)
- Visualyze: [docs.visualyze.ai](https://docs.visualyze.ai/getting-started/rpa-studio/document-ai/document-classifier/types/keyword-classifier)
- M-Files: [extensionkit.unitfly.com](https://extensionkit.unitfly.com/documentation/how-to-create-rules)
- Alfresco: [docs.alfresco.com](https://docs.alfresco.com/intelligence-services/latest/using/)
- CLARA: [OpenReview](https://openreview.net/forum?id=eAW6yuszK7)

### Scoring e normalização

| Abordagem | Resultado | Referência |
|-----------|-----------|------------|
| BM25 (Elasticsearch/Lucene) | Saturação via k1: 1o hit = 0.92, 5 hits = 2.73, 100 hits = 3.17 | [Elastic Blog](https://elastic.co/blog/practical-bm25-part-2-the-bm25-algorithm-and-its-variables) |
| Lucene fieldNorm | `norm = 1.0 / sqrt(numTerms)` -- penalização sub-linear | [Lucene API](https://lucene.apache.org/core/4_9_0/core/org/apache/lucene/search/similarities/DefaultSimilarity.html) |
| XGBoost + TF-IDF (27k docs) | **86% F1** | [Procycons 2025](https://procycons.com/en/blogs/long-document-classification-benchmark-2025/) |
| Logistic Regression + TF-IDF | **79% F1** (treino <20s) | [Procycons 2025](https://procycons.com/en/blogs/long-document-classification-benchmark-2025/) |
| BERT-base (27k docs) | **82% F1** (23min, 2GB GPU) | [Procycons 2025](https://procycons.com/en/blogs/long-document-classification-benchmark-2025/) |
| LLM embeddings vs TF-IDF | LLM supera TF-IDF em 12.7% em média | [MachineLearningMastery](https://machinelearningmastery.com/llm-embeddings-vs-tf-idf-vs-bag-of-words-which-works-better-in-scikit-learn/) |

### Sistemas cascata com fallback

| Sistema | Resultado | Referência |
|---------|-----------|------------|
| "Fail Fast, or Ask" | Erro cai de 3% para <1%, latência -40%, custo -50% | [arXiv:2507.14406](https://arxiv.org/abs/2507.14406) |
| Cascaded LLM Frameworks | Double-threshold policy (reject / accept / escalate) supera single-model | [arXiv:2602.15391](https://arxiv.org/abs/2602.15391) |

## AtlasFile vs Paperless-ngx

| Aspecto | AtlasFile | Paperless-ngx |
|---------|-----------|---------------|
| **Classificação** | Rule-based (routing + aliases) + LLM opcional | ML (CountVectorizer + MLPClassifier) + matching modes |
| **Treinamento** | Zero -- funciona day-1 com regras predefinidas | Precisa de massa de docs para treinar |
| **Flexibilidade** | Regras editáveis pelo usuário | Aprende padrões automaticamente |
| **LLM** | Integrado com guardrails (3 modos) | Sem LLM nativo |
| **Domínio** | M&A / carve-out (vocabulário especializado) | Documentos pessoais/genéricos |

**Veredicto**: AtlasFile opera em domínio especializado sem massa de treinamento no dia zero, onde controle e auditabilidade são críticos. A abordagem rule-based é correta para o usecase.

## AtlasFile vs Docling

| Aspecto | AtlasFile (extrator atual) | Docling |
|---------|---------------------------|---------|
| **Função** | Extrai texto de PDF/DOCX/XLSX/PPTX/MSG/RAR/ZIP | Converte documentos em representação estruturada |
| **Acurácia** | pypdf (text layer), XML direto para DOCX | 97.9% em tabelas complexas |
| **Velocidade** | Rápido (leitura direta sem modelo) | 137s no 1o PDF (CPU), 5s subsequentes |
| **Recursos** | ~50MB deps | 1.74GB (CPU) a 9.74GB (GPU) |
| **Docker** | Container atual ~500MB total | Adicionaria 1.7-9.7GB |

**Veredicto**: Docling é um extrator/parser, não classificador. Não substitui o classificador. Trade-offs de recurso (1.7GB+, 137s 1o processamento) não justificam para o usecase atual. Considerar no futuro se qualidade de extração de tabelas se tornar gargalo.

**Fontes**: [shekhargulati.com](https://shekhargulati.com/2025/02/05/reducing-size-of-docling-pytorch-docker-image/), [Procycons PDF Extraction Benchmark 2025](https://procycons.com/en/blogs/pdf-data-extraction-benchmark/)

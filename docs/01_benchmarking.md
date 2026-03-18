# Benchmarking e referencias verificadas

Este documento consolida fontes externas usadas para sustentar o desenho atual do AtlasFile e delimita o que ja foi adotado na 0.7.0 vs o que ainda e apenas caminho futuro.

## 1) Nomenclatura e portabilidade

- NARA recomenda nomes de arquivo previsiveis, caracteres seguros, caminhos curtos e hierarquias controladas.
- No AtlasFile 0.7.0 isso e aplicado como disciplina de path, naming canonico configuravel e rastreabilidade por metadados.
- O sistema preserva `original_name` no nome canonico e compensa portabilidade com campos de busca dedicados, em vez de forcar sanitizacao humana agressiva.

Referencia:

- [NARA Bulletin 2015-04 Appendix B](https://www.archives.gov/records-mgmt/bulletins/2015/2015-04-appendix-b.html)

## 2) Busca corporativa e metadados

- Microsoft Learn reforca que a capacidade real de busca depende do schema indexado, nao apenas do arquivo existir no repositorio.
- Isso sustenta a separacao do AtlasFile entre arquivo no filesystem e campos explicitamente indexados no OpenSearch.

Referencia:

- [Manage the search schema in SharePoint](https://learn.microsoft.com/en-us/sharepoint/manage-search-schema)

## 3) Governanca e findability

- ISO 15489 e ISO 23081 sustentam autenticidade, confiabilidade, integridade e usabilidade.
- FAIR reforca identificador persistente, metadados ricos e recurso pesquisavel.

Referencias:

- [ISO 15489 overview](https://committee.iso.org/sites/tc46sc11/home/projects/published/iso-15489-records-management.html)
- [ISO 23081 metadata for records](https://committee.iso.org/sites/tc46sc11/home/projects/published/iso-23081-metadata-for-records.html)
- [FAIR Principles](https://www.go-fair.org/fair-principles/)

## 4) Taxonomia operacional

- PARA continua valido para separar `projects`, `areas`, `resources` e `archive`.
- Johnny.Decimal segue util como referencia de enderecamento estavel, mas o eixo operacional do AtlasFile na 0.7.0 e `business_domain/document_type`, nao mais um catalogo de work areas antigas.

Referencias:

- [The PARA Method](https://fortelabs.com/the-p-a-r-a-method-a-universal-system-for-organizing-digital-information-75a9da8bfb37)
- [Johnny.Decimal](https://johnnydecimal.com/)

## 5) Busca lexical: BM25 como baseline

- OpenSearch e Elasticsearch adotam BM25 como baseline robusto para ranking lexical.
- Para o AtlasFile atual, BM25 continua sendo a escolha correta por explicabilidade, baixo custo operacional e aderencia a documentos com termos exatos como contratos, clausulas, CNPJs e codigos.

Referencias:

- [OpenSearch docs](https://opensearch.org/docs/latest/)
- [Elasticsearch BM25 similarity](https://www.elastic.co/guide/en/elasticsearch/reference/current/index-modules-similarity.html)

## 6) `pure nested` por chunks

Problema original:

- campos flat de conteudo causavam erro de highlight em documentos grandes
- havia redundancia alta de storage

Decisao adotada:

- manter o texto indexado apenas em `content_chunks`
- usar highlight e retrieval sobre nested chunks
- complementar com campos `*_ocr_folded` para melhorar busca em OCR ruidoso

Observacao de escopo:

- esta arquitetura e a implementacao vigente da 0.7.0
- ela resolve o problema atual de busca/highlight e simplifica storage
- para um corpus real proximo de `100k` documentos, a decisao de manter `pure nested` ou migrar para chunk-as-document deve ser reavaliada com metrica de latencia, tamanho de indice e nested object count; ainda nao ha promocao automatica dessa mudanca

Referencias:

- [OpenSearch Highlight](https://opensearch.org/docs/latest/search-plugins/searching-data/highlight/)
- [Elastic Labs -- Chunking via Ingest Pipelines](https://www.elastic.co/search-labs/blog/chunking-via-ingest-pipelines)
- [Elastic Labs -- Chunking Strategies](https://www.elastic.co/search-labs/blog/chunking-strategies-elasticsearch)
- [ES Issue #52155](https://github.com/elastic/elasticsearch/issues/52155)

## 7) BM25 + tool-calling vs busca vetorial

O AtlasFile atual implementa retrieval via BM25 + tool-calling sobre MCP, nao via busca vetorial classica.

| Aspecto | Estado atual do AtlasFile | Observacao |
|---------|---------------------------|------------|
| Retrieval | BM25 full-text no OpenSearch | Implementado |
| Highlight | `content_chunks` + `*_ocr_folded` | Implementado |
| Orquestracao do assistente | LLM chama tools MCP com escopo por projeto | Implementado |
| Busca vetorial / hibrida | Nao implementada | Roadmap sob evidencia |

Busca vetorial passa a fazer sentido se:

- o corpus crescer com vocabulario muito heterogeneo
- a busca em linguagem natural tiver baixa aderencia lexical
- o custo de reformulacao iterativa via assistente deixar de ser aceitavel

Referencias:

- [OpenSearch k-NN plugin](https://opensearch.org/docs/latest/search-plugins/knn/index/)
- [Elastic Labs -- Hybrid search with RRF](https://www.elastic.co/search-labs/blog/hybrid-search-rrf)
- [LLM embeddings vs TF-IDF](https://machinelearningmastery.com/llm-embeddings-vs-tf-idf-vs-bag-of-words-which-works-better-in-scikit-learn/)

## 8) Classificacao documental

Para classificacao de documentos longos, as referencias externas continuam sustentando dois pontos:

- modelos supervisionados lineares esparsos sao bons candidatos quando existe massa rotulada suficiente
- no cold start, uma camada deterministica auditavel e necessaria

No AtlasFile 0.7.0 isso se traduz em:

- `bootstrap` deterministico como classificador operacional day-1
- `sparse_logreg` e `sparse_linear_svc` como candidatos benchmark-only
- `validation_set` e `training_pool` disjuntos como gate obrigatorio

Referencias:

- [Procycons -- Long document classification benchmark 2025](https://procycons.com/en/blogs/long-document-classification-benchmark-2025/)
- [Paperless-ngx classifier.py](https://git.labexposed.com/lgcosta/paperless-ngx/src/commit/83734c3bee86d1fb99853afa8498b138c07f91c2/src/documents/classifier.py)

## 9) Papel do LLM

As referencias de cascata e sistemas hibridos continuam validas, mas no AtlasFile atual o LLM nao e classificador principal.

Na 0.7.0:

- o LLM fica desabilitado por padrao na classificacao documental
- quando habilitado, atua como enriquecedor ou revisor
- qualquer reintroducao de LLM como decisor principal exigiria benchmark e gate explicito

Referencias:

- [CLARA](https://openreview.net/forum?id=eAW6yuszK7)
- [Fail Fast, or Ask](https://arxiv.org/abs/2507.14406)
- [Cascaded LLM Frameworks](https://arxiv.org/abs/2602.15391)

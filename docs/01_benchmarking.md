# Benchmarking e referencias verificadas

Este documento consolida praticas de mercado e normas usadas no desenho do AtlasFile.

## 1) Nomenclatura e portabilidade (records management)

- NARA (Appendix B) recomenda:
  - nomes de arquivos sem espacos;
  - apenas caracteres seguros (`a-z`, `0-9`, `_`, `-`);
  - caminho total <= 255 caracteres;
  - hierarquia de pastas com limite pratico de niveis.
- Referencia: [NARA Bulletin 2015-04 Appendix B](https://www.archives.gov/records-mgmt/bulletins/2015/2015-04-appendix-b.html)

## 2) Busca corporativa e metadados indexaveis

- Microsoft Learn reforca separacao entre propriedades coletadas e propriedades gerenciadas para busca.
- O principio central: so o que vai para propriedades gerenciadas e encontravel de forma consistente.
- Referencia: [Manage the search schema in SharePoint](https://learn.microsoft.com/en-us/sharepoint/manage-search-schema)

## 3) Governanca de registros e metadados

- ISO 15489 (records management) e ISO 23081 (metadata for records) sustentam:
  - autenticidade;
  - confiabilidade;
  - integridade;
  - usabilidade.
- Referencias:
  - [ISO 15489 overview (ISO committee)](https://committee.iso.org/sites/tc46sc11/home/projects/published/iso-15489-records-management.html)
  - [ISO 23081 metadata for records](https://committee.iso.org/sites/tc46sc11/home/projects/published/iso-23081-metadata-for-records.html)

## 4) Findability machine-readable

- FAIR enfatiza:
  - identificador unico e persistente;
  - metadados ricos;
  - indexacao em recurso pesquisavel.
- Referencia: [FAIR Principles (GO FAIR)](https://www.go-fair.org/fair-principles/)

## 5) Taxonomia operacional

- PARA ajuda a separar o que e ativo vs referencia/arquivo.
- Johnny.Decimal traz enderecamento numerico estavel e reduz ambiguidade.
- Referencias:
  - [The PARA Method](https://fortelabs.com/the-p-a-r-a-method-a-universal-system-for-organizing-digital-information-75a9da8bfb37)
  - [Johnny.Decimal](https://johnnydecimal.com/)

## 6) Perfil de metadados

- Dublin Core e um baseline simples e extensivel para descricao de recursos.
- Referencia: [Dublin Core Metadata Element Set](https://dublincore.org/specifications/dublin-core/dces/)

## 7) Busca BM25 para fase inicial

- OpenSearch/Elasticsearch adotam BM25 como baseline robusto para ranking lexical.
- Vantagens para fase 1:
  - previsibilidade;
  - baixa complexidade operacional;
  - explicabilidade para auditoria e operacao.
- Referencia:
  - [OpenSearch docs](https://opensearch.org/docs/latest/)
  - [Elasticsearch BM25 similarity](https://www.elastic.co/guide/en/elasticsearch/reference/current/index-modules-similarity.html)

## 8) Pure Nested: indexacao por chunks

Problema original: campos flat de conteudo (`content`, `content_normalized`, `content_chunks_text`, `content_chunks_normalized`) causavam HTTP 400 em PDFs grandes ao exceder `max_analyzed_offset` no highlight, alem de 5 copias redundantes do mesmo texto.

Opcoes avaliadas:

| Opcao | Descricao | Resultado |
|-------|-----------|-----------|
| **A) Safety net** | Adicionar `max_analyzer_offset` nas queries de highlight | Resolve o erro, mas mantem redundancia de storage e campos flat |
| **B) Pure Nested** (adotada) | Eliminar 4 campos flat; busca, highlight e retrieval exclusivamente via `content_chunks` (nested, ~1200 chars/chunk) | Elimina o erro estruturalmente, reduz storage 60-70%, scoring passage-level |
| **C) Separate documents per chunk** | Cada chunk como documento independente com join field | Escala melhor para >100K docs, mas complexidade desproporcional para nossa escala |

Decisao: **Pure Nested (B)** -- melhor custo/beneficio para escala pessoal/equipe (centenas a milhares de docs).

- Overhead de nested queries (~10-30%) imperceptivel nesta escala (~20ms vs ~15ms)
- Cross-chunk phrase matching mitigado por overlap de 150 chars entre chunks
- Scoring passage-level (melhor chunk determina relevancia do documento)
- Se necessario escalar para >100K docs, migracao para separate-documents-per-chunk e um refator previsivel
- Requer reindexacao (`RESET_INDEX=1`)

Referencias:
  - [OpenSearch Highlight](https://opensearch.org/docs/latest/search-plugins/searching-data/highlight/)
  - [Elastic Labs -- Chunking via Ingest Pipelines](https://www.elastic.co/search-labs/blog/chunking-via-ingest-pipelines)
  - [Elastic Labs -- Chunking Strategies](https://www.elastic.co/search-labs/blog/chunking-strategies-elasticsearch)
  - [ES Issue #52155](https://github.com/elastic/elasticsearch/issues/52155)

## 9) BM25 + tool-calling vs RAG com busca vetorial

O AtlasFile implementa uma forma de RAG (Retrieval-Augmented Generation) via BM25 + MCP tool-calling, nao via busca vetorial classica:

| Aspecto | RAG classico (vetorial) | AtlasFile (BM25 + tool-calling) |
|---------|-------------------------|----------------------------------|
| Retrieval | Embedding model → vector store → similaridade semantica | BM25 full-text → OpenSearch → match lexical |
| Augmentation | Chunks injetados no prompt | Resultados de tools injetados via tool results |
| Orquestracao | Pipeline fixo: retrieve → inject → generate | Loop iterativo: LLM decide quais tools chamar, quantas vezes, com quais parametros |

### Por que BM25 e suficiente para o contexto atual

- **Precisao lexical**: documentos juridicos/financeiros dependem de termos exatos (numeros de contrato, nomes de entidades, clausulas). BM25 retorna exatamente o que contem as palavras buscadas.
- **Zero custo de embedding**: sem chamadas de API para gerar vetores na indexacao ou busca.
- **Zero infra adicional**: OpenSearch ja cobre busca, highlight e filtros estruturados.
- **Explicabilidade**: highlight mostra *por que* o resultado apareceu. Vetores sao opacos.
- **Filtros nativos**: projeto, area, tipo, data combinam naturalmente com BM25. Em busca vetorial, filtrar pos-retrieval pode cortar resultados relevantes.
- **Tool-calling compensa o gap semantico**: o LLM reformula queries iterativamente (ex: busca "penalidades atraso", depois "multa inadimplemento", depois "clausula penal") -- funciona como um agente semantico sobre BM25.

### Quando busca vetorial agregaria valor

- Corpus >5-10K documentos com vocabulario heterogeneo
- Buscas frequentes em linguagem natural que nao casam com a terminologia dos documentos
- Necessidade de busca cross-language
- Custo de multiplos roundtrips LLM para reformulacao se tornar relevante

### Caminho de evolucao (se/quando necessario)

OpenSearch suporta k-NN nativamente. A migracao seria **hibrida** (BM25 + k-NN com scoring combinado), nao substituicao:
- Gerar embeddings por chunk na indexacao (via API de embedding do provider)
- Combinar score BM25 + similaridade vetorial nas queries
- Nao altera a arquitetura Pure Nested -- adiciona um campo de embedding aos chunks existentes

Referencias:
  - [OpenSearch k-NN plugin](https://opensearch.org/docs/latest/search-plugins/knn/index/)
  - [Elastic Labs -- Hybrid search with RRF](https://www.elastic.co/search-labs/blog/hybrid-search-rrf)
  - [LLM embeddings vs TF-IDF](https://machinelearningmastery.com/llm-embeddings-vs-tf-idf-vs-bag-of-words-which-works-better-in-scikit-learn/)
  - [Procycons -- Long document classification benchmark 2025](https://procycons.com/en/blogs/long-document-classification-benchmark-2025/)

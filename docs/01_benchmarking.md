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

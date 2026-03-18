# Gap analysis -- status na 0.7.0

Este documento atualiza o gap analysis original para refletir o estado atual do AtlasFile. O foco aqui nao e mais descrever o caos do snapshot inicial, e sim mostrar o que ja foi fechado e o que ainda falta.

## Gaps ja fechados

### Estrutura e contrato de projeto

Fechado:

- profile local por projeto em `_PROFILE/profile.json`
- roots PARA padronizadas
- `_INBOX_DROP` e `_TRIAGE_REVIEW` como fluxo operacional
- layout fisico em `02_AREAS/<business_domain>/<document_type>/`

### Busca e indexacao

Fechado:

- indice local em OpenSearch
- busca full-text BM25 com highlight
- suggest/autocomplete
- filtros por projeto e metadados
- campos `*_ocr_folded` para melhorar busca em OCR ruidoso
- priorizacao de match exato de titulo/nome de arquivo

### Rastreabilidade

Fechado:

- `_INDEX.md` por projeto
- `doc_id`
- `canonical_filename`
- `sha256`
- reconcile entre filesystem e indice

### Classificacao e triagem

Fechado:

- taxonomia canonica por `business_domain` e `document_type`
- bootstrap deterministico como baseline operacional
- triagem humana via frontend
- separacao entre `validation_set` e `training_pool`
- benchmark oficial com gate de integridade entre datasets

## Gaps ainda abertos

### Acuracia do eixo funcional

Aberto:

- `business_domain` ainda e o eixo mais fragil do classificador
- ha sobreposicao semantica relevante entre `juridico`, `societario`, `financeiro`, `ti` e `operacoes`
- classes com pouco suporte estatistico continuam limitando ajuste fino

### Ciclo supervisionado

Aberto:

- ainda nao existe retreino em lote com promocao automatizada
- os modelos supervisionados continuam em modo benchmark-only
- a promocao de um novo classificador ainda depende de decisao explicita apos benchmark

### Busca semantica

Aberto:

- nao ha busca vetorial/hibrida implementada
- o assistente trabalha hoje sobre BM25 + tools MCP

### Retencao e observabilidade avancada

Aberto:

- politica de retencao automatizada
- dashboards operacionais
- alertas e observabilidade aprofundada

## Estado alvo de curto prazo

- manter bootstrap como baseline operacional
- elevar a qualidade do `business_domain` com ajustes guiados por benchmark
- ampliar `validation_set` apenas nas classes subcobertas
- promover supervisionado so se superar o bootstrap com evidencia

## KPIs de fechamento do gap remanescente

- aumentar `business_domain_accuracy`
- aumentar `exact_match_accuracy`
- reduzir `triage_rate` sem perder qualidade
- manter `dataset_integrity_status = ok`
- manter rastreabilidade completa em 100% dos documentos ingeridos

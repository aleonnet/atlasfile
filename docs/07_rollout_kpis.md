# Rollout e KPIs

## Estado consolidado da 0.7.0

### Bloco 1 -- Fundacoes e contrato de projeto

Consolidado:

- Profile V2 em JSON com schema validado por Pydantic
- templates em `config/templates/`
- roots PARA mantidas
- layout operacional em `02_AREAS/<business_domain>/<document_type>/`
- naming canonico configuravel

### Bloco 2 -- Ingestao, triagem e indice

Consolidado:

- ingestao por `_INBOX_DROP`
- dedup por SHA256
- triagem humana via frontend (`Approve`, `Correct`, `Reject`)
- reconcile filesystem <-> OpenSearch
- indexacao `pure nested` por chunks
- busca BM25 com highlight, suggest e filtros estruturados
- campos `*_ocr_folded` para robustez a OCR

### Bloco 3 -- Classificacao documental

Consolidado:

- taxonomia canonica por `business_domain` e `document_type`
- bootstrap deterministico como classificador operacional
- `validation_set` e `training_pool` separados
- benchmark oficial via `backend/scripts/benchmark_classification.py`
- candidatos supervisionados `sparse_logreg` e `sparse_linear_svc` avaliados, mas ainda sem promocao automatica

### Bloco 4 -- Assistente e canais

Consolidado:

- chat web com sessoes persistentes
- Telegram com escopo por projeto
- tools MCP sobre o indice real
- busca priorizando match exato de titulo/nome de arquivo
- rastreamento de uso/custo de chat

## O que nao deve ser tratado como concluido

Ainda planejado ou parcial:

- retreino em lote + benchmark + promocao explicita de modelo supervisionado
- busca vetorial/hibrida
- reranking semantico
- politica de retencao automatizada
- dashboards e alertas operacionais avancados

## Proximo ciclo recomendado

1. Congelar `validation_set` revisado.
2. Ajustar o bootstrap apenas onde houver evidencia no benchmark.
3. Rerodar `--mode all` e medir delta.
4. So promover supervisionado se superar o bootstrap com gate explicito.
5. Repetir o ciclo apos novas triagens revisadas entrarem no `training_pool`.

## KPIs operacionais

| KPI | Descricao |
|-----|-----------|
| `auto_classification_rate` | % de documentos roteados sem triagem |
| `triage_rate` | % de documentos enviados para triagem humana |
| `triage_sla_breach_rate` | % de triagens pendentes acima do SLA |
| `search_first_result_success_rate` | % de buscas em que o 1o resultado atende a intencao |
| `indexing_latency_p95` | Latencia p95 entre ingestao e disponibilidade no indice |
| `traceability_completeness_rate` | % de documentos com nome original, nome canonico, path e SHA256 |
| `duplicate_detection_rate` | % de duplicatas pegas antes da indexacao |

## KPIs de benchmark de classificacao

| KPI | Descricao |
|-----|-----------|
| `business_domain_accuracy` | Acuracia do eixo funcional no `validation_set` |
| `document_type_accuracy` | Acuracia do eixo formal no `validation_set` |
| `exact_match_accuracy` | Acuracia do par `business_domain + document_type` |
| `dataset_integrity_status` | Status de separacao entre `validation_set` e `training_pool` |
| `docs_per_class_min` | Menor suporte por classe no benchmark |

## Papel do LLM neste rollout

Na 0.7.0:

- o LLM nao e classificador principal
- a classificacao por LLM fica desabilitada por padrao no template default
- quando habilitado, seu papel e enriquecimento ou revisao
- o custo de classificacao deve ser auditado separadamente em `atlasfile_classification_usage`

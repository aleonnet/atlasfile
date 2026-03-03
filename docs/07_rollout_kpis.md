# Rollout e KPIs

## Fases

### Fase 0 - Framework e contratos

- aprovar estrutura, naming, indices e profile template.

### Fase 1 - MVP operacional

- ingestao por `_INBOX_DROP`;
- classificacao por profile;
- triagem no frontend;
- busca BM25.

### Fase 2 - Hardening

- observabilidade;
- reprocessamento;
- tuning de regras.

### Fase 3 - Evolucao IA

- reranking semantico;
- aprendizado supervisionado com historico de triagem.

## KPIs

- `auto_classification_rate`
- `triage_rate`
- `triage_sla_breach_rate`
- `search_first_result_success_rate`
- `indexing_latency_p95`
- `traceability_completeness_rate`

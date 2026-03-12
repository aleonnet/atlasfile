# Rollout e KPIs

## Fases

### Fase 0 — Framework e contratos (concluída)

- Estrutura de projeto, naming convention, índices e profile template definidos.
- Documentação de referência: benchmarking, gap analysis, modelo de índice.

### Fase 1 — MVP operacional (concluída)

- Ingestão por `_INBOX_DROP` com classificação por routing rules + alias scoring.
- Triagem humana no frontend (`Approve`, `Correct`, `Reject`).
- Busca full-text BM25 com highlight e autocomplete.
- Indexação em OpenSearch com 35+ campos.
- MCP server com tools de busca, tags e metadados.
- Assistente LLM com chat multi-modelo e sessões persistentes.

### Fase 2 — Hardening (concluída)

- Profile V2 (JSON) com schema validado (Pydantic).
- Templates CRUD (builtin + user) com editor visual.
- Dedup precoce por SHA256.
- Histórico de ingestões persistente (FIFO, cap 50).
- Word boundary matching + sqrt normalization no classificador.
- Reconciliação automática (filesystem ↔ OpenSearch).
- Extração multi-formato (PDF, DOCX, XLSX, PPTX, HTML, MSG, ZIP, RAR).
- Layout workspace (simulação e aplicação de migração de pastas).
- Endpoint de estatísticas agregadas (`GET /api/stats`).
- Filtros de busca por `doc_kind` e `area_key`.

### Fase 3 — Evolução IA (concluída)

- LLM no fluxo de classificação (3 modos: tag_only, review, full_override).
- Contexto de projeto injetado no prompt (áreas, aliases, topics).
- LLM visibility: campos `rule_area_key`, `llm_explanation`, `llm_proposed_area`.
- Auto-criação de áreas quando LLM propõe área inexistente.
- Guardrails configuráveis (confiança mínima para override, exigir explicação).
- Topics semânticos via dicionário (`config/topics_v1.yaml`).

### Fase 4 — Canais e observabilidade (concluída)

- Camada nativa de channels (Telegram via aiogram 3.x; extensível para Discord, Slack).
- Canais como pipe transparente: sessões, histórico e usage unificados com o chat web.
- Rastreamento de uso e custo por sessão (tokens input/output/cache + custo estimado por modelo).
- Custo configurável por modelo via `config/usage_costs.json`.
- Rastreamento separado de uso LLM na classificação de documentos (`classification_usage`).
- Gestão de janela de contexto: truncamento FIFO automático + indicador visual (ContextRing).
- Autosave de sessão com título automático.
- DOCX com localização amigável (Página/Parágrafo) via estratégia híbrida.
- Redesign da busca no estilo Mintlify.

### Fase 5 — Próximos passos (planejado)

- Reranking semântico (embeddings).
- Aprendizado supervisionado com histórico de triagem.
- Política de retenção e arquivamento (ver `06_retention_policy.md`).
- Observabilidade e métricas operacionais avançadas (dashboards, alertas).

## KPIs

| KPI | Descrição |
|-----|-----------|
| `auto_classification_rate` | % de documentos classificados automaticamente (sem triagem) |
| `triage_rate` | % de documentos enviados para triagem humana |
| `triage_sla_breach_rate` | % de triagens pendentes acima do SLA (48h) |
| `search_first_result_success_rate` | % de buscas onde o 1o resultado é relevante |
| `indexing_latency_p95` | Latência p95 de indexação após ingestão |
| `traceability_completeness_rate` | % de documentos com rastreabilidade completa (original → canônico → SHA256) |
| `duplicate_detection_rate` | % de duplicatas detectadas antes do fluxo completo |
| `llm_override_accuracy` | % de overrides do LLM aceitos (não corrigidos na triagem) |

# Plano: Grafico diario de tokens — incluir todos os processos, abas "Por tipo" e "Por processo"

**Status:** Concluido (2026-04-03)

## Context

O grafico "Uso diario de tokens" e o "Tokens por tipo" mostravam apenas dados de sessoes do assistente (via `summary.by_day`). Tokens de treinamento e classificacao eram incluidos nos cards de resumo mas nao apareciam no grafico.

Problemas:
- 03/abr (so treinamento) nao aparecia no grafico
- 02/abr mostrava 245k no grafico mas 607k nos cards
- Aba "Total" era redundante (total ja exibido acima de cada barra)
- OpenAI cached_tokens nao era capturado pelo orchestrator

## Decisoes

### Abas do grafico
- Removida aba "Total" (redundante)
- Mantida aba "Por tipo": Input/Output/Cache Read/Cache Write (todos os processos)
- Adicionada aba "Por processo": Assistente/Classificacao/Treinamento (todos os tipos)
- Legenda lateral (`TokensByTypeBar`) alterna junto com a aba selecionada

### Cores por processo
- Assistente: `#f39c12` (laranja)
- Classificacao: `#9b59b6` (roxo)
- Treinamento: `#3498db` (azul)

### Cache tokens da OpenAI
- OpenAI retorna cache read em `usage.prompt_tokens_details.cached_tokens`
- Capturado em 3 locais: `_run_chat_openai`, `_classify_openai`, `benchmark_llm_candidate`

## Mudancas realizadas

| Arquivo | Mudanca |
|---------|---------|
| `backend/app/orchestrator.py` | Captura `cached_tokens` da OpenAI em chat e classificacao |
| `backend/app/classifier_cycle.py` | Captura `cached_tokens` no benchmark_llm |
| `backend/app/main.py` | `by_day` (date_histogram) nos endpoints training e classification |
| `backend/app/models.py` | `by_day` em `TrainingUsageSummary` e `ClassificationUsageSummary` |
| `frontend/src/types.ts` | `by_day` em `TrainingUsageSummary` e `ClassificationUsageSummary` |
| `frontend/src/features/usage/UsageView.tsx` | Redesenho completo: `DailyTokenChart` (abas Por tipo/Por processo, merge 3 datasets), `TokensByTypeBar` alterna com o modo, estado `chartMode` levantado ao pai |
| `backend/tests/integration/test_api_channel_features.py` | Mocks atualizados com `by_day` buckets |

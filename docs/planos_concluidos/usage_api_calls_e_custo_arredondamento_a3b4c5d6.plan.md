# Plano: Corrigir tracking de tokens/custo, unificar nomenclatura e adicionar contagem de chamadas API

**Status:** Concluido (2026-04-03)

## Context

O benchmark_llm fez 62 chamadas a API OpenAI em 03/04. Comparando AtlasFile vs OpenAI:

| Metrica | AtlasFile | OpenAI Real | Causa |
|---------|-----------|-------------|-------|
| Total tokens | 362k (357k in + 5.2k out) | 356,729 | AtlasFile soma in+out; OpenAI destaca input. Input diff ~0.08%, irrelevante |
| Custo | $0.05 | $0.06 | `Math.floor` trunca em vez de arredondar |
| Chamadas | 1 (doc_count) | 62 requests | Persiste 1 doc com `records_processed=62`, mas exibe doc_count |

## Decisoes

### Nomenclatura unificada (duas dimensoes)

| Categoria | Dimensao 1: Processos | Dimensao 2: Chamadas API |
|-----------|----------------------|--------------------------|
| **Assistente** | Sessoes (`session_count`) | `api_call_count` (novo) |
| **Treinamento** | Treinamentos (`total_calls` = doc_count) | `total_api_calls` (exposto via `records_processed`) |
| **Classificacao** | N/A (1 doc = 1 chamada) | `total_calls` = doc_count (ja correto) |

### Custo: arredondamento vs truncamento
- `formatUsd()` e `formatUsd4()`: `Math.floor` -> `Math.round`

### Card "Chamadas API"
- Um card unico somando todas as categorias (assistente + classificacao + treinamento)

## Mudancas realizadas

| Arquivo | Mudanca |
|---------|---------|
| `frontend/src/features/usage/UsageView.tsx` | Fix formatUsd, card Chamadas API, renomear colunas |
| `frontend/src/features/usage/UsageView.test.tsx` | Novo — testes de formatUsd/formatUsd4/formatTokens |
| `frontend/src/types.ts` | `api_call_count`, `total_api_calls` em interfaces |
| `frontend/src/App.tsx` | Acumular `api_call_count` no merge de usage |
| `backend/app/orchestrator.py` | `api_call_count` em `_accumulate_usage` e `_usage_return` |
| `backend/app/models.py` | `api_call_count` em UsageTotals/TurnUsage, Training*, UsageSummaryResponse |
| `backend/app/main.py` | `api_call_count` em `_merge_usage`, endpoints summary e training |
| `backend/tests/unit/test_orchestrator_api_call_count.py` | Novo — testes de contagem |
| `backend/tests/integration/test_api_channel_features.py` | Testes para training endpoint e api_call_count |

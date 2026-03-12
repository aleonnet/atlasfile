---
name: Fix usage cost tracking
overview: "Corrigir todas as inconsistencias no rastreamento de uso e custo: discrepancia de custo multi-modelo, perda de usage em sessoes novas, e ausencia de breakdown por modelo."
todos:
  - id: bug1-models
    content: "Backend: Adicionar usage_by_model em ChatSession, ChatSessionCreate, ChatSessionUpdate, UsageSessionItem (models.py)"
    status: completed
  - id: bug1-mapping
    content: "Backend: Adicionar usage_by_model ao mapping OpenSearch (opensearch_client.py)"
    status: completed
  - id: bug1-main-crud
    content: "Backend: Persistir/ler usage_by_model em create/update/read session (main.py)"
    status: completed
  - id: bug1-summary
    content: "Backend: Summary usa usage_by_model para agregacao por modelo com fallback legado (main.py)"
    status: completed
  - id: bug1-types
    content: "Frontend: Adicionar usage_by_model em types.ts"
    status: completed
  - id: bug1-api
    content: "Frontend: Aceitar usage_by_model em create/update (api.ts)"
    status: completed
  - id: bug2-app
    content: "Frontend: Acumular usage FORA do guard activeSessionId + enviar no create + state por modelo (App.tsx)"
    status: completed
  - id: validate
    content: "Validacao: rebuild Docker, testar multi-modelo, verificar OpenSearch e UI"
    status: completed
isProject: false
---

# Diagnostico e Plano de Ajuste: Usage e Custo

## Diagnostico fim a fim (5 bugs encontrados)

### BUG 1 (Critico) -- Discrepancia custo total vs. input+output

**Sintoma observado**: Na tabela "Por modelo", `$0.26 (input) + $0.00 (output) != $0.40 (total)`.

**Causa raiz**: A sessao `81c8a30b` foi usada com **dois modelos** (gpt-4.1 e gpt-5.1). O orquestrador calcula o custo de cada turno com o modelo **correto** do turno, e o frontend soma corretamente. Resultado: `estimated_cost_usd = $0.404127` (correto).

Porem, a sessao armazena apenas **um campo `model`** (o ultimo usado, `"openai/gpt-4.1"`) e **um unico `usage_totals`** (soma de todos os turnos). Quando o endpoint `GET /api/usage/summary` recalcula `input_cost_usd` e `output_cost_usd`, ele usa **todos os 106.869 tokens** com preco de gpt-4.1 ($2.50/1M), obtendo $0.267 -- quando parte desses tokens veio de gpt-5.1 ($5.00/1M).

**Prova numerica**:

- `(106869 / 1M) * 2.50 + (982 / 1M) * 10.00 = $0.277` (recalculado, errado)
- Stored: `$0.404` (correto, acumulado por turno com modelo certo)
- Delta: `$0.127` = tokens de gpt-5.1 cobrados a preco menor

### BUG 2 (Critico) -- Sessoes novas nao salvam usage_totals

**Causa raiz**: Em [frontend/src/App.tsx](frontend/src/App.tsx) L793, a acumulacao de usage esta dentro de `if (activeSessionId)`. Sessoes novas (antes de serem salvas) nao tem `activeSessionId`. Quando o usuario clica "Salvar" (`handleRequestNewSession` L847), a sessao e criada SEM `usage_totals` (L866-871). Em seguida, `setSessionUsageTotals(null)` (L879) descarta tudo.

**Resultado**: Toda sessao criada do zero tem `usage_totals: null`, mesmo com multiplos turnos.

### BUG 3 (Menor) -- generateTitleInBackground consome tokens nao contabilizados

**Causa raiz**: `generateTitleInBackground` (L886-908) chama `sendChatMessage` e descarta `res.usage`. Tokens gastos na geracao de titulo nao entram em `usage_totals`.

**Impacto**: Residual (poucas dezenas de tokens por titulo), mas acumula ao longo do tempo.

### BUG 4 (Critico) -- Sem breakdown por modelo

**Causa raiz**: Backend armazena um unico `model` por sessao (ultimo usado). O summary agrupa por esse campo, atribuindo TODOS os tokens ao ultimo modelo. Se gpt-5.1 foi usado em turnos anteriores, seus tokens aparecem sob gpt-4.1.

### BUG 5 (Estrutural) -- Summary recalcula custos com modelo errado

**Causa raiz**: Em [backend/app/main.py](backend/app/main.py) L1399-1403, `input_cost_usd` e `output_cost_usd` sao recalculados a partir de tokens totais com o preco de um unico modelo (o da sessao). Isso e inerentemente errado para sessoes multi-modelo. Com `usage_by_model`, este bug sera eliminado.

---

## Plano de ajuste

### 1. Backend: Adicionar `usage_by_model` ao modelo de dados

**Arquivo**: [backend/app/models.py](backend/app/models.py)

- Adicionar campo `usage_by_model: Optional[dict[str, UsageTotals]] = None` em:
  - `ChatSession` (leitura)
  - `ChatSessionCreate` (criacao -- para capturar turnos pre-save)
  - `ChatSessionUpdate` (atualizacao via PATCH)
  - `UsageSessionItem` (listagem de sessions no usage)

Estrutura armazenada no OpenSearch:

```json
{
  "usage_by_model": {
    "openai/gpt-4.1": { "input_tokens": 80000, "output_tokens": 500, "total_tokens": 80500, "estimated_cost_usd": 0.205 },
    "openai/gpt-5.1": { "input_tokens": 26869, "output_tokens": 482, "total_tokens": 27351, "estimated_cost_usd": 0.199 }
  },
  "usage_totals": { "input_tokens": 106869, "output_tokens": 982, "total_tokens": 107851, "estimated_cost_usd": 0.404 }
}
```

### 2. Backend: OpenSearch mapping

**Arquivo**: [backend/app/opensearch_client.py](backend/app/opensearch_client.py)

- Adicionar `"usage_by_model": {"type": "object", "enabled": False}` ao `put_mapping` (nao precisa ser buscavel, apenas armazenado).

### 3. Backend: PATCH persiste usage_by_model

**Arquivo**: [backend/app/main.py](backend/app/main.py)

- Em `update_chat_session` (L1282): adicionar persistencia de `usage_by_model` no partial doc.
- Em `create_chat_session` (L1262): incluir `usage_by_model` se fornecido no body.
- Em `_session_doc_to_model` (L1211): ler `usage_by_model` do doc.

### 4. Backend: Summary usa usage_by_model

**Arquivo**: [backend/app/main.py](backend/app/main.py), endpoint `get_usage_summary`

Alterar a logica de agregacao "Por modelo":

- Se `usage_by_model` existe no doc, iterar SUAS chaves (cada modelo separado com tokens e custo corretos).
- Se `usage_by_model` nao existe (sessoes legadas), fallback para o comportamento atual (model do doc + usage_totals).
- `input_cost_usd` e `output_cost_usd` serao recalculados POR MODELO a partir dos tokens corretos de cada modelo.

### 5. Frontend: Tipos

**Arquivo**: [frontend/src/types.ts](frontend/src/types.ts)

- Adicionar `usage_by_model?: Record<string, UsageTotals> | null` em `ChatSession` e `UsageSessionItem`.

### 6. Frontend: API

**Arquivo**: [frontend/src/api.ts](frontend/src/api.ts)

- `createChatSession`: aceitar `usage_totals` e `usage_by_model` no payload.
- `updateChatSession`: aceitar `usage_by_model` no payload.

### 7. Frontend: App.tsx -- acumular usage por modelo

**Arquivo**: [frontend/src/App.tsx](frontend/src/App.tsx)

Mudancas:

- **Novo state**: `sessionUsageByModel: Record<string, UsageTotals>` (inicializa `{}`).
- **handleChatSend** (L786-821):
  - Mover acumulacao de usage para FORA do `if (activeSessionId)`. Sempre acumular em `sessionUsageTotals` e `sessionUsageByModel[selectedModel]`.
  - Dentro do `if (activeSessionId)`, apenas enviar o PATCH com os valores acumulados.
- **handleRequestNewSession** (L847-884):
  - Passar `usage_totals: sessionUsageTotals` e `usage_by_model: sessionUsageByModel` no `createChatSession`.
- **handleChatNewSession**: resetar `sessionUsageByModel` para `{}`.
- **Ao carregar sessao do historico** (L946): setar `sessionUsageByModel` a partir de `session.usage_by_model ?? {}`.
- **Ao deletar sessao** (L965): resetar `sessionUsageByModel`.

### 8. Frontend: UsageView nao precisa de mudanca

A `UsageView` ja consome `by_model` do response do summary. Como o summary sera corrigido no backend (item 4), os dados chegarao corretos.

### 9. Bug 3 (titulo) -- decisao necessaria

**Opcao A** (recomendada): Ignorar -- custo de titulo e residual (~100-500 tokens/titulo) e nao distorce os totais significativamente.

**Opcao B**: Acumular na sessao -- exigiria chamar updateChatSession apos gerar titulo, adicionando complexidade. Pode confundir o usuario ("por que tem custo nessa sessao se eu nao mandei nada?").

---

## Resumo de mudancas

- `backend/app/models.py`: campo `usage_by_model` em 4 classes
- `backend/app/opensearch_client.py`: mapping `usage_by_model`
- `backend/app/main.py`: create/update/read session + summary aggregation
- `frontend/src/types.ts`: campo `usage_by_model` em 2 interfaces
- `frontend/src/api.ts`: payloads de create/update
- `frontend/src/App.tsx`: states + acumulacao por modelo + envio no create/update

**Nenhum arquivo novo** precisa ser criado. **Nenhuma migracao destrutiva** -- `usage_by_model` e opcional, sessoes legadas continuam funcionando com fallback.

## Validacao pos-implementacao

- Enviar mensagens com modelo A, trocar para modelo B, enviar mais
- Verificar no OpenSearch que `usage_by_model` tem ambos os modelos com tokens e custos corretos
- Verificar que `usage_totals` = soma dos `usage_by_model`
- Verificar na UI "Por modelo" que `input_cost + output_cost ~= estimated_cost` para cada modelo
- Verificar sessao nova (criada do zero): `usage_totals` nao-null apos salvar
- Verificar sessao legada (sem `usage_by_model`): fallback funciona sem erro


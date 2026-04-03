# Plano: Gráficos no Chat + Custos de Treinamento

## Contexto

**Problema 1 — Gráficos**: O LLM recusa pedidos de visualização ("não tenho capacidade de gerar gráficos"), mas já tem acesso a dados estruturados via `get_stats()` (MCP tool). O frontend usa `react-markdown` sem renderer customizado para code blocks. Não existe biblioteca de charts. O chat é espelhado no Telegram, que só envia texto (`send_message`) — sem suporte a imagens atualmente.

**Problema 2 — Custos de Treinamento**: O sistema de custos rastreia chat (por sessão/modelo no OpenSearch) e classificação (índice dedicado `classification_usage`). Os scripts `label_corpus_llm.py` e `run_augmentation.py` fazem chamadas LLM mas não persistem custos. O `label_corpus_llm.py` acumula tokens e calcula custo hardcoded (`total_input * 0.15 / 1_000_000`). O `classifier_augmentation.py` descarta completamente os tokens da resposta LLM.

**Decisão de biblioteca**: Recharts — mesma lib usada pelo Claude.ai Artifacts para renderizar charts no chat. 139KB gzip (inclui Redux no v3), mas irrelevante para 1-2 charts por conversa. Suporta nativamente todos os tipos necessários exceto waterfall.

**Estratégia de renderização dual**:
- **Web**: Recharts client-side (SVG interativo com tooltips)
- **Telegram**: matplotlib server-side → PNG → `send_photo` via aiogram Bot API

**Schema universal do chart** (JSON emitido pelo LLM no bloco ` ```chart `):
```json
{
  "type": "bar | stacked_bar | horizontal_bar | pie | line | area | composed | treemap",
  "title": "Título do gráfico",
  "data": [{"name": "rótulo", "value": 123}],
  "series": ["value", "value2"],
  "xKey": "name",
  "yKey": "value"
}
```

- `data`: array de objetos. Cada objeto tem `name` (rótulo) + 1 ou mais campos numéricos
- `series`: opcional, para stacked/composed — lista de keys numéricas no data
- `xKey`/`yKey`: opcionais, defaults "name"/"value"
- `type: "composed"`: usa `series` para determinar quais são `bar` e quais `line` (último da lista = line)

---

## Fase 1 — Recharts + ChartBlock (frontend)

**Objetivo**: Instalar Recharts e criar o componente de renderização de charts no chat.

### TODO 1.1 — Instalar Recharts
- `cd frontend && npm install recharts`
- **Arquivo**: `frontend/package.json`

### TODO 1.2 — Criar componente ChartBlock
- **Novo arquivo**: `frontend/src/components/ChartBlock.tsx`
- Ler antes: `frontend/src/features/usage/UsageView.tsx` (paleta TOKEN_COLORS e padrão visual)
- Ler antes: `frontend/src/styles.css` (variáveis CSS do projeto)
- Props: `{ jsonString: string }`
- Parse JSON com try/catch → fallback `<pre>` se inválido
- Tipos suportados com componentes Recharts:
  - `bar` → `<BarChart>` com `<Bar>`
  - `stacked_bar` → `<BarChart>` com múltiplos `<Bar stackId="a">`
  - `horizontal_bar` → `<BarChart layout="vertical">`
  - `pie` → `<PieChart>` com `<Pie>` + `<Cell>` para cores
  - `line` → `<LineChart>` com `<Line>`
  - `area` → `<AreaChart>` com `<Area>`
  - `composed` → `<ComposedChart>` com `<Bar>` + `<Line>` mistos
  - `treemap` → `<Treemap>`
- Wrapper: `<ResponsiveContainer width="100%" height={280}>`
- Paleta de cores: array fixo de 8 cores harmônicas derivadas das variáveis CSS existentes
- Todos os charts incluem `<Tooltip>` e `<Legend>` quando aplicável

### TODO 1.3 — Criar CSS do ChartBlock
- **Novo arquivo**: `frontend/src/components/ChartBlock.css`
- Ler antes: `frontend/src/components/ChatPanel.css` (estilos de `.chat-bubble`)
- `.chart-block-container`: min-height 280px, border-radius consistente, padding 12px, background sutil

### TODO 1.4 — Teste unitário ChartBlock
- **Novo arquivo**: `frontend/src/components/ChartBlock.test.tsx`
- Casos: JSON válido (bar, pie, stacked_bar) renderiza sem erro; JSON inválido mostra `<pre>`; tipo desconhecido mostra fallback
- Rodar: `cd frontend && npx vitest run src/components/ChartBlock.test.tsx`

### Gate Fase 1
```bash
cd frontend && npx vitest run src/components/ChartBlock.test.tsx
cd frontend && npm run build
```
**Ambos devem passar antes de avançar.**

---

## Fase 2 — Integrar ChartBlock no ChatPanel + System Prompt

**Objetivo**: Conectar o componente ao fluxo de mensagens e instruir o LLM.

### TODO 2.1 — Custom code renderer no ChatPanel
- **Arquivo**: `frontend/src/components/ChatPanel.tsx` (linha 566, `markdownComponents`)
- Ler antes: o arquivo completo para entender o contexto do renderer
- Adicionar `code` ao `markdownComponents`:
  - Detecta `className === "language-chart"` e não inline → `<ChartBlock jsonString={children} />`
  - Senão: renderiza `<code>` padrão preservando o comportamento atual

### TODO 2.2 — Atualizar system prompt
- **Arquivo**: `backend/app/prompts/system_prompt_chat.md` (após "Tags e metadados", antes de "Estratégias de resposta")
- Ler antes: o arquivo completo (42 linhas)
- Nova seção:
```markdown
## Visualizações (gráficos)

Você PODE e DEVE gerar gráficos quando o usuário pedir visualizações, distribuições ou análises visuais.
Use `get_stats` ou outras ferramentas para obter os dados, depois emita um bloco de código com a tag `chart`:

\```chart
{"type": "bar", "title": "Título", "data": [{"name": "rótulo", "value": 123}]}
\```

Tipos disponíveis:
- `bar`: comparação entre categorias
- `stacked_bar`: decomposição de categorias (requer `series` com lista de keys numéricas)
- `horizontal_bar`: ranking/ordenação (ex: documentos por tamanho)
- `pie`: distribuição proporcional
- `line`: séries temporais
- `area`: volume acumulado ao longo do tempo
- `composed`: combina barras + linhas no mesmo eixo (requer `series`)
- `treemap`: hierarquia visual (ex: domínio → tipo)

Regras:
- Sempre busque os dados reais com ferramentas antes de gerar o gráfico
- Limite a 20 itens; agrupe menores em "Outros" se necessário
- Para múltiplas séries, use `series: ["key1", "key2"]`
- Inclua `title` descritivo em português
- Adicione uma frase de contexto/insight antes ou depois do bloco chart
```

### TODO 2.3 — Teste de integração frontend
- Rodar suite completa: `cd frontend && npx vitest run`
- Garantir zero regressões

### Gate Fase 2
```bash
cd frontend && npx vitest run
cd frontend && npm run build
```
**Ambos devem passar antes de avançar.**

---

## Fase 3 — Renderer server-side para Telegram

**Objetivo**: Quando o LLM gera um bloco `chart` e a resposta vai para o Telegram, renderizar como imagem.

### TODO 3.1 — Adicionar matplotlib ao backend
- **Arquivo**: `backend/requirements.txt`
- Ler antes: o arquivo completo para verificar se matplotlib já existe
- Adicionar `matplotlib>=3.9` (se não existir)

### TODO 3.2 — Criar módulo chart_renderer
- **Novo arquivo**: `backend/app/chart_renderer.py`
- Ler antes: `backend/app/channels/telegram.py` (entender o formato de envio)
- Função principal: `render_chart_png(chart_json: dict) -> bytes`
  - Recebe o dict parseado do bloco `chart`
  - Usa matplotlib para gerar o gráfico conforme `type`
  - Retorna bytes PNG (via `BytesIO` + `savefig(format='png', dpi=150, bbox_inches='tight')`)
  - Suportar os mesmos 8 tipos do frontend
  - Estilo visual: fundo escuro (`#1e1e2e`), texto claro — consistente com o tema dark do app
- Função auxiliar: `extract_chart_blocks(text: str) -> list[tuple[dict, str]]`
  - Regex para encontrar blocos ` ```chart\n{...}\n``` ` no texto
  - Retorna lista de (chart_json_parsed, bloco_original_string)

### TODO 3.3 — Adicionar `send_photo` ao TelegramChannel
- **Arquivo**: `backend/app/channels/telegram.py`
- Ler antes: o arquivo completo (~292 linhas)
- Novo método:
```python
async def send_photo(self, chat_id: str, photo_bytes: bytes, caption: str = "") -> None:
    from io import BytesIO
    await self._bot.send_photo(
        chat_id=int(chat_id),
        photo=BufferedInputFile(photo_bytes, filename="chart.png"),
        caption=caption[:1024] if caption else None,
        parse_mode=ParseMode.HTML,
    )
```

### TODO 3.4 — Integrar chart rendering no fluxo Telegram
- **Arquivo**: `backend/app/main.py` (função `_handle_channel_message`, após linha 244 onde `content` é extraído)
- Ler antes: linhas 216-287 do main.py
- Após obter `content` do orchestrator:
  1. Chamar `extract_chart_blocks(content)` para encontrar blocos chart
  2. Para cada bloco encontrado: `render_chart_png(chart_json)` → bytes
  3. Substituir o bloco chart no texto por "[ver gráfico acima]" ou similar
  4. Retornar resposta modificada + lista de imagens PNG
- Modificar o retorno de `_handle_channel_message` para suportar imagens (ou criar ChannelReply dataclass)
- No handler do Telegram (`_on_text` em telegram.py, ~linha 283): enviar fotos primeiro, depois texto

### TODO 3.5 — Testes do chart_renderer
- **Novo arquivo**: `backend/tests/unit/test_chart_renderer.py`
- Casos: cada tipo de chart gera bytes PNG válidos; JSON inválido retorna None; extract_chart_blocks encontra blocos corretamente
- Rodar: `cd backend && .venv/bin/python -m pytest tests/unit/test_chart_renderer.py -v`

### Gate Fase 3
```bash
make test-backend
make test-frontend
```
**Ambos devem passar antes de avançar.**

---

## Fase 4 — Backend de Custos de Treinamento

**Objetivo**: Infraestrutura para persistir custos de LLM nos scripts de treinamento/pipeline.

### TODO 4.1 — Config do novo índice
- **Arquivo**: `backend/app/config.py`
- Ler antes: o arquivo completo para encontrar `opensearch_classification_usage_index`
- Adicionar: `opensearch_training_usage_index: str = "atlasfile_training_usage"`

### TODO 4.2 — Criar índice no OpenSearch
- **Arquivo**: `backend/app/opensearch_client.py` (após `ensure_classification_usage_index`)
- Ler antes: linhas 134-157 (padrão existente)
- Nova função `ensure_training_usage_index(client)` — mesmo padrão
- Schema: `script_name` (keyword), `run_id` (keyword), `provider` (keyword), `model` (keyword), `timestamp` (date), `input_tokens` (integer), `output_tokens` (integer), `cache_read_input_tokens` (integer), `cache_creation_input_tokens` (integer), `estimated_cost_usd` (float), `records_processed` (integer), `error_count` (integer)

### TODO 4.3 — Chamar ensure no startup
- **Arquivo**: `backend/app/main.py` (bloco de startup)
- Ler antes: encontrar onde `ensure_classification_usage_index` é chamado
- Adicionar `ensure_training_usage_index(os_client)` logo após

### TODO 4.4 — Helper de persistência
- **Novo arquivo**: `backend/app/training_usage.py`
- Ler antes: `backend/app/ingestion.py` linhas 34-62 (`_persist_classification_usage` — padrão a seguir)
- Ler antes: `backend/app/usage_costs.py` (função `estimate_usage_cost`)
- Funções:
  - `generate_run_id() -> str` — retorna `str(uuid4())`
  - `persist_training_usage(script_name, run_id, provider, model, usage, records_processed=0, error_count=0) -> None`
    - Importa `get_client` do opensearch_client
    - Chama `estimate_usage_cost(usage, provider, model)` para calcular custo
    - Indexa documento no `settings.opensearch_training_usage_index`
    - `timestamp` = `int(time.time() * 1000)`
    - Wrapped em try/except com logging — nunca crasha o script chamador

### TODO 4.5 — Teste unitário do helper
- **Novo arquivo**: `backend/tests/unit/test_training_usage.py`
- Mock do OpenSearch client
- Casos: persist grava documento correto; estimate_usage_cost é chamado; exceção não propaga
- Rodar: `cd backend && .venv/bin/python -m pytest tests/unit/test_training_usage.py -v`

### Gate Fase 4
```bash
make test-backend
```
**Deve passar antes de avançar.**

---

## Fase 5 — Instrumentar Scripts de Treinamento

**Objetivo**: Conectar scripts existentes ao helper de persistência.

### TODO 5.1 — Instrumentar `label_corpus_llm.py`
- **Arquivo**: `backend/scripts/label_corpus_llm.py`
- Ler antes: o arquivo completo (~300 linhas)
- Mudanças:
  - Import: `from app.training_usage import persist_training_usage, generate_run_id`
  - Gerar `run_id = generate_run_id()` antes do loop (após linha 175)
  - Após extração de usage (linha 237-239): chamar `persist_training_usage(script_name="label_corpus_llm", run_id=run_id, provider="openai", model=args.model, usage=usage, records_processed=1)`
  - Remover cálculo hardcoded (linhas 277-278: `cost_in = total_input * 0.15 / ...`), substituir por `estimate_usage_cost` ou pelo total acumulado dos registros persistidos

### TODO 5.2 — Instrumentar `classifier_augmentation.py`
- **Arquivo**: `backend/app/classifier_augmentation.py`
- Ler antes: linhas 284-337 (`generate_synthetic_text`) e 382-453 (`generate_synthetic_records`)
- Mudança em `generate_synthetic_text`:
  - Capturar `response.usage` (OpenAI) ou `response.usage` (Anthropic) — atualmente descartados
  - Retornar `tuple[str, dict]` ao invés de `str` — (text, usage_dict)
  - Ou adicionar campo `usage` ao retorno para não quebrar a assinatura: retornar dataclass `SyntheticResult(text: str, usage: dict)`
- Mudança em `generate_synthetic_records`:
  - Acumular usage retornado de cada `generate_synthetic_text`
  - Adicionar `on_usage` callback ou retornar usage total no resultado
- **Arquivo**: `backend/scripts/run_augmentation.py`
  - Ler antes: o arquivo completo (~161 linhas)
  - Após `asyncio.run(generate_synthetic_records(...))`: persistir resumo com `persist_training_usage(script_name="run_augmentation", ...)`

### TODO 5.3 — Testes dos scripts instrumentados
- Rodar testes existentes: `make test-backend` — garantir zero regressões
- Os scripts alterados não têm testes unitários dedicados, mas os módulos que importam sim

### Gate Fase 5
```bash
make test-backend
```
**Deve passar antes de avançar.**

---

## Fase 6 — API + Frontend de Custos de Treinamento

**Objetivo**: Expor dados de custo de treinamento via API e exibir no frontend.

### TODO 6.1 — Modelos Pydantic
- **Arquivo**: `backend/app/models.py`
- Ler antes: encontrar `ClassificationUsageByModel` e `ClassificationUsageSummary` (padrão a seguir)
- Adicionar:
  - `TrainingUsageByModel(model, call_count, input_tokens, output_tokens, estimated_cost_usd)`
  - `TrainingUsageByScript(script_name, call_count, input_tokens, output_tokens, estimated_cost_usd)`
  - `TrainingUsageSummary(total_calls, total_input_tokens, total_output_tokens, estimated_cost_usd, by_model: list[TrainingUsageByModel], by_script: list[TrainingUsageByScript])`

### TODO 6.2 — Endpoint API
- **Arquivo**: `backend/app/main.py`
- Ler antes: endpoint `/api/usage/classification` (linhas ~2309-2367) — padrão a seguir
- Novo endpoint: `GET /api/usage/training?start_date&end_date&project_id`
- OpenSearch aggregation por `model` (terms) e por `script_name` (terms)
- Somar `input_tokens`, `output_tokens`, `estimated_cost_usd`
- Retorna `TrainingUsageSummary`

### TODO 6.3 — Tipos TypeScript
- **Arquivo**: `frontend/src/types.ts`
- Ler antes: encontrar `ClassificationUsageSummary` (padrão a seguir)
- Adicionar interfaces: `TrainingUsageByModel`, `TrainingUsageByScript`, `TrainingUsageSummary`

### TODO 6.4 — Função API frontend
- **Arquivo**: `frontend/src/api.ts`
- Ler antes: encontrar `fetchClassificationUsage` (padrão a seguir)
- Adicionar `fetchTrainingUsage(params)` — mesmo padrão

### TODO 6.5 — UsageView: seção de treinamento
- **Arquivo**: `frontend/src/features/usage/UsageView.tsx`
- Ler antes: o arquivo completo (~413 linhas)
- Mudanças:
  - Adicionar `fetchTrainingUsage` ao `Promise.all` existente no `useEffect`
  - Novo state: `trainingUsage`
  - Card de resumo "Treinamento" ao lado de "Classificações" (mesmo padrão visual)
  - Somar custo de treinamento no total geral (padrão aditivo: `summary.estimated_cost_usd + classifUsage + trainingUsage`)
  - Nova tabela "Treinamento / Pipeline" com colunas: Script, Modelo, Chamadas, Input, Output, Custo

### TODO 6.6 — Testes frontend
- Rodar: `cd frontend && npx vitest run`
- Garantir zero regressões

### Gate Fase 6
```bash
make test-backend
make test-frontend
cd frontend && npm run build
```
**Todos devem passar.**

---

## Resumo de fases e dependências

| Fase | Escopo | Depende de | Gate |
|------|--------|------------|------|
| 1 | Recharts + ChartBlock | — | vitest ChartBlock + build |
| 2 | ChatPanel integration + system prompt | Fase 1 | vitest all + build |
| 3 | Renderer matplotlib + Telegram send_photo | Fase 2 | make test (backend + frontend) |
| 4 | Infra custos (config, índice, helper) | — | make test-backend |
| 5 | Instrumentar scripts (label, augmentation) | Fase 4 | make test-backend |
| 6 | API + frontend custos | Fase 5 | make test (all) + build |

**Nota**: Fases 1-3 (charts) e Fases 4-6 (custos) são independentes entre si. Podem ser executadas em paralelo se desejado.

---

## Arquivos impactados

| Arquivo | Ação | Fase |
|---------|------|------|
| `frontend/package.json` | Adicionar recharts | 1 |
| `frontend/src/components/ChartBlock.tsx` | **Novo** | 1 |
| `frontend/src/components/ChartBlock.css` | **Novo** | 1 |
| `frontend/src/components/ChartBlock.test.tsx` | **Novo** | 1 |
| `frontend/src/components/ChatPanel.tsx` | Custom code renderer | 2 |
| `backend/app/prompts/system_prompt_chat.md` | Seção de visualizações | 2 |
| `backend/requirements.txt` | matplotlib | 3 |
| `backend/app/chart_renderer.py` | **Novo** — renderer server-side | 3 |
| `backend/app/channels/telegram.py` | send_photo + integração | 3 |
| `backend/app/main.py` | Chart no fluxo Telegram + startup index + endpoint API | 3, 4, 6 |
| `backend/tests/unit/test_chart_renderer.py` | **Novo** | 3 |
| `backend/app/config.py` | Config índice training_usage | 4 |
| `backend/app/opensearch_client.py` | ensure_training_usage_index | 4 |
| `backend/app/training_usage.py` | **Novo** — helper persistência | 4 |
| `backend/tests/unit/test_training_usage.py` | **Novo** | 4 |
| `backend/scripts/label_corpus_llm.py` | Instrumentar com persistência | 5 |
| `backend/app/classifier_augmentation.py` | Retornar usage de LLM | 5 |
| `backend/scripts/run_augmentation.py` | Persistir custos | 5 |
| `backend/app/models.py` | Modelos Pydantic training | 6 |
| `frontend/src/types.ts` | Tipos TypeScript training | 6 |
| `frontend/src/api.ts` | fetchTrainingUsage | 6 |
| `frontend/src/features/usage/UsageView.tsx` | Seção de treinamento | 6 |

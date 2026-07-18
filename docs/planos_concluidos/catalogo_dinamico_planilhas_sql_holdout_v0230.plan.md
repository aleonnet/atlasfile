# Catálogo dinâmico de modelos + análise de planilhas no chat + ciclo do classificador destravado (v0.23.0)

> Concluído em 2026-07-18. Três gaps do teste from-scratch do usuário, num plano único aprovado.

## Problemas

1. **Catálogo de modelos hardcoded** (`llm_catalog.py`, 6 modelos) — modelos novos exigiam deploy; custo de modelo desconhecido virava $0 silencioso.
2. **Agente não agrega planilhas** — XLSX vira texto linear truncado; caso real: CMDB de 776 linhas, o agente (corretamente) recusou contar e mandou o usuário para o Excel.
3. **"Validation set has no labeled entries"** — nenhum fluxo operacional alimentava o validation set; ciclo era beco sem saída em instalação nova.

## Decisões de design

- **Fonte do catálogo: LiteLLM JSON** (decisão do usuário via AskUserQuestion) — as páginas oficiais são client-rendered (scraping frágil) e as APIs `/v1/models` só devolvem nomes; o JSON comunitário agrega custos+limites+modo estruturadamente. Fallback builtin + cache em `{PROJECTS_ROOT}/_ATLASFILE/llm/` (runtime-writable; `config/` é baked na imagem). Filtro: `mode == chat` **e** `supports_function_calling` (requisito do chat) — exclui whisper/embeddings/tts/imagem por construção; snapshots datados e variantes audio/realtime excluídos por nome.
- **Modelo custom**: validação de existência na API do provedor (`models.retrieve`), key só no header; valor ativo do combobox só muda por seleção do catálogo ou custom **validado** (digitação parcial fica em draft — lição do bug ListInput repetida aqui e pega no E2E: um `gpt-99-teste` digitado no teste virou modelo ativo e quebrou o chat).
- **Planilhas: SQL SELECT-only sobre DuckDB** (padrão da indústria; evita "LLM escreve pandas"/injeção de código). MCP fino → REST (padrão existente); doc_id→path físico com confinamento ao projects root (padrão do endpoint download). Colunas xlsx como VARCHAR (CAST documentado no prompt). `remark-gfm` era necessário — o CSS de tabela do ChatPanel existia mas nunca ativou.
- **Hold-out operacional**: só decisões HUMANAS entram nos datasets; auto-roteados ficam fora (self-training congela erros; validar contra a própria saída infla métrica). Determinismo por SHA (mesmo arquivo → mesmo lado); regra semente mata o beco no primeiro doc elegível; warm-up (3 por classe) preserva elegibilidade do sparse; backfill estratificado nunca deixa classe < 2 no treino e é idempotente (quota sobre o total da classe, não sobre o restante). Anti-leakage bidirecional (índices SHA; `validation_sha_index` agora cobre entries sem rótulo). Rollback: `classifier_holdout_modulus=0` desliga tudo (inclusive semente).

## Refinos pós-plano (pedidos do usuário antes do commit)

- **`install.sh --enable-auth`**: a autenticação é decisão de deployment → o instalador é o dono dela. Re-run idempotente gera/preserva a key (formato `{"keys":[{key,name,projects:["*"]}]}` de auth.py), seta `API_AUTH_ENABLED` + `ATLASFILE_API_TOKEN` (o MCP server precisa da key para chamar a API — plumbing já existia no compose) e rebuilda. E2E: 401/200/401.
- **Separação operação × configuração**: Processar INBOX + fila da INBOX saíram da aba Classificador para o Painel (`InboxQueueChips` reutilizável; testes de scan portados para `InboxScanCard.test.tsx`); Rodar ciclo fica — atualiza o estado do classificador (champion/registry), é configuração evoluindo. Empty state no padrão do Perfil quando "Todos os projetos"; aba Acesso ganhou o passo a passo de habilitação da autenticação (decisão de deployment, sem toggle na UI por segurança).

- **Aba "Catálogo de modelos"** no modal do assistente: URL da fonte editável (validação dry-run no backend antes de salvar; https obrigatório; persistida em `_ATLASFILE/llm/catalog_source.json`), refresh manual, tabela de modelos com preços/capacidades/origem (`GET /api/models/detail`).
- **Modelo de triagem por projeto**: o campo do modal só gravava no localStorage e a política real (perfil do projeto) só sincronizava com o card do Classificador montado — agora o campo aparece só com projeto selecionado e persiste direto no perfil (`llm_policy.provider/model`), com feedback "salvo no projeto X".

## Gotchas encontrados na execução

- `get_cost_per_1m` retornava `(0,0,0,0)` para modelo desconhecido (default `{}` no `.get`) contradizendo o docstring — corrigido para `None`; teste antigo codificava o bug.
- `model_copy(update=...)` do pydantic **não valida** — entries de validação construídas via constructor.
- Backfill "idempotente" com quota sobre o pool restante drenaria ~20% a cada chamada — quota calculada sobre treino+validação da classe.
- LiteLLM corrigiu limites do builtin (gpt-5.1: 272k input, não 400k; sonnet-4-6/opus: 1M).

## Arquivos principais

Novos: `backend/app/llm_catalog_refresh.py`, `backend/app/spreadsheet_query.py`, `backend/app/dataset_holdout.py` (+3 arquivos de teste).
Modificados: `llm_catalog.py` (camada de cache, helpers intactos), `usage_costs.py` (merge override), `main.py` (7 endpoints novos, `_relocate_document` → roteador), `classifier_cycle.py` (mensagem pt-BR), `config.py`, `evaluation_dataset.py` (`include_unlabeled`), `mcp/server.py` (2 tools), `prompts/system_prompt_chat.md`, `requirements.txt` (+duckdb); frontend: `AssistantSettingsModal` (combobox+validar+refresh), `SettingsContext` (custom models; fix do reset de seleção), `UsageView` (badge), `ChatPanel` (+remark-gfm), `IngestTriageCard` (readiness+backfill), `api.ts`/`types.ts`.

## Validação (2026-07-18, instância real)

- 445 unit + 81 integration backend; 134 vitest frontend.
- **CMDB real** (arquivo do teste do usuário): engine devolveu a tabela exata — OI SA 508 Não Crítico / 113 Crítico / 89 Muito Crítico; OI SA COMPARTILHADO 21/16/13; VTAL COMPARTILHADO 8/3/5 (776 linhas, 0 truncagem).
- **Loop completo no chat da UI**: agente encadeou `list_documents → spreadsheet_schema → spreadsheet_query`, tabela `<table>` renderizada com citação (screenshot).
- **Refresh real**: 46 modelos (36 OpenAI, 10 Anthropic), todos com preço, claude-opus-4-8 presente, zero whisper/embeddings; validate 200 `valid:true` para gpt-4o-mini e `valid:false` para modelo inventado (API real).
- **Readiness na instância real**: `cycle_ready:true` (62 validação rotulada via splits); cenário instalação-nova coberto por unit tests (semente/warm-up/backfill/422).

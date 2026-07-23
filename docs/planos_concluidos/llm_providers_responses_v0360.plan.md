# llm_providers_responses_v0360 — Responses API + providers OpenAI-compatíveis + validação de chaves no modal

> **CONCLUÍDO em 2026-07-22.** Execução fiel ao plano com os desvios registrados abaixo.

## Desvios do plano (registrados na execução)

1. **`config/usage_costs.json` NÃO foi semeado com preços de gpt-5.2/kimi** — inventar valores violaria a regra "no arbitrary defaults"; o refresh LiteLLM preenche o override com preços reais (validado no E2E: 67 modelos, 67 com preço) e `cost_tracked=False` sinaliza no intervalo.
2. **Fix extra descoberto no E2E**: LiteLLM prefixa o provider no nome de modelos não-OpenAI (`moonshot/kimi-k2-...`), gerando ids duplicados (`moonshot/moonshot/...`); o prefixo agora é removido em `_to_model_option` (com teste no fixture).
3. **Fix extra de infra de teste**: Node ≥26 expõe um `localStorage` experimental que sombreia o do jsdom e quebrava 9 testes de frontend de forma intermitente (pré-existente, reproduzido com o tree limpo); `npm run test` agora roda com `NODE_OPTIONS=--no-experimental-webstorage`.
4. **E2E Moonshot**: chave validada AO VIVO na API real (badge ✓ no modal) e chamada de chat autenticada e roteada com `base_url` correto; a resposta final foi bloqueada por **saldo da conta** (`exceeded_current_quota_error` exibido no chat) — integração tecnicamente validada; `kimi-k3` mantido no builtin (o LiteLLM ainda lista a família k2; o catálogo real do usuário resolve no refresh).
5. **E2E executado em stack paralelo** (uvicorn + vite com config e2e isolada + OpenSearch descartável) porque o stack Docker do usuário roda imagem antiga de outro checkout (`/Users/alessandro/AtlasFileBranch`).

## Resultados do E2E (stack real)

- **gpt-5.6 + tools + thinking**: respondeu via Responses API com 5 tool calls encadeados (search_documents ×4 + semantic_search_chunks) — o bug 400 está corrigido.
- **Regressão gpt-5.1**: chat.completions intocado (get_stats respondeu normal).
- **Ollama `gemma4:12b` local**: validado na combobox (badge "disponível na Ollama"), apareceu no select do chat via customModels e respondeu à conversa.
- **Badges do modal**: ✓ válida (Moonshot real), ✗ inválida (chave errada de propósito) — ambos ao vivo.
- **`make test`**: 602 backend + 223 frontend, tudo verde.

## Contexto

Três entregas num branch único (`feature/llm-providers-responses-v0360`, base `main`, versão 0.35.0 → **0.36.0**):

1. **Bug ativo (A1)**: modelos OpenAI pós-gpt-5.2 (ex.: gpt-5.6) retornam 400 no chat — `"Function tools with reasoning_effort are not supported ... use /v1/responses or set reasoning_effort to 'none'"`. Causa verificada: `orchestrator.py:250-260` envia `reasoning_effort="medium"` + `tools` no `chat.completions.create`; não há uso da Responses API no repo. O SDK instalado (**openai==2.24.0**) já suporta `client.responses.create` — sem bump de dependência.
2. **Providers novos (A2)**: Moonshot (Kimi) e Ollama local via caminho OpenAI-compatible (`base_url`), inexistente hoje (grep zero; providers são enum fechado openai/anthropic em ~7 pontos por camada).
3. **Validação de chaves no Assistant Settings (A3)**: endpoint `/api/keys/validate` existe e só o OnboardingWizard usa (padrão-ouro: debounce 700ms, 5 estados incl. `unreachable`, stale-guard). O modal não valida nada.

Usuário tem **chave Moonshot E Ollama local** → E2E completo dos dois providers.

**Não-objetivos** (documentar no plano concluído): `embeddings.py`, `classifier_cycle.py`, `classifier_augmentation.py`, scripts offline, streaming, Responses para Anthropic, generalização do OnboardingWizard (fica openai/anthropic — moonshot/ollama são caso avançado do modal).

---

## BACKEND

### B1. Registro central de providers — novo `backend/app/llm_providers.py`

`ProviderSpec` frozen dataclass: `name, label, sdk_flavor("openai"|"anthropic"), key_header, key_env, requires_key, base_url_setting, placeholder_key`.

```
openai    → sdk openai,    X-OpenAI-API-Key,    OPENAI_API_KEY,    sem base_url
anthropic → sdk anthropic, X-Anthropic-API-Key, ANTHROPIC_API_KEY, sem base_url
moonshot  → sdk openai,    X-Moonshot-API-Key,  MOONSHOT_API_KEY,  base_url_setting="moonshot_base_url"
ollama    → sdk openai,    (requires_key=False, placeholder_key="ollama"), base_url_setting="ollama_base_url"
```

Funções: `get_provider`, `resolve_base_url` (getattr em settings em call-time, p/ monkeypatch), `resolve_api_key(spec, transient)` (transient > env > placeholder > None; para openai/anthropic retorna `transient or None` — preserva fallback de env do SDK byte-a-byte), `make_async_client`, `make_sync_client`. **Imports do SDK DENTRO das factories** — preserva os padrões de teste A (`sys.modules`) e B (`patch("openai.AsyncOpenAI")`). Para openai/anthropic **não passar** `base_url` (kwargs idênticos aos atuais).

`config.py` (~L106): `moonshot_base_url: str = "https://api.moonshot.ai/v1"`, `ollama_base_url: str = "http://localhost:11434/v1"`. Chaves seguem transientes/env — nunca em settings.

### B2. Catálogo — campo `openai_api`

- `models.py:199` `ModelOption`: `openai_api: Literal["chat_completions","responses"] = "chat_completions"` (default cobre cache antigo e desconhecidos — fail-safe no caminho atual).
- `llm_catalog.py`: gpt-5.1 **permanece** chat_completions (funciona hoje; relato empírico: quebra é pós-5.2 exclusive). Builtin novo: `gpt-5.2` (responses, reasoning, 400k/128k) e `moonshot/kimi-k3` (label "Moonshot Kimi K3", contexto conservador 256k/32k — refresh LiteLLM corrige; confirmar id exato do modelo via `GET {moonshot_base_url}/models` com a chave do usuário na fase E2E). Ollama SEM builtin: modelos locais entram pela combobox custom + `/api/models/validate` estendido. Helper `get_openai_api(provider, model) -> str`.
- `llm_catalog_refresh.py`: `_SUPPORTED_PROVIDERS += "moonshot"`; inferência `_infer_openai_api` (só litellm_provider==openai): `supported_endpoints` sem `/v1/chat/completions` → responses; `supports_reasoning` + versão gpt ≥ (5,2) → responses; senão chat_completions.
- `config/usage_costs.json`: bloco `moonshot` (kimi-k2). Ollama fora → custo 0 + `cost_tracked=False` (comportamento existente).

### B3. Orchestrator — branch Responses API

`orchestrator.py`:
- `mcp_tools_to_openai_responses(tools)`: tools **FLAT** `{"type":"function","name","description","parameters","strict":False}` (sem wrapper `function` — diferença crítica vs chat.completions).
- `_messages_to_responses_input(messages)`: system → `instructions=`; `{role,content}` direto; content-lista (visão) → `input_text`/`input_image`.
- `_run_chat_openai_responses(...)`: loop `MAX_TOOL_LOOPS` com `client.responses.create(model, input, tools, instructions, [reasoning={"effort":"medium"} se supports_reasoning_effort])`; sem function_call em `resp.output` → retorna `resp.output_text`; senão **append de `resp.output` INTEIRO ao input** (itens reasoning obrigatórios de volta, senão 400 na 2ª volta) + `{"type":"function_call_output","call_id","output"}` por tool executada (mesmo fluxo `_apply_project_scope_to_tool_args`/`mcp_call_tool`/`_truncate_tool_result`). Usage: `resp.usage.input_tokens/output_tokens`, `input_tokens_details.cached_tokens` → `_accumulate_usage`. Contrato de retorno idêntico (`content/tool_calls_used/usage`; `context_pressure` segue vindo de `run_chat_loop:230`).
- Dispatch em `run_chat_loop:203-228` via registro: `sdk_flavor=="openai"` → se `provider=="openai" and get_openai_api(...)=="responses"` → branch novo; senão `_run_chat_openai` (moonshot/ollama caem aqui). `_run_chat_openai:246` e `_classify_openai:551`: `AsyncOpenAI(...)` → `make_async_client(provider, api_key)` (corpo intocado). `classify_with_llm`: mesmo dispatch + `_classify_openai_responses` com `tool_choice={"type":"function","name":"submit_classification"}` flat (o mesmo 400 atinge classificação LLM).

### B4. main.py — headers, validates, erro dedicado

- Header `X-Moonshot-API-Key` em `/api/chat:2374`, `/api/classify:~2885`, `/api/keys/validate:2291`, `/api/models/validate:2331`. Ternário `:2388` → dict `{provider: header}.get(provider)`; resolução env/placeholder fica no registro.
- `keys/validate` + `models/validate` generalizados via registro (import inline mantido — Padrão A), códigos por template `{PROVIDER}_KEY_HEADER_REQUIRED` / `{PROVIDER}_KEY_INVALID` / `{PROVIDER}_REQUEST_FAILED` — byte-idênticos aos atuais para openai/anthropic. Ollama valida sem chave (`models.list()`/`retrieve()` no base_url local — `/v1/models` existe em moonshot e ollama).
- Erro dedicado em `api_chat:2406` ANTES do check de auth: mensagem com `reasoning_effort` + (`/v1/responses`|`function tools`) → `http_error(503, "LLM_MODEL_NEEDS_RESPONSES_API", ...)` orientando `POST /api/models/refresh`. Fallbacks atuais intactos.

---

## FRONTEND

### F1. Registro — novo `frontend/src/lib/providers.ts`
`PROVIDERS = ["openai","anthropic","moonshot","ollama"] as const`; `PROVIDER_KEY_HEADER` (ollama → null); `isProviderId`, `providerNeedsKey`.

### F2. Tipos/storage
`types.ts:614` `LLMPolicy.provider` → `ProviderId`; `types.ts` `ModelOption` += `openai_api?: string` (passthrough). `lib/storage.ts` += `moonshotApiKey: "atlasfile-moonshot-api-key"`.

### F3. api.ts
`validateProviderKey(provider: ProviderId, key)` com header via mapa (ollama: só body); `validateModel` keys += `moonshot?`; `sendChatMessage` option `moonshotApiKey?` → header condicional (padrão :599-600).

### F4. SettingsContext
Estado `moonshotApiKey` (init/persist/expose espelhando openai :81/:101/:140+). Fallback de seleção :107-118 sem mudança.

### F5+F6. AssistantSettingsModal + App.tsx (mesmo commit — TS strict quebra em passo intermediário)
- Props novas `moonshotApiKey`/`onChangeMoonshotKey`; App.tsx:585-599 passa do context.
- Derivação generalizada (substitui needOpenAI/needAnthropic :537-540): `usedProviders` dos modelos chat/triage → campos de chave para os que `providerNeedsKey`; `usesOllama` → só hint `settings:assistant.ollamaNoKey`.
- **Novo `ApiKeyField` interno**: password input + debounce 700ms/stale-guard (padrão OnboardingWizard:86-106) chamando `validateProviderKey`; estados `idle|checking|valid|invalid|unreachable` com badge inline (unreachable ≠ invalid); reset a idle quando vazio; nunca bloqueia (modal persiste on-change).
- `normalizeModelValue` :70-74 intacta; hint novo `combobox.prefixHint` (prefixo explícito `moonshot/…`, `ollama/…`) junto de `outsideCatalog`; `ModelCombobox` apiKeys += moonshot.
- `persistTriageModelToProject:522`: `isProviderId(provider) ? provider : "openai"`.

### F7. useChatSession
`moonshotApiKey` do context; nas 2 chamadas `sendChatMessage`: enviar só quando `provider === "moonshot"`.

### F8. customModels no seletor do chat
`ChatPanel.tsx:320-336`: prop `customModels?: string[]`; options = catálogo + customs dedupe (`key` vira `provider/model` — labels podem colidir); label reutiliza `settings:combobox.validatedByYou`; `disabled` considera customs. `AssistenteView`: lê `customModels` de `useSettings()` e passa; guard :75 idem. (Sem isso, modelo Ollama validado não é utilizável no chat.)

### F9. i18n — chaves novas nos DOIS locales (parity.test.ts valida)
`settings.json`: `assistant.moonshotKey`, `assistant.keyChecking`, `assistant.keyValid`, `assistant.keyInvalid`, `assistant.keyUnreachable`, `assistant.ollamaNoKey`, `combobox.prefixHint`. `errors.json`: `LLM_MODEL_NEEDS_RESPONSES_API`, `MOONSHOT_KEY_INVALID`, `MOONSHOT_KEY_HEADER_REQUIRED`, `MOONSHOT_REQUEST_FAILED`, `OLLAMA_REQUEST_FAILED`.

---

## TESTES (régua: sem regressões; padrões existentes A/B/C)

Backend:
| Teste | Arquivo | Padrão |
|---|---|---|
| Loop Responses: output=[reasoning, function_call c1] → 2ª chamada contém function_call_output c1 E o item reasoning; tools flat (sem wrapper `function`); reasoning={"effort":"medium"}; usage acumulado (cached→cache_read); contrato de retorno | novo `tests/unit/test_orchestrator_responses.py` | B (`patch("openai.AsyncOpenAI")`+AsyncMock) |
| Regressão: gpt-4o-mini/4.1/5.1 → `chat.completions.create` chamado, `responses.create` NUNCA, sem base_url | idem | B |
| Factory: moonshot → `assert_called_with(api_key, base_url=moonshot)`; ollama → placeholder key + base_url local; monkeypatch settings respeitado; resolve_api_key com env | novo `tests/unit/test_llm_providers.py` | B |
| keys/validate + models/validate moonshot/ollama (header, valid t/f, NotFound); códigos openai/anthropic byte-iguais | estender `test_keys_validate.py` + novo `test_models_validate.py` (lacuna pré-existente) | A (sys.modules fake SDK) |
| Refresh: gpt-5.6 reasoning→responses; supported_endpoints; cache antigo sem campo→default; entrada moonshot aceita + custo | `test_llm_catalog_refresh.py` (fixture LITELLM) | fixture |
| /api/chat: mensagem do 400 → code `LLM_MODEL_NEEDS_RESPONSES_API`; auth → código atual; moonshot header → api_key correto em run_chat_loop | `test_api_chat_models.py` | C (patch run_chat_loop) |

Frontend:
| Teste | Arquivo |
|---|---|
| **CRÍTICO**: adicionar `validateProviderKey` ao `vi.mock("../../api")` existente (sem isso os 3 testes atuais quebram — ApiKeyField valida no mount) + `beforeEach(vi.clearAllMocks)` | `AssistantSettingsModal.test.tsx` |
| Debounce+badge válido (waitFor `toHaveBeenCalledWith("openai", ...)` + golden PT `/✓ Chave válida/`); inválido; unreachable ≠ invalid; campo Moonshot com modelo moonshot; ollama sem campo + hint | idem (padrão OnboardingWizard.test.tsx:201-241) |
| customModels no select (+dedupe, keys por provider/model) | novo `ChatPanel.test.tsx` |
| Headers moonshot em sendChatMessage/validateProviderKey/validateModel; ollama sem header | `api.test.ts` (spyOn fetch) |
| Paridade i18n | `parity.test.ts` (passa por construção) |

## Verificação E2E (stack real — usuário tem chave Moonshot + Ollama)

1. **Repro do bug ANTES do fix**: chat com gpt-5.6 (refresh do catálogo) → 400 atual documentado. Depois do fix: mesma pergunta com tools (busca com citação) responde; thinking ligado.
2. Regressão: chat gpt-5.1 e claude com tools funcionam como hoje.
3. Moonshot: **chave fornecida pelo usuário nesta sessão** (usar direto no modal/browser de teste — NUNCA ecoar em logs, commits ou arquivos) → badge valida ao vivo; chat com **`moonshot/kimi-k3`** (confirmar id exato via listagem de modelos) com tool call de busca.
4. Ollama: **`ollama/gemma4:12b`** (já baixado localmente pelo usuário) via combobox custom (validate → customModels) → aparece no select do chat → conversa (tool call se o modelo suportar; senão resposta direta é aceitável — registrar comportamento). Atenção Docker: API containerizada alcança o Ollama do host via `host.docker.internal:11434`.
5. Modal: chave errada → badge ✗; backend derrubado → unreachable; nada bloqueia.
6. `make test` completo verde (backend + frontend).

## Checklist de conclusão (CLAUDE.md)
1. Plano em `docs/planos_concluidos/llm_providers_responses_v0360.plan.md` + atualizar README de lá
2. Bump 0.35.0 → **0.36.0** em `frontend/package.json` + lock
3. `CHANGELOG.md`
4. `README.md`/`README.pt-BR.md`/`INSTALL.md`: seção de providers (Moonshot/Ollama, envs `MOONSHOT_API_KEY`, base_urls); `docker-compose.yml`: propagar `MOONSHOT_API_KEY`, `MOONSHOT_BASE_URL`, `OLLAMA_BASE_URL` no serviço api (ollama local: host.docker.internal como base default documentada para Docker)
5. Staging + proposta de commit (sem commitar sem autorização)

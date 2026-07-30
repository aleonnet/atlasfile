# Fase 2 — Um app, um container (v0.57.0)

> **Status: EXECUTADO em 2026-07-30**, na branch `fase2-um-container` (base:
> `main` @ `5267251`, v0.56.6). Fase 2 de
> `docs/roadmap/distribuicao_build_imagens_ghcr.md`. Todo item abaixo é fato
> verificado no código ou medição na stack real, salvo onde marcado.

## O que mudou

Consolidação de `api` (:8000) + `mcp` (:8001) + `web` (vite dev :5173) num
único uvicorn no `:8000`: API em `/api/*` + `/health`, FastMCP em `/mcp`,
bundle vite de produção em `/` (StaticFiles). **Breaking por desenho**: MCP
`:8001/mcp` → `:8000/mcp` (e com auth ligado o `/mcp` passa a exigir a MESMA
API key); UI `:5173` → `:8000`. Dashboards virou opt-in
(`profiles: [dashboards]` + `DASHBOARDS_ENABLED=true`). `config/api_keys.json`
saiu da camada de imagem e virou bind mount.

## As armadilhas — 4 previstas no roadmap, 3 achadas na execução

| # | Armadilha | Tratamento |
|---|---|---|
| A | `streamable_http_path` default do SDK é `/mcp` → `app.mount("/mcp", ...)` viraria `/mcp/mcp`; Mount+Route("/") responde 307 por request | `Route("/mcp")` com wrapper ASGI que delega a `session_manager.handle_request` resolvido POR REQUEST (property) — zero redirect, validado empiricamente antes de codificar |
| B | Lifespan de sub-app não roda via mount; `session_manager.run()` é single-use por instância | Lifespan envolve yield+shutdown com `async with run():` e RECRIA o manager a cada ciclo (`_session_manager = None`) — atributo privado aceito com SDK pinado + teste E2E duplo que detecta quebra |
| C | Auth em 2 lados: Route/Mount não herdam `dependencies=[Depends(require_auth)]`; e `streamable_http_client` não aceita `headers=` | `MCPAuthMiddleware` (auth.py) reusando `resolve_api_key`/`_extract_key`; client interno passa `httpx.AsyncClient` autenticado via `http_client=` — com `aclose()` no finally (o SDK NÃO fecha client fornecido) e defaults replicados |
| D | **NOVA (planejamento)**: `FastMCP.__init__` auto-liga proteção DNS-rebinding quando `transport_security is None` e host ∈ localhost → 421 fora de localhost (hoje OFF por acaso via `host="0.0.0.0"`) | `TransportSecuritySettings(enable_dns_rebinding_protection=False)` explícito + guarda em test_mcp.py. O mutante matou em dobro: a guarda E o handshake E2E (421 real) |
| E | Threadpool: tools + 81 handlers sync dividem o pool (40); tool call em voo segura 2 slots | Limiter → 100 no lifespan. Medido na stack real: 50 calls concorrentes em 1.2s, p95 ~1s, /health vivo |
| F | **NOVA (planejamento)**: `api.ts` tem 11 `new URL(\`${API_URL}/...\`)` — API_BASE vazio lançaria `TypeError: Invalid URL` | `API_BASE = VITE_API_URL \|\| window.location.origin` (nunca string vazia); zero testes quebraram |
| G | **NOVA (E2E, a mais grave)**: o SDK executa tool síncrona INLINE no event loop (`func_metadata.py:92-95`) — a premissa "tools rodam no threadpool" era FALSA no lado servidor. Consolidado = deadlock: a tool bloqueia o loop, o loopback dela nunca é atendido, o processo inteiro fica surdo (até o 401 do middleware) até o timeout de 60s do api_client. Invisível na topologia antiga (API em outro processo) | Wrapper `@tool()` em `app/mcp/server.py`: registra versão `async` que despacha ao `anyio.to_thread` preservando assinatura (functools.wraps → inspect.signature segue `__wrapped__`); devolve a função ORIGINAL para os testes das funções cruas. **Medido: 60.100ms → 59ms por call.** Guarda: toda tool registrada tem de ser coroutine |

## Arquivos (28 tocados + 3 removidos)

- Backend: `config.py` (static_dir, dashboards_enabled, atlasfile_api_token, mcp_server_url→:8000/mcp), `dashboards_setup.py` (curto-circuito), `main.py` (payload, lifespan, Route /mcp, _mount_static no FIM — Mount("/") casa tudo), `auth.py` (MCPAuthMiddleware), `mcp/server.py` (transport_security, wrapper @tool(), sem run_server), `mcp_client/client.py` (credencial + lifecycle), `Dockerfile` (multi-stage webbuild → /workspace/static). Removido: `app/mcp/__main__.py`.
- Frontend: `api.ts` (origin + SetupStatus.dashboards_enabled), `App.tsx`/`PainelView.tsx` (link condicional via prop), `App.test.tsx`, `i18n settings.json` ×2. Removidos: `frontend/Dockerfile`, `frontend/.dockerignore`.
- Infra: `docker-compose.yml` (serviço `atlasfile`, primeiros healthchecks do arquivo + `service_healthy`, bind mount de api_keys, profile dashboards), `Makefile` (`ensure-api-keys-file`, `--remove-orphans`, listas/echo), `scripts/smoke-project-init.sh` (container default), `ci.yml` (comentários do docker-build).
- Instaladores: `install.sh` (portas/painel/next-steps/open→:8000, materialização incondicional de api_keys, `--remove-orphans`, guarda de dono p/ nome novo E legado, `un_collect` casa `atlasfile` + api/web/mcp legados), `install.ps1` (open :8000), bancada +1 teste.
- Docs: INSTALL.md (7 seções), README ×2, CLAUDE.md (arquitetura), .env.example, agent-tools-flow.md, CHANGELOG.md, roadmap marcado.

## Testes — 749 pytest (+17) · 253 vitest (+1) · 220 bash (+2), todos verdes

**12 mutantes, cada um morto pela guarda desenhada antes de reverter:**
middleware "sempre passa" (3 testes acusaram) e "sempre 401" (4); rota /mcp
registrada nua (wiring); lifespan sem `session_manager.run()` (mensagem exata
"Task group is not initialized"); sem o reset single-use (2º ciclo explode);
sem `transport_security` (guarda + E2E com 421 real); client sem header
Bearer; client sempre criado; sem `aclose()` (is_closed acusou); gate do
dashboards removido; `_mount_static` "nunca monta" e "monta sempre" (este
derruba o próprio IMPORT do módulo — quebraria todo boot de dev);
`un_collect` sem o nome consolidado (bancada vermelha com a mensagem
desenhada); tool registrada sync direto no SDK (guarda da armadilha G).

## E2E na stack real (VM lima atlas-e2e, decisão desta sessão)

Base: instalação REAL da VM (auth ligado, `.env` de 81 linhas do instalador)
atualizada para v0.56.6, stack 0.56.6 buildada e semeada (projeto
`e2e_fase2`, PDF real de contrato → triagem pendente).

1. **Migração** — working tree da branch por cima (simulando `git pull`) +
   `docker compose up -d --build --remove-orphans`: **47.7s**, órfãos
   api/mcp/web removidos, OpenSearch esperado via healthcheck novo
   (`service_healthy`), `.env` antigo SEM EDIÇÃO, volume preservado (item de
   triagem sobreviveu com estado completo).
2. **UI de produção** no :8000 via Playwright: AuthGate → key → Painel com
   estado migrado (badge v0.57.0) → **Aprovar triagem** → roteado para
   `02_AREAS/ti/contrato/` com nome canônico → **busca com highlight**
   multi-página (evidências com `<em>`, facetas pdf/contrato/ti) →
   screenshot registrado.
3. **Auto-ingest consolidado**: 2º fixture na inbox → watcher ingeriu e
   indexou (2 indexados, 0 triagem).
4. **/mcp externo real** (SDK do Mac, porta encaminhada): sem key recusado;
   com key sessão completa (13 tools, tool call com resultado); carga leve
   10 concorrentes 0.2s. **Hop interno** (caminho exato do orchestrator, com
   `ATLASFILE_API_TOKEN`): list_tools 34ms, call_tool 59ms.
5. **Carga** (dentro do container, sem túnel): degraus 10/30/50 —
   0.2s/0.6s/1.2s de parede, p95 158/517/1019ms, `/health` 200 após cada um.
6. **Dashboards opt-in nos dois ramos**: desligado → link ausente na UI;
   ligado (env+profile) → link aparece e o SSO responde
   `302 → :5601/app/dashboards#/view/atlasfile-dashboard-operacao`.

**Como a armadilha G foi achada**: a primeira carga externa travou o app por
~8 min (33 sessões, 9 buscas completas, 46 ClientDisconnect) e o healthcheck
novo acusou `unhealthy`. Diagnóstico em matriz (curl 4.8ms vs SDK 60s; GET
direto 56ms vs tool 60s "timed out"; servidor surdo até para o 401 durante um
call_tool em voo) → fonte do SDK lido → correção → 59ms.

## Desvios do plano aprovado (flagados para revisão)

1. **`--remove-orphans`** em `make docker-up`/`docker-update` e no
   `install.sh`: risco de migração NÃO previsto — sem isso, o
   `atlasfile-api` órfão de 0.56.x segura a :8000 contra o serviço novo.
2. **Wrapper `@tool()` com to_thread** (armadilha G): o plano dizia "manter
   tools sync + loopback + limiter", assumindo dispatch em threadpool que o
   SDK não faz. A correção preserva a arquitetura aprovada (loopback,
   api_client sync, limiter) trocando só o registro.
3. ~~Chat com LLM real não exercitado~~ — **resolvido na mesma sessão**: com
   chave OpenAI fornecida pelo autor (via UI, enviada só por request — grep no
   filesystem do container e no .env da VM: zero ocorrências), o gpt-5.1
   respondeu usando `get_stats` + `list_documents` via /mcp, com citações e
   chips de fonte; logs confirmam POST /api/chat → POST /mcp loopback →
   CallTool. A chave foi limpa do browser ao final.

## Notas de migração (fatos medidos)

- `docker compose up` SEM `--remove-orphans` conflita na :8000 (motivo do
  desvio 1). `make docker-up`/`docker-update` e o instalador já o passam.
- O container `atlasfile-dashboards` de uma instalação anterior NÃO é órfão
  para o compose (serviço existe, com profile) — segue rodando até um
  `docker compose --profile dashboards down` ou `docker stop`. Inofensivo.
- `make docker-update` exige toolchain de dev (roda `make test`); máquina de
  usuário migra com `docker compose up -d --build --remove-orphans` (a VM
  provou esse caminho).
- Sobras de `git pull` real inexistentes aqui (transferência por tar não
  apaga arquivos removidos) — num `git pull` verdadeiro, `frontend/Dockerfile`,
  `frontend/.dockerignore` e `app/mcp/__main__.py` somem sozinhos.

## Fora de escopo (inalterado)

Fase 3 (GHCR, release.yml, digests, bundle, primeira tag), 4a/4b, site,
hardening de portas do OpenSearch, `--workers > 1` (documentado no
Dockerfile: sessões MCP em memória por worker + watchers duplicados).

# Changelog

Todas as mudanças relevantes do AtlasFile são documentadas neste arquivo.

---

## Instalador — 2026-07-31 (Fase 4b; sem bump — a versão do app segue 1.0.0)

### `install.ps1` alinhado à release: flags novas, ajuda sem promessa de clone, painel com o dono real (Fase 4b)

- **`-Version X.Y.Z` (novo)** — pina a release, com **validação cedo no próprio ps1** (mesmo shape aceito pelo `install.sh`): um typo falha em segundos, antes de instalar WSL e Docker Desktop. Fato medido na bancada: antes da guarda, `-Version banana` via `powershell -File` rodava a instalação **inteira** — o encaixe posicional engolia o parâmetro desconhecido (a crença "PowerShell recusa parâmetro desconhecido com erro terminante" só vale sob `iex`).
- **`-FromSource` (novo)** — correção de regressão da 4a: desde o merge do PR #15 o Windows não tinha como pedir o caminho de contribuidor (clone + build) — um `-Branch` de trabalho virava warn+ignore do outro lado. **`-RepoUrl` (novo)** vale só com `-FromSource` e fecha a dor do item 2 do ROADMAP (testar um fork de ponta a ponta no Windows). `-Version` com `-FromSource` é **recusado** na entrada: o `.sh` ignoraria a versão em silêncio, e ignorar o que o usuário digitou é mentira.
- **`-NoOpen` (novo)** — e o browser ganhou seam observável: `Open-AfBrowser` **anuncia** a abertura antes de tentá-la (a mensagem antiga só existia no `catch`, ou seja, só na falha — um sinal que só aparece na falha não prova nada numa bancada).
- **Painel final** (item 3 do ROADMAP) — os comandos ensinados de `logs`/`stop` carregam o dono real da instalação: `wsl -u root -e` quando a distro roda como root; contrapositivo na bancada garante `wsl -e` para instalação de usuário padrão.
- **Ajuda e header sem promessa de clone incondicional** — `-Branch` re-documentado ("only with -FromSource"); o texto do uninstall segue falando de clone porque instalação fonte/legada É um clone. A fase 3 anuncia pull da imagem publicada (~290 MB, sem promessa de minutos — espelha a decisão da 4a).
- **Guarda ressuscitada** — a metade "header" do `check_flags` era **morta**: as linhas do cabeçalho começam com `#` e a âncora nunca casava (extração devolvia conjunto vazio). Consertada em `check_consistency.py` e provada com mutante (flag `-Fake` no header reprova).
- **Bancada Windows 206→228** no canal prlctl/SYSTEM, comparada por **nome de asserção** (zero regressão da baseline), com 16 vermelhos naturais registrados antes da implementação e **7 mutantes na VM + 1 local**, cada um matando exatamente a guarda-alvo. Cenários de instalação completa agora passam `-NoOpen` — a bancada abria um Edge de verdade a cada rodada.
- **O que deliberadamente NÃO nasceu**: `-NoOllama` (flag já-depreciada que nunca existiu no ps1) e `-Registry` (o `install.sh` não tem `--registry`; o override de imagem é `ATLASFILE_IMAGE` no compose, via de smoke, não alavanca de usuário).
- Docs: `INSTALL.md`, `README.md`, `README.pt-BR.md` e ROADMAPs atualizados. **Errata da 4a**: o registro daquela fase afirmava que o `install.ps1` encaminhava `--repo-url` — falso; até esta fase o ps1 não tinha a flag.

---

## Instalador — 2026-07-31 (Fase 4a; sem bump — a versão do app segue 1.0.0)

> Decisão registrada: mudança de instalador não altera a versão do App. O
> `install.sh` é servido por `raw.githubusercontent.com/main` e não faz parte
> do bundle da release — o merge na main entrega a mudança a todo usuário novo
> sem precisar de tag.

### Instalar sem clone: bundle da release + pull da imagem publicada (Fase 4a)

O caminho padrão do `install.sh` deixa de clonar o repositório e compilar a imagem: resolve a última release estável (ou a pinada por `--version X.Y.Z`), baixa o bundle (~10 KB) com verificação de SHA256, valida o conteúdo antes de tocar o disco e sobe a stack por `docker compose pull` da imagem publicada no ghcr.io. git deixa de ser pré-requisito do caminho padrão; `tar` entra (exigido, nunca instalado — como o curl).

- **`--from-source` (novo)** — o caminho de contribuidor é o de sempre: clone + build local pelo overlay. Instalações existentes com `.git` **permanecem no caminho de clone** no re-run (auto-detecção com aviso): migrar para bundle é decisão do usuário (`--uninstall --keep-data` + instalação nova), nunca efeito colateral. `--repo-url`/`--branch` continuam aceitos e só valem com `--from-source` (aviso + ignore no caminho bundle — o `install.ps1` os encaminha quando usados).
- **`--version X.Y.Z` (novo)** — pina a release (prereleases `X.Y.Z-rc.N` aceitas). O valor — digitado ou resolvido da API — passa por validação estrita de shape antes de tocar URL, `.env` ou compose. Sem o flag, a última release estável via API do GitHub, com mensagem acionável em caso de rate-limit (60/h anônimo) apontando o contorno e a lista de releases. **Downgrade** é detectado e exige confirmação interativa (`--yes` não pula essa).
- **Integridade e conteúdo do bundle** — SHA256 verificado **antes** de o tar ser aberto (provado na bancada com wrapper que grava a ordem); pós-extração, o conteúdo tem de ser exatamente os 4 arquivos esperados — entrada estranha ou symlink recusa a instalação sem tocar o dir. Declarado no plano: o checksum mitiga download truncado/corrompido, não comprometimento do host (a raiz de confiança é o TLS do GitHub, a mesma do próprio `curl | bash`).
- **Update sem clobber** — os 4 arquivos do bundle são do instalador e são substituídos no update, mas "nosso" se prova: o hash gravado no manifesto (`bundle_sha`) diz se o arquivo em disco ainda é o entregue; divergiu, ganha cópia datada ao lado (`docker-compose.yml.backup.<ts>`, registrada em `bundle_backups`) com aviso nomeando o arquivo. `.env`, `config/api_keys.json` e qualquer arquivo do usuário nunca são tocados. Re-executar o instalador É o ato deliberado de update: o pin `ATLASFILE_VERSION` é atualizado com backup automático do `.env`.
- **Uninstall no mundo bundle** — `repo_clone=bundle` marca dir criado pelo instalador no caminho novo, removível com as MESMAS guardas do clone `created`: o `install_dir` do manifesto tem de bater, e arquivo que o instalador não pôs lá (respondido pelo manifesto, já que não há git) preserva a pasta nomeando os intrusos. `--doctor` ganhou o braço correspondente (sem ele, diria que o `--uninstall` preserva exatamente o que o plano remove). Guarda nova de bancada: a imagem GHCR entra no plano de remoção mesmo quando é a ÚNICA imagem da instalação.
- **Update cross-branch do clone corrigido** (achado 1 da Fase 3, prometido "corrigir na 4a"): `af_update_clone` passa a buscar com refspec explícita (`+refs/heads/<b>:refs/remotes/origin/<b>`) — o clone raso nasce com refspec só de `main` e `--branch outra` morria em "unknown revision".
- **Guard de volume no re-run**: a detecção de "instalação nova" passou de `.git` para "sem `.git` E sem manifesto" — sem isso, o re-run de uma instalação bundle com volume existente seria barrado como instância estrangeira.
- **Mensagens honestas** — fase 4 no bundle path: "first run downloads the app image (~290 MB)…" (tamanho medido no rc.2; nenhuma promessa de segundos); erro de rede agora cita os registries reais (ghcr.io e Docker Hub) e o host de redirect (`objects.githubusercontent.com`) para allowlists corporativas. `--dry-run` segue read-only: no bundle path não toca a API, e mostra "would be INSTALLED from the release bundle".
- **Bancada**: 253 → 291 PASS, incluindo release LOCAL real (tar.gz + SHA256SUMS de verdade servidos por stub de curl), e **11 mutantes** provando as guardas novas (cada um reprova exatamente no caso-alvo). Seams de teste: `ATLASFILE_API_BASE` / `ATLASFILE_DOWNLOAD_BASE`.
- **`un_compose_down` sobrevive a `.env` removido** (achado do E2E na VM, em três tempos): uninstall parcial anterior remove o `.env` e o `down` morria na interpolação de QUALQUER variável `:?` (e na spec do bind de `PROJECTS_HOST_ROOT`) com zero containers no ar; a entrega dos placeholders é por `--env-file` porque o export morre no shim de sudo (o sudo limpa o ambiente). Provado na VM real e por mutante.
- **E2E completo na VM lima** (Ubuntu ARM64): install bundle real contra a release v1.0.0 em 1m07s (pull 17s), smoke OCR/triagem/busca/MCP verde, re-run idempotente 33s, ciclo `--keep-data` com índice sobrevivendo, `--from-source` + re-run cross-branch real (1s), purge final limpo.

---

## [1.0.0] - 2026-07-30

_A 1.0.0 é release interna até o fechamento do plano de distribuição e segue
recebendo correções sem bump (decisão de 2026-07-31); a imagem pública será
re-emitida com elas quando o plano fechar._

### Adicionado em 2026-07-31 — portas de host configuráveis (subplano pós-4b)

- **`ATLASFILE_PORT`** (default 8000), **`OPENSEARCH_PORT`** + **`OPENSEARCH_BIND`** e **`DASHBOARDS_PORT`** interpoladas no compose (`${VAR:-default}` — padrão de mercado medido em 8 produtos self-hosted; nenhum faz auto-increment de porta, e o AtlasFile também não: conflito continua falhando cedo, agora com o remédio na mensagem). O instalador ganhou `--port N` (`-Port` no Windows), com validação cedo nos dois lados; a porta pedida persiste no `.env` e o re-run a honra sem repetir a flag. Guarda de portas, doctor, esperas de health, painel final e abertura do browser falam da porta EFETIVA (flag > env > `.env` > default) — no Windows, o browser lê a porta da instalação pelo `.env` de dentro do WSL.
- **MUDANÇA DE COMPORTAMENTO**: o OpenSearch passa a nascer em `127.0.0.1:9200` (consenso dos apps self-hosted: banco/índice fora da rede; o Docker publica portas por cima do firewall do host) — localhost continua funcionando (`make reset-index`, curls das docs); rede local exige `OPENSEARCH_BIND=0.0.0.0` no `.env`. A porta **9600** (performance analyzer) deixou de ser publicada: zero consumidores. O link "Observabilidade" passou a derivar a porta do Dashboards de `DASHBOARDS_PUBLIC_PORT` (era um `:5601` fixo no backend que quebraria em silêncio com binding custom).
- De carona, um defeito real pego pela bancada de forma real: `af_env_lookup` com chave ausente matava o instalador em silêncio (`set -euo pipefail` + rc do grep atravessando a atribuição). E `set_env` mudou para a zona de funções (vivia abaixo do gate de biblioteca, invisível para a bancada).

### Adicionado em 2026-07-31 (pós-tag inicial)

- **fix(api): `upload_to_inbox` neutraliza path traversal no filename do multipart** — pré-existente desde a criação do endpoint (flagado na Fase 3): `dest = inbox / filename` cru permitia que um multipart com `../../x` ou caminho absoluto escrevesse FORA da inbox. Agora só o componente final é usado, com rejeição explícita de `''`/`.`/`..` (pathlib só descarta `.` — `Path("..").name` devolve `..`, medido no teste: virava `..__2` no dedup). Mesmo padrão de guarda do `delete_inbox_file`; 3 testes nascidos vermelhos, suíte backend 755 passed.

### A primeira imagem publicada — e provada (Fase 3 do plano de distribuição)

O AtlasFile passa a ser distribuído como imagem: `ghcr.io/aleonnet/atlasfile`, multi-arch (amd64+arm64), construída em runners nativos e publicada por um workflow de release disparado por tag. **1.0.0 pela régua operacional, não de API**: a API só ganhou um campo aditivo, mas o contrato de deploy quebra — o `docker-compose.yml` deixa de buildar e passa a consumir imagem por versão explícita — e a primeira imagem pública com prova funcional é o compromisso de estabilidade que a série 0.x nunca assumiu. Publicada após ensaio com `v1.0.0-rc.1` (prerelease no GitHub, sem `latest`).

- **`.github/workflows/release.yml` (novo)** — 4 jobs com o invariante central: `latest`/`X.Y`/`X.Y.Z` **nunca apontam para bits que não passaram no smoke**. `version` guarda a tag (formato, tag∈main — a branch protection segue desligada —, tag↔`package.json`); `build` publica por digest (sem tag) em amd64 e arm64 nativos; `smoke` sobe a stack **pela imagem publicada** em cada arch e roda o E2E completo; `publish` só então aplica as tags (`imagetools create`), prova multi-arch no próprio job, atesta proveniência (`attest-build-provenance`) e anexa o bundle (~10 KB: compose + `.env.example` pinado + configs) ao GitHub Release. Smoke vermelho deixa apenas digests sem tag, invisíveis a `docker pull`.
- **`scripts/smoke-e2e.sh` (novo)** — o conteúdo da palavra "testada": gate de versão (`/api/setup/status.version == tag`), upload de PDF nativo e de PDF **escaneado**, scan determinístico, triagem aprovada (o único caminho que indexa — fato provado na revisão do plano: doc pendente NÃO é indexado), busca com highlight da sentinela vinda do **OCR do tesseract da imagem** (não o do runner), `/mcp` recusando sem key e fechando o loop tool→loopback→API com key (`isError` checado — status 200 sozinho é gate furado), e prova de que a imagem publicada **não contém** `config/api_keys.json`. É a primeira vez que o CI exercita OpenSearch de verdade.
- **Versão consultável** — `ARG ATLASFILE_VERSION` no `backend/Dockerfile` → env → campo `version` em `GET /api/setup/status` ("dev" em build local). Antes, a única prova de versão era a sidebar; agora o smoke afirma "a imagem publicada é a v1.0.0" por HTTP.
- **`docker-compose.yml` vira consumo** — `image: ghcr.io/aleonnet/atlasfile:${ATLASFILE_VERSION}` **sem default** (um `latest` implícito faria duas instalações em datas diferentes divergirem; atualizar é ato deliberado), com `ATLASFILE_IMAGE` como via de digest para o smoke; OpenSearch e Dashboards pinados por **digest sha256** (padrão Immich) com guarda nova em `scripts/check_pins.sh`; `EMBEDDING_ENABLED`/`AUTO_INGEST_ENABLED` repassados (feature desligada pula o caminho caro de verdade); `start_period` do healthcheck para 90s (primeiro boot em runner de 4 vCPU — unhealthy é terminal para `up --wait`).
- **`docker-compose.build.yml` (novo)** — o build local vive num overlay, como `image: atlasfile-local:dev` **de propósito**: bits caseiros nunca usurpam o nome oficial (um `up` sem overlay não pode "achar" um build local e pular o pull; o `COPY config` do Dockerfile assa o config do dev — essa imagem não pode se apresentar como a publicada), e a tag fixa mantém o `docker image prune` reclamando a imagem anterior como sempre. `make docker-build/docker-up/docker-update` usam os dois arquivos; novo `ensure-atlasfile-version` grava a var no `.env` de quem atualiza por `git pull` (sem jq — sed BSD-safe lendo `frontend/package.json`).
- **`install.sh` na medida mínima** (o grosso — instalar sem clone — é a Fase 4a): grava `ATLASFILE_VERSION` no `.env` (novo e preexistente), builda/sobe pelo overlay, e o **uninstall parou de vazar imagem**: `down --rmi local` não remove imagem com `image:` nomeado, então `un_collect` passou a listar `ghcr.io/aleonnet/atlasfile:*` e `atlasfile-local:*` com remoção explícita e passo próprio na tela — guarda de bancada provada com mutante (sem a correção, a bancada fica vermelha). `un_compose_down` tolera `.env` anterior à 1.0.0 (placeholder só para a interpolação do `down`).
- **Migração de 0.57.0**: `git pull` + `make docker-up`/`docker-update` seguem buildando local e ganham `ATLASFILE_VERSION` automaticamente; `.env` antigo sobe sem edição; volume `opensearch_data` intocado. Quem rodava `docker compose up -d` cru precisa passar a incluir o overlay (`-f docker-compose.yml -f docker-compose.build.yml`) ou definir `ATLASFILE_VERSION` — o erro do compose diz exatamente isso.
- **Fixture de OCR commitada** (`backend/tests/fixtures/ocr/`, com gerador e proveniência): PDF de 1 página só-imagem com a sentinela `SENTINELA QUARENTA E DOIS`; `tests/unit/test_pdf_ocr_fixture.py` exercita o OCR **sem monkeypatch** pela primeira vez, com âncora que reprova se a fixture ganhar camada de texto.
- Durante o ensaio rc.1, a sidebar mostra `v1.0.0` (versão do bundle) e `/api/setup/status` mostra `1.0.0-rc.1` (versão da tag) — assimetria esperada, não é bug.

---

## [0.57.0] - 2026-07-30

### ⚠️ BREAKING — um app, um container (Fase 2 do plano de distribuição)

Consolidação de `api` + `mcp` + `web` num único processo uvicorn no `:8000`. Duas quebras deliberadas, sem caminho de compatibilidade:

- **Clientes MCP externos param**: o MCP saiu de `http://localhost:8001/mcp` para `http://localhost:8000/mcp` — e, com `API_AUTH_ENABLED=true`, o `/mcp` passa a exigir a MESMA API key da API (`Authorization: Bearer`). A porta 8001 não existe mais; o aviso antigo "porta 8001 não valida key" morreu junto com ela.
- **A UI saiu de `http://localhost:5173` para `http://localhost:8000`**, agora como bundle de produção (vite build) servido por StaticFiles — o vite dev server (HMR aberto, sem minificação) deixou de ir para produção, e o acesso de outra máquina funciona porque a UI fala com a API pela própria origem (morreu o `VITE_API_URL=http://localhost:8000` hardcoded que mandava o browser remoto procurar a API no localhost dele).

O que a consolidação corrige de uma vez: 5 containers → 2 (3 com Dashboards), servidor de desenvolvimento em produção, acesso remoto quebrado e o segredo assado na imagem. `docker compose up -d --build web` e o restart granular de web/mcp deixam de existir (um crash agora derruba API+MCP juntos — custo aceito do nível de consolidação).

- **`backend/app/main.py`**: FastMCP montado como `Route("/mcp")` que delega ao `session_manager.handle_request` por request — não é `app.mount()`, porque o Starlette interno do SDK registra a própria rota em `/mcp` (mount viraria `/mcp/mcp`) e Mount responde 307 no path exato. O lifespan envolve o `yield` com `async with session_manager.run():` (mount não executa lifespan de sub-app) e recria o manager a cada ciclo (`run()` é single-use por instância). StaticFiles em `/` montado no FIM do arquivo, só quando o diretório existe (dev/CI seguem sem dist).
- **`backend/app/auth.py` — `MCPAuthMiddleware`**: Route/Mount NÃO herdam o `dependencies=[Depends(require_auth)]` global do FastAPI — sem o middleware, `/mcp` nasceria aberto com auth ligado. Mesma key, mesmos três canais (`Bearer`, `X-API-Key`, `?api_key=`).
- **`backend/app/mcp_client/client.py`**: o outro lado da mesma armadilha — fechar `/mcp` quebraria o orchestrator, que conectava sem credencial. Com `ATLASFILE_API_TOKEN` configurado, o client passa um `httpx.AsyncClient` autenticado ao SDK (`streamable_http_client` não aceita `headers=`) e o fecha no finally — o SDK não fecha client fornecido; sem o `aclose()`, vazaria 1 client por tool call.
- **`backend/app/mcp/server.py`**: `transport_security` explicitamente sem DNS-rebinding — sem isso, remover o `host="0.0.0.0"` (que morreu com o standalone) auto-ligaria a proteção do SDK e `/mcp` responderia **421** fora de localhost. `run_server()`/`python -m app.mcp.server` removidos (o uvicorn consolidado serve o `/mcp`).
- **Deadlock de event loop achado no E2E e corrigido — o defeito mais grave do ciclo**: o SDK (mcp==1.26.0, `func_metadata.py:92-95`) executa tool síncrona INLINE no event loop, não no threadpool como o plano supunha. Consolidado, cada tool call congelava o processo inteiro: a tool bloqueava o loop, o HTTP loopback dela para o próprio servidor nunca era atendido, e até o `/health` e o 401 do `/mcp` morriam até o timeout do api_client (**medido na stack real: 60.100ms por call, com erro interno "timed out"**). Na topologia antiga o defeito era invisível — a API vivia em outro processo. Correção: as tools são registradas via wrapper `@tool()` (`app/mcp/server.py`) que despacha a função síncrona ao `anyio.to_thread`, preservando assinatura; **60.100ms → 59ms**, e guarda nova impede registro sync direto.
- **Threadpool dimensionado e MEDIDO**: as 13 tools e os 81 handlers síncronos dividem o mesmo threadpool do anyio (default 40), e cada tool call em voo segura 2 slots (tool + endpoint chamado por loopback) — ~20 chamadas saturariam. Limiter elevado para 100 no startup. Carga real na stack consolidada: 50 tool calls concorrentes (o teto de projeto) em 1.2s de parede, p95 ~1s, `/health` respondendo após cada degrau.
- **`backend/Dockerfile` multi-stage**: estágio `node:22-alpine` roda `npm ci && npm run build` e o estágio final copia o `dist` para `/workspace/static` — a imagem passa a rodar bundle de produção, e `frontend/Dockerfile`/`frontend/.dockerignore` morreram.
- **`docker-compose.yml`**: serviço único `atlasfile` (container `atlasfile`); **primeiros healthchecks do arquivo** (OpenSearch autenticado + `/health` do app) com `depends_on: service_healthy` — ordem de start deixou de ser confundida com prontidão; `config/api_keys.json` virou **bind mount** (trocar key não exige mais rebuild — o vetor "key numa camada de imagem" morreu). Dashboards virou **opt-in** (`profiles: [dashboards]` + `DASHBOARDS_ENABLED=true`): é ~1/3 do download de terceiros e o produto opera sem ele; a UI esconde o link de observabilidade quando desligado (senão seria um 502).
- **Armadilha do bind mount, guardada**: arquivo ausente no host viraria um DIRETÓRIO criado pelo Docker — e o auth rejeitaria toda key em silêncio. `install.sh` e `make docker-up`/`docker-update` materializam `{"keys": []}` antes do `up`.
- **`frontend/src/api.ts`**: `API_BASE` cai para `window.location.origin` (não string vazia: 11 call sites de `new URL()` exigem base absoluta). `VITE_API_URL` segue como escape hatch de dev.
- **Instaladores**: painel final, pré-checagem de portas, doctor e open apontam para `:8000`; o passo opcional do Dashboards entrou nos next steps; `un_collect` casa a imagem consolidada **e** as legadas api/web/mcp (upgrade de 0.56.x não vaza imagem no uninstall) — com guarda nova na bancada.
- **Migração de 0.56.x**: `git pull` + `make docker-update` com o `.env` antigo sobe sem edição (`extra="ignore"` no backend; envs órfãs só viram ruído inerte) e o volume `opensearch_data` sobrevive (nome vem do projeto compose, inalterado).

### Guardas novas, cada uma provada com seu mutante

`MCPAuthMiddleware` isolado (6 mutantes de auth), wiring real do `/mcp` (401 sem key; com key atravessa o middleware), handshake MCP E2E **duplo** no mesmo processo (mata "esqueceu o `session_manager.run()`" e "esqueceu o reset single-use"), guarda do DNS-rebinding (`transport_security` explícito), injeção e fechamento do client autenticado, curto-circuito do Dashboards desligado (feature off não pode custar), mount condicional do static (dir ausente não monta; presente serve), e a asserção de bancada do `un_collect`.

## Não versionado — Ferramental

### PoC: MarkItDown vs Extrator AtlasFile (`extractor-benchmark_mdxaf`)

- **Nova pasta de benchmark** comparando MarkItDown (vanilla) vs o extrator de produção do AtlasFile, lado a lado, sobre 6 contratos reais (PDF/DOCX/XLSX/PPTX)
- **Comparação determinística** (sem LLM-judge, sem custo de API): métricas objetivas (tamanho, linhas de tabela markdown, densidade numérica, latência, memória) + outputs lado a lado para inspeção humana
- **Achado principal**: extrator do AtlasFile superior em PDF nativo (preserva espaçamento; MarkItDown mangla) e escaneado (OCR; MarkItDown sai vazio após ~24 min). MarkItDown só agrega como gerador de Markdown estruturado de Office
- **Não toca** backend, frontend nem o `extractor-benchmark/` existente. `corpus/` e `results/` fora do git (contratos sensíveis). Detalhes em `extractor-benchmark_mdxaf/ACHADOS.md`

---

## [0.56.6] - 2026-07-29

### O artefato instalado passa a ser resolvível ao artefato testado (Fase 1 do plano de distribuição)

Primeira fase de `docs/roadmap/distribuicao_build_imagens_ghcr.md`: fechar a camada de aplicação. Nove dependências do backend tinham piso `>=` sem teto e o frontend declarava `lucide-react: "latest"` — dois builds da mesma versão em datas diferentes podiam instalar coisas diferentes, e nenhum teste provaria.

- **`backend/requirements.txt`**: os 9 pisos abertos (`pymupdf`, `Pillow`, `duckdb`, `mcp`, `httpx`, `openai`, `anthropic`, `aiogram`, `matplotlib`) viraram `==` na versão que o ambiente de referência já roda.
- **Novo `backend/requirements.lock.txt`**: o resolve inteiro (99 pacotes, transitivos inclusive) travado. Gerado **dentro de `python:3.12-slim`** — a mesma base da imagem — porque o venv local é Python 3.11 e um `pip freeze` nele herdaria resolução de outra versão; a proveniência e o comando de regeneração estão no cabeçalho do arquivo. O `backend/Dockerfile` agora instala do lock.
- **`backend/requirements-dev.txt` parou de contradizer o produto**: redeclarava `httpx>=0.24.0` (contra `>=0.27.0` do produto) e duplicava `scikit-learn` — a bancada rodava com piso mais baixo do que o que ia para a imagem. Agora faz `-r requirements.lock.txt`: a bancada instala o MESMO resolve do produto, mais o pytest.
- **`frontend/package.json`**: `lucide-react` de `"latest"` (único outlier entre 39 deps) para `^0.576.0`, a versão que o lockfile já resolvia. E `frontend/Dockerfile` trocou `npm install` por `npm ci` — o `npm install` re-resolvia o dist-tag e **reescrevia o lockfile dentro da imagem**, invisível para o CI que usa `npm ci`.
- **Novo `frontend/.dockerignore`**: o build context do `web` é `./frontend`, onde o `.dockerignore` da raiz não vale — numa máquina com `npm install` local, o `node_modules` do host entrava no `COPY . .` por cima do install nativo do container. Medido após a correção: transferência de contexto instantânea.

### Guarda nova, provada com mutante antes de valer

`scripts/check_pins.sh` reprova range aberto (`>=`, `~=`, `<`, `>`) nos requirements do backend (produto e extra opcional) e `"latest"`/`"*"` em qualquer `package.json` — o mesmo script roda no CI (job `pins`) e na máquina local. Provada nos dois sentidos antes de entrar: reintroduzir `openai>=1.0.0` reprova, reintroduzir `lucide-react: "latest"` reprova, e o próprio `fastembed>=0.4.0` real serviu de mutante natural — a guarda estendida reprovou o arquivo antes do pin. `fastembed` pinado em `==0.8.0` (o resolve do dia; não havia versão instalada para herdar), com `pip check` limpo por cima do lock em container 3.12.

E o teste que faltava: `test_mcp_client_import.py` importa `app.mcp_client.client` **sem patch** e afirma que `streamable_http_client` resolve de verdade. Os testes existentes patcham o símbolo por atributo e nunca pegariam um `mcp` antigo. Prova de mutante em container 3.12 real: com `mcp==1.9.3` (que o piso `>=1.0.0` aceitava) o teste reprova com a mensagem desenhada; com o lock (`mcp==1.26.0`), passa.

### O plano de distribuição foi recalibrado para a v0.56.5

O plano tinha sido escrito contra a v0.56.2, e os PRs #7–#9 mexeram exatamente nos arquivos que ele referencia. Recalibração completa contra o código: a narrativa do "piso falso do mcp" corrigida (fragilidade real, não `ImportError` provado — um resolve limpo pega o topo, não o piso), itens já resolvidos marcados (o "~15 min" morreu na v0.56.5; o `--dry-run` na v0.56.3), números remedidos (bancadas, linhas, offsets) e o drift do site registrado (4 comandos publicados recomendam `--with-ollama`, que é no-op depreciado desde a v0.55.0 — a promessa "also install Ollama" é falsa hoje). O rascunho superado `plan_one_line_installer.md` foi movido para `docs/planos_concluidos/`, por decisão do autor.

### O que esta fase NÃO fecha

Registrado no próprio plano: apt sem versão no Dockerfile, imagem base em tag móvel e a ausência de prova funcional da imagem ficam para as Fases 2–3. Terminar a Fase 1 não autoriza a frase "reprodutibilidade resolvida".

---

## [0.56.5] - 2026-07-29

### O instalador rodou num Windows 11 real, e achou quatro defeitos

Primeiro teste do `install.ps1` **com a stack de verdade no ar num Windows de verdade** — bloqueado por hardware desde a v0.54.0, porque exige virtualização aninhada em convidado Windows, que nem Parallels nem UTM entregam em Apple Silicon.

**O que passou:** instalação do zero em 15m56s (WSL2, Docker Desktop e os cinco containers), reinstalação por cima em 26s com `.env`, senha do OpenSearch e chave de API preservados, e os dois caminhos de desinstalação testados — o plano dos dois lados e o `-KeepData`, que removeu a stack e o clone e preservou volume, documentos e Docker.

**A correção da v0.56.4 estava incompleta.** Ela impedia o `wsl -e`, mas `Test-WslUsable` chamava `--status` e `--list` em sequência, sempre — e o teste provou que **`wsl --list` também dispara** o prompt "Pressione qualquer tecla para instalar Subsistema do Windows para Linux" quando o recurso está ligado sem distro. A correção só trocava a origem do prompt. Agora há curto-circuito: se o `--status` já disse que não está instalado, a função retorna antes de listar.

**O script de reset tinha o mesmo defeito que eu havia acabado de corrigir.** `scripts/reset-wsl-windows.bat` chamava `wsl --list --verbose` e `wsl --shutdown` sem guarda, e o prompt do Windows apareceu duas vezes na tela. Agora a inspeção usa fontes que não tocam no `wsl.exe`: o `dism` para saber se o recurso está ligado, e **o registro do Windows** para listar as distros.

**O reset dizia "Docker Desktop IS installed" e "done" sem remover nada.** A detecção era `winget list` com `if errorlevel 1`, mas **o winget sai 0 mesmo quando não acha o pacote** — escreve "No installed package found" e considera que o comando funcionou. Numa máquina sem Docker o script anunciou que estava lá, tentou remover, não achou o desinstalador, caiu no winget que não achou nada, e imprimiu sucesso. É a mesma lição do `wsl --status`: **código de saída não é sinal, a mensagem é**. Agora a detecção casa o identificador na saída, e o resultado é conferido depois de remover em vez de anunciado.

**O plano da desinstalação ignorava a decisão já tomada.** Com `-KeepData` na linha de comando, ele imprimia que o volume "ainda é sua escolha" — o texto de indecisão é honesto quando nada foi decidido e falso quando a decisão veio na linha de comando. A flag não chegava ao `--plan-only`; agora chega.

### As estimativas de tempo estavam erradas de um jeito curioso

Terceira medição, agora em máquina real: **build de 1m05s** (contra 48s numa VM ARM64 e 94s no runner do CI). O instalador prometia `~15 min` para o build — e o total de fato deu 15m56s, **mas onze desses minutos foram o download do Docker Desktop**, não a compilação. O número acertava por coincidência e atribuía o tempo à coisa errada. Recalibrado para `~1-2 min`.

E a mensagem "um bom momento para um café" saía idêntica na **reinstalação**, onde o build reaproveita o cache e levou 3 segundos. Agora ela depende do estado.

### Os documentos deixam de nascer dentro do OneDrive

No Windows testado, a pasta Documentos estava redirecionada para o OneDrive — então os documentos **e o estado operacional em `_ATLASFILE`** foram criados dentro de uma pasta sincronizada, que o AtlasFile reescreve a cada ingestão.

O padrão agora detecta esse redirecionamento e usa a pasta do perfil do usuário: continua visível no Explorer, sem sincronização em nuvem. Quem quiser na nuvem passa `-ProjectsRoot` apontando para lá.

### Guardas

Provadas na ordem certa: **o commit dos testes foi ao CI sozinho e reprovou**, com três asserções acusando `casou /-e bash/ e nao devia`; só o commit seguinte, com a correção, ficou verde. Há contrapositivo — com WSL presente, os modos read-only têm de continuar delegando ao `install.sh`, senão a correção passaria mesmo se alguém simplesmente parasse de falar com o lado Linux.

### O que continua em aberto

O bug do painel final (`wsl -e` sem `-u root`) **não se manifestou**: a distro ficou sem conta inicializada e roda como root. Confirmá-lo exige completar o assistente de conta do Ubuntu. E `-PurgeData`, `-RemoveDeps` e o ciclo `-KeepData` → reinstalar reusando o volume seguem sem exercitar.

---

## [0.56.4] - 2026-07-29

### Um `--dry-run` que oferecia instalar o sistema operacional

Primeiro defeito encontrado pelo teste do instalador **num Windows 11 real**, com a máquina recém-zerada. O `-DryRun` anunciou `WSL2 is already here`, abriu **"Pressione qualquer tecla para instalar o Subsistema do Windows para Linux"** e terminou dizendo `-DryRun: nothing was installed`.

**Duas causas, no mesmo bloco.**

A detecção mentia: era `Get-Tool wsl`, que só verifica se o executável existe — e **`wsl.exe` vem com o Windows 11 mesmo com o recurso desligado**. O próprio código já registrava essa medição num comentário da fase de instalação, que usa a lógica correta (a mensagem do `wsl --status`); o caminho do `-DryRun` a ignorava e perguntava só pelo arquivo.

E o modo invocava o WSL de verdade: para montar o plano do lado Linux ele roda `wsl -e bash -c ...`. Num Windows sem WSL, **quem responde a essa chamada é o próprio Windows**, com o instalador do subsistema. Não era o AtlasFile pedindo para instalar — era o sistema operacional reagindo a ser chamado.

**Não era só o `-DryRun`.** As mesmas invocações estavam no `-Doctor` e nos dois pontos do `-Uninstall`: os três modos que prometem não mudar nada.

**A correção.** `Test-WslUsable` é read-only de verdade — só `--status` e `-l -q`, nunca `wsl -e` — e trata os dois estados que enganam: recurso desligado (a mensagem sai na stderr e o código de saída é 0, então só o texto serve de sinal) e recurso ligado com zero distro, que também cai no instalador do Windows.

No `-Uninstall`, a saída vazia com código diferente de zero é deliberada: ela cai no caminho de "plano ilegível" que já existia e **não toca no lado Windows**. Nenhum caminho novo foi inventado para o desinstalador.

O `-Doctor` também deixa de contar WSL ausente como "broken" — é um fato da máquina, não uma falha do diagnóstico. Antes ele saía com código diferente de zero num Windows limpo, que é um estado perfeitamente legítimo.

**A guarda foi provada na ordem certa:** o commit com os testes foi ao CI **sozinho e reprovou**, com as três asserções acusando `casou /-e bash/ e nao devia`; só o commit seguinte, com a correção, ficou verde. O stub de `wsl` ganhou `AF_WSL_NOT_INSTALLED`, que replica o estado real medido. E há um contrapositivo: com WSL presente, os modos read-only têm de continuar delegando ao `install.sh` — sem ele, a correção passaria mesmo se alguém simplesmente parasse de falar com o lado Linux.

---

## [0.56.3] - 2026-07-29

### O nome do documento perdia o identificador na ingestão

Relatado pelo usuário com arquivo real, e reproduzido contra o código antes de qualquer correção:

```
entrada : DocuSign_Project_Neptune___SPA__Anexos_v_A__v01__v01.pdf
saída   : Anexos_v_A__v01.pdf
```

**O que acontecia.** O arquivo chega ao INBOX com o nome **do usuário**, que já termina em `__v01.pdf` — versionamento manual, convenção comum em documento real — e contém `__` no meio. A cauda casava com `_CANONICAL_TAIL_RE`, o nome era tratado como canônico sem nunca ter sido embrulhado, e a repartição por `__` devolvia o terceiro pedaço. `DocuSign_Project_Neptune___SPA` ia para o lixo.

O guarda que deveria impedir isso validava o **candidato de saída** em vez de provar a **entrada**: `Anexos_v_A` não é data, nem `project_id`, nem domínio conhecido, então passava.

**O caminho legítimo sempre esteve certo** — o mesmo arquivo *com* prefixo canônico era desembrulhado preservando tudo, e havia teste para isso desde a v0.45.0. O defeito era só no caso sem prefixo.

**A correção.** Antes de desembrulhar, o instalador prova que o prefixo **é** canônico, checando cada segmento contra o campo que ele deveria ser, com fatos do profile: `{date}` casa `\d{8}`, `{project}` casa o `project_id`, `{area}`/`{document_type}` casam chaves conhecidas. Nada de heurística sobre a forma do nome. Campo que o profile não conhece não bloqueia, porque o pattern é configurável.

Nenhum arquivo em disco é renomeado e o formato canônico não muda — escapar o `__` na geração seria correto na raiz, mas exigiria migrar tudo que já foi canonizado.

### O reconcile nunca rodava logo após a instalação

Numa instalação nova apontada para uma pasta que **já tem documentos**, a interface mostrava zero por dez minutos, e "Reconciliar agora" era o único caminho.

A causa é uma linha: o laço do reconcile automático faz `wait(interval)` **antes** do corpo, então o primeiro ciclo só sai um intervalo inteiro depois da subida — 600s no default do compose. (O `0` que aparece no `config.py` não é o valor efetivo: o `docker-compose.yml` o sobrescreve.)

Agora um ciclo dispara na subida **quando há projeto no disco e o índice ainda está vazio**. A condição é deliberadamente essa, e não "algum projeto sem documento": ela precisa ser falsa em todo `docker compose restart` de rotina, senão um corpus grande pagaria uma reconciliação completa a cada reinício. Projeto novo em instalação já povoada segue coberto pelo laço periódico e pelo watcher.

### `--dry-run` se contradizia na mesma tela

O `--dry-run` mostrava o veredito sobre os pré-requisitos duas vezes, e as duas discordavam:

```
│ ✘ docker not found
│ ✔ none — everything needed is already here
```

Pior do que o registrado no roadmap, que só previa o caso do daemon parado: as duas seções discordavam sobre a própria **existência** do Docker.

A causa eram duas fontes de verdade sobre o mesmo fato. O retrato de pré-requisitos pergunta ao daemon e exige que a ferramenta responda `--version`; o bloco do `--dry-run` reperguntava com `command -v docker`, que tem sucesso com o daemon parado **e** com um binário mudo.

Agora o retrato registra **o que** faltou, não só quantos, separado por quem resolve: o que o instalador instala sozinho aparece como `!` ("would be installed"), e o que exige ação sua aparece como `✘` ("start Docker before installing"). O bloco do `--dry-run` consome esse registro em vez de remedir a máquina — a contradição fica impossível por construção, não por remendo.

O `install.ps1` delega o lado Linux ao `install.sh --dry-run`, então a correção vale para o Windows sem tocar no PowerShell.

### A bancada travava seis horas no CI gerando uma senha

O job macOS do CI batia o **teto de 6h do GitHub** em três execuções seguidas — ~18 horas de runner queimadas, e o log não dizia onde parava, porque a bancada é silenciosa por desenho (só imprime falhas e o placar final).

Com um rastreio novo (`AF_BENCH_TRACE=1`, que anuncia cada teste em stderr) o ponto de parada ficou provado na primeira execução: o teste que gera a senha do OpenSearch — o único que exercita a **geração**, já que o anterior usa senha reusada e retorna antes.

A causa é o padrão do gerador:

```sh
(LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom || true) | head -c 20
```

O `tr` lê `/dev/urandom` **para sempre** e só termina quando o `head` fecha o pipe e o `SIGPIPE` chega. Naquele runner não chegava. Não reproduz em macOS local (300 gerações sem uma falha, nenhum processo órfão) nem no runner Linux, que roda exatamente a mesma bancada.

Por isso a correção ataca a **classe** do problema e não o sintoma: `af_random_token` limita a **entrada** (`head -c 1024 /dev/urandom`), então nenhum processo lê sem fim e ninguém depende de sinal para terminar. Aplicado nos três geradores — senha do OpenSearch, chave de cookie do Dashboards e chave de API.

`timeout-minutes` em todos os jobs fecha a porta para o próximo travamento: dez minutos onde a bancada roda em cinquenta segundos, o que transforma qualquer trava futura em falha rápida em vez de seis horas.

**A guarda nasceu inútil**, e só passou a valer depois de duas correções. A primeira filtrava linhas com `head -c` e deixava o mutante passar verde — o padrão defeituoso *também* tem `head -c`, só que na saída, que é justamente onde ele não resolve. A segunda passou a acusar o próprio comentário que documenta o padrão antigo. A versão final reprova o mutante apontando a linha e passa limpa no código correto.

### Bancadas

Backend 725 → **731** asserções, instalador 211 → **218**. Cada guarda nova foi provada contra o defeito: neutralizada a prova de canonicidade, o nome volta a ser mutilado; removida a condição de índice vazio, o reconcile volta a rodar em todo restart; e a asserção do `--dry-run` reprovava antes da correção. A do `--dry-run` vem em par com o contrapositivo — com tudo no lugar a frase *tem* de continuar aparecendo —, que é o que impede a correção preguiçosa de apenas apagar a mensagem.

---

## [0.56.2] - 2026-07-28

### A desinstalação apagava os meios de reverter e falhava em reverter

Primeiro E2E do `install.sh` **em Linux com stack de verdade no ar** — VM Ubuntu 24.04 ARM64 limpa, sem Docker. Todas as validações anteriores (v0.54.0 a v0.56.1) foram macOS ou Windows, e por isso este defeito nunca apareceu.

**O que foi medido.** Numa desinstalação logo após a instalação, o resultado foi: cinco containers **ainda rodando**, volume e três imagens construídas **ainda lá**, e o clone e o manifesto **apagados**. O usuário ficava com a stack no ar e sem nenhuma ferramenta para removê-la.

A cadeia:

- **O plano nascia cego.** O `un_collect` trancava *todo* o retrato do Docker atrás de um `docker info` **sem sudo**. No Linux o grupo `docker` só vale no próximo login — o próprio instalador avisa isso —, então na janela entre instalar e relogar, que é exatamente quando alguém desinstala, o plano dizia **"0 container(s)"** com cinco no ar
- **O volume sumia das duas seções**, e com ele a única garantia desta tela que não tem default: `--uninstall --yes` deixou de exigir `--purge-data`/`--keep-data` e seguiu em frente
- **`docker compose down` falhava** por permissão e **a execução continuava**, apagando o clone (que contém o `docker-compose.yml`, a única forma de descer a stack) e o manifesto (o registro do que criamos)

**As correções:**

- **`af_docker_shim_linux`** — o shim que torna o `docker` alcançável nesta sessão, extraído do `ensure_docker_group_linux` e **sem efeito colateral nenhum**: não mexe em grupo, não escreve manifesto e não aborta. Desinstalar que adiciona alguém a um grupo seria o oposto do contrato
- **`run_uninstall` monta o retrato antes de coletar os fatos** e, quando nem com sudo alcança, **diz na tela** que o plano não enxerga containers nem volumes, em vez de mentir com zero
- **`un_execute` para na falha da stack.** Nada que sirva de ferramenta de recuperação sai antes de o que ela remove ter saído. A tela explica a parada e o que fazer

**Validado na VM, com stack real**, os cinco caminhos: plano em `--dry-run` (5 containers e o volume, onde antes eram 0 e nenhum), exigência de decisão explícita em headless, `--keep-data` (volume sobrevive, imagens upstream preservadas, documentos intactos), `--purge-data` (índice apagado) e `--purge-data --remove-deps` (Docker e grupo revertidos, `git` preexistente preservado, documentos intactos).

**Bancada: 197 → 202 asserções**, com o shim, a ausência de efeito colateral e a barreira do `un_execute` provados contra cópia mutada.

### `--keep-data` era um beco sem saída

O plano prometia, em letras, *"a future reinstall reuses it"* — e a instalação seguinte **recusava** o volume como *"data from another instance"*. Como o `--keep-data` remove o clone, a próxima instalação é sempre "nova" e a guarda sempre disparava. Os dois remédios sugeridos não devolvem o dado: `--dir` diferente muda o nome do projeto compose (e o volume preservado fica órfão), e `docker volume rm` apaga justamente o que se pediu para guardar.

Faltava um sinal que separasse *"volume que **nós** preservamos"* de *"volume de outra instância"* — sinal que a desinstalação tinha e jogava fora. Agora ela anota o volume preservado em `~/.atlasfile/kept-volumes` (fora do manifesto, que o `rm-state` apaga), e a instalação seguinte reusa **quando o diretório é o mesmo**. O registro é consumido no reuso: uma instalação futura, sem desinstalação no meio, volta a esbarrar na guarda — reuso é de uma vez, não permissão eterna.

**A senha vai junto, e isso não é detalhe.** A primeira tentativa de conserto liberou só a guarda, e o resultado medido foi pior que o bug: o índice de segurança do OpenSearch nasce com a senha da primeira subida e não muda, então a instalação nova gerava outra senha, **subia cinco containers e não funcionava** — `Authentication finally failed for admin` em todas as requisições. Uma falha alta e clara é melhor que uma stack quebrada em silêncio. O registro guarda a senha (arquivo `600`), a instalação a restaura, e o plano de remoção diz isso ao usuário em vez de esconder.

Guardar credencial em disco não é novidade aqui: a desinstalação já preserva backups de `.env` anunciando, no próprio plano, que eles *"hold the OpenSearch password and API key of earlier installs"*.

**Validado na VM**, o fluxo inteiro: instala → `--uninstall --keep-data` → reinstala. Mesmo volume (`CreatedAt` idêntico), mesma senha, API `{"status":"ok"}`, UI 200 e **zero** falhas de autenticação.

---

## [0.56.1] - 2026-07-28

### Auditoria de paridade entre os dois instaladores

Auditoria dos dois instaladores lado a lado, funcional e estética, com os dois fontes lidos por inteiro (4.663 linhas) e os caminhos read-only executados. **A guarda de consistência estava verde e 26 divergências viviam sob ela**: ela compara TABELAS e EXISTÊNCIA de primitivas, e o que divergia eram os ALGORITMOS que consomem essas tabelas e o USO das primitivas.

#### O que estava errado e o usuário via

- **O `-DryRun` do Windows prometia instalar o Ollama**, que saiu do instalador na v0.55.0. Um dry run que anuncia o que não vai acontecer mente sobre o próprio trabalho
- **A desinstalação abandonava o Docker Desktop em silêncio.** Com o WSL mudo, o `install.ps1` apenas abortava, e o Docker Desktop que ELE instalou ficava órfão sem uma palavra na tela. Agora ele é **relatado, não removido**: a tela nomeia o que o manifesto registra como nosso e diz como revertê-lo. Remover automaticamente foi tentado e **descartado** — "não consegui ler o plano" não prova que não há instalação do outro lado (o WSL pode estar vivo com AtlasFile rodando, e só a comunicação ter falhado), e o manifesto não desempata, porque `install_dir` só existe desde a v0.55.0. É a mesma disciplina já aplicada ao Ollama no Linux e ao Homebrew: listados com os passos, executados pela pessoa
- **`-Verbose` não atravessava a fronteira**: o build de ~15 min roda dentro do WSL, e era exatamente ele que continuava mudo
- **`-Dir` com espaço quebrava** a linha que viaja dentro de um `bash -c`. A citação virou uma função só (`ConvertTo-AfShArg`), com aspas DUPLAS: aspas simples protegeriam o espaço mas matariam o `~` — e o manifesto grava literalmente `~/AtlasFile`, então o `install.sh` procuraria uma pasta chamada `~`

#### O trilho (a calha `│`), furado dos dois lados

- **`install.sh --dry-run` imprimia 4 linhas fora da calha** — o plano de instalação inteiro, o bloco mais importante da tela. Escapavam da varredura da bancada porque ela mirava o prefixo `printf '  %s` e essas linhas começavam com espaços literais
- **`install.sh --uninstall` abria o trilho e nunca fechava** em três saídas: nada a fazer, cancelado e falhou. A guarda cobria `--doctor`, `--dry-run` e `--uninstall --dry-run` — justamente as que já tinham sido consertadas
- **`install.ps1` tinha 8 linhas vazias cruas dentro do trilho** (cinco réguas do `-Doctor`, a abertura do `-DryRun`, o bloco que explica o WSL na fase 1, o respiro do `-Verbose`), a régua do WSL2 sem separador, o placar do `-Doctor` quebrado em duas linhas com a segunda fora da calha, o despejo do manifesto com a calha na coluna 5, a barra de fase e o `Wait-Spinner` fora do trilho, e os blocos de orientação de FALHA — as telas que mais se lê — com recuo de 4 espaços

#### O banner: quatro divergências que a paridade de arte não via

A `check_art_parity` compara órbita, cometa, rampa, hexes e índice de repouso. Nada disso pega o que os algoritmos fazem com esses dados:

- **A cauda do cometa era contígua no bash e faiscada no PowerShell** — exatamente a forma que o comentário do `install.sh` registra como medida e REJEITADA ("deixava vãos de 3-5 colunas e lia como faísca")
- **As luas congelavam durante o voo do cometa** no Windows e seguiam orbitando no bash. Só o quadro FINAL coincidia — que era o único que a guarda do índice de repouso olhava
- **A ignição revelava uma linha a mais** em cada um dos cinco quadros iniciais
- **O brilho especular usava outra fórmula e outra linha de destaque** (3 em vez de 2), sombreando a esfera de um jeito que o outro lado nunca produz
- **A cabeça do cometa era salmão** (`ffd0c4`) em vez de branca, e a **ordem de escrita** era outra: o cometa passava por cima do orbe em vez de sair de trás dele

Mantida de propósito uma única divergência, decidida pelo dono do projeto: a linha `(Windows / WSL2)` que identifica a plataforma. A guarda a perdoa explicitamente **e cobra que ela continue existindo**.

#### Documentação

- **O `--help` do `install.sh` prometia instalar `curl`** e não instala — não existe `ensure_curl`; a checagem apenas falha. O `README.md` estava certo; quem mentia era a ajuda do instalador
- `INSTALL.md` não mostrava o `-DryRun` do Windows; não havia ponteiro para `install.ps1 -Help` (só para `install.sh --help`); a lista de flags do `.ps1` tinha 5 de 17
- Os exemplos de instalação manual recomendavam `Documents/Projects` e o instalador usa `Documents/AtlasFileProjects` — quem instala à mão e quem usa o one-liner acabavam em pastas diferentes
- `docs/roadmap/plan_one_line_installer.md` seguia como rascunho vigente com URLs (`atlasfile.dev`) e flags (`--install-dir`, `--gum`, `--no-prompt`) que nunca existiram — marcado como SUPERADO, com tabela do que de fato ficou de pé
- `docs/ROADMAP.md` ainda citava `--with-ollama`; `docs/11_scripts_and_operations.md` não mencionava os instaladores, apesar de o `INSTALL.md` apontar para ele como a visão consolidada dos scripts

#### Guardas (todas provadas com mutante)

- **`check_frame_parity`** — a que faltava: renderiza os **26 quadros dos dois instaladores** e compara caractere a caractere. Um seam `ATLASFILE_DUMP_FRAMES=1` no `install.ps1` espelha o `af_frame_plain` do bash. Provada com três mutantes (luas congeladas, ignição adiantada, linha de plataforma removida)
- **Varredura de calha do bash** ampliada: qualquer `printf` que comece com espaço literal, não só o prefixo `  %s`. E **descartando linhas de comentário** — sem isso ela casava com o próprio comentário que explica o defeito
- **Fechamento do trilho** passou a cobrir o `--uninstall` real, não só os três modos já consertados
- **`check_gutter_holes`** deixou de olhar só o corpo do `Write-Phase` e passou a varrer a faixa inteira do trilho no `install.ps1`, delimitada por marcas `AF-INICIO-DO-TRILHO`/`AF-FIM-DO-TRILHO`. **A primeira versão desta guarda nasceu cega** — a busca casava com a menção à marca dentro do próprio comentário de abertura e a faixa virava 1 linha —, então ela ganhou âncora de início de comentário e um piso de sanidade que grita se a faixa for pequena demais
- **Cores do cometa** (cabeça e as três células de cauda) entraram na paridade de arte: a guarda de quadros compara glifos, não cor
- **`make test-installer` passou a rodar `check_consistency.py`** e, quando há `pwsh`, o parse do `install.ps1` — os dois só existiam no CI, a minutos de distância

### Bancadas

- Bash: **196 → 197** asserções, verdes
- `check_consistency.py`: 11 → 12 checagens
- PowerShell: 3 asserções novas (til resolvido, til nunca literal, `-Dir` com espaço). **Não verificáveis no macOS** — a bancada invoca `powershell` 5.1; precisa do CI ou da VM

---

## [0.56.0] - 2026-07-28

### Validação em máquina real: macOS e Windows 11

A v0.55.0 entregou a orquestração dos dois lados com CI verde. Esta versão é o que **o uso real encontrou** — sete rodadas de instalação e desinstalação num Windows 11 e num macOS de verdade. Nenhum destes defeitos aparecia na bancada.

#### Impediam a instalação

- **`winget` instalava o Docker Desktop com INTERFACE.** Faltava `--silent`, e `--disable-interactivity` desliga os prompts *do winget*, não a janela do instalador — que ficava esperando um clique em "Close" e devolvia falha mesmo tendo instalado. A chamada de remoção já passava `--silent`; a de instalação não. Somado a isso, `--accept-license` aceita o contrato **na instalação** em vez de no primeiro uso, e `3010` passa a contar como sucesso-com-reinício
- **A integração Docker↔WSL não subia sozinha.** Agora é ligada em `%APPDATA%\Docker` (com o questionário de boas-vindas suprimido junto) e o Docker é reiniciado. Formato interno, sem contrato público: arquivo ausente, JSON inválido ou esquema desconhecido não derrubam nada
- **`git pull --ff-only` matava a instalação num clone divergente.** Recusar está certo; morrer ali não. Sem trabalho seu dentro, realinha e **diz** que realinhou; com trabalho dentro, para nomeando os arquivos
- **Desinstalar sem nada instalado abortava** e deixava o Docker Desktop instalado, mesmo com `-RemoveDeps`. Delegado, a ausência deixa de ser erro, e o orquestrador só para quando os **dois** escopos estão vazios

#### Diziam coisas que não eram verdade

- **O log era acumulado entre execuções**: o "last lines of…" mostrou um `winget uninstall` bem-sucedido de **outra** execução, logo abaixo de "Nothing was removed."
- **"Ollama preserved"** era dito sem olhar a máquina — o Ollama tinha sido removido pelo usuário antes de instalar
- **O volume de dados era apagado em silêncio**, sem linha própria, embora o plano o listasse em destaque
- **O `--doctor` dizia "package manager: none"** em qualquer macOS, com Homebrew instalado
- **"has local changes"** nunca dizia *qual* mudança — e o que travava a pasta era um `.env.backup` do próprio instalador

#### Onde os documentos ficam, no Windows

- **Eles nasciam em `/root/Documents` dentro da distro**: invisíveis no Explorer e reféns de um `wsl --unregister`. Agora ficam na pasta **Documentos do Windows**, com `-ProjectsRoot` para escolher outra
- A conversão do caminho é **léxica** (`C:\x` → `/mnt/c/x`) e o resultado é **conferido**: numa reinstalação o `wslpath` devolveu um ponto de montagem do Docker Desktop no lugar da pasta

#### A tela

- **Um trilho só, atravessando a fronteira**: a largura, o `TERM`, o `COLORTERM` e a cor-sob-captura viajam na delegação. Sem eles o lado Linux se degradava em silêncio — réguas brancas, desinstalação inteira sem cor
- **Divisória do handover** (`├┄┄ handover ┄ Linux installer ┄┄`), tracejada e rotulada, com a mesma rampa
- **A régua do Windows varre a rampa do produto**, como a do `install.sh` — antes eram três cores fixas de 16
- **Rastro da animação, mojibake, `[?]` na barra, caixa vazando, calha furada em nove pontos e o log do desinstalador do Docker por cima do spinner** — todos corrigidos, cada um com guarda
- **Falha de rede não explode mais na cara de quem instala**: é reconhecida pelo que a ferramenta escreveu e explicada em três linhas, dizendo que reexecutar é seguro

#### Bancada

- **196 asserções no bash** (eram 116) e **~200 no Windows** (eram 73). Toda guarda nova foi provada contra uma cópia mutada — se não reprova o defeito, não entra
- Guardas locais para o que só o CI enxergava: substantivo plural em nome de função (`PSUseSingularNouns`), aspa não fechada (que quebra o *parse* e aponta para a linha errada) e variável local sombreando glifo global (`$ok` vs `$OK`, que já mordeu duas vezes)

---

## [0.55.0] - 2026-07-27

Ciclo aberto por um `-Uninstall -RemoveDeps` rodado numa máquina Windows 11 real. O log mostrou que **o plano que o usuário confirma descrevia apenas o lado WSL**, enquanto o lado Windows agia depois, sem plano e sem confirmação. Ao ler os dois instaladores por inteiro apareceu um defeito pior, que ninguém tinha visto.

### Corrigido

- **CRÍTICO — cancelar o plano não impedia a remoção do Docker.** O `install.sh` devolvia `0` ao responder "n" (`return 0` no caminho de cancelamento) e o `install.ps1` **nunca lia o código de saída** da delegação. Resultado: quem cancelava tinha o Docker Desktop e o Ollama removidos assim mesmo. Agora o lado Windows exige **as duas provas** — código de saída 0 **e** a linha-sentinela `ATLASFILE_UNINSTALL: confirmed` — antes de encostar em qualquer pacote. Não existe documentação oficial de que o `wsl.exe` propague o código de saída do comando Linux; com a sentinela, um código engolido faz o instalador **falhar fechado** em vez de ler silêncio como confirmação
- **O plano dizia "Docker preserved" segundos antes de apagar o Docker.** As duas frases eram verdadeiras no próprio escopo: dentro do WSL a CLI vem da integração do Docker Desktop, então o manifesto da distro diz `preexisting`, enquanto o do Windows dizia `created`. Os fatos do outro lado da fronteira agora viajam como dado (`--host-extra docker=created,…`) e são renderizados no **mesmo plano, antes da mesma confirmação**
- **O Ollama não aparecia em nenhuma das duas seções do plano** e ainda assim era removido. Com a chave ausente do manifesto, os três ramos da decisão falhavam e o resultado era silêncio. Chave desconhecida passa a produzir uma frase — e só quando a ferramenta está de fato na máquina, medido antes de afirmar
- **A pasta de instalação nunca era removida.** `.gitignore` tinha `backend/runs/config/api_keys.json` numa linha só, aparentemente duas entradas fundidas, que **não ignorava nenhuma das duas** (medido com `git check-ignore`). Como o one-liner recomendado usa `--enable-auth`, o instalador gravava `config/api_keys.json` não rastreado dentro do clone, o guard de "local changes" disparava e a remoção era recusada em **toda** instalação feita pelo caminho documentado
- **No Windows, a pergunta do Ollama aparecia duas vezes.** A decisão de projeto — Ollama vive do lado Windows, os containers o alcançam por `host.docker.internal` — existia só num comentário. Sem `--no-ollama` o `install.sh` reencontrava as condições de oferecer dentro da distro (onde `command -v ollama` naturalmente falha, porque o binário está no outro sistema operacional) e um "sim" puxava vários GB de duplicado
- **Dois vereditos finais, o primeiro falso**: o `install.sh` anunciava "AtlasFile removed" enquanto o lado Windows ainda tinha pacotes para remover. Agora quem delega tem a última palavra (`--delegated`)
- **Dois banners diferentes na mesma tela.** O estático do `install.ps1` era arte escrita à mão — luas em posições que a animação nunca produz e uma linha de texto a mais; o quadro final ainda pintava cauda de cometa (proibido e testado do lado bash); e `AF_ORBIT_START` era 2 contra 10, o que trocava as duas luas de lugar. O banner estático passa a **ser** o quadro final da própria animação, e o `install.sh` não desenha quando é chamado por delegação
- **Falha do Ollama sem diagnóstico**: o `winget` saía com `-1978335107` e a única orientação era "remove it from Settings > Apps". Agora o pacote é **verificado antes** (`winget list -e --id`) e, na falha, saem o código e as últimas linhas do log

### Adicionado

- **`--doctor` / `-Doctor`** — diagnóstico read-only, que não existia e era exatamente o que faltou na máquina real. No Linux: sistema, pré-requisitos com versão, o manifesto chave a chave, o estado da instalação, a stack, as portas e a pasta de documentos. No Windows: elevação, WSL com **prova de execução**, daemon do Docker, integração com o WSL, Ollama, manifesto — e então **delega o lado Linux ao mesmo `install.sh`**. Um comando para a máquina inteira, terminando num placar e saindo `!= 0` quando algo está quebrado
- **`--plan-only`** (o dry run do uninstall) e **`--dry-run` / `-DryRun`** (o que uma instalação faria aqui). Nenhum dos dois instala coisa alguma — nem do lado Windows
- **`--verbose` / `-Verbose`** devolve a saída das ferramentas para a tela
- **`-Dir` e `-Force` no `install.ps1`**, que só existiam do lado bash
- **Códigos de saída do mundo Windows**: `1602` quando o usuário cancela e `3010` quando o desinstalador do Docker agenda arquivos em uso para exclusão no próximo boot — sucesso com reinício pendente, não falha
- **Relatório da execução** em `~/.atlasfile/last-run.log` e `%LOCALAPPDATA%\AtlasFile\last-run.log`, com tempo por passo: o log guardava a saída das **ferramentas**, e o que o instalador fez não ficava em lugar nenhum

### Mudado

- **UX dos dois instaladores no padrão do nosso `mac_env_install.sh`**, em ANSI puro dos dois lados: calha vertical (`│`) que transforma uma lista de linhas soltas em fluxo, régua de fase varrida com a rampa do produto, barra de fase viva apagada antes de cada mensagem, placar no fim e "próximos passos" **condicionais ao que de fato aconteceu** (grupo docker, Ollama, Docker Desktop recém-instalado) — antes eram sempre as mesmas três linhas. O `gum` ficou de fora de propósito: baixa binário de terceiro a cada execução e não tem equivalente no PowerShell, o que recriaria a divergência que este ciclo está consertando
- **`curl` endurecido** (`--proto '=https' --tlsv1.2 --retry 3`) e `trap` global restaurando o cursor em qualquer saída

### Testes

- Bancada bash: **79 → 119** asserções. Bancada PowerShell: **73 → 100+**, com o stub do `wsl` agora **atravessando a fronteira** (devolve plano, fatos e sentinela). Sem isso o `install.sh` nunca rodava na bancada e o plano não existia em asserção nenhuma — a razão estrutural de o defeito ter passado
- Cenários novos que travam o defeito crítico: lado WSL cancelou → **nenhum** `winget uninstall`; código de saída engolido → falha fechada; plano ilegível → para antes de tocar em qualquer coisa
- `check_consistency.py` ganhou **paridade de arte** (órbita, cometa, rampa, hex das quatro luas, wordmark, frase, índice de repouso) e **paridade de UI** (cada primitiva existe nos dois arquivos) — as duas provadas numa cópia isolada, injetando as divergências e conferindo que reprovam
- CI: guarda de `Invoke-Native` estendida ao `Invoke-NativeCapture`; a do `Stop-Installer` aceitava só código de um dígito e reprovava `1602`; e um passo novo cobra que o git ignore o que o instalador gera — teria pego o `config/api_keys.json` na origem

### Removido

- **O Ollama saiu da instalação** (`--with-ollama`, `-WithOllama`, `--ollama-model`, `--no-ollama`). Puxar um modelo são vários GB dentro de uma instalação que precisa ter duração previsível — não dá para prometer minutos e entregar um download indeterminado. De quebra, o defeito de o Ollama viver em **dois sistemas operacionais ao mesmo tempo** deixa de existir por construção. O painel final ensina a habilitá-lo depois, em um comando, e a mensagem muda conforme ele já esteja ou não na máquina. **A reversão continua inteira**: um Ollama instalado por versões anteriores segue registrado no manifesto daquelas instalações e segue sendo revertido por `--uninstall --remove-deps`

### Corrigido — auditoria dos registros de ida e volta

Sete lacunas encontradas ao auditar os manifestos, todas verificadas no código:

- **CRÍTICA — o uninstall no Windows podia olhar para o `$HOME` errado.** `$script:WslUser` só era decidido na fase 1, que roda **depois** dos blocos `-Uninstall`, `-Doctor` e `-DryRun`: neles ele estava sempre vazio e o `wsl -e` rodava como usuário **padrão** da distro. Uma instalação feita como root — exatamente o que acontece quando o próprio AtlasFile instala o WSL com `--no-launch` — morava em `/root/AtlasFile` e `/root/.atlasfile`, e a desinstalação não achava nem instalação nem manifesto: **nada era revertido**. Funcionava por sorte em distro cujo usuário padrão ainda é root. O manifesto do Windows passa a gravar `wsl_user` e `install_dir`, e os três blocos recuperam a identidade antes de falar com o outro lado
- **A garantia do `install_dir` não existia.** O CHANGELOG da v0.54.0 prometia que a pasta só seria apagada "se ela bater com o `install_dir` registrado"; a chave era gravada e **nunca lida**. Agora é lida, e uma pasta que não bate é preservada com o motivo na tela
- **Chave de API viva ficava em disco.** `api_keys_file` e `env_file` eram gravadas e nunca consultadas: num clone preexistente — sempre preservado — o `config/api_keys.json` criado por `--enable-auth` sobrevivia à desinstalação
- **O `.env` do usuário era reescrito sem backup.** Passa a haver cópia datada antes da primeira alteração, registrada no manifesto e citada no plano. É o único mecanismo do nosso `mac_env_install.sh` que faltava aqui
- **Artefato órfão quando o instalador morre no meio.** Cada `ensure_*` grava `pending` **antes** de tentar. `pending` nunca autoriza remover — não dá para provar que criamos —, mas vira uma frase no plano: *"o instalador foi interrompido instalando isto; preservado, remova à mão se não for seu"*. Antes o artefato ficava sem digital nenhuma e a execução seguinte o registrava como `preexisting`
- **A distro baixada por nós não era registrada.** `wsl --install --no-launch` traz ~500 MB de Ubuntu e só gravava `wsl created`; o plano falava do **recurso** e ficava calado sobre a distro
- **Nada garantia que chave gravada virasse decisão.** O `check_consistency.py` passa a cobrar que toda chave do manifesto seja lida, nos dois instaladores — a guarda que teria pego as três chaves mortas acima

### Mudado — `--dry-run` unificado

- **`--dry-run` é o nome público e compõe**: sozinho mostra o **retrato** da máquina (o que ele vê) e o plano de instalação; com `--uninstall`, o plano de remoção — nos dois casos sem tocar em nada. `--plan-only` continua existindo como flag de **protocolo** entre os dois instaladores e saiu da ajuda
- No Windows, `-Uninstall -DryRun` caía no plano de **instalação** porque o bloco do `-DryRun` vinha antes do `-Uninstall` (achado pelo CI, no cenário escrito para essa propriedade)

### Corrigido — o que o teste real no macOS achou

Seis defeitos, todos na **mesma pergunta** (a pasta de projetos) ou no caminho dela, e nenhum alcançável por bancada sem terminal de verdade:

- **A tecla de seta corrompia a resposta e derrubava a instalação.** `read -r` não tem readline, então cada seta virava byte de escape *dentro* da resposta. O `.env` recebeu `PROJECTS_HOST_ROOT=\033[C\033[D…` e o `${PROJECTS_HOST_ROOT}:/projects` do compose matou a instalação com *"service api refers to undefined volume :"*. Conferir o caminho antes do Enter quebrava a instalação
- **Esse `.env` era relido na execução seguinte, sem validação.** O `.env already exists — preserved` pegava o lixo da primeira tentativa e nem chegava a perguntar. Havia **quatro** origens para esse caminho e só uma estava blindada; agora existe **um portão** por onde todas passam
- **`~` não expandia**: `mkdir -p "~/Desktop/x"` criaria uma pasta chamada literalmente `~` no diretório atual
- **`2>/dev/null` no `read -e` apagava a digitação da tela.** O readline escreve o eco no **stderr** — silenciá-lo deixava o cursor parado depois dos dois-pontos. Isolado sob pty com três experimentos antes de tocar no código
- **O backspace comia o próprio prompt.** Impresso por um `printf` separado, o readline não sabia que havia texto na linha e redesenhava desde a coluna 0. Agora o prompt vai *para* o readline (`-p`), com os escapes de cor marcados em `\001..\002` para ele não contar bytes invisíveis como largura
- **Cinco mensagens da fase 3 ainda saíam fora da calha.** A bancada passa a varrer o fonte inteiro: nenhum `printf` de mensagem pode existir sem a calha

Mais: a barra de fase aparecia como `fase 0/5` nos fluxos que não têm fase (uninstall, doctor, dry-run), e a linha-sentinela vazava para a tela de quem digitou o comando em vez de ficar só no protocolo entre os dois instaladores.

**Bancada: 116 → 152**, incluindo um teste que dirige um terminal real (pty), digita, apaga com backspace e cobra três coisas: o valor final, o prompt desenhado uma única vez e o eco na tela.

### Compatibilidade

- **As flags do Ollama viraram depreciadas, não desconhecidas.** O site publica `--with-ollama` e `-WithOllama` em quatro lugares e é repositório separado: responder "Unknown flag" a um comando que nós mesmos publicamos quebraria o usuário na primeira linha — no PowerShell, com erro terminante, sem nem mostrar o banner. Elas são aceitas, avisam e a instalação segue

### Verificado em máquina real (macOS)

Instalação pelo one-liner do site, completa e funcional (API `{"status":"ok"}`, UI 200, 5 containers). **Cancelar a desinstalação não removeu nada** — 5 containers de pé, pasta, volume e Docker/git/Ollama intactos. Desinstalação confirmada removeu só o que foi criado, preservando o Docker (a stack de desenvolvimento divide o mesmo daemon), o Ollama (não foi este instalador que o instalou) e os documentos. Num clone preexistente, o `.env` e o `config/api_keys.json` criados pelo instalador foram removidos individualmente — a chave de API não fica em disco.

### Pendente de prova real

O E2E na máquina Windows: instalar pelo one-liner, conferir que o plano cita Docker/Ollama/WSL nas seções certas, **responder "n"** e verificar que nada foi removido, repetir com "y". Nenhuma VM aqui roda Docker, então essa continua sendo a única prova que falta.

---

## [0.54.0] - 2026-07-26

### Adicionado

- **`install.sh --uninstall` — o instalador sabe se desinstalar** revertendo apenas o que ele criou. Antes de agir imprime um plano em texto com duas seções (o que será removido / o que será preservado, com o motivo) e espera confirmação; `--yes` para modo não-interativo
- **Manifesto de instalação** em dois escopos, porque os escopos são diferentes: `~/.atlasfile/host-prereqs` (dependências do sistema — há um Docker por máquina, gravado no instante em que cada `ensure_*` decide, de modo que uma instalação que falhe depois de instalar o Docker não perca o registro) e `<instalação>/.atlasfile-install-manifest` (fatos daquela instalação). Valores `created`/`preexisting`; `created` nunca é rebaixado numa reinstalação e chave ausente lê como `preexisting` — na dúvida, preserva
- **Volume de dados sem default**: o uninstall pergunta explicitamente antes de apagar o índice (`--purge-data` / `--keep-data`; headless exige uma das duas). Documentos e journal ficam em disco e não são afetados
- **Guardas de segurança do uninstall**: stack removido via `docker compose down --rmi local` rodado de dentro da instalação (o compose resolve o projeto sozinho, respeitando `COMPOSE_PROJECT_NAME`) e **nunca** por nome de container, já que os nomes `atlasfile-*` são fixos e podem ser de outra instalação; a pasta só é apagada se o manifesto disser que o instalador a criou, se ela bater com o `install_dir` registrado e se não houver alteração local (`--force` para forçar) — um clone de desenvolvimento é sempre preservado; a pasta de projetos nunca é apagada (só um diretório criado pelo instalador e ainda vazio, via `rmdir`, que se recusa a agir se algo tiver aparecido); Docker é preservado se sobrar qualquer outro artefato AtlasFile na máquina; Homebrew nunca é removido automaticamente
- **`--help` de verdade** nos dois instaladores, no estilo do mac-env-setup (Uso, opções por seção, variáveis de ambiente), e `make uninstall`
- **Banner animado no terminal** com a identidade real do produto (`CompanionOrb`): ignição do orbe linha a linha, duas luas em órbita keplerianas opostas com profundidade (glifo menor e cor mais escura no lado de trás) e um cometa ejetado de trás do orbe que **acende o wordmark** ao passar por cima. ~1,1 s no total. A frase de chamada agora é a mesma do site: *Your documents have gravity.*
- **Guardas do banner**: cor só com `NO_COLOR` ausente e TTY; rampa 24-bit só quando o terminal anuncia `COLORTERM`, caindo na rampa quente de 256 cores em vez disso; sem animação em CI, sem `tput` ou em terminal com menos de 60 colunas; `trap` restaura o cursor se você interromper com Ctrl-C

### Corrigido

- **`--help` não funcionava sob `curl | bash`** — ele fazia `grep '^#' "$0"`, e nesse caminho `$0` é `bash`: a saída era só `grep: bash: No such file or directory`. Agora é um heredoc, idêntico nos dois modos de entrega
- **`install.ps1` não fazia parse no Windows PowerShell 5.1 quando salvo como arquivo** (o modo documentado no bloco de parâmetros): UTF-8 sem BOM é lido como ANSI e o `✔` vira uma sequência com aspa embutida que encerra a string, cascateando erros de sintaxe. Medido numa VM limpa que **adicionar BOM conserta o `-File` mas quebra o `irm | iex`** (a string passa a começar com U+FEFF e o `#` deixa de ser o primeiro caractere), então o arquivo agora é **ASCII puro** e monta os glifos por code point — a única forma que sobrevive aos dois caminhos, e também a um servidor que omita `charset=utf-8`
- **`install.ps1` morria com stack trace numa máquina sem WSL** — justamente o cenário para o qual ele existe. `wsl.exe` acompanha o Windows mesmo sem a feature instalada, então `Get-Command wsl` sempre encontra; e `wsl --status` escreve no stderr e **sai com código 0**, o que com `ErrorActionPreference = Stop` virava `NativeCommandError` terminante. A detecção passa a olhar o conteúdo da mensagem (normalizando o UTF-16 do `wsl.exe`, cujos NULs faziam todo `-match` falhar em silêncio) e degrada com instrução acionável
- **`install.ps1` abortava quando `$env:LOCALAPPDATA` é nulo** (acontece em sessões não interativas): `Join-Path` lançava e derrubava a instalação inteira antes de qualquer passo
- **Shim do grupo docker no Linux estava quebrado**: `sudo command docker "$@"` depende de um executável `command`, que **não existe** no Debian/Ubuntu (verificado em `ubuntu:24.04`) — todo `docker ...` seguinte falharia com `sudo: command: command not found`. O binário real passa a ser resolvido antes do shim
- `make test-installer` voltou a passar com shellcheck instalado (o `main` estava vermelho por duas advertências no shim acima e por uma constante órfã)

---

## [0.53.0] - 2026-07-25

### Adicionado
- **Chats e eventos de custo deixam de viver só no índice** (incidente real do dia: dois resets de volume levaram o período inteiro, sem origem para reconstruir): journal local-first em `_ATLASFILE/journal/` — eventos (`chat_usage`, `classification_usage`, `training_usage`) em NDJSON append-only por mês, e sessões de chat em snapshot atômico por arquivo. O journal é gravado **antes** do índice: o disco vira a fonte durável e o índice, a projeção consultável. Falha de escrita nunca derruba a operação; linha corrompida por append interrompido não inutiliza o journal.
- **Restauração automática no reconcile**, com guarda: só age em índice **vazio** (o cenário de perda de volume) e jamais sobrescreve índice vivo; id determinístico por conteúdo torna a reimportação idempotente. Sessão apagada de propósito some do journal — a restauração não ressuscita o que o usuário excluiu. Os números entram no resumo do reconcile e contam como correção (o run automático anuncia). **E2E do incidente**: sessão criada → índice de sessões apagado → reconcile → sessão de volta.

## [0.52.0] - 2026-07-25

### Adicionado
- **A triagem passa a dizer a causa REAL de "sem texto extraível"** (item do roadmap registrado na v0.48.0): a mensagem era sempre "(OCR vazio)" — genérica e às vezes **falsa**, porque o OCR podia nem ter rodado. O `ExtractionResult` já sabia a resposta e ela morria no extrator; agora 7 causas estáveis chegam à UI nos dois idiomas — imagem embutida sem texto legível, imagem sem texto, PDF escaneado ilegível, OCR indisponível no servidor, formato sem extrator, arquivo corrompido, documento vazio. Precedência decidida com critério: OCR indisponível vence "só imagem embutida" (com o motor fora do ar, culpar a imagem mentiria).
- **Toggle de idioma na sidebar** (pedido do usuário): ícone na mesma fileira do tema e do colapso, com as mesmas classes. São dois idiomas — o clique alterna direto, como o tema cicla, e o tooltip diz o destino. Complementa o seletor de Configuração e o das telas de primeiro acesso.

## [0.51.1] - 2026-07-25

### Mudado
- **O link "Observabilidade" cai direto no dashboard "AtlasFile — Operação"** (follow-up aprovado pelo usuário), em vez do Home. Como o auto-import roda em background com retry no boot, um deep link para um id ainda inexistente mostraria "Dashboard not found" — pior que o Home: o endpoint consulta o saved object antes (uma request local, na mesma sessão recém-criada) e cai no Home se não existir. Sem sessão, o destino continua sendo o Home.

### Corrigido
- **SSO robusto a sessão dividida e a cookie renomeado** (pergunta do usuário sobre risco futuro): o endpoint passa a repassar **todos** os cookies devolvidos pelo login, em vez de procurar `security_authentication` pelo nome. Cobre os dois modos de falha mais prováveis — o security plugin divide sessões grandes em `security_authentication_1/_2/…` e o nome pode ser trocado por `opensearch_security.cookie.name`. Os riscos remanescentes (proposta de Origin-Bound Cookies no Chromium; mudança do `/auth/login` numa major futura) degradam para a tela de login, que é o comportamento anterior — nenhum caminho quebra a aplicação.

## [0.51.0] - 2026-07-25

### Adicionado
- **Link "Observabilidade" abre o Dashboards já logado** (achado do usuário, duas ocorrências: o link caía na tela de login e a senha mora no `.env`): novo `GET /api/observability/open` — a API autentica no OpenSearch Dashboards pela rede interna com a senha que já tem no ambiente e devolve o cookie de sessão no redirect. **A senha nunca chega ao browser, à URL ou ao histórico**; o que trafega é o mesmo cookie que um login manual geraria. O truque que sustenta isso foi medido no Chrome real antes de projetar: cookies ignoram porta, então um cookie do host vale entre a API (:8000) e o Dashboards (:5601). Guardas explícitas: com `DASHBOARDS_PUBLIC_URL` em outro domínio o cookie não valeria e o endpoint **nem tenta logar** (redireciona para o login normal); falha de login, resposta sem cookie ou Dashboards fora do ar degradam do mesmo jeito, nunca em erro na cara do usuário. A API key entra sozinha no link (mesmo helper de SSE/downloads), então funciona com `API_AUTH_ENABLED`. Validado ao vivo: cookies limpos → clique → Home do Dashboards sem login.

## [0.50.5] - 2026-07-25

### Corrigido
- **Dashboard volta a viver depois de um rebuild do índice** (pergunta do usuário: "por que o dashboard está quase vazio mesmo com 108 documentos reindexados?"): o reconcile zerava `ingested_at`/`processed_at` na mão e o index pattern do dashboard usa `ingested_at` como time field — **todo painel temporal ficava cego para sempre** (medido: 0 de 108 docs com data). Quem reconstruísse o índice pela reconciliação — o fluxo de recuperação que o produto promove — perdia o dashboard inteiro. Agora os **fatos do evento original** são restaurados das fontes que sobrevivem em filesystem (`_PROFILE/ingest_history.json` + metas do `_TRIAGE_REVIEW/resolved`, com o prefixo `YYYYMMDD__` do nome canônico como terceira fonte só para data), com merge campo a campo e sem inventar valor quando não há fonte. Medido: `ingested_at` 0 → 108/108 (83 na janela default de 30 dias).
- **Modo do classificador e entidades repostos no rebuild**: mesma família do bug acima — campos que o reconcile não deriva do disco e não repunha (medido: `classifier_mode` 0/108 → **73/108**, 69 bootstrap + 4 sparse_logreg; os demais não têm fonte no filesystem — o `ingest_history` é FIFO de 50 entradas de scan — e ficam honestamente vazios em vez de receber valor inventado).
- **Saúde de embeddings deixa de mentir**: `index_document_chunks_embeddings` devolvia `up_to_date` sem gravar a flag; como o delete do doc principal não apaga os vetores, todo doc reindexado perdia o `embedding_status` e nunca o recuperava (0/108 com 10k+ vetores presentes). Agora a flag é regravada nesse retorno **e** reposta no caminho de skip do reconcile quando o doc a perdeu num ciclo anterior — em ambos os casos com um `update`, sem recomputar embedding nenhum. Medido: 0 → **108/108**.
- **Backfill sem reescrita infinita**: o caminho incremental reindexa só quando o campo está ausente no índice **e** disponível na fonte — e os campos restauráveis entraram no `_source` do `get` do skip, senão pareceriam sempre ausentes (teste dedicado à guarda; prova ao vivo: segundo reconcile seguido pula os 108 docs).

## [0.50.4] - 2026-07-25

### Corrigido
- **Faxina automática do build cache** (pergunta do usuário: "como isso fica com o usuário final?" — resposta: nunca é tarefa dele): `make docker-up` e `make docker-update` agora rodam `docker builder prune --keep-storage=2GB` após o build (caso real: 36GB acumulados em rebuilds derrubaram a ingestão por disco cheio; teto de 2GB ≈ 2 ciclos completos, um ciclo medido gera ~1GB).
- **Multi-checkout documentado no `.env.example`**: dois clones do repo na mesma máquina derivam o MESMO projeto compose — mesmos containers e mesmo volume do OpenSearch, com os dois `.env` disputando a senha do mesmo índice (a causa factual das quedas recorrentes "instância offline": 401 no boot de quem tem a senha que não bate). Solução: `COMPOSE_PROJECT_NAME` próprio no clone de desenvolvimento.

## [0.50.3] - 2026-07-25

### Corrigido
- **Sugestões de alias voltam a sumir na hora após aprovar/dispensar** (bug report do usuário; backend sempre aplicou — a UI é que não refletia): o refetch disparava e ficava pendurado porque o GET das sugestões re-extraía TODOS os docs resolvidos a cada request, e o PDF escaneado de 46 páginas que entrou no triage_resolved no teste da aura passou a custar ~60s de OCR por chamada (medido: 61,8s no *080 vs 0,66s em projeto leve). Fix: cache persistente do excerpt por sha256 (identidade de conteúdo, já no meta) em `_PROFILE/feature_text_cache/` — medido 62,5s na primeira chamada (aquece) e **35ms** nas seguintes (1.780×); nome do arquivo recomposto por chamada (mesmo conteúdo re-resolvido sob outro nome não herda o antigo); falha do cache degrada para extração ao vivo. E2E no browser real: linha some em ~1s após a ação.

## [0.50.2] - 2026-07-25

### Mudado
- **Widget de upload sem pilha de concluídos** (sugestão do usuário após lote de 18 arquivos): item enviado colapsa numa linha-resumo ("✓ N enviados") — padrão de gerenciador de upload; em voo e aguardando seguem individuais e **erro nunca colapsa** (fica visível com a mensagem até fechar). A fase do scan volta a ser protagonista no widget. Validado ao vivo: upload de 2 arquivos pelo picker → "2 enviados" no lugar de duas barras.

### Corrigido
- **Key React duplicada no histórico de processamentos** (flagrada pelo próprio teste em lote): dois DUPs do mesmo documento no mesmo scan compartilham timestamp e doc_id — linhas podiam sumir/duplicar; índice do item no lote desempata.

## [0.50.1] - 2026-07-25

### Corrigido
- **UI agora reage a runs iniciados pelo servidor** (achado do usuário no primeiro teste do auto-ingest: arquivo sumiu da inbox mas widget/toast/listas só apareceram após reload): o `useSseChannel` só abria SSE/poll quando já via `running=true` — run disparado pelo backend era invisível, e run curto (DUP ~3s) terminava entre dois polls sem re-disparar o `onFinished`. Fix no canal, para os três consumidores: poll de vigia em idle (`idlePollMs` — ingest 3s, reconcile 5s; GET de dict em memória), `runStamp` (mudança de `last_run_finished_at` em idle = run inteiro perdido → dispara término mesmo assim) e `meta.observedTransition` (boot com snapshot de run antigo não anuncia nem invalida nada). Widget e toast keiados no stamp. Validado ao vivo no browser: página aberta, `cp` pelo host, toast do auto-ingest aos ~11s sem reload.

## [0.50.0] - 2026-07-25

### Adicionado
- **Auto-ingest: a inbox processa sozinha** (pergunta do usuário: "se o widget aparece sozinho, pra que o botão?"; fato descoberto: `watcher.py` era código morto — auto-ingest de filesystem nunca existiu): watcher por projeto com escuta ampla (medido no container: VirtioFS entrega criação de arquivo do host como `modified`, o handler antigo de `on_created` perderia tudo) + quiescência de 4s + guarda de estabilidade de 5s (OneDrive sincronizando não é ingerido pela metade) + sweep de 60s (cobre WSL2 sem inotify, arquivos caídos com a API desligada e projetos novos) + anti-loop de falha (sobra na inbox só re-tenta se mudar). `AUTO_INGEST_ENABLED` desliga em manutenção. Lock real no scan (a corrida check→set do flag `running` foi fechada).

### Mudado
- **Widget global é a superfície única de processamento**: a fase real do scan (SSE) aparece dentro do widget do portal — inclusive em runs do auto-ingest, sem upload nenhum — com projeto, barra, contagem e arquivo; o monitor inline do card do Painel e o spinner genérico saíram. 409 no scan pós-upload virou aviso honesto ("auto-ingest processa em seguida"), não erro.

### Removido
- **Botões "Processar INBOX" e "Reconciliar INDEX"** (decisão do usuário, premissa "o sistema roda sempre reconciliado" — que JÁ era verdade: auto-reconcile de 600s com o mesmo escopo do botão): fica a linha "Última reconciliação" com o escape hatch discreto "Reconciliar agora" (mesma semântica de escopo da v0.44.0). Run automático de reconcile só anuncia quando CORRIGIU algo — transparência sem ruído a cada ciclo; run manual sempre anuncia. `InboxScanCard` deletado; constante órfã `auto_scan_on_startup` removida.

## [0.49.0] - 2026-07-25

### Adicionado
- **OCR de imagens no PPTX roda SEMPRE, não só no deck-"envelope"** (pergunta do usuário sobre a v0.48.0; decisão de custo-benefício: só PPTX, onde imagem É conteúdo — docx/xlsx seguem só-envelope): shape PICTURE de cada slide passa por tesseract com âncora exata `slide:N:image:M`, texto da imagem entra após o texto nativo do mesmo slide. Bônus do caminho por `slide.shapes`: logos herdados do master/layout nem aparecem — timbre não paga OCR. Corte de ruído **medido, não arbitrado**: 40 imagens de 12 decks reais do corpus → logos OCRizam para 0–14 chars, diagramas para 513+; corte em 85 (média geométrica dos extremos), sem efeito no modo envelope (onde OCR fraco é o único sinal). WMF/EMF (PIL não abre) pulados por imagem. Validado no deck real de sistemas: 2 diagramas de topologia viraram chunks pesquisáveis, 2 ruídos filtrados.

## [0.48.0] - 2026-07-25

### Adicionado
- **OCR de imagens embutidas em Office "envelope"** (caso real na instância: DOCX com zero texto próprio e o scan das atas colado como PNG único saía "sem texto extraível" com confiança 0, sem o sistema jamais tentar OCR): quando docx/pptx/xlsx não têm NENHUM texto nativo, o extrator agora roda tesseract (mesmo motor do PDF escaneado, por+eng) sobre as imagens do pacote (`word/media/*`, `ppt/media/*`, `xl/media/*`) — o envelope legível passa a classificar normalmente. Cap de 10 imagens (decks de ícones não viram fatura de OCR), nunca silencioso (`embedded_images_ocr_capped` no metadata); documento com texto próprio não paga nada; contadores `embedded_images_found/ocr` ficam no metadata como insumo para a UI dizer a causa real. Validado no docx original que motivou o item: `ok_ocr`, 1.698 chars legíveis. Cobre a família moderna `.xlsx/.xlsm/.xltx/.xltm`; legados OLE2 (.doc/.xls/.ppt) registrados no ROADMAP com gatilho. 7 testes novos com Tesseract real.

## [0.47.0] - 2026-07-25

### Adicionado
- **Sugestão de document_type pelo LLM, governada** (decisão do usuário após o caso real do gpt-5 respondendo 'outro'): o prompt **bane a sentinela 'outro'** (omissão honesta + justificativa no lugar); o tipo do LLM só é APLICADO se existir na taxonomia do profile (espelho da validação que o business_domain sempre teve); valor desconhecido vira `llm_proposed_document_type`, visível ao revisor. Cinto e suspensório: rótulo sem pasta configurada degrada para TRIAGEM com motivo legível, nunca FALHA do arquivo.
- **Medidor de contexto honesto**: janela REAL dos modelos Ollama via `/api/show` (fato medido: gemma4:12b = 262.144 tokens, o dobro do fallback de 128k; cache em processo, falha não vira tempestade de consultas); o percentual **recalcula na hora ao trocar de modelo** (antes ficava defasado até a próxima mensagem); tooltip do gauge documenta a janela e a heurística (≈4 chars/token).

- **Extensão banida como critério de tipo no prompt** (caso real: gpt-5 recusou classificar um diagrama .png "porque não corresponde às extensões esperadas"): a lista de tipos no briefing perdeu as extensões, e o prompt instrui explicitamente que document_type é GÊNERO pelo CONTEÚDO — um plano pode chegar em .docx, .pptx ou .png. Reverte com registro uma decisão da era pré-v0.39 (tipos-formato).

- **Histórico de processamentos com estado vivo** (achado do usuário): a linha do doc que está processando mostra o orb pulsante no lugar do ícone da decisão — o checkmark com o arquivo ainda em voo mentia; ao concluir, o ícone real volta automaticamente.
- **Card em espera na triagem explica o porquê** (achado do usuário): quando um doc cai na fila durante um processamento, os botões travados agora vêm com a linha "Aguardando — processando «arquivo»…" — antes pareciam quebrados, sem indicação nenhuma.

### Mudado
- **Aura de processamento com wow de verdade** (design iterado ao vivo com o usuário): o card focal ganha o **shader backdrop do blackhole (deriva + lente gravitacional)** atrás do conteúdo + borda accent em respiração + orb junto ao rótulo; o cursor da página vira "progress" enquanto processa. Véu global e bloqueio de cliques foram avaliados e DISPENSADOS após análise factual: os botões de decisão já desabilitam em todos os cards e o backend serializa por claim atômico (409 amigável) — redundância sem função. O progresso do ciclo do classificador também ganhou o lensing (sem véu — roda em background). Scrim local do Painel removido (o véu global o substitui); halo arco-íris e seu CSS removidos. Flagrado ao vivo: véu + 2 canvas + cursor em 100ms após o clique de aprovação. O item de arte do ROADMAP foi redefinido pelo usuário para este destino.

## [0.46.1] - 2026-07-25

### Corrigido (incidente do 429 — diagnóstico factual completo no plano)
- **Dedup só contra documento VIVO**: metas da triagem são trilha de auditoria e sobreviviam à deleção+reconcile — uma meta órfã em `rejected/` (deixada por um 429 antigo) envenenava todo re-drop do mesmo SHA ("DUP compliance" para doc vivo em TI, e DUP até para arquivo deletado). Agora: `pending/` só vale com o arquivo na fila; `resolved/` só com `final_path` existente; `rejected/` nunca (tombstone); hit do índice confere existência do path (janela deleção→reconcile). Deletar + reconciliar + re-drop = reprocessa.
- **Os dois 429 do OpenSearch com tratamentos opostos no indexador**: `circuit_breaking_exception` (heap, rajada) → retry com backoff 1s/2s; `cluster_block_exception` (disco/flood-stage, NÃO transitório) → sem retry e erro legível no histórico ("Disco cheio: índice em somente-leitura… libere espaço e rode Reconciliar"). Incidente real: VM Docker a 97% bloqueou o índice em silêncio.
- **Heap do OpenSearch: 1g default, parametrizável** (`OPENSEARCH_JAVA_OPTS` no .env): com 512m o parent breaker saturou de fato (`502.6mb > 486.3mb`, 72 trips) sob indexação com vetores kNN.
- ROADMAP: item de alerting ganha o monitor "disco acima do watermark / índice com bloco read-only" com o incidente como gatilho.

## [0.46.0] - 2026-07-25

### Adicionado
- **Combo rápido de modelos com curadoria** (proposta do usuário + benchmark ChatGPT/Claude.ai ~5 modelos expostos; Cursor = recentes + busca): os seletores do chat e da triagem deixam de listar o catálogo inteiro (68+ modelos) e mostram só **atual + usados recentemente + customs validados**, agrupados por provedor via `<optgroup>` nativo (labels sem a marca redundante — o grupo já diz o provedor). A opção **"Todos os modelos…"** e a engrenagem ao lado abrem o settings, onde o catálogo completo com busca sempre viveu; escolher lá alimenta os recentes (localStorage `atlasfile-recent-models`, cap 5 — referência dos players). Cascata provedor→modelo foi avaliada e rejeitada com critério: dobraria o custo da troca frequente entre favoritos de provedores diferentes.

### Mudado
- Seção "Estrutura de Layout" do perfil do projeto agora inicia **fechada** (pedido do usuário).

## [0.45.0] - 2026-07-25

### Adicionado
- **Estado vivo do modelo custom** (achado do usuário na v0.44.0): o selo "(validado por você)" era localStorage estático — agora o estado vai **no próprio seletor de modelo** (chat e triagem), na gramática do botão de raciocínio: **esmaecido = endpoint indisponível/desligado, borda/texto laranja = disponível**, detalhe e dica no tooltip ("Indisponível agora — Ollama parado? rode: ollama serve" / "ollama pull"). Sem ícone novo e sem LED de bolinha em botão (o botão do Telegram na toolbar adota a mesma gramática: esmaecido desconectado, laranja conectado). Re-verificação **a cada 15s — inclusive com a janela desfocada** (cenário real do teste: olhar o browser enquanto se desliga o Ollama no terminal) e ao refocar (staleTime 10s); nunca bloqueia nem desabilita a UI. A opção do select mostra só o valor; a proveniência (data da validação) vive no combobox de settings; storage evolui para `{value, validatedAt}` com migração dos legados. Design fechado por desenho anotado do usuário após 3 iterações ao vivo.
- **Link "Observabilidade" no Painel** (pergunta do usuário na v0.44.0): abre o OpenSearch Dashboards derivando a URL do host atual (`:5601`); env opcional `DASHBOARDS_PUBLIC_URL` para proxy/acesso remoto (a `DASHBOARDS_URL` interna da rede Docker não serve para o browser).
- **Reconcile varre órfão físico da triagem**: arquivo sem meta em `_TRIAGE_REVIEW/pending` (ex.: interrupção entre o move e a escrita do JSON) era invisível na UI e lixo em disco — agora vai para `rejected/` com meta sidecar (visível e reversível, nunca deletado), com guarda de idade de 600s para não varrer arquivo em trânsito da ingestão; contador no summary da reconciliação.

- **ESC fecha todos os modais** (achado do usuário: "Migrar/remover" e "Novo tipo/domínio" não fechavam): o suporte foi para a casca compartilhada (`ModalShell.onClose` → `useEscapeKey`) — os 5 modais sem ESC ganharam (criar taxonomia, migrar taxonomia, novo projeto, excluir report do ciclo, e os 2 de conflito de rótulos); única exceção deliberada e documentada é o modal de recuperação da raiz (fluxo bloqueante — fechar deixaria o app quebrado).
- **Caixa vazia removida do Profile**: a seção de Migração/Simulação era sempre renderizada — sem mudanças de layout, sobrava uma caixa órfã com o hint "No pending layout changes…" perdida entre as seções colapsáveis (parecia warning). Agora a seção só existe quando há mudança de layout.
- **Botões de ação de linha padronizados em toda a aplicação** (varredura completa a pedido do usuário): duas classes canônicas compartilhadas — `rowDeleteButtonClass` (vermelha, já existente) e a nova irmã `rowActionButtonClass` (accent, não-destrutiva, ex.: mover ⇄) — substituem o ✕ fantasma do editor de layout e o ⇄ espremido dentro da célula de confiança do histórico; **toda coluna de ação agora tem rótulo "Ação"/"Action"** (histórico, evolução do classificador, editor de template ×2, editor de layout). No histórico, o DE/PARA de reclassificação saiu da célula (truncava ilegível): célula limpa com marcador `*`, DE→PARA completo no tooltip e linha própria no bloco expandido "Detalhes da Classificação". Auditoria de CSS: zero classe órfã (2 falsos positivos são hooks de tema do Recharts, já documentados no próprio arquivo).

- **LEDs de status uniformizados** (regra de excelência de UI registrada a pedido do usuário): todo indicador de estado usa o padrão do LED "online" da sidebar — pontinho com glow (`--ok`/`--danger`; neutro sem glow) — incluindo o badge do botão do Telegram na toolbar do chat e o status do canal no modal de settings; bolinhas de legenda de gráfico (chaves de cor, não estado) ficam sem glow por decisão.

### Corrigido
- **Reingestão de arquivo já canônico não re-embrulha o nome** (caso real: `20260725__proj__20260320__proj__...__v01__v01`): a ingestão agora detecta a cauda `__vNN`, extrai o nome original embutido (cadeia de patterns com rejeição de resíduo por fatos do profile — data, project_id, domínios conhecidos) e restaura a linhagem de versão — reingerir vira v02 do mesmo título, não um v01 embrulhado.

## [0.44.0] - 2026-07-24

### Adicionado
- **Aliases por projeto**: aprovar sugestão do minerador agora escolhe o escopo — "Aprovar no projeto" (default recomendado: só o profile do projeto aprende; projetos novos não herdam) ou "Global" (template default + todos os profiles, comportamento anterior). API: `POST /api/taxonomy/aliases` ganha `scope` e `project_ref` (compat retro: default `global`); nova `add_project_aliases` em `taxonomy.py`.
- **`backend/scripts/trace_classification.py`**: bancada de diagnóstico do bootstrap — mostra por domínio/tipo quais aliases casaram (por campo), o que foi filtrado por colisão de léxico e a conta exata da confiança. Foi ela que diagnosticou o caso do kit marítimo.
- **Chave do cookie de sessão do Dashboards por instalação** (`DASHBOARDS_COOKIE_PASSWORD`): cookie de instância anterior vira redirect limpo de login em vez de 500 (a chave default era igual entre instâncias). Gerada pelo `install.sh` (só quando ausente) e pelo `make docker-up` (guard para quem atualiza via git pull); vai ao container como flag CLI porque a allowlist de env do entrypoint não cobre `opensearch_security.*` (verificado na imagem 2.17.1).

### Corrigido
- **Classificador: domínio não vence mais só por overlap com o vocabulário do TIPO**: todo doc classificado como `relatorio` nascia "operacoes 46%" por compartilhar o alias "status report", mesmo com zero evidência no documento (caso real do kit marítimo — o item do roadmap atribuía o sintoma ao √N, diagnóstico refutado pelo trace). Overlap tipo↔domínio agora só pontua com hit de conteúdo (nome/texto/entidades); sem evidência, cai em best-effort (0.05) e vai para triagem. Benchmark 62 docs: idêntico antes/depois (domínio 87.1%, tipo 93.6%, exact 82.3%) — zero regressão; thresholds mantidos com base em dados.
- **Escopo do reconcile explícito na UI**: o botão agora mostra "Reconciliar INDEX — {{projeto}}" (tooltip: sem limpeza global de órfãos; `cleanup_orphans=False` no endpoint por projeto) ou "— todos os projetos" (tooltip: inclui limpeza global). Antes os dois modos eram indistinguíveis no botão.

## [0.42.0] - 2026-07-23

### Adicionado
- **Dashboard interativo v2**: controles de filtro (projeto/domínio) no topo; **curva da taxa de auto-route** (TSVB `filter_ratio` — a métrica do classificador aprendendo com as correções); heatmap de ingestão domínio × tempo; custo LLM vira TOTAL (classificação + chat + treino) via index pattern combinado.
- **Uso LLM do chat achatado**: novo índice `atlasfile_chat_usage` (1 evento por chamada: provider, modelo, tokens, cache, custo, projeto, canal), gravado em `/api/chat` (web) e no fluxo de canais; falha na gravação nunca afeta a resposta do chat (testado). Resolve a limitação do custo aninhado em `usage_by_model` das sessões.
- Aprendizados de plataforma registrados no gerador: nunca setar `fields` no index-pattern (substitui o cache de campos inteiro); TSVB do fork 7.10 usa strings lucene em `filter_ratio`; heatmap hora×dia exigiria campo derivado na indexação (candidato futuro).

## [0.43.4] - 2026-07-23

### Corrigido
- **Número de versão congelado em 0.42.0**: o bump da v0.43.0 fez um replace sem assert que virou no-op silencioso (procurava "0.41.1" com o arquivo já em "0.42.0") e a cadeia inteira 0.43.x nunca tocou o `package.json` — o CHANGELOG avançou, a sidebar não. O código em si sempre acompanhou o main; só o rótulo mentia. Corrigido para 0.43.4 com verificação.

## [0.43.3] - 2026-07-23

### Adicionado
- **Tema escuro como default de fábrica do OpenSearch Dashboards** (identidade dark-first do AtlasFile): o auto-import define `theme:darkMode=true` — mas SÓ quando o usuário nunca mexeu no tema; escolha explícita (incluindo voltar ao claro) é respeitada em todos os boots seguintes (testado). Validado ao vivo na instância nova com screenshot do dashboard escuro.

## [0.43.2] - 2026-07-23

### Alterado
- **One-liner recomendado agora inclui `--enable-auth --with-ollama`** (site, READMEs e INSTALL): instalação padrão sai com API key impressa e assistente 100% local configurado. Windows ganhou paridade: `install.ps1` aceita `-EnableAuth` (repassado ao install.sh) e o snippet do site usa a forma scriptblock (`iex` puro não aceita switches).

## [0.43.1] - 2026-07-23

### Corrigido
- **Box final do instalador**: larguras calculadas (a linha "Projects" estourava a borda com paths longos — agora reticências à esquerda preservando o nome da pasta); linha nova **Dashboards** (http://localhost:5601) e bloco de credencial do OpenSearch Dashboards com a senha lida automaticamente do `.env` da instância (login admin), harmonizado com o bloco da API key.

## [0.43.0] - 2026-07-23

### Adicionado
- **Instalador bootstrapa os próprios pré-requisitos**: Docker/git ausentes viram OFERTA de instalação com confirmação (macOS: Homebrew + cask do Docker Desktop, abre o app e espera o daemon até 5 min; Linux: get.docker.com oficial + apt/dnf com sudo consentido e shim para o grupo docker; Windows: `wsl --install` e Docker Desktop via winget). Política conservadora: `--yes` sozinho não instala software de sistema — `--install-deps` autoriza headless. Idempotente com sinalização: itens presentes mostram ✔ e versão; upgrades disponíveis viram aviso (casks auto-atualizáveis excluídos dos hints — receipt do brew atrasa).
- **Ollama opt-in no instalador**: `--with-ollama` (+ `--ollama-model`, default `gemma4:12b`) instala o Ollama (cask/script/winget oficial) e puxa o modelo com progresso nativo; roda após a stack subir e falha nunca derruba a instalação. `docker-compose.yml` ganhou `extra_hosts: host.docker.internal:host-gateway` (necessário no Docker Engine Linux).
- **`make test-installer`**: lint (`bash -n` + shellcheck) e runner puro-bash com 17 casos sobre stubs (contrato 0/100/1, política de confirmação, parser); smoke real validado em `ubuntu:24.04` limpo (`--bootstrap-only`).

### Alterado
- **Idioma padrão dos instaladores agora é en-US** (`install.sh` e `install.ps1` traduzidos por inteiro).
- Site: step 0 "Before you start" removido — o instalador prepara os pré-requisitos sozinho; flags novas documentadas; `docs/ROADMAP.md` consolidado como documento único de pendências.

## [0.41.1] - 2026-07-23

### Alterado
- **Fonte única do dashboard**: removido o duplicado `dashboards/atlasfile.ndjson` — o artefato canônico é `backend/app/data/dashboards.ndjson` (embarcado, auto-importado e também o caminho de import manual); gerador e docs atualizados.

## [0.41.0] - 2026-07-23

### Adicionado
- **Dashboard de observabilidade "AtlasFile — Operação" auto-importado**: 18 painéis sobre 3 index patterns (documentos, uso LLM de classificação, sessões de chat) — pulso do acervo, recortes por domínio/doc_kind/tipo/projeto, ingestão no tempo × decisão, distribuição de confiança, modo do classificador, saúde de extração/embeddings, custo LLM por dia × modelo e tag cloud de tópicos. Conjunto gerado deterministicamente (`backend/scripts/build_dashboards_ndjson.py` → `app/data/dashboards.ndjson` embarcado + `dashboards/atlasfile.ndjson` manual, teste garante sincronia). Import automático no boot da API (thread com retry ~150s, `overwrite=true` idempotente, nunca bloqueia o startup; `DASHBOARDS_URL`/`DASHBOARDS_AUTO_IMPORT`). Validado ao vivo: 22/22 objetos importados e dashboard renderizando com dados reais.

## [0.40.4] - 2026-07-23

### Corrigido
- **Card do Classificador honesto com modelos custom**: o select "Modelo triagem" só listava o catálogo — com um modelo custom salvo (ex.: `ollama/gemma3:12b`) o select nativo exibia a primeira opção do catálogo em vez do valor real do profile; agora os modelos validados pelo usuário entram como opções ("(validado por você)"), com fallback para o valor atual.
- **Aviso de API Key respeita o registro de providers**: o `hasKey` era hard-coded openai/anthropic — Ollama (sem chave por design) disparava "API Key não configurada para ollama"; agora usa `providerNeedsKey` (Ollama nunca avisa; Moonshot valida a chave própria).

## [0.40.3] - 2026-07-23

### Corrigido
- **Triagem com Ollama/Moonshot destravada (achado em campo)**: o enum `LLMProvider` do profile parou na v0.35 (openai/anthropic) e o PATCH do modelo de triagem com `ollama/...` reprovava com "falha ao salvar no projeto" — agora aceita os 4 providers do registro central (invariante coberto por teste: todo provider do registro é válido no `LLMPolicy`).
- **Kimi K3 ordenado**: entradas `user_models` do snapshot embarcado entram na ordem (provider, modelo) em vez de penduradas no fim da lista.
- **Docs**: fluxo de modelos custom (Ollama/Moonshot) documentado nos 2 READMEs e no INSTALL — digitar `provider/modelo` na combobox das configurações do assistente, com validação ao vivo sem chave para Ollama.

## [0.40.2] - 2026-07-23

### Corrigido
- **Decisão de triagem com mensagem honesta**: o 409 benigno (documento já decidido / decisão em andamento — card desatualizado ou duplo clique) não aparece mais como "Falha ao registrar decisão"; mostra o motivo real localizado e atualiza a fila (o card some). Erros reais agora exibem a mensagem específica da API em vez do genérico.
- **Modal sem vazamento**: `ModalActions` quebra linha (`flex-wrap`) quando os rótulos são longos — os botões do modal de recuperação não estouram mais o painel.
- **Default de modelo custo-consciente**: instância nova usa `openai/gpt-5.1` como default de agente e triagem (preferência explícita → primeiro openai → primeiro da lista), nunca "o primeiro do catálogo" (que colocava um modelo caro como default silencioso); backend `LLMPolicy.model` acompanha (gpt-4.1 → gpt-5.1). Seleção salva do usuário nunca é sobrescrita.

## [0.40.1] - 2026-07-23

### Corrigido
- **Recuperação da raiz cobre o segundo modo de falha (achado no teste destrutivo)**: a deleção da pasta host pode manifestar como mount QUEBRADO (EPERM no listdir), não só como mount fantasma vazio. Nesse modo o `/api/setup/status` respondia 503 via handler de OSError e o modal de recuperação nunca aparecia — sobrava a mensagem manual antiga. Agora: `setup/status` nunca falha (reporta `projects_root_state: unavailable`), o modal de um clique abre nos DOIS estados (`emptied` e `unavailable`) e o banner passivo antigo foi removido. Validado com probe real: `docker restart` com a pasta host deletada recria a pasta, re-vincula o mount e escritas voltam ao host.

## [0.40.0] - 2026-07-23

### Adicionado
- **Self-healing da raiz de projetos esvaziada** (pasta host deletada sob bind mount — no macOS/VirtioFS o container passa a ver um "mount fantasma" vazio, sem quebrar a sonda):
  - Estado novo `emptied` em `/api/setup/status`: raiz saudável sem o marcador `.atlasfile_root` (gravado no startup) + índice com documentos = pasta foi excluída/substituída.
  - Modal de recuperação com um clique: `POST /api/system/restart` encerra a API graciosamente, a política `restart: unless-stopped` (nova no compose, 5 serviços) religa o container, o Docker recria a pasta host e re-vincula o mount (comportamento validado no Docker Desktop/macOS); a UI aguarda o health voltar, roda o reconcile global (limpa o índice órfão) e recarrega no onboarding.
  - Guard anti-limbo: upload, scan e criação de projeto retornam `503 PROJECTS_ROOT_EMPTIED` enquanto o estado persistir — sem ele, escritas iriam para um inode deletado e se perderiam em silêncio. Onboarding também não é sugerido sobre mount fantasma.

## [0.39.2] - 2026-07-23

### Corrigido
- **Aprendizado nunca mais em silêncio (achados de campo do teste kit 2)**:
  - Decisão de triagem agora invalida a query de sugestões de aliases — a seção do Classificador atualiza sem reload.
  - Toast após Aprovar/Corrigir quando surgem termos NOVOS no minerador ("N novos termos aprendidos aguardam sua revisão no Classificador"), com dedupe por projeto na sessão.
  - Seção "Sugestões de aliases" sempre visível em projeto único, com estado vazio explicativo: sem correções ainda / aguardando contraste (≥2 docs de outras classes) / nenhum termo passou nos cortes (suporte ≥2, precisão ≥80%).
- **Painel**: cards com o mesmo respiro do Classificador (`gap-4`) — estavam emendados desde a introdução do scrim de processamento.

## [0.39.1] -- 2026-07-23

### Corrigido (achados de campo do sugeridor de aliases)

- **Marcadores do extrator não viram alias**: "[page 1]"/"[sheet …]" eram tokenizados junto do conteúdo — "page" chegou a ser proposto como alias. Marcadores `[...]` são removidos antes da mineração.
- **Bigramas com borda funcional mortos**: "partes e"/"junto ao" passavam pelo corte contrastivo em corpus minúsculo; agora TODO token do n-grama exige ≥3 letras (sem lista de stopwords arbitrária).
- **Precisão exige contraste real**: com <2 docs de outras classes, precisão 100% é ilusão estatística — o alvo é pulado até haver contraste mínimo.
- **Plural nativo no i18n**: "2 correção(ões)"/"2 doc(s)" viram pluralização i18next (`_one`/`_other`) nos 2 idiomas.

---

## [0.39.0] -- 2026-07-23

### Alterado

- **Taxonomia essencial de document_types (14 → 10)**: saem os tipos-FORMATO `apresentacao`, `planilha` e `email` (formato já é a faceta `doc_kind`, derivada da extensão e filtrável na busca/stats) e o nicho `fato_relevante` (recriável pela criação governada onde o projeto pedir). Um `plano.pptx` agora classifica pelo GÊNERO (`plano` + `doc_kind=pptx`) — antes o atalho de extensão 0.98 curto-circuitava o conteúdo. Templates `default` e `default-en`; instâncias existentes migram opt-in pela ferramenta governada.
- **Regras de cabeçalho agora olham o cabeçalho** (`head_chars` nas detection_rules): a remoção do atalho expôs falsos positivos 0.96+ de regras "structural_header" que casavam menção profunda no corpo (kickoff citando RFP → edital; processo de pagamentos citando NF → nota_fiscal; fato relevante citando aditamento → aditivo — offsets 1.5k-3k medidos nos 12 arquivos reais). Regras `any_of` de cabeçalho ganham `head_chars: 600` (retrocompatível: ausente = texto inteiro); `all_of` de evidência distribuída (contratante/contratada) mantém escopo total.
- **Frequência de alias nunca auto-roteia sozinha**: teto do caminho de alias desce para 0.84 (< auto_route 0.85) — auto-route de tipo exige regra estrutural ou extensão característica. Régua nova no teste de piso (12 arquivos reais): **zero auto-route com tipo errado**, acerto exato nos cabeçalhos reais, ambíguos vão à triagem (que treina o classificador e alimenta o sugeridor de aliases).

---

## [0.38.0] -- 2026-07-23

### Corrigido

- **Resiliência à perda da pasta de projetos** (cenário real: usuário deleta a raiz com o stack no ar → bind mount quebrado → "NetworkError" sem pista): sonda de saúde da raiz (`projects_root_health`) exposta no `/api/setup/status`; `PermissionError/OSError` com raiz indisponível vira **503 `PROJECTS_ROOT_UNAVAILABLE`** com instrução de recuperação (em vez de 500 cru); **banner global** na UI (poll de 20s) orientando recriar a pasta e reiniciar o stack; wizard não é sugerido com a raiz quebrada (não é instância nova).
- **Limpeza de órfãos do índice destravada**: o guard `valid_projects` pulava o `cleanup_orphan_projects` justamente no caso "raiz recomeçada do zero" (0 projetos) — docs fantasmas ficavam para sempre. Agora a limpeza é liberada com a **raiz saudável mesmo vazia** e pulada (com `skipped_reason` no relatório) apenas com a raiz indisponível — proteção contra apagar o índice por um mount transitório.
- **Templates nunca somem**: leituras do diretório user (`_ATLASFILE/templates`) tolerantes a OSError — com a raiz quebrada, a listagem e o `get_template` caem nos **builtin** (default/default-en seguem disponíveis no wizard).

---

## [0.37.0] -- 2026-07-23

### Adicionado

- **Sugeridor de aliases do bootstrap** (nova seção no Classificador): minera n-gramas discriminativos das CORREÇÕES humanas da triagem (par sugerido→final dos metadados resolvidos) e **propõe** aliases de domínio/tipo com evidência (nº de docs, precisão) — aprovação com um clique adiciona ao template default e propaga aos projetos (`taxonomy.add_taxonomy_aliases`, novo caminho de append em entrada existente); dispensa persiste no profile e o termo não volta. Corte contrastivo (suporte ≥2 docs corrigidos da classe, precisão ≥0.8 sobre todas as classes, ≥2 rótulos no corpus) sem stopwords artesanais — validado em dados reais: correções isoladas e ruído de OCR não passam. Candidatos garantidamente compatíveis com o matching real do bootstrap (`fold_ocr_spacing` + word boundary, colisão com o léxico de tipos descartada; extensões de arquivo nunca viram alias). Endpoints: `GET /api/projects/{ref}/alias-suggestions`, `POST /api/taxonomy/aliases`, `POST .../alias-suggestions/dismiss`.

---

## [0.36.0] -- 2026-07-22

### Corrigido

- **Modelos OpenAI pós-gpt-5.2 no assistente** (bug 400 "Function tools with reasoning_effort are not supported ... use /v1/responses"): o chat (e a classificação LLM) agora roteiam esses modelos pela **Responses API** (`client.responses.create`) preservando tools + reasoning — itens de reasoning retornam íntegros no loop de tools, tools no formato flat, usage acumulado (input/output/cache). Roteamento por capacidade de catálogo: campo novo `openai_api` ("chat_completions" | "responses") no `ModelOption`, com builtin (gpt-5.2) e inferência no refresh LiteLLM (`supported_endpoints` ou reasoning + versão ≥ 5.2). Modelos atuais (gpt-4o-mini/4.1/5.1) permanecem byte-a-byte no caminho existente. Erro dedicado `LLM_MODEL_NEEDS_RESPONSES_API` orienta o refresh do catálogo quando o cache está desatualizado.
- **Refresh do catálogo**: nomes de modelos de provedores não-OpenAI vinham com o prefixo LiteLLM duplicado (`moonshot/moonshot/...`); o prefixo do provider agora é removido do id.

### Adicionado

- **Providers OpenAI-compatíveis**: Moonshot (Kimi; `MOONSHOT_API_KEY`/`X-Moonshot-API-Key`, `MOONSHOT_BASE_URL`) e **Ollama local** (sem chave; `OLLAMA_BASE_URL`, default `host.docker.internal:11434` no Docker). Registro central de providers (`backend/app/llm_providers.py` + `frontend/src/lib/providers.ts`) substitui os ternários openai/anthropic em orchestrator, endpoints de chat/classify e validações — adicionar um provider novo é 1 entrada no registro. Catálogo aceita modelos moonshot no refresh (builtin `kimi-k3`); modelos Ollama entram pela combobox custom com validação real (`/api/models/validate` generalizado, que também ganhou testes — antes não tinha nenhum).
- **Validação de chaves no modal Assistant Settings**: campos de chave (OpenAI/Anthropic/Moonshot) validam automaticamente com debounce de 700ms e badge inline — ✓ válida, ✗ inválida, e "não foi possível verificar" (rede/backend fora) distinto de inválida; nada bloqueia. Mesmo padrão do wizard (stale-guard incluso). Modelos Ollama exibem hint "roda localmente, sem chave".
- **Modelos custom no seletor do chat**: modelos validados pelo usuário (ex.: `ollama/gemma4:12b`) agora aparecem no select do chat — antes só existiam no modal e eram inutilizáveis no chat.
- **Snapshot LiteLLM embarcado** (`backend/app/data/llm_catalog_snapshot.json`, ~68 modelos com preços): substitui a lista builtin mínima como camada base do catálogo — instância nova já nasce com o catálogo completo, mesmo sem rede. Atualizável por `backend/scripts/update_catalog_snapshot.py`, com merge que **preserva as linhas do usuário** (`user_models`/`user_costs`): o LiteLLM só atualiza o que existe em ambos e promove entradas que passou a cobrir. Primeira entrada de usuário: **Moonshot Kimi K3** (id `kimi-k3`, contexto 1M, saída 131k; $3.00/$15.00, cache-read $0.30 — preços da doc oficial; thinking always-on no servidor, sem envio de `reasoning_effort`). Custos passam a 3 camadas: config → snapshot → override do refresh.
- **Refresh automático do catálogo no primeiro boot** (background, não-fatal offline) + recarga da lista de modelos ao concluir o wizard — o "Atualizar agora" vira apenas re-atualização manual.
- **Correção da regra do bug**: o roteamento por Responses API vale para modelos **pós-gpt-5.2 exclusive** (5.3+); o gpt-5.2 em si permanece no chat/completions (relato original do erro conferido).
- **Chat não rola mais sozinho durante a leitura**: a prop `messages` nascia com identidade nova a cada re-render (polls do app) e o efeito de auto-scroll disparava sem mensagem nova — memoizada na `AssistenteView`; e o `ChatPanel` ganhou guarda de leitura (só auto-rola quando já se está perto do fim da thread — quem rolou para cima está lendo).
- **Consistência de headers**: Dashboard ganha o ícone `LayoutDashboard` no título (paridade com as demais views); o Classificador passa a exibir o cabeçalho rico de projeto ("Project: … · Profile v2 JSON · ID/Versão/Última alteração") via componente `ProjectHeaderMeta`, extraído do editor de perfil (Configuração) e reutilizado nos dois lugares.

---

## [0.35.0] -- 2026-07-19

### Adicionado

- **Tour de looks do buraco negro** no fundo do gate/wizard: Inferno (5500K, filamentos âmbar) → Gargantua (4500K, névoa suave estilo filme) → Quasar (15000K, disco azul-branco gigante), 14s por look com crossfade de 2.5s — mecânica `DiskLook`/`mixLook` do shader original em ritmo contemplativo (5s/slot é ritmo do modo demo de gravação); ajuste num número só (`TOUR_SLOT_SEC`). O orb da sidebar permanece no Inferno (o Quasar tem raio externo 14 r_s e estouraria 40px). Constante órfã `LENS_DEPTH` removida.

---

## [0.34.5] -- 2026-07-19

### Corrigido

- **Quiralidade do buraco negro**: o port mantinha o flip de y do Ghostty (uv top-down), mas o WebGL é y-up — o mundo ficava espelhado e o disco cruzava na diagonal invertida em relação ao demo original. Removido o `-p.y`; orientação agora idêntica à referência.

---

## [0.34.4] -- 2026-07-19

### Corrigido

- **Lente gravitacional sobre o starfield**: o céu estava ancorado nas coordenadas do buraco e viajava junto com ele (parecia uma foto colada). Agora o céu é fixo na TELA (papel que o texto do terminal tem no shader original) e só a deflexão gravitacional é relativa ao buraco — as estrelas ficam paradas e esticam em arcos de Einstein quando a lente passa (perto do anel de fótons `nv.z→0` e a deflexão explode). Validado com dois frames espaçados no Chrome real: buraco deriva, céu fixo, arcos visíveis.

---

## [0.34.3] -- 2026-07-19

### Corrigido

- **Estrelas invisíveis no Chrome real (Metal)**: o shader emitia as estrelas como pixel premultiplicado inválido (cor > 0 com alfa 0) — comportamento indefinido por spec; o compositor Metal do Chrome interativo clampa cor≤alfa e as estrelas viravam preto, enquanto compositores de software (headless/Playwright) deixavam passar — por isso os screenshots de validação anteriores mentiam. Alfa agora deriva da luminância (`max(occ, maxComponent(luz))`), válido em qualquer compositor. Diagnóstico e validação feitos no ambiente real: captura de tela do Chrome interativo do usuário (ANGLE Metal, M3 Max) antes e depois.

---

## [0.34.2] -- 2026-07-19

### Corrigido

- **Starfield de verdade**: as estrelas da 0.34.1 existiam mas eram fracas demais para ler como céu — densidade ~2.3x (limiar 0.86), estrelas maiores (0.16), brilho com piso (0.35 + 1.3x) e base de visibilidade 0.70 na tela toda. No original Ghostty as estrelas eram um detalhe sobre o texto do terminal; na UI elas são o próprio céu.

---

## [0.34.1] -- 2026-07-19

### Corrigido

- **Starfield visível no céu inteiro** do BlackholeGL: longe do buraco a direção do raio tendia a uma constante e toda a tela amostrava um único ponto do céu (fundo preto) — adicionado campo de visão de câmera (`SKY_FOV`) para variação por pixel, com base de visibilidade em toda a tela e reforço perto da lente.
- **Contraste do rótulo de processamento** ("Aprovando — indexando para busca" e afins): o shimmer `atlas-thinking-text` usava `--muted` como base — agora `--text`, legível sobre a aura/scrim nos dois temas.
- **Orb da sidebar também vira buraco negro em ingestão/decisão de triagem** (`atlas:ingest-active`), não só no ciclo do classificador — aprovar um documento é "documento sendo puxado", com a mesma exibição mínima de 4s.

---

## [0.34.0] -- 2026-07-19

### Adicionado

- **Buraco negro de Schwarzschild como elemento vivo da UI** (`BlackholeGL`, port WebGL2 do [ghostty-blackhole](https://s13k.dev/blackhole/), MIT): física real por pixel — geodésicas nulas integradas (lente gravitacional, sombra, anel de fótons), disco de acreção Shakura–Sunyaev com Doppler/beaming relativístico e dilatação temporal; starfield lenteado; saída premultiplicada (a luz soma sobre a página, a sombra oclui). Dois usos: **fundo do gate de API key e do wizard de onboarding** (deriva Lissajous atrás do card, em camada com a aurora) e **orb da sidebar durante o ciclo do classificador** ("documentos sendo puxados"), com exibição mínima de 4s para ciclos curtos não virarem pisca. Pausa fora de viewport/aba oculta; `prefers-reduced-motion` congela num frame estático; leitura do status do ciclo por observer de cache (zero fetch novo).

### Corrigido

- Acentuação da tela de boas-vindas do onboarding ("gestão", "ficarão", "instalação", "Começar") — resíduos da UI legada que a varredura ortográfica da 0.33.0 não cobriu.

---

## [0.33.0] -- 2026-07-19

### Adicionado

- **Internacionalização completa (PT-BR + EN-US)**: toda a interface passa a ser servida por catálogos i18next (12 namespaces, ~1.000 chaves por idioma, plurais reais e interpolação). PT-BR é o idioma-fonte e fallback; EN-US completo com teste automatizado de paridade estrutural (chaves e interpolações). Detecção automática pelo navegador no primeiro acesso, com seletor persistido em **Configuração → Preferências** (aba nova) e alternador discreto nas telas de primeiro acesso (gate de API key e wizard de onboarding).
- **Códigos de erro estáveis no backend**: `HTTPException.detail` passa a ser `{code, params, message}` (62 codes SCREAMING_SNAKE, helper `app/http_errors.py`); blockers/suggestions de prontidão de datasets ganham `params`. O frontend resolve `code` → tradução do catálogo (`lib/apiError.ts`); mensagens dinâmicas de exceções de domínio seguem como texto cru por design. Lógica condicional usa exclusivamente `ApiError.code` — nunca texto exibido.
- **Formatação regional central** (`lib/format.ts`): números, datas, percentuais e moeda via `Intl.*` no idioma ativo (pt-BR: "US$ 1,23", "92,0%", "19/07/2026"; en-US: "$1.23", "92.0%", "7/19/26"); date-fns e calendário com locale dinâmico; padrões de data por idioma no catálogo.
- **Gate de integridade i18n** na suíte: toda chave `t()` estática do código é validada contra o catálogo; paridade PT×EN falha o build se divergirem.
- **Prompts do assistente cientes de idioma**: resposta sempre no idioma das mensagens do usuário; títulos de gráfico e título automático de sessão no idioma da conversa (prompt canônico único, sem duplicação por idioma).
- **Troca de idioma AO VIVO**: alterar o idioma (Preferências, gate ou wizard) aplica instantaneamente em toda a interface — sem reload, sem blink; a escolha persiste no navegador.
- **Classificação bilíngue para corpus misto** (modelo SKOS/EuroVoc — key canônico + sinônimos multilíngues): o template `default` ganha ~146 aliases EN nos domínios/tipos e +20 termos EN nas detection_rules (documentos em inglês voltam a auto-rotear no bootstrap, sem mudança de código); `topics_v1.yaml` vira multilíngue (+315 sinônimos EN nos 94 tópicos, `language: multi`).
- **Template `default-en`** (M&A / Carve-out em inglês): pastas, keys, labels, aliases e regras 100% EN para instalações EN-nativas; wizard e modal de novo projeto pré-selecionam o template pelo idioma da UI (o usuário pode escolher qualquer um).

### Mudado

- **Estado de servidor consolidado no TanStack Query v5** (F1–F3 do plano): cache por chave com invalidação por domínio substitui o bus de eventos manual; SSE alimenta o cache por uma ponte única (`useSseChannel`) com fallback-poll exclusivo; polls viram `refetchInterval`; `App.tsx` enxuto (busca e chat descem para as views; ~44 props eliminadas); persistência local centralizada em `lib/storage.ts`.
- **Classificador promovido a tela de primeiro nível** na sidebar (era aba da Configuração) — é um agente operacional como o Assistente. Configuração fica com Perfil/Templates/Acesso/Preferências.
- **Severidade de status estrutural**: toasts de erro/informação são classificados pelo emissor (`onStatus(msg, severity)`), não por regex sobre o texto.
- **Ortografia PT-BR corrigida no catálogo**: 47 strings sem acentuação herdadas da UI legada ("Ultima reconciliacao", "Decisao registrada", "correcao"...) e 9 em inglês técnico agora em PT correto; plurais "(s)"/"(ões)" viraram plurais gramaticais reais.

### Corrigido

- Paleta ⌘K não listava o Classificador no grupo Navegação.
- Motivo de rejeição (`sem_texto_extraivel`) e status do último ciclo (`succeeded`) exibidos como código cru — agora traduzidos.
- Detail de erro do backend em formato dict quebrava a exibição (`[object Object]`) — parse central em `lib/apiError.ts` com fallback.

---

## [0.32.1] -- 2026-07-19

### Corrigido

- **Keep-alive também nas abas da Configuração**: alternar entre Perfil/Classificador/Templates/Acesso desmontava o conteúdo da aba inativa (Radix Tabs default) — o Perfil do projeto voltava ao estado inicial. Agora as abas usam `forceMount` (inativa fica oculta, não desmontada): rascunhos, colapsáveis e estado interno sobrevivem à alternância, no mesmo padrão do keep-alive das telas.

---

## [0.32.0] -- 2026-07-19

### Mudado

- **Keep-alive global de telas** (Painel/Assistente/Configuração): cada tela monta na primeira visita e **nunca mais desmonta** — navegar apenas alterna a visibilidade (CSS). TODO o estado sobrevive à navegação: chat em andamento, abas, colapsáveis, rascunhos de formulário, filtros de busca e monitores ao vivo (ciclo do classificador continua atualizando mesmo com a tela oculta). Padrão tab-navigator (React Navigation/Vue KeepAlive/React Activity). A persistência em localStorage (abas/colapsáveis) permanece para sobreviver a reload.

---

## [0.31.2] -- 2026-07-19

### Corrigido

- **Status do ciclo não congela mais ao navegar**: o monitor ao vivo (SSE) parava quando o card desmontava (troca de tela) e não era retomado na volta — o status ficava no último snapshot (ex.: "3/3") mesmo com o ciclo concluído no backend, até um reload. Agora, remontar com ciclo em andamento religa o monitor automaticamente.
- **Estado de abas e colapsáveis sobrevive à navegação**: a aba ativa da Configuração e o aberto/fechado dos colapsáveis (Processamentos, Rejeitados, Classificador operacional, Classificação LLM) persistem em localStorage — navegar entre Painel/Assistente/Configuração não reseta mais a tela.

---

## [0.31.1] -- 2026-07-19

### Corrigido

- **Rota do decision-status**: `/api/triage/decision-status` colidia com `GET /api/triage/{project_id}` (o path virava project_id) — movida para `/api/triage-decision-status` (pego no E2E real).
- **Aura focal no fluxo de correção**: o card era removido da fila otimisticamente ("em segundo plano") antes do processamento — sem palco para a aura. Agora o card permanece processando com aura/fases, como no aprovar/rejeitar; o bus o remove ao concluir.

---

## [0.31.0] -- 2026-07-19

### Adicionado

- **Processamento Focal** (evolução da Aura): decisões de triagem agora têm estado **global** (`ProcessingContext`) com **fases reais do backend** — novo `GET /api/triage/decision-status` reporta `movendo arquivo → extraindo conteúdo → indexando para busca → atualizando datasets` (poll 1s). O card em decisão fica focal com a aura; **todo o resto do Painel esmaece sob um scrim** (cliques bloqueados, cursor de espera — processar em série é a regra e agora é visível); ao **navegar para outra tela, um pill flutuante** (padrão Gmail) mantém o processo à vista com fase e clique-para-voltar; o **orb da sidebar pulsa** em `ingesting` durante a operação. O tempo decorrido usa o início real da operação — **sobrevive a navegação e remount**.

### Corrigido

- **Citações clicáveis no chat para imagens**: a lista de extensões dos chips (`DOC_EXTENSIONS`) não incluía imagens — `Fluxo instalação.png` citado pelo agente não virava pill clicável (PDFs funcionavam). Adicionados `png/jpg/jpeg/tif/tiff/bmp/webp/xml/html`.

---

## [0.30.0] -- 2026-07-19

### Adicionado

- **Aura de Processamento** (`ProcessingAura` + `MiniOrb`): feedback vivo e honesto para operações longas — halo conic-gradient da marca girando ao redor do card (mesma arte do compose do chat), mini-orb pulsante, rótulo da ação com varredura de gradiente e **tempo decorrido real** (nunca uma barra de progresso inventada). Respeita `prefers-reduced-motion`.
- **Aplicada em**: decisões de triagem ("Aprovando — movendo, extraindo e indexando" / "Rejeitando…"), restaurar/excluir rejeitados, aprovar com correção, mover documento e aplicar layout do profile. Scan da INBOX e ciclo do classificador (que já têm progresso real) ganharam o mini-orb para consistência visual.

### Mudado

- **Benchmark: "previsto" → "classificado"** no detalhe expansível (esperado = seu rótulo; classificado = a resposta do classificador).

---

## [0.29.1] -- 2026-07-19

### Corrigido

- **Passo final do wizard atualizado ao fluxo atual**: a tela "Tudo pronto!" descrevia o processo manual antigo ("coloque seus arquivos em `_INBOX_DROP/` e clique em Processar INBOX"). Agora orienta o fluxo real — arrastar arquivos em qualquer tela com processamento automático — e mantém o caminho manual como alternativa.

---

## [0.29.0] -- 2026-07-19

### Adicionado

- **OCR de imagens soltas** (.jpg/.jpeg/.png/.tif/.tiff/.bmp/.webp): o extrator agora roda Tesseract (o mesmo motor do PDF escaneado) sobre imagens — uma foto de contrato entra no pipeline com texto real, é classificada e indexada com chunks citáveis. Hint do portal atualizado.

### Corrigido

- **Proteção sem-texto (fim da sugestão fabricada)**: imagem sem texto legível (OCR vazio) ou formato ilegível não gera mais chute a partir do nome do arquivo (o caso "tela-rota.jpg → societario/relatorio 5%"). O documento vai para a triagem com `reason: sem_texto_extraivel`, **sem sugestão**, confiança 0.0, e a fila mostra "sem texto extraível (OCR vazio) — decida manualmente". O LLM é pulado nesses casos (custo zero sobre entrada vazia).

---

## [0.28.3] -- 2026-07-19

### Corrigido

- **Auditoria de reatividade (pedido: "nada pode depender de reload")**: o App agora **assina** o bus `atlas:data-refresh` para triagem + stats (estado que vive no App e nunca remonta) e toda mutação apenas **emite** — fonte única, sem pontos esquecidos. Passam a atualizar ao vivo: migração/remoção de taxonomia (stats/painel), mover documento (histórico + busca + stats), fim de reconciliação (todos os cards), salvar política LLM, e o card de conflitos de rótulo (assina o bus — conflitos criados por correções aparecem sem reload).

### Mudado

- **Briefing do classificador LLM com extensões**: o contexto do projeto agora lista as extensões esperadas por tipo (`plano — extensões esperadas: .pdf, .docx`) e o system prompt instrui a usar a extensão como evidência estrutural — um `.pptx` não deve virar `plano`. Vale para a classificação ao vivo e para o benchmark do ciclo.

---

## [0.28.2] -- 2026-07-19

### Corrigido

- **Excluir rejeitado atualiza o badge do Processamentos ao vivo**: o Excluir agora notifica o bus (mesmo canal do Restaurar) — a linha vira "excluído" sem reload.
- **Projeto selecionado sobrevive ao reload**: a seleção persiste em `localStorage` (`atlasfile_selected_project`); se o projeto salvo não existir mais, volta para "todos" automaticamente.

---

## [0.28.1] -- 2026-07-18

### Corrigido

- **Key curta no wizard não validava**: um guard de "mínimo 15 caracteres" fazia entradas como `123` passarem em silêncio, sem ✗ nem verificação. Agora qualquer key não-vazia é validada (o backend responde `Chave OpenAI inválida` para lixo — confirmado contra a API real) — nunca silêncio.

---

## [0.28.0] -- 2026-07-18

### Adicionado

- **Validação de key no onboarding (não-impeditiva)**: ao digitar a key OpenAI/Anthropic no wizard, um check assíncrono contra a API do provedor (novo `POST /api/keys/validate`, key transiente no header, nunca persistida) mostra ✓ válida / ✗ inválida / "não foi possível verificar" — **nunca bloqueia** o avançar.
- **LLM tag_only ligado por default quando a key valida**: com key ✓ e projeto criado no wizard, o projeto já nasce com `llm_policy.enabled=true, mode=tag_only` e o modelo default do provedor (gpt-4o-mini / claude-haiku-4-5) — os documentos são enriquecidos desde a primeira ingestão, em vez de nascer com a política desligada. O passo final confirma: "Classificação LLM ativada (tag_only)". Falha na ativação não trava o wizard.

### Corrigido

- **Sem toast de erro no boot durante o wizard**: recarregar a página com backend zerado (ou API ainda subindo) mostrava "Falha ao carregar dados: Falha ao carregar status de reconciliacao". O carregamento inicial (projetos + status de reconciliação) agora é best-effort e silencioso — conectividade é sinalizada pelo orb de health; o toast fica reservado para falhas durante uma reconciliação realmente em andamento.

---

## [0.27.3] -- 2026-07-18

### Corrigido

- **Processamentos com badge fiel ao ciclo de vida**: o histórico já gravava `approved`/`corrected`/`rejected`, mas a UI mostrava "triagem" para tudo. Agora: `aprovado`, `corrigido`, `rejeitado` e — após o Excluir de um rejeitado — `excluído` (o endpoint marca o histórico via `update_history_item`). A linha nunca some: trilha de auditoria. Linhas rejeitadas/excluídas não oferecem mais a ação de mover.
- **Painel de detalhes enxuto e honesto**: título "Detalhes da classificação" (sem "LLM" quando não há LLM) e **uma linha por classificador** — `bootstrap: domínio X | tipo Y | final Z` e, quando o LLM participou, `llm: domínio A · tipo B (conf C)`. A linha "Regra:" saiu (a seta `← regra` na própria linha já mostra override).

### Adicionado

- **Benchmark oficial expansível**: clicar num modo (bootstrap/llm) abre o detalhe por documento do validation set — arquivo, esperado vs previsto com ✓/✗ por eixo. É onde se vê, por exemplo, que o LLM previu `plano` para o pptx "Plano convênio bancário" (foi no nome do arquivo).

---

## [0.27.2] -- 2026-07-18

### Corrigido

- **Benchmark do ciclo com a taxonomia real dos projetos**: o ciclo avaliava bootstrap/LLM contra a taxonomia do template default — tipos/domínios criados pelo usuário (ex.: `memorando` via triagem) não eram opções possíveis, condenando o rótulo esperado a 0% por construção. Agora `merge_project_taxonomies` une business_domains e document_types de todos os profiles reais ao profile do benchmark; o report registra `taxonomy_sources`.
- **Estado do classificador sobrevive a rebuilds**: dentro do container, `PROJECTS_HOST_ROOT` (path do host, inexistente lá) era escolhido como raiz do estado — registry, campeão e reports iam para o filesystem efêmero do container e sumiam a cada rebuild. O resolvedor agora prefere o primeiro candidato que existe (o `/projects` montado). Datasets já estavam no lugar certo.
- **Linha "LLM:" do histórico honesta**: o painel de detalhes imprimia o domínio FINAL da classificação rotulado como "LLM". Agora a ingestão persiste a resposta crua do LLM (`llm_business_domain`, `llm_document_type`, `llm_confidence`) e a UI mostra a contribuição genuína (domínio e tipo sugeridos pelo LLM, com a confiança dele); a linha some em entradas antigas sem os campos.

### Mudado

- **Painel: "Rejeitados" abaixo da caixa "Solte arquivos"**: a caixa de drop é perene; blocos condicionais (Rejeitados) ficam abaixo dela — o layout não salta quando o card aparece/some.

---

## [0.27.1] -- 2026-07-18

### Corrigido

- **Card "Rejeitados" no padrão do design system**: agora usa o `CollapsibleSection` canônico (chevron + chip "N arquivos"), idêntico ao card Processamentos — a versão anterior tinha header próprio (ícone + "mostrar"), fora do guia.
- **Label do projeto reativo**: salvar o profile (ex.: renomear o project label) atualiza o switcher da sidebar na hora — o `ProjectContext` agora assina o bus `atlas:data-refresh`, e o editor de profile emite após salvar e após aplicar layout. Antes exigia reload de página.

### Nota

- O **project label** é o nome de exibição e é persistido em `_PROFILE/profile.json`; a **pasta física** do projeto é o `project_id` (identificador imutável) e não é renomeada — renomear a pasta exigiria migração de todos os paths indexados.

---

## [0.27.0] -- 2026-07-18

### Adicionado

- **Seção "Rejeitados" no Painel** (projeto único): card colapsável lista os documentos rejeitados na triagem (arquivo, motivo, data) com ações **Restaurar** (devolve à fila de triagem, com arquivo e metadados) e **Excluir** (popover de confirmação; apaga arquivo + registro). Registros órfãos (sem arquivo físico) só oferecem Excluir. Antes, rejeitar um doc o fazia sumir da UI sem nenhum caminho de recuperação.
- **Endpoints de rejeitados**: `GET /api/triage/{project_id}/rejected`, `POST /api/triage/{project_id}/{doc_id}/restore`, `DELETE /api/triage/{project_id}/{doc_id}/rejected`.

### Corrigido

- **Corrida na decisão de triagem** (registro órfão fantasma): aprovar movia o arquivo no início e só removia o meta pendente ao final (~14s com extração/indexação) — uma requisição concorrente via "pendente sem arquivo" e gravava `orphaned_missing_source` em rejeitados. Agora a decisão faz **claim atômico** (rename do meta para `.processing`): a concorrente recebe 409; falha no processamento restaura o claim. Na UI, os botões de decisão ficam desabilitados enquanto uma decisão está em voo.

### Mudado

- **Reatividade sem reload em todo o Painel**: novo bus de eventos (`atlas:data-refresh`) — qualquer scan (portal ou botão) ou decisão de triagem notifica os cards derivados (Processamentos, fila da INBOX, Rejeitados), que recarregam sozinhos. O colapsável de Processamentos agora aparece/atualiza imediatamente após o processamento, sem F5.

---

## [0.26.2] -- 2026-07-18

### Corrigido

- **Orb da sidebar não treme mais com blips transitórios**: o estado `error` (único com shake, por design) disparava com UMA falha do `/health` (ex.: restart de container) e a recuperação esperava o tick de 30s — parecia bug até o reload. Agora exige 2 falhas consecutivas e, em erro, re-verifica a cada 5s (recupera sozinho).

---

## [0.26.1] -- 2026-07-18

### Corrigido

- **Migração multi-template**: o destino é válido se existir em QUALQUER template ou profile (antes exigia o default); profiles/templates que têm a origem mas não o destino ganham a definição canônica inserida na hora — sem isso o move falharia no `_ensure_*_in_profile`.
- **Pastas vazias da origem removidas** após a migração (`rmdir` só de vazias, nunca forçado; folder names capturados ANTES do rename, que apaga a entrada do profile); `removed_dirs` no resultado.

---

## [0.26.0] -- 2026-07-18

### Adicionado

- **Migração e remoção governada de taxonomia** (`POST /api/taxonomy/migrate`, `DELETE /api/taxonomy/{kind}/{key}` + modal "Migrar / remover" no editor de templates): aponta um tipo/domínio antigo → novo cobrindo os 9 lugares onde uma key vive — documentos movidos no filesystem + reindexados (docs fora de `02_AREAS` só metadados, com aviso), datasets reescritos **por rótulo antigo** (treino, validação, corpus, splits — zero registros novos), sugestões pendentes de triagem, todos os templates + profiles (a origem **vira alias** do destino: bootstrap segue reconhecendo o legado; routing_rules reapontadas antes do filtro silencioso; `layout.business_domain_folders` ajustado). **Dry-run primeiro** (contagens por projeto/dataset/pendência + avisos, incluindo "champion sparse contém a classe antiga — rode um ciclo"). Crucial: o move em massa usa `_relocate_document(dataset_routing=False)` — **não dispara o hold-out** (moves em lote não são decisões humanas novas). Remoção pura é **guardada**: 409 com contagens quando documentos/datasets/pendências ainda usam a key. 11 testes unit backend + 3 de componente novos.

---

## [0.25.2] -- 2026-07-18

### Segurança

- **Cobertura completa de autenticação**: 40 endpoints que ficavam públicos com `API_AUTH_ENABLED=true` (sessões de chat, templates, classify, usage, reconcile, ciclo/status do classificador, catálogo de modelos, setup/status, streams SSE...) agora exigem key — header `Authorization: Bearer` ou `?api_key=` nos streams (EventSource não envia header; os getters do frontend já anexavam o param). `/health` permanece público (monitoramento/instalador). Efeito colateral positivo: o AuthGate valida a key contra um endpoint de fato autenticado (`setup/status` era público — qualquer key "passava" no gate). 16 testes de cobertura de auth novos.

---

## [0.25.1] -- 2026-07-18

### Corrigido

- **Combobox de modelos imune ao gerenciador de senhas**: no Firefox, o datalist nativo era sequestrado pelo "Manage Passwords" (heurística: input de texto adjacente a campo password vira "usuário", e o browser suprime a lista). O combobox agora tem **dropdown próprio** no design system (type="search", lista estilizada com filtro, teclado ↑↓/Enter/Esc, seleção por mousedown) — melhor que o nativo e à prova de heurística de browser.
- **Benchmark LLM não roda mais silenciosamente sem key**: o benchmark lia `OPENAI_API_KEY` só do ambiente do servidor — em instalações novas a key vive no navegador (por design), então o modo `llm` marcado era pulado sem explicação. Agora a key do navegador viaja no header do "Rodar ciclo" (transiente, como no chat; fallback: env). E o **motivo do skip aparece na tabela** de benchmark ("skip — sem key OpenAI (configure no assistente)", "treino insuficiente", etc.) — o skip mudo já custou uma investigação.

---

## [0.25.0] -- 2026-07-18

### Adicionado

- **Criar tipo/domínio direto do "Aprovar com correção"**: link "+ O destino certo não existe? Criar novo tipo ou domínio" abre o modal de criação governada (reuso do CreateTaxonomyEntryModal, que agora informa kind+key criados); ao criar, o catálogo recarrega e o novo destino já vem selecionado.
- **Gráfico `bubble` (4 dimensões em um)**: eixos categóricos x × y, cor = grupo, tamanho + rótulo = valor — ex.: domínio × tipo, cor formato, tamanho quantidade. Alternativa aos facets quando small multiples gerariam muitos painéis. (Gráficos 3D em perspectiva foram avaliados e descartados: leitura de dados ruim por oclusão/distorção — bubble matrix e heatmap são o padrão recomendado.)
- **Tabelas com linha de Total**: regra no system prompt — toda tabela com colunas numéricas termina com linha **Total** (somando só o que faz sentido; no SQL, preferir computar junto).

### Corrigido

- **Coleções pequenas destravaram o primeiro ciclo**: a regra semente agora vem ANTES do warm-up — a partir da 2ª decisão humana, uma vai para a validação (o warm-up protege o sparse, que exige 100 docs e é irrelevante nessa escala; caso real: 6 arquivos triados e ciclo bloqueado com "validação: 0 · treino: 3"). E quando a validação está vazia mas o pool de treino resolve, **o "Rodar ciclo" se auto-cura**: reserva automaticamente os documentos necessários (com fallback para pools minúsculos — move 1 mesmo com todas as classes pequenas) e roda — sem botão extra, sem clique a mais; o status informa "N documento(s) reservados automaticamente". O endpoint `POST /api/classifier/datasets/backfill-validation` permanece para uso operacional explícito.

---

## [0.24.0] -- 2026-07-18

### Adicionado

- **Gráficos de 3 variáveis no chat**: tipo `heatmap` (matriz de cruzamento com intensidade na paleta da marca — o melhor formato para domínio × tipo), `grouped_bar` (séries lado a lado) e **`facets`** (small multiples: um mini-gráfico por valor da 3ª dimensão, funciona com qualquer tipo). System prompt ensina o pivot e a coleta (`list_documents` traz business_domain + document_type + doc_kind). Validado E2E: "domínio vs tipo vs formato" → heatmaps facetados renderizados no chat. A base recharts permanece (mainstream sólida) — o gap era vocabulário de tipos + instrução ao LLM, não a biblioteca.

### Corrigido

- **API key é a primeira coisa quando auth está ligada**: novo AuthGate — qualquer 401 faz a tela inteira virar o gate (orb + campo de key + validação na API na hora); key válida → boot normal (onboarding incluído). Antes o site abria "quebrado" e o usuário tinha que achar Configuração → Acesso antes do wizard.
- **Painel atualiza sozinho após decisões de triagem**: aprovar/corrigir/rejeitar agora refaz stats do painel na hora (a decisão indexa sincronamente) — sem refresh manual.

---

## [0.23.0] -- 2026-07-18

### Adicionado

- **Catálogo dinâmico de modelos LLM**: `POST /api/models/refresh` busca o JSON comunitário LiteLLM (parâmetros + preços dos modelos OpenAI/Anthropic, mesma informação das páginas oficiais) e grava cache em `_ATLASFILE/llm/` — filtrado para modelos de chat com tool use (sem whisper/embeddings/tts). `GET /api/models` serve o merge builtin+cache (fallback offline preservado; helpers do orchestrator intactos). Combobox na Configuração do Assistente aceita **modelos digitados** com validação na API do provedor (`POST /api/models/validate`, key só no header) — digitação parcial nunca vira modelo ativo (só seleção do catálogo ou custom validado); custom validados persistem no navegador. Botão "Atualizar catálogo" na UI.
- **Configuração vira só configuração**: o botão "Processar INBOX" (e a fila da INBOX) saem da aba Classificador — ação operacional mora no Painel, onde a fila com remoção por arquivo agora aparece junto do botão (componente `InboxQueueChips`). "Rodar ciclo" permanece na aba (treina/elege o champion — é evolução das configurações do classificador). A aba ganha empty state "Nenhum projeto selecionado" no padrão do Perfil quando em "Todos os projetos".
- **Autenticação habilitável pelo instalador**: `install.sh --enable-auth` gera a key (`atlas_sk_*`), grava `config/api_keys.json`, define `API_AUTH_ENABLED=true` e `ATLASFILE_API_TOKEN` (MCP) no `.env` e rebuilda — re-executar numa instalação existente habilita auth preservando dados e key (idempotente; a key é exibida ao final). Validado E2E: 401 sem key, 200 com a key gerada, 401 com key inválida. A aba Acesso explica o atalho do instalador e o caminho manual — e o porquê de não ser um toggle na UI (uma interface sem auth não deve conseguir ativar auth).
- **Aba "Catálogo de modelos"** na Configuração do Assistente: URL da fonte editável com validação dry-run ("Testar fonte" busca e parseia sem persistir), "Atualizar agora", data do último refresh e tabela completa (contexto, max output, reasoning, preços por 1M, origem builtin/remoto). Endpoints `GET/PUT /api/models/catalog-config` (persistida em `_ATLASFILE/llm/`, https obrigatório) e `GET /api/models/detail`.
- **Modelo de triagem honesto no modal do assistente**: o campo antes só gravava no localStorage — a política LLM real é POR PROJETO e só sincronizava com o card do Classificador montado. Agora o campo aparece apenas com um projeto selecionado (rotulado "Modelo triagem — projeto X") e **grava direto no perfil do projeto** ao selecionar; em "Todos os projetos", orientação no lugar do campo.
- **Custos honestos**: preços atualizados junto com o catálogo (`usage_costs_override.json`, mesclado sobre o `config/usage_costs.json`); modelo sem preço mostra badge "custo não rastreado" e "—" na tela de Uso em vez de $0 fabricado (`cost_tracked` no payload; `get_cost_per_1m` agora retorna `None` para modelo desconhecido, alinhado ao docstring).
- **Análise estruturada de planilhas no chat** (caso real: contagem de aplicações por Empresa×Situação numa CMDB de 776 linhas que o agente se recusava a computar sobre texto truncado): tools MCP `spreadsheet_schema` e `spreadsheet_query` — o backend abre o xlsx/csv **original** do filesystem (path por doc_id, confinado ao projects root) numa tabela DuckDB em memória e executa SELECT-only (single statement, blocklist DDL/DML/ATTACH/COPY, timeout 20s, cap 500 linhas). Endpoints `GET/POST /api/documents/{doc_id}/spreadsheet/{schema,query}`; orientação no system prompt (nunca contar linhas em texto); `remark-gfm` no ChatPanel — tabelas markdown agora renderizam como tabela de verdade. Dependência nova: `duckdb`.
- **Ciclo do classificador destravado em instalação nova** (fim do beco "Validation set has no labeled entries"): decisões humanas (aprovar/corrigir triagem, mover documento) passam por um roteador de hold-out (`dataset_holdout.py`) — ~20% determinístico por SHA256 vira validação **já rotulada** (cópia própria em `validation_set/files/`), com regra semente (primeiro doc elegível quando a validação está vazia) e warm-up (primeiros 3 por classe vão ao treino para alimentar a elegibilidade do sparse). Decisão humana sobre doc já em validação **atualiza o ground truth** (antes a correção se perdia). `GET /api/classifier/datasets/readiness` + pré-check 422 no ciclo com mensagem pt-BR; botão "Reservar N para validação" (backfill estratificado e idempotente do pool de treino, `POST .../backfill-validation`); botão Rodar ciclo desabilitado com orientação quando não pronto. Docs auto-roteados continuam fora dos datasets (rótulo de máquina = self-training/métrica inflada). Rollback: `CLASSIFIER_HOLDOUT_MODULUS=0`.

---

## [0.22.3] -- 2026-07-17

### Corrigido

- **Onboarding mostra o caminho físico dos arquivos**: o passo 1 exibia `/projects` (mount interno do container) — sem significado para quem acabou de digitar um caminho real no instalador. O compose agora repassa `PROJECTS_HOST_ROOT` à API, o `/api/setup/status` devolve `projects_host_root`, e o wizard exibe "Seus arquivos ficarão em <caminho do host>"; quando o caminho não é conhecido, o campo é ocultado (nunca mais `/projects`)

---

## [0.22.2] -- 2026-07-17

### Segurança

- **Senha OpenSearch única por instalação**: o `install.sh` gera uma senha aleatória forte ao criar o `.env` (só na criação — trocar após o primeiro boot quebraria a auth). O default público hardcoded (`Kaid0Search!2026X`) saiu do `docker-compose.yml` (variável agora obrigatória via `:?` com mensagem clara) e do `.env.example` (placeholder com instrução para instalação manual). Docs (INSTALL/README) passam a referenciar a senha do `.env` em vez do valor fixo
- **Scripts legados removidos**: `atlasfile_install.sh` (substituído pelo `install.sh` one-liner) e `backup-atlasfile.sh` (INSTALL.md agora orienta backup do que importa: `PROJECTS_HOST_ROOT`; o índice é reconstruível via Reconciliar INDEX)

---

## [0.22.1] -- 2026-07-17

### Corrigido

- **Instalador — guards contra colisão de instâncias**: o compose deriva o project name do nome da pasta; instalar em um diretório com o mesmo nome de outra instância (ex.: `~/AtlasFile` vs `~/Development/AtlasFile`) fazia a nova stack adotar silenciosamente containers **e volumes** (dados!) da existente. Agora o `install.sh` detecta e aborta com orientação: (1) project name igual ao de containers de outro diretório; (2) volume `*_opensearch_data` pré-existente em instalação nova; (3) containers `atlasfile-*` (nomes fixos) pertencentes a outro diretório
- **Instalador — prompt interativo**: via `curl | bash` o `read` lia do próprio script em vez do terminal (`/dev/tty`); e o placeholder real do `.env.example` não era reconhecido como "não configurado", pulando a pergunta da pasta de projetos
- **Onboarding em instalação nova**: com backend zerado (`initialized_projects === 0`), o wizard abre mesmo com a flag `atlasfile-onboarding-done` no localStorage — a flag pode ser de outra instância servida na mesma origem (localhost:5173)
- **UX pós-portal**: fila da INBOX visível no Classificador (chips com remoção por arquivo); dropzone redundante do Painel removida — o DropHintCard clicável (file picker → mesma fila do portal global) assume o convite de upload nas duas visões

### Mudado

- **Banner do instalador com carinha** 🙂 no orb (install.sh e install.ps1 alinhados)

---

## [0.22.0] -- 2026-07-17

### UI de conflitos de rótulo + criação governada de taxonomia

- **Card "Conflitos de rótulo"** no Painel (junto à Triagem): pendências da reconciliação com fontes divergentes em chips, proposta do LLM em painel púrpura (confiança + justificativa) e arbitragem em um clique — Aceitar proposta ou Corrigir (fontes/proposta/personalizado). Endpoints `GET /api/classifier/label-conflicts` e `POST .../{sha}/resolve`; a resolução propaga o canônico por SHA às fontes (validation/training, nota `reconciled:ui`) e derivados (corpus/splits), com proveniência `human`/`human_confirmed_llm`
- **Criação governada de taxonomia** (`app/taxonomy.py` + `POST /api/taxonomy/create` + `GET /api/taxonomy`): quando a sugestão aprovada usa um `document_type`/`business_domain` inexistente, a UI avisa ("usa taxonomia nova") e oferece **"Criar no template e aplicar"** — diálogo com label/aliases editáveis; a criação atualiza o template `default` (persistido em `_ATLASFILE/templates/`, com proveniência no `template_meta`) e propaga aos profiles de todos os projetos. **Só aprovação humana cria** (chave `outro` bloqueada). Efeito imediato: `bootstrap` e `llm` leem a taxonomia em runtime — o tipo novo com aliases classifica na próxima ingestão; `sparse_logreg` aprende no ciclo seguinte
- Rehome aplicado: 20/20 arquivos dos projetos realinhados ao canônico (dataset ↔ filesystem sem descasamento); reconcile preserva resoluções prévias em re-execuções
- Testes: 495 backend (+8) e 140 frontend (+5)

---

## [0.21.0] -- 2026-07-17

### Instalador one-liner + reconciliação de rótulos por consenso

- **`install.sh`** — instalação em um comando (`curl -fsSL .../install.sh | bash`): verifica pré-requisitos (Docker/Compose v2/git, daemon, portas), clona/atualiza em `~/AtlasFile`, cria `.env` perguntando só a pasta de projetos, sobe a stack, aguarda `/health` e abre a UI — o onboarding guia o primeiro projeto. Idempotente; flags `--dir/--projects-root/--yes/--no-open`. **`install.ps1`** (Windows) verifica WSL2 + Docker Desktop e delega ao instalador Linux dentro do WSL. Seção "Instalação rápida" no README e INSTALL
- **`backend/scripts/reconcile_labels.py`** — reconciliação de rótulos por SHA256 com proveniência: agrupa training_pool + validation_set + árvores `02_AREAS` dos projetos (observacional), detecta conflitos (antes resolvidos silenciosamente por "último ganha"), resolve por unanimidade (`consensus`), LLM forte como **proponente** com justificativa (`llm_consensus` quando concorda com uma fonte; default `gpt-5.1`) e arbitragem humana só no resíduo (`label_conflicts_report.md` editável + `--apply`); `--rehome-projects` (dry-run) e `--rehome-apply` realinham os arquivos dos projetos ao canônico via API de move
- **Guardrail permanente**: `compute_dataset_integrity` agora reporta `label_conflicts` (divergência de rótulo por SHA) como warning no relatório do ciclo
- Execução real: 24 SHAs, 9 conflitos detectados — 4 resolvidos por consenso-LLM, 4 pendentes de arbitragem, 1 por fonte autoritativa única
- Primeiro push do repositório para `github.com/aleonnet/atlasfile`
- Testes: +8 unit (núcleo de consenso + guardrail) — 487 backend

---

## [0.20.0] -- 2026-07-17

### Orb WebGL: o logo vivo (Fase 7 do plano rag_hibrido_permissoes_ui_v2 — encerra o plano)

- **Novo `components/OrbGL/`** — WebGL2 cru (um quad + fragment shader, sem three.js): esfera com **aurora FBM domain-warped** (4 oitavas de value noise 3D nas cores da marca), **iluminação direcional real** (difuso + specular Blinn-Phong), **fresnel com dispersão cromática** tingido coral→púrpura, glow volumétrico analítico (sem multipass) e **anti-aliasing proporcional ao pixel** em todas as bordas
- **Estados dirigem uniforms, nunca trocam shader** (`orbStates.ts`, puro e testado): idle respira; thinking acelera fluxo/pulso e luas 4×; **ingesting (novo)** — espiral de partículas convergindo ao núcleo, conectado de verdade ao portal de upload via evento `atlas:ingest-active`; success flash verde; error treme (no espaço do shader) e avermelha; transições sempre por lerp
- **Mecânica kepleriana preservada**: Newton-Raphson extraído puro (`kepler.ts`) — a CPU resolve as órbitas e o shader desenha as luas com brilho de proximidade e oclusão atrás da esfera; testes de periapsis/apoapsis, convergência e fechamento de órbita
- **Fallback integral**: sem WebGL2, prefers-reduced-motion ou queda do contexto GL → CompanionOrb SVG intacto; render loop pausa com aba oculta e fora do viewport (zero GPU idle); DPR ≤ 2
- **Wordmark "AtlasFile"** com stroke draw-on (~1.5s) e fill emergindo no hero do onboarding (orb 112px), micro-interação de glow no hover
- **Chat: fim das URLs fabricadas** — regra no system prompt do orchestrator (nunca inventar links; citar `original_filename` entre backticks) + safety net no renderer (links placeholder viram chip clicável quando o texto é um arquivo, ou texto puro) — validado E2E com resposta real
- Testes: 135 frontend (9 novos do OrbGL) + 479 backend

---

## [0.19.0] -- 2026-07-17

### UI reformulada "instrumento de precisão vivo" — 100% das telas, zero CSS legado (Fase 6 do plano rag_hibrido_permissoes_ui_v2)

- **Shell**: sidebar colapsável com spring (Framer Motion), project switcher rico (avatar/cor determinística, busca inline), luz do orb, indicador ativo deslizante; CommandPalette ⌘K (cmdk) absorve o SearchModal — docs com trecho/location, navegação, projetos, tema, ações; Topbar reduzida a breadcrumb
- **Painel**: stat tiles com números que contam e cursor-glow; resultados de busca como tiles com aura por match_type (púrpura semântico/laranja lexical) e stagger; filtros como chips com contagem; barra de progresso com glow
- **Assistente**: chips de citação clicáveis sob as respostas (resolve via suggest e abre o doc); gráficos (ChartBlock + UsageView) na paleta da marca --chart-1..8 por tema
- **Triagem**: fila redesenhada (badge pulsante, tiles com barra accent, contexto do classificador em painel mono, ações Aprovar/Corrigir/Rejeitar temadas)
- **Upload portal global**: drop em qualquer lugar escurece a UI e projeta o portal (anel conic girando + partículas convergindo); sem projeto ativo, dialog de escolha; fila com progresso XHR por arquivo e scan automático único por lote
- **Toasts (sonner)** substituem o footer .status (toast único auto-atualizável; falhas de ingest com motivo por arquivo)
- **Zero CSS legado**: `styles.css` 2.416 → ~150 linhas (só design tokens dark/light); `ChatPanel.css` (~780) e `ingestTriageCard.css` (818) **eliminados** — conversão integral para Tailwind com reuso das primitivas (CollapsibleSection com badge rico, Badge, DataTable, selects padrão); restam apenas 8 linhas de override do recharts e o fallback SVG do orb (Fase 7)
- **Preflight-lite** em `@layer base`: reset de `button` (buttonface/borda nativos vazavam sem o preflight) e margens UA de headings/parágrafos — headers das 4 abas de Config **medidos idênticos (31px topo / 21px esquerda)** via getBoundingClientRect; `color-scheme` por tema (scrollbars e date pickers nativos acompanham dark/light)
- **Uso e custo**: StatTiles com ícones e cursor-glow (mesmos do Painel), **DateRangePicker pt-BR** (react-day-picker v10 + date-fns, calendário duplo com presets) substituindo o input nativo que exibia datas em formato US, **granularidade Dia/Semana/Mês** com default calculado do tamanho do range (≤31d dia, ≤26sem semana, senão mês) e barras animando do eixo
- **Chat**: empty state hero com starter prompts ancorados nas tools MCP; **aura Apple-Intelligence** (conic-gradient girando via @property) no compose durante streaming; "Pensando..." com shimmer de gradiente; compose reestruturado como container único (textarea + barra de ações interna, Enviar↔Parar contextuais); **órbita de contexto** — medidor na linguagem do orb (lua percorre órbita tracejada com rastro em gradiente, núcleo respira e esquenta accent→âmbar→vermelho, ≥90% pulsa e clique inicia nova sessão); popover de histórico redesenhado; markdown do assistente com tipografia completa via seletores arbitrários; **echo otimista corrigido** (refresh da sessão não engole mais a mensagem recém-enviada)
- **Onboarding**: fundo AuroraField (canvas 2D, blobs da marca com mola seguindo o pointer; `multiply` no light / `lighter` no dark — contraste correto nos dois temas)
- **Tabs com ícones** (Assistente e Config) e headers de card padronizados (CardTitle + ícone accent, min-h uniforme)
- Cascade layers: CSS legado em @layer legacy (legacy < theme < base < utilities) durante a migração — camada legacy hoje contém apenas tokens
- **Correções achadas em teste E2E real**: download de arquivos acentuados (RFC 6266), keyframes × propriedade translate do Tailwind v4, tokens @theme circulares, scan em loop na fila de upload, buttonface/borda nativos de button, scrollbar clara no dark, contraste light (--text-tertiary 3.4:1 → 4.55:1 AA)
- prefers-reduced-motion respeitado em todas as animações; navegação 100% por teclado no shell
- Novas deps frontend: react-day-picker, date-fns
- Testes: 126 frontend (15 novos na fase) + 479 backend

---

## [0.18.0] -- 2026-07-16

### UI Foundation: Tailwind + primitivas temadas + quebra do App.tsx (Fase 5 do plano rag_hibrido_permissoes_ui_v2)

- **Tailwind v4 (CSS-first)** via `@tailwindcss/vite`, **sem preflight** — o CSS legado convive intacto até o fim da Fase 6; só utilities + tokens
- **Tema 100% custom desde o dia 1** (`src/styles/theme.css`): `@theme inline` referencia os CSS vars existentes (accent `#ff5a36`, superfícies dark, DM Sans/Fragment Mono, radius/easings) — fonte única de verdade, dark/light automático via `data-theme`; nova paleta de gráficos `--chart-1..8` na marca (dark + light)
- **14 primitivas `components/ui/`** (copy-in estilo shadcn, temadas, zero cinza default): Button (cva, 6 variantes), Card, Dialog (glass overlay), DropdownMenu, Popover, Tooltip, Tabs (pill com accent), Input/Textarea, Select, Badge (inclui variante púrpura p/ semântico), Separator, Skeleton (shimmer na direção de leitura), ScrollArea, Command (cmdk) + Toaster (sonner) + `EmptyState`/`ErrorState` próprios
- **Quebra do App.tsx** (1.379 → shell): `SettingsContext` (tema, modelos, LLM keys, persistência), `NavigationContext` (view + hash sync `#/painel` — deep-link sem react-router), `ProjectContext` (projects/selected/labels — mata prop-drilling), hooks `useSearch` (⌘K + busca completa) e `useChatSession` (mensagens, sessões, usage, SSE); App virou providers + AppShell
- **Piloto migrado**: ConfigView agora em Tabs/Card/Input/Button temados (prova do tema); aba Acesso com a API key
- Testes: +7 das primitivas ui; 111 frontend verdes; build Vite ok

---

## [0.17.0] -- 2026-07-16

### Permissões mínimas: API key + escopo de projeto (Fase 4 do plano rag_hibrido_permissoes_ui_v2)

- **Novo `app/auth.py`**: `require_auth` como dependency global do app (Bearer/`X-API-Key`/query `api_key` para SSE e links de download), comparação em tempo constante (`secrets.compare_digest`, sem early-return), `AuthContext(name, allowed_projects)` e `enforce_project_scope` → 403
- **`API_AUTH_ENABLED=false` por default** — backward compat total; `/health` e preflight CORS nunca exigem key
- **Escopo por projeto aplicado** em: search (filtro `terms` quando a key é restrita), `/api/search/chunks`, `/api/projects` (lista filtrada), `/api/stats`, `/api/documents` (lista + get/chunks por doc), download (1º segmento do path), upload/inbox/scan/history, triagem, reconcile por projeto, move, chat (project_id do body), classifier override, initialize
- **Keys em `config/api_keys.json`** (fora do git; template `config/api_keys.example.json`; cache por mtime); MCP usa `ATLASFILE_API_TOKEN` (api_client já enviava Bearer); porta 8001 do MCP não valida key — manter interna
- **Frontend**: wrapper `apiFetch` injeta `Authorization: Bearer` de `localStorage("atlasfile_api_key")` (52 chamadas migradas); URLs de SSE/download anexam `api_key`; nova aba **Config → Acesso** para gravar a key; 401/403 exibem aviso via handler global
- Validação live: sem key 401, key errada 401, key ok 200, projeto fora do escopo 403, busca sem projeto filtrada ao escopo da key
- Testes: 8 novos de auth + 3 de triagem ajustados (AuthContext explícito)

---

## [0.16.0] -- 2026-07-16

### Busca híbrida BM25 + kNN + RRF com rerank opcional (Fase 3 do plano rag_hibrido_permissoes_ui_v2)

- **Novo `app/search_hybrid.py`**: braço semântico (kNN filtrado no `atlasfile_chunk_vectors`, agregado por documento com top-3 chunks como evidências), fusão RRF manual determinística (OpenSearch 2.17 sem RRF nativo; módulo isola o ponto de troca para ≥2.19), rerank opcional por **cross-encoder ONNX via fastembed** (sem torch; decisão ajustada após verificação SOTA — cross-encoder supera LLM listwise em custo/latência)
- **`GET /api/search` ganha `mode`**: `hybrid` (default), `lexical`, `semantic`; fallback silencioso para lexical quando embeddings indisponíveis, com `search_mode_effective` na resposta; docs achados só via kNN entram com evidências `match_type: "semantic"`; paginação pós-fusão sobre o top-N fundido
- **Novo `GET /api/search/chunks`** + **tool MCP `semantic_search_chunks`**: chunks crus com location/filename para RAG com citações; `search_documents` (MCP) ganha `mode`
- **Novo `scripts/benchmark_retrieval.py`**: Recall@5/MRR/NDCG@10 por modo contra golden set de queries pt-BR (`_ATLASFILE/retrieval_golden_set.jsonl`; template em `config/retrieval_golden_set.example.jsonl`) — decisões de RRF k e rerank passam a ser mensuráveis no corpus real
- **Frontend**: badge "semântico" (aura púrpura) em evidências vindas do braço vetorial; tipos atualizados
- **Settings novos**: `SEARCH_HYBRID_ENABLED`, `SEARCH_KNN_K`, `SEARCH_RRF_RANK_CONSTANT`, `SEARCH_RERANK_ENABLED`, `SEARCH_RERANK_MODEL`, `SEARCH_RERANK_TOP_N`
- Testes: 16 novos (RRF, filtros, braço semântico, rerank, integração do endpoint)

---

## [0.15.0] -- 2026-07-16

### Camada semântica: embeddings + índice de vetores (Fase 2 do plano rag_hibrido_permissoes_ui_v2)

- **Novo `app/embeddings.py`**: providers plugáveis — `openai` (text-embedding-3-small, dim 1536, batching, tokens rastreados) e `fastembed` (local/ONNX, `intfloat/multilingual-e5-small` dim 384 com prefixos query/passage; lazy import com erro claro; dependência opcional em `requirements-local-embeddings.txt`)
- **Novo índice `atlasfile_chunk_vectors`** (1 doc por chunk, knn_vector hnsw/cosinesimil/engine lucene — filtered k-NN no OpenSearch 2.17): metadados duplicados por chunk (project_id, business_domain, document_type, doc_kind, tags, datas) para k-NN filtrado; `_meta` com provider/modelo/dimensão e alerta em divergência (nunca recria sozinho). Zero reindex do índice principal
- **Ingestão e reconcile geram embeddings**: `index_document_chunks_embeddings` com skip incremental por sha256+provider+modelo; falha de embedding nunca quebra ingestão (doc flagado com `embedding_status`); reconcile faz backfill de docs sem vetores e remove vetores órfãos (doc removido e projeto órfão)
- **Novo `scripts/backfill_embeddings.py`**: migração do corpus já indexado; idempotente, flags `--project` e `--force`
- **Custos**: `text-embedding-3-small` ($0.02/1M input) em `config/usage_costs.json`; uso gravado no índice de training usage com `script_name: embeddings_ingest|embeddings_backfill`
- **Settings novos**: `EMBEDDING_ENABLED`, `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION`, `EMBEDDING_BATCH_SIZE` (documentados em `.env.example`/INSTALL.md)
- Testes: 15 novos (providers/factory, ensure do índice, indexação/skip/falha, custo)

---

## [0.14.0] -- 2026-07-16

### Remoção do modo de classificação `setfit`

- **Modos suportados agora são 3**: `bootstrap`, `sparse_logreg` e `llm`. O `setfit` perdia do `sparse_logreg` no benchmark, nunca era servido em ingestão por padrão e era o único usuário de torch/transformers/setfit/sentence-transformers (~545 MB no venv)
- **Dependências removidas** de `requirements.txt`: `setfit`, `sentence-transformers`, `transformers` (imagem Docker do backend encolhe)
- **Saneamento automático de registry legado**: `registry.json` persistido com `champion_mode`/`fallback_mode: "setfit"` é rebaixado na carga para `sparse_logreg` (se houver artefato) ou `bootstrap`, com warning; entradas `setfit` em `benchmark_enabled_modes` e `champion_summary` são removidas e o registry saneado é persistido
- **Arquivos deletados**: `backend/app/classifier_setfit.py`, `backend/tests/unit/test_classifier_setfit.py`
- **Frontend**: `setfit` removido de `OperationalClassifierMode` e das listas/labels do IngestTriageCard
- **Dados preservados**: `_ATLASFILE/classifier/models/setfit/` não é deletado — apenas ignorado
- Parte da Fase 1 do plano `rag_hibrido_permissoes_ui_v2`

---

## [0.13.0] -- 2026-04-08

### Upload de arquivos via frontend

- **Drag-and-drop + file picker**: zona de upload no Painel envia multiplos arquivos para `_INBOX_DROP/` via HTTP
- **Lista de arquivos enviados**: estado done mostra cada arquivo com botao × para remover da inbox
- **Persistencia**: inbox carregada do backend ao montar — arquivos permanecem visiveis entre trocas de aba
- **Endpoints**: `POST /api/ingest/upload`, `GET /api/ingest/inbox`, `DELETE /api/ingest/upload/{filename}`

### Move de documentos

- **Endpoint move**: `POST /api/documents/{project_id}/{doc_id}/move` com integracao training pool
- **MoveDocumentModal**: modal compartilhado com seletores bd/dt, confirmacao e erro inline
- **Dois pontos de entrada**: botao [Mover] nos resultados de busca + icone na tabela Processamentos
- **Todas as decisoes**: move habilitado para AUTO, TRIAGEM, aprovados e corrigidos (exceto DUP e error)
- **Ingest history**: triage approve/correct/reject e move atualizam `ingest_history.json`

### Refatoracao e componentizacao

- **`_relocate_document()`**: funcao extraida do triage para reuso pelo move
- **`PainelView`**: extraido do App.tsx (~280 linhas removidas)
- **`IngestHistoryCard`**: tabela Processamentos extraida do IngestTriageCard, movida para o Painel
- **`FileUploadZone`**: componente de upload com estados idle/dragover/uploading/done/error

### Fixes

- **Reconcile incremental**: comparacao de skip agora inclui `path` — detecta renomeacoes de arquivo
- **`build_corpus.py`**: `_load_existing_labels` usa ultimo registro por SHA256 (correcoes sobrescrevem)
- **`.gitignore`**: `_ATLASFILE/` adicionado para evitar artefatos de runtime no repo
- **Teste isolado**: `test_build_corpus_last_label_wins` usa `tmp_path` em vez de poluir o repo

---

## [0.12.0] -- 2026-04-06

### Evolucao UI — arquitetura de informacao e refinamento visual

- **Navegacao reestruturada**: 3 views por frequencia de uso — Painel (diario), Assistente (consulta), Configuracao (setup)
- **Painel**: KPIs com contagem de triagem pendente, TriageQueue em destaque, InboxScanCard + Reconciliar INDEX, atividade recente
- **Configuracao**: sub-tabs Perfil do projeto, Classificador, Templates (antes view isolada)
- **Templates integrado**: deixa de ser view top-level, agora sub-tab contextualizada junto ao perfil

### Decomposicao de componentes

- **IngestTriageCard**: triage queue extraida (TriageQueue.tsx), scan extraido (InboxScanCard.tsx), hooks SSE (useIngestMonitor, useClassifierCycleMonitor)
- **App.tsx**: Topbar, SearchModal, AssistenteView extraidos como componentes independentes
- **Novos componentes**: Skeleton (loading shimmer), EmptyState, ToastContext (notificacoes)

### Refinamentos visuais

- **Tipografia**: DM Sans como body font (15px), Fragment Mono reservado para dados numericos (KPIs, tabelas, badges)
- **Espacamento**: content/cards com padding e gap aumentados para sensacao editorial
- **Motion**: hover elevation em cards, button active scale(0.97), entrance animation com reduced-motion support
- **Charts**: animacoes Recharts ativadas (600ms), container com gradient background, titulo DM Sans
- **Tabelas**: row hover, header uppercase normalizado, zebra striping, total row com background
- **Chat compose**: textarea harmonizado com tema dark, focus ring accent, botoes alinhados
- **Modal overlay**: fix position:fixed quebrado por transform residual de animation fill-mode
- **CompanionOrb**: tamanho aumentado de 40px para 48px no topbar

### Testes

- 94 testes passam (vitest)
- Build TypeScript limpo
- Smoke test visual em Docker

---

## [0.11.0] -- 2026-04-03

### Uso e custo — precisao e visibilidade

- **Fix custo truncado**: `formatUsd` trocado de `Math.floor` para `Math.round` — $0.0567 agora mostra $0.06 (antes: $0.05)
- **Contagem de chamadas API**: novo campo `api_call_count` rastreado no orchestrator (OpenAI e Anthropic), persistido por sessao, exposto no endpoint `/api/usage/summary`
- **Treinamento: chamadas reais**: `records_processed` exposto como `total_api_calls` e `api_call_count` no endpoint `/api/usage/training` — benchmark_llm agora mostra 62 chamadas (antes: 1)
- **Card "Chamadas API"**: novo card no dashboard somando chamadas de todos os processos (assistente + classificacao + treinamento)
- **Colunas renomeadas**: "Chamadas" → "Chamadas API" nas tabelas de treinamento e classificacao

### Grafico diario — todos os processos

- **by_day nos endpoints**: `GET /api/usage/training` e `GET /api/usage/classification` agora retornam `by_day` via `date_histogram` do OpenSearch
- **Aba "Por tipo"** (default): barras empilhadas Input/Output/Cache Read/Cache Write somando todos os processos
- **Aba "Por processo"** (nova): barras empilhadas Assistente/Classificacao/Treinamento com cores dedicadas
- **Aba "Total" removida**: redundante (total ja exibido acima de cada barra)
- **Legenda lateral sincronizada**: "Tokens por tipo" / "Tokens por processo" alterna com a aba selecionada

### Cache tokens da OpenAI

- Captura de `prompt_tokens_details.cached_tokens` (cache read) em `_run_chat_openai`, `_classify_openai` e `benchmark_llm_candidate`
- Antes: campo ignorado, sempre 0 para OpenAI

### Testes

- Novo: `test_orchestrator_api_call_count.py` (6 testes)
- Novo: `UsageView.test.tsx` (12 testes — formatUsd, formatUsd4, formatTokens)
- Atualizados: testes de integracao para endpoints training e classification com by_day e api_call_count

---

## [0.10.0] -- 2026-04-02

### Gráficos no chat

- **ChartBlock** (Recharts): 8 tipos de gráfico renderizados inline no chat — bar, stacked_bar, horizontal_bar, pie, line, area, composed, treemap
- **Renderer server-side** (matplotlib): gráficos enviados como PNG via `send_photo` no Telegram e no mirror web→Telegram
- **System prompt** com instruções de geração de gráficos e guia para cruzamento de dimensões (stacked_bar)
- Fix flicker: `MARKDOWN_COMPONENTS` como constante de módulo + `React.memo` + `isAnimationActive={false}`

### Custos de treinamento / pipeline

- Novo índice OpenSearch `atlasfile_training_usage` com helper `persist_training_usage()`
- Instrumentação de custos em: `benchmark_llm_candidate` (ciclo via UI), `label_corpus_llm.py`, `classifier_augmentation.py`, `run_augmentation.py`
- Endpoint `GET /api/usage/training` com agregação por modelo e por script
- UsageView: card "Treinamento", tabelas de 5 colunas alinhadas, total tokens consolidado (assistente + classificação + treinamento)

### CompanionOrb

- Orb animado com mecânica orbital Kepleriana substituindo avatar estático do assistente no chat

### Correções

- `config/usage_costs.json` atualizado com preços corretos de abril/2026 (OpenAI e Anthropic)
- Opus 4.6: $15/$75 → $5/$25; gpt-4.1: $2.50/$10 → $2/$8; gpt-5.1: $5/$15 → $1.25/$10; Haiku 4.5: $0.80/$4 → $1/$5
- Cache read/write adicionados para OpenAI; cache write Anthropic ajustado para tier 5min (1.25x input)

---

## [0.9.0] -- 2026-04-02

### Pipeline de dados

- Corpus unificado com dedup SHA256: ~363 documentos únicos (de 401 arquivos), 14 tipos, 11 domínios
- Splits estratificados 70/15/15 (`build_corpus.py`, `build_splits.py`, `label_corpus_llm.py`, `inject_training_records.py`)
- Data leakage eliminado: 24 SHA256 duplicados entre treino e validação removidos
- `evaluation_dataset.py`: `splits_available()`, `load_split_as_training_records()`, `load_split_as_validation_entries()`

### Classificação — expansão para 4 modos

- **SetFit/ModernBERT** (`classifier_setfit.py`, 489 linhas): two-phase training em subprocesses isolados (spawn), OOM fix com truncagem em 2000 chars para encode/predict
- **LLM Classifier** integrado ao ciclo via `benchmark_llm_candidate()` (OpenAI/Anthropic, texto integral 20k chars)
- **sparse_logreg** melhorado: FeatureUnion char n-grams (3-5) + word n-grams (1-2), gate graduado (≥2 amostras com warning), `LinearSVC` removido
- **Bootstrap** como campeão: 87.1% domain / 93.5% type / 82.3% exact match
- Modos de benchmark configuráveis e persistidos via `benchmark_enabled_modes` no registry
- Bootstrap pode ser desmarcado — cada modo é opcional
- Herança de métricas: modos pulados preservam valores do ciclo anterior no relatório (`inherited_from_report_id`)

### Ciclo ML

- `_MAX_EXTRACT_CHARS`: 50.000 → 20.000 (alinhado ao "Lost in the Middle" ACL 2024)
- `extract_feature_text`: truncamento arbitrário `[:4000]` removido — texto completo ao modelo
- `_cross_validate_sparse()` com `StratifiedKFold(n_splits=5)`
- Progresso dinâmico por modo habilitado com phases granulares (`extracting`, `baseline:{mode}`, `benchmark:{mode}`)
- Cancelamento de ciclo: `DELETE /api/classifier/cycle` com `threading.Event` e `InterruptedError`

### API

- `PUT /api/classifier/benchmark-modes` — configurar modos habilitados
- `DELETE /api/classifier/cycle` — cancelar ciclo em andamento (202)
- `DELETE /api/classifier/reports/{report_id}` — excluir relatório (protege campeão ativo, 409)
- `GET /api/classifier/status` inclui `benchmark_enabled_modes`

### Frontend

- Barras de progresso SSE para scan INBOX e ciclo do classificador (mesmo padrão visual de Reconciliar INDEX)
- "Evolução recente" em tabela compacta com data formatada, campeão, exact, bd F1 e botão de delete por relatório
- Cancelar ciclo: botão com popover de confirmação e estado "Cancelando..."
- Modos pulados esmaecidos (opacity 0.45) com métricas reais do ciclo anterior
- Sync bidirecional do combobox "Modelo triagem" entre card Ingestão e modal Configurações
- Cabeçalho simplificado: removidos campos técnicos (Versão/Última), adicionado contador de pendentes
- Badges accent pill em "Classificador operacional" e "Processamentos"
- Card renomeado para "Perfil e Organização" com empty state alinhado ao estilo ITC
- Espaçamentos dos colapsáveis alinhados entre cards ITC e Perfil e Organização

### Augmentation (feature flag desabilitada)

- `classifier_augmentation.py` (453 linhas): augmentação sintética via LLM para classes sub-representadas
- `AugmentationConfig` no profile schema e template default

### System prompt de classificação

- Instrução explícita para analisar conteúdo (não apenas nome do arquivo)
- `document_types` do projeto injetados no contexto do LLM
- `explanation` obrigatória em todos os casos

### Testes

- 4 novos arquivos: `test_classifier_augmentation.py`, `test_classifier_setfit.py`, `test_corpus_splits.py`, `test_inject_training_records.py`
- **Total: 403 backend + 71 frontend = 474 testes**

### Docs

- Benchmark card completo com dados do ciclo `cycle_20260401_194500_343482` (4 modos, accuracy + F1-macro por eixo)
- Fundamentação SOTA: F1-macro vs accuracy, exact_match como critério de promoção, StratifiedKFold
- Justificativa sparse_logreg vs LinearSVC, XGBoost, BERT, SetFit

### Removido

- `frontend/mockup-chat-ui.html` (protótipo HTML não usado)
- `sparse_linear_svc` dos modos suportados

---

## [0.8.1] -- 2026-03-28

### Extração de PDF

- Migração do motor de extração PDF de `pypdf` para `pymupdf` com parsing espacial via bounding boxes
- Nova função `_spatial_extract_page`: agrupa spans por proximidade vertical (Y), ordena por X dentro de cada linha e reconstrói colunas com padding espacial
- Benchmark em 10 PDFs reais (216 QA pairs): qualidade equivalente (~76%), 3.5x mais rápido, 4.2x menos memória; em PDFs grandes (244p) pymupdf foi 64x mais rápido
- OCR fallback (pdf2image + Tesseract) inalterado — acionado quando texto nativo < 50 chars
- Interface `ExtractionResult` inalterada — zero impacto em consumidores (indexer, classifier)

### Testes

- 5 testes novos de PDF: multipage, metadata pages, max_chars early stop, empty page skipped, OCR fallback
- **Total: 365 backend + 71 frontend = 436 testes**

### Docs

- Projeto de benchmark independente em `extractor-benchmark/` com corpus, providers, ground truth e scripts de avaliação
- Sessão de decisão registrada em `docs/claude_chats/`
- Planos concluídos renomeados com nomes descritivos em `docs/planos_concluidos/`

---

## [0.8.0] -- 2026-03-20

### Ciclo operacional do classificador

- registry persistido em `_ATLASFILE/classifier` com `champion_mode`, ultimo report, gates de promocao e override por projeto
- novo fluxo de `benchmark + retreino` pela API/UI, com reports versionados, artefatos sparse persistidos e politica `auto_best_with_ui_override`
- ingestao passa a servir o modo efetivo do classificador (`bootstrap`, `sparse_logreg`, `sparse_linear_svc`) com fallback explicito para `bootstrap` quando o artefato supervisionado estiver ausente ou falhar
- datasets operacionais consolidados em `_ATLASFILE/classifier/datasets` como fonte fisica unica; o runtime nao copia mais `validation_set`/`training_pool` a partir do repo
- status em tempo real do ciclo do classificador e do processamento da INBOX corrigidos no frontend, sem reload manual
- scorecards por documento, override manual e estado operacional exibidos na UI sem expor `baseline` como modo publico

### Naming, triagem e indice

- corte do contrato publico legado `area_key` / `{area}` para `business_domain` nas superficies ativas, hints de UI, template/profile e validacao de schema
- `decide_triage()` agora recomputa `canonical_filename` em `correct`, preserva data de ingestao e versao e regrava o metadata resolvido
- `_INDEX.md` passa a ser atualizado por `doc_id`, mantendo `corrected` / `rejected` consistentes com filesystem e OpenSearch
- runtime do profile passa a incluir `naming`, evitando divergencia entre profile salvo e nome canonico aplicado na ingestao

### Docs e validacao

- `docs/plano_teste_e2e_v0.8.0.md` registrado como delta do `0.7.0`, com rerun usando o mesmo lote real de arquivos e evidencia do fix de streaming
- fixture mínima de `validation_set` mantida em `backend/tests/fixtures/classifier_datasets` apenas para um teste de integração, sem versionar cópia completa dos datasets operacionais
- `README.md` e docs tecnicos atualizados para o contrato `business_domain`, ciclo do classificador, fonte unica em `_ATLASFILE` e fixture mínima de teste dedicada
- novas regressions backend/frontend para naming, triagem, `_INDEX.md` e streaming de INBOX/ciclo

---

## [0.7.0] -- 2026-03-18

### Classificação e benchmark

- `bootstrap` consolidado como classificador operacional atual em `business_domain` + `document_type`
- refatoração config-driven do bootstrap: `classification.*` e `default.json` passam a ser a fonte de verdade da política de negócio; remoção de `DEFAULT_*` e fallback silencioso
- taxonomia expandida com `suprimentos` em `business_domain` e `edital` / `plano` em `document_type`
- `config/validation_set` e `config/training_pool` operacionalizados como artefatos distintos
- decisões de triagem `approve` / `correct` alimentam `config/training_pool/records.jsonl`
- benchmark oficial (`backend/scripts/benchmark_classification.py`) endurecido com:
  - checagem de integridade entre `validation_set` e `training_pool`
  - gates de elegibilidade do supervisionado
  - accuracy, macro-F1, recall por classe e matriz de confusão por eixo
- `sparse_logreg` e `sparse_linear_svc` seguem como candidatos de benchmark; promoção automática não foi introduzida neste release

### Busca, índice e assistente

- busca prioriza nome de arquivo e título exatos acima de ruído de score/evidências
- chat web passa `project_id` explicitamente ao orquestrador e às tools MCP compatíveis
- Telegram ganha `/projeto <project_id>` para fixar ou limpar o escopo de projeto no chat
- `/api/search`, `/api/stats`, triagem e UI operam de forma consistente com `business_domain` / `document_type`

### Operação e datasets

- `training_pool` desacoplado dos projetos físicos para benchmark reproduzível a partir de `config/training_pool/files`
- limpeza do estado operacional para manter apenas projetos úteis de validação do fluxo
- `validation_set` ampliado para cobrir classes antes sub-representadas sem sobreposição com o `training_pool`

### Docs

- novo roteiro `docs/plano_teste_e2e_v0.7.0.md`, orientado a teste via frontend e fiel ao estado implementado
- planos concluídos do ciclo arquivados em `docs/planos_concluidos/`
- `README.md` atualizado para refletir bootstrap operacional, datasets de benchmark e layout por `business_domain/document_type`

---

## [0.6.0] -- 2026-03-12

### Canais transparentes

- Telegram (e futuros canais) opera como pipe transparente: sessões, histórico e usage/custo compartilhados com o chat web
- Session manager para canais: busca sessão ativa por `(channel, chat_id)` no OpenSearch, timeout configurável (`channel_session_timeout_minutes`, default 30min)
- Comando `/novo` no Telegram para forçar nova sessão
- Concorrência por `asyncio.Lock` per `chat_id` (single-instance)
- Campo `channel` e `channel_chat_id` em `ChatSession`; campo `channel` per-message em `StoredChatMessage`
- Migração automática no startup: sessões existentes sem `channel` recebem `channel='web'` via `update_by_query`
- Campo `channel` opcional nos modelos (sem fallback mascarado; UI exibe "—" quando ausente)

### Rastreamento de uso LLM na classificação

- Novo índice OpenSearch `classification_usage` com mapping dedicado (doc_id, filename, project_id, provider, model, tokens, custo)
- `_classify_openai` e `_classify_anthropic` capturam `resp.usage` (input/output/cache tokens + custo estimado)
- `_persist_classification_usage` persiste uso no OpenSearch após cada classificação na ingestão
- Novo endpoint `GET /api/usage/classification` com agregação por período, projeto e modelo
- Card "Classificações" e seção "Classificação (uso LLM na ingestão)" no UsageView
- Custo total na aba "Uso e custo" agrega sessões do assistente + classificação

### Gestão de janela de contexto

- `_trim_history_to_context`: truncamento FIFO automático a 60% da janela do modelo (reserva 20% para tools, 20% para resposta)
- `_estimate_context_pressure`: estimativa de pressão de contexto retornada em cada resposta do `POST /api/chat`
- `get_context_tokens` no `llm_catalog.py`: lookup da janela de contexto por provider/modelo a partir do `LLM_MODEL_CATALOG`
- Modelo `ContextPressure` (context_tokens_estimate, context_tokens_limit, context_pressure_ratio)
- Componente `ContextRing` no footer do ChatPanel: indicador circular de pressão de contexto
  - 0-50%: neutro (cinza), 50-75%: atenção (amarelo), 75-100%: alerta (vermelho)
  - Tooltip a 90%: "Contexto quase cheio. Considere iniciar nova sessão."

### UsageView

- Filtro "Canal" (Todos / Web / Telegram) nos endpoints e na UI
- Coluna "Canal" na tabela de sessões
- Filtro de projeto unificado com o seletor global do header (removido filtro duplicado local)

### Sincronização cross-channel e espelhamento

- Append atômico de mensagens via `append_messages` no PATCH — elimina overwrite destrutivo quando web e Telegram operam na mesma sessão
- Refresh automático antes de enviar: frontend busca mensagens frescas do backend (`getChatSession`) antes de montar contexto para o LLM
- Espelhamento configurável: respostas enviadas via web em sessões originadas no Telegram são encaminhadas ao Telegram (mensagem do usuário com prefixo 🌐, resposta do assistente com conversão Markdown→HTML)
- Toggle "Espelhar respostas para o Telegram" na configuração de canais (default: off)
- `send_message` do Telegram aplica `_md_to_tg_html()` para conversão automática de Markdown para HTML do Telegram
- Proteção anti-loop: `source_channel` no PATCH impede espelhamento quando a origem é o próprio canal

### Atualização em tempo real (SSE)

- Event bus in-memory via `asyncio.Event` por sessão — notifica clientes SSE quando a sessão é modificada por outro canal
- Endpoint SSE `GET /api/chat/sessions/{id}/events` com keepalive a cada 25s
- `_notify_session_update` disparado no PATCH (web) e no `_handle_channel_message` (Telegram)
- Frontend abre `EventSource` quando uma sessão está ativa; atualiza mensagens, usage e by-model em tempo real
- Cleanup automático do Event ao desconectar

### Bug fixes

- Responsividade da tabela Sessões na aba "Uso e custo": `nowrap` em Data/Modelo, `text-overflow: ellipsis` no Título
- Remoção de fallback que mascarava sessões sem canal como "web" — exibe "—" quando `channel` é nulo

### Testes

- 4 novos arquivos de teste: `test_api_channel_features.py`, `test_context_management.py`, `test_llm_catalog_context.py`, `test_persist_classification_usage.py`
- 3 novos arquivos: `test_mirror_channel.py` (6 testes — mirror fires/skip/disabled/user-only/no-content), `test_session_events.py` (4 testes — event bus), `test_api_session_sse.py` (3 testes — SSE generator)
- 2 novos testes em `test_api_chat_sessions.py`: append atômico e conflito messages+append_messages (400)
- **Total: 339 backend + 69 frontend = 408 testes**

### Docs

- `docs/planos_concluidos/`: 5 planos movidos (canais_transparentes, fix_cross-channel_session_sync, fix_usage_cost_tracking, search_ui_mintlify_redesign, docx_pagina-paragrafo)
- `docs/07_rollout_kpis.md`: fases 2 e 3 marcadas como concluídas; nova fase 4 (Canais e observabilidade) adicionada

---

## [0.5.0] -- 2026-03-09

### Uso e custo do Assistente

- Nova aba "Uso e custo" no Assistente com visão consolidada de tokens e custo estimado por período, projeto e modelo
- Tabela "Por modelo" com breakdown de input/output tokens e custo (4 casas) por modelo, linha de totais
- Tabela "Sessões" com tokens e custo por sessão, paginação de 10 em 10
- Gráficos "Uso diário de tokens" (barras empilhadas por tipo) e "Tokens por tipo" (barra horizontal proporcional)
- Datas no formato brasileiro (dd/mm/aaaa) nos filtros de período
- Coluna Modelo nas sessões exibe modelos sem prefixo de provider; sessões multi-modelo listam todos (ex: "gpt-4.1, gpt-5.1")

### Rastreamento de uso por sessão

- Cada resposta do LLM retorna `usage` (input/output/cache tokens + custo estimado) ao frontend
- `usage_totals` e `usage_by_model` acumulados e persistidos por sessão no OpenSearch
- Sessões multi-modelo rastreiam tokens e custo separadamente por modelo usado
- Tokens de geração de título (background) acumulados na sessão correspondente
- Backend `GET /api/usage/summary` agrega tokens por tipo (input, output, cache_read, cache_write) por dia e por modelo

### Custo configurável por modelo

- Arquivo `config/usage_costs.json` com preços $/1M tokens por provider/modelo (input, output, cache_read, cache_write)
- Módulo `backend/app/usage_costs.py`: `get_cost_per_1m()` e `estimate_usage_cost()` — zero hardcoded
- Preços incluem cache read/write para Anthropic (prompt caching)

### Autosave de sessão

- Sessão criada automaticamente após a 1ª resposta do LLM (sem necessidade de clicar "+")
- Título derivado da primeira mensagem do usuário; título LLM gerado em background (se habilitado)
- Botão "+" sempre inicia nova conversa (sessão atual já salva)

### Identificação de modelo por mensagem

- Cada mensagem do assistente armazena o modelo que a gerou (`model` field)
- Footer do chat exibe "Assistente (gpt-4.1)" ao invés de apenas "Assistente"
- Retrocompatível: mensagens antigas sem `model` exibem "Assistente"

### UI/UX

- Abas "Chat" / "Uso e custo" em estilo segmented control (pill)
- Formatação de custo: totais com 2 casas decimais (truncado), componentes input/output com 4 casas
- Estilos do UsageView alinhados com o design system do App (sem CSS customizado conflitante)

---

## [0.4.0] -- 2026-03-06

### Canais de comunicação (Telegram)

- Camada nativa de channels no backend: módulo plugável `backend/app/channels/` com protocol `Channel`, `ChannelManager` e `TelegramChannel`
- Canal Telegram via **aiogram 3.x** (long-polling async), rodando dentro do mesmo processo FastAPI (zero containers novos)
- Mensagens inbound do Telegram despachadas diretamente para `run_chat_loop()` (zero hop HTTP, latência mínima)
- Endpoints REST: `GET/PUT /api/channels/config`, `GET /api/channels/status`, `POST /api/channels/test`
- UI: seção "Canais de comunicação" no modal de configuração do assistente com toggle, bot token (mascarado) e indicador de status em tempo real
- Placeholders visuais para Discord e Slack ("Em breve")
- Configuração via env vars (`CHANNELS_ENABLED`, `TELEGRAM_ENABLED`, `TELEGRAM_BOT_TOKEN`) e via API (PUT com restart automático)
- Falha no channel startup não impede o backend de subir (canais são opcionais)
- Testes unitários e de integração para o módulo channels e endpoints

### Formato canônico configurável

- Pattern de nomeação canônica configurável via `naming.canonical_pattern` no template/profile
- Nome original do arquivo preservado intacto (case, acentos, underscores) — apenas chars inválidos de filesystem removidos
- Campos disponíveis: `{date}`, `{project}`, `{area}`, `{original_name}`, `{document_type}`
- Sufixo `__v{version}{ext}` sempre adicionado automaticamente
- Pattern default simplificado: `{date}__{project}__{original_name}` (removido `area_key` do nome)
- Migração automática: arquivos no formato antigo (`__proj__area__title__`) renomeados para novo formato durante reconciliação
- `extract_original_name_from_canonical()`: parsing reverso robusto do nome original a partir do formato canônico

### Listagem de documentos e ferramentas MCP

- Novo endpoint `GET /api/documents`: listagem/browse de documentos com filtros (`project_id`, `doc_kind`, `document_type`, `area_key`) sem necessidade de query textual, com paginação
- Nova tool MCP `list_documents`: equivalente ao endpoint, usada pelo assistente para enumerar documentos de um projeto
- Guard `min_length` no MCP `search_documents`: retorna erro orientativo se query < 2 caracteres, direcionando para `list_documents`
- Modelos Pydantic: `ListDocumentItem` e `ListDocumentsResponse`

### Normalização de `project_id`

- `project_id` normalizado (sem acentos, lowercase) na criação de perfis (`profile_store.py`)
- `_resolve_project_root`: matching fuzzy com normalização de acentos, case e espaço↔underscore
- `_project_scope_filter`: aliases expandidos com variantes normalizadas para busca tolerante a acentos/case
- Agregação `by_project_id` adicionada ao endpoint `GET /api/stats`

### Arquitetura de indexação de conteúdo (Pure Nested)

- Campos flat de conteúdo removidos do mapping OpenSearch: `content`, `content_normalized`, `content_chunks_text`, `content_chunks_normalized`
- Todo o conteúdo textual agora armazenado exclusivamente em `content_chunks` (nested, ~1200 chars/chunk)
- Busca full-text migrada para nested queries com `inner_hits` e highlight por chunk
- Highlight via `inner_hits` elimina estruturalmente o erro `max_analyzed_offset` em documentos grandes (PDFs de qualquer tamanho)
- `GET /api/documents/{doc_id}`: campo `content` computado on-the-fly a partir da concatenação dos chunks
- Armazenamento reduzido ~60-70% por eliminação de 4 campos flat redundantes

### Highlighting de busca

- Dual highlight nativo do OpenSearch: `content_chunks.text` (preserva acentos) + `content_chunks.text_normalized` (fallback para queries sem acentos)
- Todas as ocorrências do termo destacadas nos snippets (antes: apenas a primeira)
- Funções de highlight manual eliminadas (`_build_evidence_snippet`, `_rehighlight_snippet`) em favor do highlight nativo do OpenSearch
- `_trim_highlight` reescrito para preservar todos os `<em>` tags dentro da janela de contexto
- Tamanho do snippet ampliado de 80 para 120 caracteres (melhor contexto sem poluir a UI)
- `number_of_fragments` aumentado de 1 para 2 nos inner_hits (cobre termos em partes distantes do mesmo chunk)
- Ordenação híbrida de evidências: trecho mais relevante (mais matches) no topo, demais em ordem sequencial do documento
- Chunks sem highlight nativo são pulados (sem snippets de texto puro sem destaque)
- Scoring passa de document-level para passage-level (melhor relevância em busca documental)
- Safety net: `max_analyzer_offset: 1_000_000` adicionado nas queries de highlight + `highlight.max_analyzed_offset: 10_000_000` nos index settings
- **Requer `RESET_INDEX=1` na atualização** (`make docker-update RESET_INDEX=1`)

### Reconciliação

- Scan de todas as roots PARA (`01_PROJECTS`, `02_AREAS`, `03_RESOURCES`, `04_ARCHIVE`): documentos em qualquer root são indexados no `_INDEX.md` e OpenSearch
- `area_key` para roots não-areas usa a categoria PARA (ex: `projects`, `resources`, `archive`); `02_AREAS` continua inferindo da subpasta
- Removido fallback legado `_WORK/`
- `cleanup_orphan_projects` integrado ao fluxo `run_reconcile` — executa automaticamente ao final
- Reconciliação default alterada para modo `incremental` (era `full`)
- Relatório de orphans (`orphan_projects_found`, `orphan_docs_deleted`) incluído no summary

### Assistente LLM

- System prompt atualizado: instruções para usar `list_documents`, obter `project_id` exato via `get_stats`, apresentar `original_filename` (não o título canônico), escopo e limites do assistente

### Onboarding

- Novo `OnboardingWizard`: wizard de primeira execução com detecção automática via `GET /api/setup/status`
- Endpoint `GET /api/setup/status`: retorna estado da instalação (`projects_root`, contagem de projetos, flag `onboarding_suggested`)

### Sessões de chat

- Save instantâneo: título gerado a partir da primeira mensagem do usuário (sem chamada LLM bloqueante); reduz latência de ~3-6s para ~200ms
- Flag `autoTitleLLM` (default desativado): se ativado, gera título via LLM em background após o save, sem bloquear a UI
- Sessão carregada do histórico não é duplicada ao clicar "Nova conversa" — apenas limpa o chat (mensagens já salvas automaticamente a cada resposta)
- Backend: PATCH `/api/chat/sessions` otimizado com `_update` parcial (em vez de GET + full INDEX)
- Configuração no modal do Assistente (checkbox "Gerar título da sessão via LLM")

### UI/UX

- Controle operacional redesenhado: layout compacto com métricas (total docs, tipos, extensões), mini-table de projetos e footer de reconciliação
- Dashboard stats carregado automaticamente na inicialização e pós-reconciliação
- Mensagem de reconciliação inclui contagem de órfãos removidos
- Classe CSS global `checkbox-inline`: fix para `flex: 1` global que distorcia checkboxes em modais

### Infraestrutura

- `make docker-update RESET_CHAT=1`: reseta índice de sessões de chat independente do índice de documentos
- `make docker-update RESET_INDEX=1 RESET_CHAT=1`: reseta ambos os índices
- `make reset-chat`: target standalone para resetar apenas sessões de chat
- Script `reset-opensearch-index.sh` refatorado com modos (`docs`, `chat`, `all`)

### Bug fixes

- Sync incremental: `project_id` agora comparado além de SHA256 — mudanças de metadados forçam reindexação
- `original_filename`: reconstruído corretamente via `extract_original_name_from_canonical()` quando `_INDEX.md` é recriado
- `cleanup_orphan_projects`: normalização de `project_id` (acentos, case, espaços/underscores) evita exclusão acidental de documentos legítimos

### Schema

- Nova seção `naming` no template e profile: `canonical_pattern`, `date_format`
- `NamingConfig` adicionado ao `profile_schema_v2.py` com validação de `{original_name}` obrigatório

### Testes

- 64+ novos testes: `fs_safe`, `build_canonical_filename`, `extract_original_name_from_canonical`, migração old→new, reconstrução de `original_filename`, normalização de orphans, `list_documents` endpoint, `project_id` normalization (14 cenários), `setup/status`, MCP `list_documents` tool, `OnboardingWizard` (14 cenários)

### Docs

- `docs/roadmap/plan_one_line_installer.md`: plano para instalador one-liner estilo OpenClaw

---

## [0.3.0] -- 2026-03-05

### Classificador

- Word boundary matching (`\b`) substituindo substring match em alias scoring e routing rules, eliminando falsos positivos (ex: "ativo" não casa mais com "interativo")
- Normalização sqrt: `hits / sqrt(len(aliases))` com cap em 1.0, inspirado no Lucene fieldNorm
- Helper `_match_normalize`: underscores e hífens convertidos em espaços para word boundary funcionar em nomes compostos (`Contrato_Servicos.pdf`)
- Routing rules completas para todas as 9 áreas (`juridica`, `financeiro`, `sistemas_migracao`, `processos_tsa`)

### LLM Visibility

- Campos `rule_area_key`, `rule_confidence`, `llm_explanation`, `llm_proposed_area` preservados na classificação
- Contexto de projeto (áreas, aliases, topics) injetado no prompt de classificação (`system_prompt_classify.md`)
- Prompt de chat enriquecido com contexto do projeto (`system_prompt_chat.md`)

### Template Management (CRUD)

- Novo `template_store.py`: store backend com templates `builtin` e `user`, CRUD completo
- API endpoints: `GET/POST/PUT/DELETE /api/templates`, `POST /api/templates/initialize`
- Novo `TemplateEditorView.tsx`: editor visual de templates (áreas, routing rules, confiança, LLM policy, indexação)
- Novo `TemplateSelectModal.tsx`: seleção de template na inicialização de projetos com opção de criar novo
- Removido `profile_v2_default.json` duplicado, consolidado em `config/templates/default.json`

### Busca e Estatísticas

- Novo endpoint `GET /api/stats`: agregações por `doc_kind`, `area_key`, `document_type`
- Filtros `doc_kind` e `area_key` adicionados à API de search

### UI/UX

- Hook `useEscapeKey`: todos os modais fecham com `Escape`
- Seções colapsáveis no editor de perfil (default: todos colapsados)
- Header harmonizado: alturas padronizadas de botões, selectors e combos
- Mobile responsiveness: largura mínima ajustada, scroll horizontal controlado
- Correção de radio buttons: override do `flex: 1` global para `input[type="radio"]`
- Modal overflow corrigido com flexbox scrollável
- `_ATLASFILE` e `.DS_Store` ocultos da listagem de projetos

### Infraestrutura

- `PROJECTS_HOST_ROOT` configurável via env var (default: `$HOME/Documents/Projects`), diretório criado se inexistente
- `.env.example` atualizado com todas as variáveis de ambiente
- `docker-compose.yml` ajustado para volume mount do `PROJECTS_HOST_ROOT`

### Testes

- 37 testes de classificador (word boundary, routing rules, sqrt scoring, aliases compostos)
- 6 testes de LLM visibility (preservação de campos rule/llm)
- 5 testes de classify context (briefing de projeto ao LLM)
- 6 testes de auto area creation (criação automática de área pelo LLM)
- 3 testes de stats endpoint (agregações)
- 10 testes de template store (CRUD, proteção default, merge builtin/user)
- **Total: 200 backend + 49 frontend = 249 testes**

---

## [0.2.0] -- 2026-03-05

### Profile V2

- Schema V2 de perfil com áreas de trabalho, routing rules, confidence thresholds, LLM policy e indexação
- `profile_store.py` e `profile_runtime.py`: gerenciamento e validação de perfis por projeto
- `profile_schema_v2.py`: validação estrutural do schema
- `area_resolver.py`: resolução de áreas com suporte a JD numbering

### Layout de Projeto

- `layout_service.py`: simulação (dry-run) e aplicação de layouts com rename, move e remoção de pastas
- `ProfileLayoutWorkspace.tsx`: workspace visual para editar estrutura de diretórios
- `ProfileLayoutEditor.tsx` e `LayoutPlanPreview.tsx`: editor e preview de plano de migração
- API endpoints `GET/PUT /api/profile`, `POST /api/profile/layout/plan`, `POST /api/profile/layout/apply`

### Ingestão e Triagem

- LLM toggle no card de ingestão: ativar/desativar LLM com seleção de modo e modelo
- `ingest_history.py`: histórico persistente em `_PROFILE/ingest_history.json` (FIFO, cap 50)
- Paginação de histórico: últimos 10 visíveis, paginado de 10 em 10
- Dedup precoce: SHA256 check antes do fluxo completo, sem cópias `_dup_*`
- `IngestTriageCard.tsx`: card completo com scan, histórico e LLM controls
- `CorrectDecisionModal.tsx`: modal para corrigir decisões de classificação

### Extração de Documentos

- Suporte a `.docx` com detecção de page breaks (explicit, last-rendered, estimated)
- Suporte a `.xlsx`, `.pptx`, `.msg`, `.zip`, `.rar` (listagem de conteúdo)
- Chunking com localização (`page:N`, `sheet:Name`, `slide:N`)
- Modo de extração `all` vs `excerpt` com `extraction_max_chars` configurável

### Topics e Enriquecimento

- `topics.py`: matching semântico de tópicos via `config/topics_v1.yaml`
- Campos `topics`, `topics_source`, `document_type`, `correspondent` derivados
- `doc_kind` inferido a partir de extensão do arquivo

### Reconciliação

- `reconcile_service.py`: reconciliação entre filesystem, index e profile
- Detecção de documentos órfãos, duplicados e ausentes

### UI/UX

- `AssistantSettingsModal.tsx`: modal de configuração do assistente (API key, modelo)
- Colapsáveis com chevrons em seções do perfil
- Responsividade mobile para header e cards
- Formatadores de busca (`searchFormatters.ts`)

### Testes

- 163 testes backend (profile layout, search, document extractor, ingest history, dedup, LLM policy, layout service, topics, reconcile)
- 49 testes frontend (App, API, IngestTriageCard, ProfileLayout, TemplateEditor)
- Scripts: `e2e_layout_scenarios.py`, `smoke-project-init.sh`

---

## [0.1.0] -- 2026-03-03

### Core

- Pipeline de ingestão: inbox drop → classificação por aliases → renomeação canônica → movimentação para área
- Classificação baseada em aliases com normalize_text (lowercase, remoção de acentos)
- Naming convention: `YYYYMMDD__proj__area__title__vNN.ext` (ver 0.4.0 para formato configurável)
- Versionamento automático de documentos duplicados (`_v01`, `_v02`, ...)

### MCP Server

- `mcp/server.py`: servidor MCP com tools `search_documents`, `get_document_chunks`, `list_projects`
- `mcp_client/client.py`: cliente MCP para integração com ferramentas externas

### Chat / Assistente

- `orchestrator.py`: orquestrador de chat com suporte a multi-modelos (OpenAI, Anthropic, Google)
- `llm_catalog.py`: catálogo de modelos com limites por provider
- Sessões de chat persistentes com histórico (`GET/POST/PUT/DELETE /api/chat/sessions`)
- `ChatPanel.tsx`: painel de chat com reasoning, markdown rendering e topbar
- System prompts configuráveis (`system_prompt_chat.md`, `system_prompt_classify.md`)

### Indexação (OpenSearch)

- `opensearch_client.py`: cliente com mapping completo (35+ campos)
- `indexer.py`: indexação de documentos com chunking e enriquecimento
- Busca full-text com highlight e suggest (autocomplete)
- API: `GET /api/search`, `GET /api/suggest`, `GET /api/documents/{id}`, `POST /api/documents/{id}/tags`

### Frontend

- SPA React + TypeScript + Vite
- Cards: Ingestão, Busca (modal + resultados completos), Chat/Assistente
- Tema claro/escuro com variáveis CSS
- Header com seletor de projeto, health check e theme toggle

### Infraestrutura

- Docker Compose: backend (FastAPI), frontend (Nginx), OpenSearch, OpenSearch Dashboards
- `atlasfile_install.sh`: instalador one-liner
- Makefile com targets: `build`, `up`, `test`, `docker-update`
- Dashboard Kibana importável (`dashboards/atlasfile.ndjson`)
- Scripts: `bootstrap_project.py`, `reset-opensearch-index.sh`, `import-dashboards.sh`

### Testes

- Pytest (backend): API health, chat models, document tags/chunks, MCP server/client
- Vitest (frontend): setup inicial

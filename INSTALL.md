# AtlasFile - Guia de Instalação (Mac, Linux e Windows)

## Instalação rápida (recomendada)

Com o [Docker Desktop](https://docs.docker.com/get-docker/) rodando:

```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.sh | bash -s -- --enable-auth
```

```powershell
# Windows (PowerShell; usa WSL2 + Docker Desktop)
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.ps1))) -EnableAuth
```

O instalador verifica pré-requisitos, baixa o **bundle da última release** em `~/AtlasFile` (~10 KB; a imagem da app, ~290 MB comprimida, vem por `docker compose pull` do ghcr.io — sem compilador, sem git), cria o `.env` (perguntando só a pasta de projetos), sobe a stack e abre a interface — o onboarding guia o resto. Flags úteis: `--dir`, `--projects-root`, `--version X.Y.Z` (pina uma release), `--from-source` (caminho de contribuidor: clone + build local), `--yes` (não-interativo), `--no-open`, `--install-deps` (instala o Docker que faltar, sem perguntar). Re-executar atualiza a instalação para a última release — instalações feitas por clone continuam no caminho de clone. **A lista completa está em `install.sh --help`.**

No **Windows** o AtlasFile é instalado dentro do WSL, mas **seus documentos ficam no disco do Windows**, na sua pasta Documentos (`…\Documents\AtlasFileProjects`) — visíveis no Explorer e independentes da distro. Flags do `install.ps1`: `-Dir`, `-ProjectsRoot`, `-Version X.Y.Z` (pina uma release), `-FromSource` (caminho de contribuidor: clone + build local; `-RepoUrl` e `-Branch` valem só com ela), `-Yes`, `-EnableAuth`, `-EnableDashboards`/`-NoDashboards` (liga/desliga a observabilidade), `-InstallDeps` (instala WSL2 e Docker Desktop sem perguntar), `-NoOpen`, `-Verbose`, e as de diagnóstico e desinstalação descritas abaixo. **A lista completa está em `install.ps1 -Help`.** O Docker Desktop é instalado em silêncio, com o contrato de licença aceito na instalação, e a integração com o WSL é ligada automaticamente.

**Modelo 100% local não faz parte da instalação**: o download são vários GB e tiraria a previsibilidade da duração. O painel final mostra o comando (`ollama pull …`) para habilitá-lo depois.

**Antes de instalar, ou quando algo der errado**, os dois instaladores têm modos que não mudam nada:

```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.sh | bash -s -- --doctor
curl -fsSL https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.sh | bash -s -- --dry-run
```

```powershell
# Windows — diagnosticam os DOIS lados: o Windows e, dentro do WSL, o Linux
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.ps1))) -Doctor
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.ps1))) -DryRun
```

`--doctor` relata pré-requisitos com versão, o manifesto do que o instalador criou nesta máquina, o estado da instalação e da stack, as portas e a pasta de documentos — e sai com código diferente de zero se algo estiver quebrado. `--dry-run` é *mostre, não faça*: sozinho relata o que uma instalação encontraria e faria aqui; combinado com `--uninstall`, o plano de remoção. `--verbose` mostra a saída das ferramentas em vez de escondê-la no log.

**Duas trilhas a partir da v1.0.0** — o guia distingue explicitamente:

- **Usuário**: o one-liner acima. A stack roda a **imagem publicada** `ghcr.io/aleonnet/atlasfile` (multi-arch, com proveniência atestada), selecionada por `ATLASFILE_VERSION` no `.env` — o instalador grava a versão; atualizar é ato deliberado, nunca um `latest` implícito.
- **Desenvolvedor/contribuidor**: clone + `make` (seções 5, 12 e 13). O build local usa o overlay `docker-compose.build.yml` e produz a imagem `atlasfile-local:dev` — bits caseiros nunca usam o nome da imagem oficial.

O restante deste guia cobre a **instalação manual** e a operação completa.

---

Este guia cobre o setup completo para qualquer pessoa rodar o AtlasFile localmente.

Para uma visão consolidada dos scripts do repositório e de quando cada um entra no processo, veja `docs/11_scripts_and_operations.md`.

---

## 1) Pré-requisitos

**O instalador cuida deles**: quando falta Docker, o `install.sh` detecta e **oferece instalar** (macOS: Homebrew + cask do Docker Desktop, abrindo o app e aguardando o daemon; Linux: script oficial get.docker.com + apt/dnf, com sudo só após confirmação). `curl` e `tar` são exigidos mas nunca instalados (todo sistema suportado os traz); git só é necessário — e só é oferecido — no caminho `--from-source`. Itens já instalados aparecem com ✔ e versão; upgrades disponíveis viram aviso informativo. Política do modo não-interativo: `--yes` sozinho **não** instala dependências de sistema (falha com instrução) — a flag `--install-deps` autoriza o bootstrap sem perguntas. O Ollama **saiu do instalador**: puxar um modelo são vários GB e transformava uma instalação de minutos em algo sem duração previsível — o painel final ensina a habilitá-lo depois, em um comando. Um Ollama instalado por versões anteriores continua sendo revertido pelo `--uninstall --remove-deps`. No Windows, o `install.ps1` oferece `wsl --install` e o Docker Desktop via winget.

### Instalação manual dos pré-requisitos (se preferir)

- Docker Desktop
  - Mac: <https://www.docker.com/products/docker-desktop/>
  - Windows: <https://www.docker.com/products/docker-desktop/>
  - Linux: <https://docs.docker.com/engine/install/>

### Validação rápida

Abra o terminal e rode:

```bash
docker version
docker compose version
```

Se os dois responderem sem erro, o Docker está pronto.

---

## 2) Obter o projeto

Clone ou copie o repositório e entre na pasta:

```bash
cd AtlasFile
```

---

## 3) Configurar variáveis de ambiente

Copie o arquivo de exemplo e edite:

```bash
cp .env.example .env
```

O campo **obrigatório** é `PROJECTS_HOST_ROOT` — o path absoluto no host onde ficam seus projetos. Este diretório será montado como `/projects` dentro do container.

Esse mesmo root também passa a armazenar o estado operacional compartilhado do AtlasFile em `PROJECTS_HOST_ROOT/_ATLASFILE/`, incluindo registry, reports, models e datasets vivos do classificador.

### Exemplos

O nome da pasta é livre, mas os exemplos usam `AtlasFileProjects` porque é **o mesmo default do instalador** — quem instalou pelo one-liner e quem instalou à mão acabam no mesmo lugar, e as instruções de suporte servem para os dois.

```bash
# macOS
PROJECTS_HOST_ROOT=/Users/seu_usuario/Documents/AtlasFileProjects

# Linux
PROJECTS_HOST_ROOT=/home/seu_usuario/Documents/AtlasFileProjects

# Windows (WSL) — no disco do Windows, como o install.ps1 configura
PROJECTS_HOST_ROOT=/mnt/c/Users/seu_usuario/Documents/AtlasFileProjects
```

Se a pasta não existir, o AtlasFile a cria automaticamente no primeiro uso.

**Senhas por instalação**: o `install.sh` gera automaticamente `OPENSEARCH_PASSWORD`/`OPENSEARCH_INITIAL_ADMIN_PASSWORD` e, desde a v0.44.0, `DASHBOARDS_COOKIE_PASSWORD` (chave que encripta o cookie de sessão do Dashboards — com chave própria, cookie de uma instalação anterior vira redirect limpo de login em vez de erro 500). Na instalação manual, defina as três no `.env` — a de cookie com **32+ caracteres**. Quem atualiza uma instalação existente via `git pull` não precisa fazer nada: `make docker-up`/`make docker-update` geram a variável nova se estiver faltando.

### Variáveis opcionais

```bash
# Chaves LLM (para chat e classificação assistida)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
# Providers OpenAI-compatíveis (opcionais): Moonshot (Kimi) e Ollama local
MOONSHOT_API_KEY=sk-...
# OLLAMA_BASE_URL=http://host.docker.internal:11434/v1  # default no Docker; Ollama não precisa de chave
# Modelos Ollama/Moonshot entram pela UI: configurações do assistente → digite
# "provider/modelo" na combobox (ex.: ollama/gemma3:12b, como no `ollama list`)
# → validação ao vivo → o modelo aparece no seletor do chat e da triagem

# Habilitar LLM no fluxo de ingestão (default: false)
CLASSIFICATION_LLM_ENABLED=true

# Root operacional dos datasets do classificador
# Default recomendado: não alterar
CLASSIFIER_DATASETS_ROOT=/projects/_ATLASFILE/classifier/datasets
```

```bash
# Embeddings / busca semântica (default: habilitado com provider openai)
# EMBEDDING_ENABLED=true
# EMBEDDING_PROVIDER=openai   # ou "fastembed" (local, sem API):
#   cd backend && .venv/bin/pip install -r requirements-local-embeddings.txt
```

Para popular embeddings de um corpus já indexado (migração), rode:

```bash
cd backend && .venv/bin/python scripts/backfill_embeddings.py           # idempotente
cd backend && .venv/bin/python scripts/backfill_embeddings.py --force   # re-embedar tudo
```

```bash
# Autenticação por API key (default: desligada)
# Caminho simples — re-execute o instalador com a flag (gera key, configura .env
# e preserva dados; a key aparece no final):
curl -fsSL https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.sh | bash -s -- --enable-auth

# Manual, se preferir:
# API_AUTH_ENABLED=true
# 1) Crie config/api_keys.json a partir de config/api_keys.example.json (fica
#    fora do git; é bind mount no container — trocar key NÃO exige rebuild)
# 2) Coloque a key do próprio app em ATLASFILE_API_TOKEN no .env (precisa existir
#    no json com projects ["*"]) — é a credencial do orchestrator→/mcp e das tools→API
# 3) docker compose -f docker-compose.yml -f docker-compose.build.yml up -d atlasfile
#    (recria o container com o .env novo; o overlay mantém o build local)
# 4) No frontend: Config → Acesso → cole a key do navegador
# Obs.: o /mcp (mesma porta 8000) valida a MESMA key — clientes MCP externos
# precisam enviá-la (Authorization: Bearer).
```

Veja `.env.example` para a lista completa de variáveis (CORS, OpenSearch, reconciliação, embeddings, auth, etc.).

---

## 4) Testes antes de subir

Antes de subir ou atualizar os containers, rode os testes:

```bash
make test
```

Ou individualmente:

- Backend: `cd backend && python -m pytest tests/ -v` (requer virtualenv com `pip install -r requirements-dev.txt` — instala o mesmo resolve pinado do produto, via `requirements.lock.txt`, mais o pytest)
- Frontend: `cd frontend && npm run test`

---

## 5) O que acontece no primeiro boot

Depois do primeiro `make docker-update`, o AtlasFile passa a usar `PROJECTS_HOST_ROOT/_ATLASFILE/` como estado operacional persistido:

```text
<PROJECTS_HOST_ROOT>/
├── _ATLASFILE/
│   ├── classifier/
│   │   ├── datasets/
│   │   │   ├── validation_set/
│   │   │   │   ├── files/
│   │   │   │   └── expected.json
│   │   │   └── training_pool/
│   │   │       ├── files/
│   │   │       └── records.jsonl
│   │   ├── models/
│   │   ├── reports/
│   │   └── registry.json
│   ├── llm/                     ← cache do catálogo de modelos e customs
│   └── journal/                 ← chats e eventos de custo (durabilidade)
│       ├── chat_sessions/
│       └── chat_usage-AAAAMM.ndjson
└── <SEUS_PROJETOS>/
```

Estado inicial de um AtlasFile novo:

- a ingestão já funciona com o classificador `bootstrap`, sem depender de `validation_set` ou `training_pool` previamente populados;
- `validation_set` e `training_pool` começam vazios no root operacional;
- benchmark e retreino supervisionado só ficam úteis depois que você alimentar o `validation_set` com arquivos reais e acumular exemplos revisados no `training_pool`.
- `journal/` (v0.53.0) guarda em disco os chats e os eventos de custo LLM, que antes viviam só no índice: perder o volume do OpenSearch deixa de significar perder esse histórico — a reconciliação restaura o que o índice não tiver.

O repo não é mais usado como seed automático desses datasets no runtime.

---

## 6) Subir os serviços

### Primeira vez ou rebuild completo

```bash
make docker-update
```

Isso roda os testes, faz build das imagens, sobe todos os serviços e executa o smoke test de inicialização.

### Alternativa manual

Duas trilhas desde a v1.0.0 — o compose base consome a **imagem publicada** (`ghcr.io/aleonnet/atlasfile`, selecionada por `ATLASFILE_VERSION` no `.env`); o build local vive no overlay `docker-compose.build.yml`:

```bash
# Usuário: rodar a imagem publicada (requer ATLASFILE_VERSION no .env —
# o instalador e o make gravam automaticamente)
docker compose up -d

# Desenvolvedor/contribuidor: buildar da fonte (imagem atlasfile-local:dev)
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

### Serviços esperados

```bash
docker compose ps
```

| Container | Serviço | Porta |
|-----------|---------|-------|
| `atlasfile-opensearch` | OpenSearch 2.17 | 9200 |
| `atlasfile` | App consolidado: UI + API + MCP num uvicorn | 8000 |
| `atlasfile-dashboards` | OpenSearch Dashboards (opt-in: `COMPOSE_PROFILES=dashboards`) | 5601 |

> **Portas configuráveis via `.env`**: `ATLASFILE_PORT` (app, default 8000 — o instalador aceita `--port`/`-Port` e grava a chave), `OPENSEARCH_PORT` + `OPENSEARCH_BIND` (default `127.0.0.1:9200` — o índice **não** aparece na rede local; `OPENSEARCH_BIND=0.0.0.0` restaura a exposição) e `DASHBOARDS_PORT` (5601). A porta 9600 (performance analyzer) deixou de ser publicada.

---

## 7) Verificação de saúde

### Frontend

Abra <http://localhost:8000> — a interface deve carregar com o seletor de projetos no header.

O idioma da interface (PT-BR ou EN-US) é detectado pelo navegador no primeiro acesso; para trocar manualmente, use **Configuração → Preferências → Idioma** (ou o alternador no rodapé da tela de API key / onboarding). A escolha persiste no navegador.

### Backend

```bash
curl http://localhost:8000/health
```

Resposta esperada: `{"status":"ok"}`

### Se a pasta de projetos sumir

Se a pasta apontada por `PROJECTS_HOST_ROOT` for excluída ou ficar inacessível com o stack no ar, a UI abre sozinha o modal **"Pasta de projetos excluída ou inacessível"** — clique em **Recriar pasta e reiniciar**: a aplicação reinicia, o Docker recria a pasta, o índice órfão é limpo e o assistente de configuração reabre. Nenhum comando manual é necessário (os serviços sobem com `restart: unless-stopped`). Os documentos excluídos não são recuperados — a recuperação restaura a estrutura e a consistência índice↔disco.

### OpenSearch Dashboards (observabilidade)

Abra <http://localhost:5601> (login `admin` + `OPENSEARCH_PASSWORD` do `.env`). O dashboard **"AtlasFile — Operação"** é importado automaticamente no primeiro boot da API — procure em Dashboards. Se ainda não apareceu, aguarde ~1 min (o serviço sobe depois da API) ou importe manualmente `backend/app/data/dashboards.ndjson` em Management → Saved Objects → Import.

### OpenSearch

```bash
# a senha está no seu .env (OPENSEARCH_PASSWORD)
curl -k -u "admin:$(grep '^OPENSEARCH_PASSWORD=' .env | cut -d= -f2-)" https://localhost:9200
```

---

## 8) Criar um projeto

### Via UI (recomendado)

1. No seletor de projetos do header, selecione uma pasta do seu `PROJECTS_HOST_ROOT`.
2. O modal de inicialização aparece com templates disponíveis.
3. Selecione um template (ex: "M&A / Carve-out") e clique em "Inicializar com template".
4. O AtlasFile cria a estrutura completa:

```
/<PROJETO>/
├── _INBOX_DROP/
├── _TRIAGE_REVIEW/pending|resolved|rejected
├── _PROFILE/profile.json
├── 01_contratos_comunicacao/
├── 02_financeiro/
├── ...
└── _INDEX.md
```

### Via script (requer virtualenv do backend)

```bash
# Template padrão (M&A / Carve-out)
python3 scripts/bootstrap_project.py --name "meu_projeto"

# Com template específico e label legível
python3 scripts/bootstrap_project.py --name "due_diligence" --template default --label "Due Diligence Alfa"
```

O script reutiliza os mesmos módulos do backend (`profile_store`, `bootstrap`), garantindo que o `profile.json` e a estrutura de pastas sejam idênticos ao que a API produz.

---

## 9) Preparar datasets do classificador (opcional)

Para um AtlasFile novo do zero, esta etapa é opcional. Só é necessária quando você quiser usar benchmark, score comparativo e ciclo supervisionado com dados reais.

### `validation_set`

Popule o dataset operacional com arquivos reais usando o script do backend (requer ambiente Python do backend já configurado):

```bash
cd backend
python scripts/bootstrap_validation_set.py "/caminho/para/documentos_reais"
```

Isso copia os arquivos aceitos para `PROJECTS_HOST_ROOT/_ATLASFILE/classifier/datasets/validation_set/files/` e sincroniza `expected.json`.

### `training_pool`

O `training_pool` operacional é alimentado automaticamente por decisões `Approve` / `Correct` na triagem. Para importar histórico já revisado de um projeto (também requer ambiente Python do backend):

```bash
cd backend
python scripts/backfill_training_pool.py "/caminho/absoluto/do/projeto" --replace-project-records
```

Isso grava snapshots estáveis e atualiza `PROJECTS_HOST_ROOT/_ATLASFILE/classifier/datasets/training_pool/`.

---

## 10) Teste funcional rápido (fim a fim)

1. Copie um arquivo para `<PROJECTS_HOST_ROOT>/meu_projeto/_INBOX_DROP/`

2. Na UI (<http://localhost:8000>), selecione o projeto e clique em **Processar INBOX** no card "Ingestão e triagem".

3. Resultado esperado:
   - Arquivo roteado para `02_AREAS/{business_domain}/{document_type}/` (se confiança alta), ou
   - Item em triagem pendente para `Approve/Correct/Reject`.

4. Se você aprovar ou corrigir um item na triagem, o AtlasFile também atualiza o `training_pool` operacional em `_ATLASFILE/classifier/datasets/training_pool/`.

5. Use a busca (Cmd+K ou Enter) para localizar o documento indexado.

### Via API (alternativa)

```bash
curl -X POST http://localhost:8000/api/ingest/scan/meu_projeto
```

---

## 11) Operação diária

- **Ingestão**: coloque arquivos em `/<PROJETO>/_INBOX_DROP/`
- **Processamento**: clique em "Processar INBOX" na UI ou aguarde reconciliação automática
- **Triagem**: decida pendências no card de triagem (Approve, Correct, Reject)
- **Busca**: use Cmd+K para busca rápida ou o card "Resultados completos" com filtros
- **Chat**: use o assistente LLM (aba "Assistente") para perguntas sobre os documentos

---

## 12) Atualização Docker após mudanças de código

O comando recomendado roda testes, faz rebuild e smoke test:

```bash
make docker-update
```

### Opções adicionais

```bash
# Resetar índice de documentos (requer reconciliação depois)
make docker-update RESET_INDEX=1

# Resetar índice de sessões de chat
make docker-update RESET_CHAT=1

# Resetar ambos os índices
make docker-update RESET_INDEX=1 RESET_CHAT=1

# Rebuild completo (do zero) — build local exige o overlay desde a v1.0.0
docker compose down
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build

# Rebuild só do app (backend + UI saem da mesma imagem multi-stage)
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build atlasfile
```

---

## 13) Makefile targets

| Target | O que faz |
|--------|-----------|
| `make test` | Roda todos os testes (backend + frontend) |
| `make docker-update` | Testa + rebuild + sobe stack + smoke test |
| `make docker-update RESET_INDEX=1` | Idem + reseta índice de documentos |
| `make docker-update RESET_CHAT=1` | Idem + reseta índice de sessões de chat |
| `make docker-up` | Sobe stack sem rodar testes |
| `make docker-build` | Testa + build das imagens (sem subir) |
| `make reset-index` | Remove índice de documentos |
| `make reset-chat` | Remove índice de sessões de chat |

---

## 14) Troubleshooting

### Docker Desktop: "Integrity issue detected"

1. Clique em **Repair**
2. Reinicie o Docker Desktop
3. Rode: `docker version && docker compose version`

### API não sobe

```bash
docker compose logs atlasfile --tail=200
```

### OpenSearch não sobe

```bash
docker compose logs opensearch --tail=200
```

### Subiu parcialmente

```bash
docker compose down
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

### Limpar ambiente local (containers + rede + volumes)

```bash
docker compose down -v
```

### Reset de índices OpenSearch

Para recriar índices com mapping atualizado (ex.: após upgrade):

1. Documentos: `make reset-index` — depois execute **Reconciliar INDEX** na UI para repopular
2. Sessões de chat: `make reset-chat` — limpa histórico de conversas do assistente
3. Ambos: `make docker-update RESET_INDEX=1 RESET_CHAT=1`

---

## 15) Credenciais e portas (dev)

| Serviço | URL | Credenciais |
|---------|-----|-------------|
| AtlasFile (UI + API) | http://localhost:8000 | — |
| MCP | http://localhost:8000/mcp | mesma API key da API (quando auth ligado) |
| Vite dev server (só desenvolvimento) | http://localhost:5173 | — |
| OpenSearch | https://localhost:9200 | admin / `OPENSEARCH_PASSWORD` do seu `.env` |
| Dashboards (opt-in) | http://localhost:5601 | admin / `OPENSEARCH_PASSWORD` do seu `.env` |

> A senha é única por instalação (gerada pelo install.sh na criação do `.env`).
> As portas acima são os defaults — remapeáveis via `ATLASFILE_PORT`/`OPENSEARCH_PORT`/`DASHBOARDS_PORT` no `.env` (o OpenSearch nasce em `127.0.0.1`).

---

## 16) Dashboard programático (OpenSearch Dashboards)

> Dashboards é **opt-in**: exige `COMPOSE_PROFILES=dashboards` e
> `DASHBOARDS_ENABLED=true` no `.env` (ver seção 4) antes destes passos —
> ou simplesmente re-execute o instalador com `--enable-dashboards`
> (`-EnableDashboards` no Windows), que grava as chaves e sobe o serviço.

Os saved objects estão em `dashboards/atlasfile.ndjson`.

1. Com o stack no ar, importe: `./scripts/import-dashboards.sh`
2. Faça login em http://localhost:5601 (admin / senha do OpenSearch) e mantenha o tenant padrão.
3. Abra o dashboard pelo link direto: http://localhost:5601/app/dashboards#/view/atlasfile-overview

---

## 17) Backup

O que precisa de backup fica **fora** do repositório: a pasta de projetos (`PROJECTS_HOST_ROOT`, que inclui `_ATLASFILE/` com datasets e templates) e, se quiser preservar o índice, o volume `atlasfile_opensearch_data`. O código é recuperável do GitHub.

```bash
# Pasta de projetos (documentos + datasets + templates)
tar -czf AtlasFileProjects_$(date +%Y%m%d).tar.gz -C "$(dirname <PROJECTS_HOST_ROOT>)" "$(basename <PROJECTS_HOST_ROOT>)"
```

O índice OpenSearch pode ser reconstruído a qualquer momento com **Reconciliar INDEX** no Painel.

---

## 18) Desinstalação

O instalador sabe se desinstalar, e reverte **apenas o que ele criou** — o que já existia na máquina antes fica intacto.

```bash
# a partir da instalação
bash ~/AtlasFile/install.sh --uninstall

# ou, se a pasta da instalação já não existir
curl -fsSL https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.sh | bash -s -- --uninstall --dir ~/AtlasFile

# a partir do repositório
make uninstall
```

```powershell
# Windows
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.ps1))) -Uninstall
```

**Como ele sabe o que é dele.** Durante a instalação são gravados dois manifestos: `~/.atlasfile/host-prereqs` (dependências do sistema — há um Docker por máquina) e `<pasta da instalação>/.atlasfile-install-manifest` (fatos daquela instalação). Cada item vale `created` ou `preexisting`; `created` nunca é rebaixado numa reinstalação, e chave ausente lê como `preexisting`. Ou seja: **na dúvida, preserva**.

**O que acontece.** Antes de tocar em qualquer coisa ele imprime um plano em texto com duas seções — o que será removido e o que será preservado, com o motivo — e espera confirmação (`--yes` para modo não-interativo). Para só ver o plano, sem confirmar nada: `--uninstall --dry-run` (no Windows, `-Uninstall -DryRun`).

**No Windows, o plano cobre a máquina inteira.** São dois escopos com dois manifestos — a distro e o Windows —, e quem instalou o Docker Desktop e o Ollama foi o `install.ps1`. Ele pede os fatos ao `install.sh` dentro do WSL, imprime **um** plano com os dois lados e faz **uma** pergunta; só depois de o lado Linux confirmar a execução é que qualquer pacote do Windows é tocado. Se você responder "não", nada é removido dos dois lados — e o instalador sai com `1602`, o código que o mundo Windows usa para "o usuário cancelou". Quando o desinstalador do Docker agenda arquivos em uso para exclusão no próximo boot, a saída é `3010`: sucesso com reinício pendente.

| Item | Comportamento |
|---|---|
| Containers, rede e imagens do app | `docker compose down --rmi local` rodado de dentro da instalação (o compose resolve o projeto sozinho), mais remoção explícita das imagens nomeadas (`ghcr.io/aleonnet/atlasfile:*` e `atlasfile-local:*` — `--rmi local` não remove imagem com `image:` no compose). Nunca por nome de container (os nomes `atlasfile-*` são fixos e podem ser de outra instalação) |
| Volume do OpenSearch (o índice) | **Sem default**: ele pergunta. `--purge-data` apaga, `--keep-data` mantém. Modo headless exige uma das duas. Seus documentos e o journal em `_ATLASFILE/` ficam em disco e não são afetados — o índice se reconstrói com Reconciliar |
| Imagens `opensearchproject/*` | Preservadas (podem ser compartilhadas com outros stacks); o resumo mostra como liberar o espaço |
| Pasta da instalação | Removida **só** se o manifesto disser que o instalador a criou (clone `created` ou bundle) e não houver trabalho seu dentro — alterações locais no clone, ou arquivos que o instalador não pôs numa instalação bundle (`--force` para forçar). Um clone de desenvolvimento é sempre preservado |
| Pasta de projetos | **Nunca apagada.** A única exceção é uma pasta que o instalador criou e que continua vazia |
| Docker, git, Ollama, plugin do compose, grupo docker | Revertidos apenas com `--remove-deps` **e** apenas se o manifesto disser `created`. O Docker ainda é preservado se sobrar qualquer outro artefato AtlasFile na máquina |
| Homebrew | **Nunca** removido automaticamente — o plano imprime o comando oficial |
| Ollama no Linux | Listado com os passos do fornecedor, não executado (o instalador oficial não traz desinstalador) |

**Instalação antiga, sem manifesto.** Quem instalou antes desta versão não tem manifesto: o stack e o volume seguem removíveis, o clone é preservado, e toda dependência de sistema aparece como *"não dá para provar que foi o instalador → preservada"*. A próxima execução do `install.sh` grava o manifesto com o que der para provar.

# Plano: Instalador One-Line (`curl | bash`)

> **Status:** Rascunho -- ponto de decisao aberto (hospedagem + repo publico).

## Objetivo

Permitir que qualquer usuario instale o AtlasFile com um unico comando:

```bash
curl -fsSL --proto '=https' --tlsv1.2 https://atlasfile.dev/install.sh | bash
```

Apos ~2 minutos, o browser abre em `http://localhost:5173` com o wizard de onboarding.

Zero pre-requisitos manuais. Zero edicao de `.env`. Zero `git clone`.

---

## Referencia: Padrao OpenClaw

O OpenClaw oferece 3 scripts de instalacao servidos via CDN (`openclaw.ai`):

| Script | Plataforma | O que faz |
|---|---|---|
| `install.sh` | macOS / Linux / WSL | Instala Node se necessario, instala via npm ou git, roda onboarding |
| `install-cli.sh` | macOS / Linux / WSL | Instala Node + app em prefix local (`~/.openclaw`), sem root |
| `install.ps1` | Windows (PowerShell) | Instala Node se necessario via winget/choco/scoop, instala via npm ou git |

### Bells and whistles que queremos replicar

| Feature | OpenClaw | AtlasFile atual | Gap |
|---|---|---|---|
| OS detection (macOS/Linux/WSL) | Sim | Sim | -- |
| Gum UI (spinners, styled output) | Nao | Sim (gum temp bootstrap) | AtlasFile ja tem |
| Colored output (ANSI) | Sim | Sim | -- |
| Docker install automatico | Parcial (Node, nao Docker) | Sim (brew/get.docker.com) | -- |
| Docker daemon auto-start (macOS) | N/A | Sim | -- |
| `.env` auto-gerado com defaults | N/A (usa npm config) | Sim | -- |
| Clone/download do repo | Sim (git clone + npm) | **NAO** | **Gap principal** |
| Versioning (`--version`, `--beta`) | Sim | Nao | Gap |
| Health checks pos-install | Nao | Sim | AtlasFile ja tem |
| Browser auto-open | Nao | Sim | AtlasFile ja tem |
| `--dry-run` | Sim | Sim | -- |
| `--no-prompt` (CI mode) | Sim | Sim | -- |
| `--verbose` | Sim | Sim | -- |
| JSON output (CI) | Sim (`install-cli.sh --json`) | Nao | Nice-to-have |
| PowerShell (`install.ps1`) | Sim | Nao | Fase 2 |
| Post-install doctor | Sim (`openclaw doctor`) | Nao | Nice-to-have |
| Onboarding no terminal | Sim | Nao (onboarding e na UI) | By design |

---

## Arquitetura Proposta

### Dois scripts, dois propositos

```
install.sh          (hospedado remotamente)
  |
  |-- detect_os
  |-- install_docker_if_missing
  |-- ensure_docker_running
  |-- clone_or_download_repo     <-- NOVO
  |-- cd <install_dir>
  |-- generate_env_if_missing    (ja existe)
  |-- docker compose up -d --build
  |-- wait_for_health            (ja existe)
  |-- open_browser               (ja existe)
  |-- print_footer


atlasfile_install.sh (no repositorio, para uso local)
  |-- (mesmo fluxo de hoje, sem clone)
```

O `install.sh` remoto e um **wrapper leve** que:
1. Baixa/clona o repositorio
2. Delega para `atlasfile_install.sh` local (ou incorpora a logica diretamente)

### Alternativa: script unico auto-contido

Incorporar toda a logica (incluindo download) em um unico `install.sh` servido remotamente. Evita manter dois scripts, mas aumenta o tamanho do script.

**Recomendacao:** Script unico auto-contido (como OpenClaw faz com `install.sh`).

---

## Fluxo Detalhado

```
  Usuario executa:
  curl -fsSL https://atlasfile.dev/install.sh | bash

  ┌─── install.sh ──────────────────────────────────────────────┐
  │                                                              │
  │  1. Detect OS (macOS / Linux / WSL)                         │
  │     - Fail: Windows nativo sem WSL → mensagem + exit        │
  │                                                              │
  │  2. Bootstrap gum (UI bonita) [best-effort]                 │
  │                                                              │
  │  3. Ensure Docker                                            │
  │     a. check_docker_cli + check_compose_cli                 │
  │     b. Se ausente:                                           │
  │        - macOS: brew install --cask docker                  │
  │        - Linux: curl get.docker.com | sh                    │
  │     c. ensure_docker_running                                 │
  │        - macOS: open -a Docker + wait loop 120s             │
  │        - Linux: systemctl start docker (se sudo)            │
  │                                                              │
  │  4. Ensure Git (se metodo=git)                               │
  │     - macOS: xcode-select --install ou brew install git     │
  │     - Linux: apt/dnf/yum install git                        │
  │                                                              │
  │  5. Clone ou download                                        │
  │     a. --install-method git (default):                      │
  │        git clone --depth 1 <REPO_URL> <INSTALL_DIR>         │
  │        ou git pull se ja existe                              │
  │     b. --install-method tarball:                             │
  │        download release tarball do GitHub                    │
  │        tar xzf → <INSTALL_DIR>                              │
  │                                                              │
  │  6. cd <INSTALL_DIR>                                         │
  │                                                              │
  │  7. generate_env_if_missing                                  │
  │     - PROJECTS_HOST_ROOT=$HOME/Documents/Projects           │
  │     - OpenSearch defaults                                    │
  │     - Idempotente: nao sobrescreve .env existente           │
  │                                                              │
  │  8. mkdir -p $PROJECTS_HOST_ROOT                             │
  │                                                              │
  │  9. docker compose up -d --build                             │
  │                                                              │
  │ 10. Health check loop (backend + opensearch + frontend)      │
  │     - Retry com backoff: 5s, 10s, 15s... ate 120s          │
  │     - Se falhar: exibir logs + exit 1                       │
  │                                                              │
  │ 11. open_browser (macOS: open, Linux: xdg-open)             │
  │                                                              │
  │ 12. Footer com URLs + instrucoes                             │
  │                                                              │
  └──────────────────────────────────────────────────────────────┘
```

---

## Flags e Variaveis de Ambiente

### Flags

| Flag | Descricao | Default |
|---|---|---|
| `--install-dir <path>` | Diretorio de instalacao | `~/AtlasFile` |
| `--projects-root <path>` | Pasta raiz de projetos | `$HOME/Documents/Projects` |
| `--version <tag>` | Tag do git ou release para baixar | `main` |
| `--install-method git\|tarball` | Metodo de obtencao do codigo | `git` |
| `--no-git-update` | Nao fazer `git pull` se ja clonado | `false` |
| `--dry-run` | Exibir plano sem executar | `false` |
| `--verbose` | Output detalhado | `false` |
| `--no-prompt` | Modo CI (sem interacao) | `false` |
| `--gum` / `--no-gum` | Forcar/desabilitar gum UI | `auto` |
| `--help`, `-h` | Mostrar ajuda | -- |

### Variaveis de ambiente

| Variavel | Descricao |
|---|---|
| `ATLASFILE_INSTALL_DIR` | Diretorio de instalacao |
| `ATLASFILE_PROJECTS_HOST_ROOT` | Pasta raiz de projetos |
| `ATLASFILE_VERSION` | Tag/versao |
| `ATLASFILE_INSTALL_METHOD` | `git` ou `tarball` |
| `ATLASFILE_NO_PROMPT` | Modo CI |
| `ATLASFILE_DRY_RUN` | Dry run |
| `ATLASFILE_VERBOSE` | Debug mode |
| `ATLASFILE_USE_GUM` | Forcar gum |

---

## Ponto de Decisao Aberto

### Hospedagem e repositorio

Para que `curl -fsSL https://atlasfile.dev/install.sh | bash` funcione, precisamos resolver:

1. **O repositorio sera publico?**
   - Se sim: `git clone` direto do GitHub funciona.
   - Se nao: precisamos de autenticacao (token) ou distribuir via tarball de release privado.

2. **Dominio para servir os scripts:**
   - Opcao A: `atlasfile.dev` (ou `.io`, `.ai`) com Cloudflare Pages / Netlify / Vercel servindo os scripts estaticos
   - Opcao B: `raw.githubusercontent.com/<org>/AtlasFile/main/install.sh` (sem dominio proprio, mas URL longa e feia)
   - Opcao C: GitHub Pages no proprio repo (`https://<org>.github.io/AtlasFile/install.sh`)

3. **Repo URL no script:**
   - `REPO_URL` precisa estar hardcoded no `install.sh` remoto
   - Ex: `https://github.com/<org>/AtlasFile.git`

**Recomendacao:** Decidir se o repo sera publico antes de implementar. Se publico, o fluxo e identico ao OpenClaw. Se privado, o metodo `tarball` com token e mais adequado que `git clone`.

---

## O que o INSTALL.md se tornaria

Com o one-liner funcionando, o INSTALL.md passaria a ter:

```markdown
## Instalacao rapida

    curl -fsSL https://atlasfile.dev/install.sh | bash

Pronto. O script instala Docker (se necessario), baixa o AtlasFile,
configura defaults e abre o browser em http://localhost:5173.

## Instalacao manual (alternativa)

<detalhes para quem prefere controle total -- seções 1-5 atuais>
```

As secoes 1-5 atuais (pre-requisitos, clone, .env, testes, subir servicos) viram uma secao "manual/avancado" colapsavel.

---

## Fases de Implementacao

### Fase 1 -- Script remoto basico (macOS + Linux)

| Item | Descricao | Esforco |
|---|---|---|
| `install.sh` remoto | Script auto-contido com clone + delegacao | 1d |
| `clone_or_download_repo()` | Funcao com git clone --depth 1 + fallback tarball | 0.5d |
| `ensure_git()` | Install git se ausente (macOS: xcode-select, Linux: apt/dnf) | 0.5d |
| Health check com retry/backoff | Melhorar loop atual para retry com backoff exponencial | 0.25d |
| Hospedagem do script | Cloudflare Pages / GitHub Pages / raw URL | 0.25d |
| Teste E2E em VM limpa | macOS (limpo) + Ubuntu (Docker pre-instalado e nao) | 0.5d |
| Atualizar INSTALL.md | Simplificar com one-liner + secao manual | 0.25d |

**Total estimado:** ~3 dias

### Fase 2 -- PowerShell para Windows (opcional)

| Item | Descricao | Esforco |
|---|---|---|
| `install.ps1` | Equivalente Windows com winget/choco para Docker Desktop | 1.5d |
| Teste em Windows limpo | VM Windows 11 com e sem Docker | 0.5d |

**Total estimado:** ~2 dias

### Fase 3 -- Polimento (nice-to-have)

| Item | Descricao |
|---|---|
| `--version` com releases tagadas | Baixar release especifica por tag |
| `--json` output para CI | NDJSON events (como OpenClaw `install-cli.sh`) |
| `atlasfile doctor` | Comando de diagnostico pos-install |
| Update in-place | `atlasfile update` que faz git pull + rebuild |

---

## Exemplos de Uso (objetivo final)

```bash
# Instalacao padrao (tudo automatico)
curl -fsSL https://atlasfile.dev/install.sh | bash

# Com pasta de projetos customizada
curl -fsSL https://atlasfile.dev/install.sh | bash -s -- --projects-root /data/projetos

# Dry run (ver o que seria feito)
curl -fsSL https://atlasfile.dev/install.sh | bash -s -- --dry-run

# Versao especifica
curl -fsSL https://atlasfile.dev/install.sh | bash -s -- --version v0.3.0

# CI/CD (sem prompts, sem browser)
ATLASFILE_NO_PROMPT=1 curl -fsSL https://atlasfile.dev/install.sh | bash

# Diretorio de instalacao custom
curl -fsSL https://atlasfile.dev/install.sh | bash -s -- --install-dir /opt/atlasfile

# Download sem instalar Docker (ja tenho)
# (o script detecta automaticamente e pula a instalacao)
```

```powershell
# Windows (Fase 2)
iwr -useb https://atlasfile.dev/install.ps1 | iex
```

---

## Comparacao lado a lado: Antes vs Depois

### Antes (v0.3.0)

```bash
# 1. Instalar Docker Desktop manualmente
# 2. Clonar o repo
git clone https://github.com/<org>/AtlasFile.git
cd AtlasFile
# 3. Copiar e editar .env
cp .env.example .env
vi .env   # setar PROJECTS_HOST_ROOT
# 4. Subir
docker compose up -d --build
# 5. Abrir browser manualmente
open http://localhost:5173
```

**5 passos, ~10 minutos, requer conhecimento de Docker e terminal.**

### Depois (objetivo)

```bash
curl -fsSL https://atlasfile.dev/install.sh | bash
```

**1 passo, ~2 minutos, zero conhecimento tecnico necessario.**

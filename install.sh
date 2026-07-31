#!/usr/bin/env bash
# AtlasFile — one-liner installer (macOS/Linux)
#
#   curl -fsSL https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.sh | bash
#
# Host requirements: Docker (with Compose v2) — if it is missing, the
# installer OFFERS to install it for you (Homebrew/cask on macOS, official
# get.docker.com + apt/dnf on Linux). curl and tar are also required but NOT
# installed for you: every supported system ships them. git is only needed for
# --from-source. No make/node/python needed.
# Idempotent: re-running updates the install to the latest release and
# restarts the stack.
#
# Ollama is NOT part of the install: pulling a model is several GB and made the
# install take an unpredictable amount of time. The final panel shows how to
# enable a local model afterwards, in one command.
#
# Flags (this list is a summary — `--help` is the complete one):
#   --version X.Y.Z       (default: the latest stable release)
#   --from-source         contributor path: clone the repo and build locally
#   --repo-url URL        (only with --from-source; env ATLASFILE_REPO_URL)
#   --branch NAME         (only with --from-source; default: main)
#   --dir PATH            (default: ~/AtlasFile)
#   --projects-root PATH  (default: ~/Documents/AtlasFileProjects)
#   --yes                 non-interactive (accepts defaults; does NOT install
#                         missing system dependencies — see --install-deps)
#   --install-deps        authorize installing missing prerequisites without
#                         prompting (Homebrew/Docker/git; sudo on Linux)
#   --no-open             do not open the browser at the end
#   --enable-auth         enable API authentication (generates a key in
#                         config/api_keys.json, sets API_AUTH_ENABLED=true and
#                         ATLASFILE_API_TOKEN in .env). Re-running with this flag
#                         enables auth on an existing install without data loss.
#   --uninstall           revert what this installer created (see --help)
#   --doctor / --dry-run  read-only diagnosis / show, do not do
set -euo pipefail

REPO_URL="${ATLASFILE_REPO_URL:-https://github.com/aleonnet/atlasfile.git}"
BRANCH="main"
# Fase 4a: o caminho padrao baixa o bundle da release e faz pull da imagem
# publicada. As duas bases sao costuras de teste (a bancada serve uma release
# LOCAL por elas), no mesmo espirito de ATLASFILE_REPO_URL — dois seams porque
# sao dois endpoints: a API que resolve a versao e o host que serve o asset.
AF_API_BASE="${ATLASFILE_API_BASE:-https://api.github.com}"
AF_DOWNLOAD_BASE="${ATLASFILE_DOWNLOAD_BASE:-https://github.com}"
FROM_SOURCE=0
AF_PIN_VERSION=""
AF_PORT_FLAG=""
AF_TARGET_VERSION=""
AF_SOURCE_PATH=0
AF_FRESH_INSTALL=0
INSTALL_DIR="${HOME}/AtlasFile"
PROJECTS_ROOT_DEFAULT="${HOME}/Documents/AtlasFileProjects"
PROJECTS_ROOT=""
ASSUME_YES=0
INSTALL_DEPS=0
# Só sugestão para o painel final — o instalador não baixa modelo nenhum.
OLLAMA_MODEL="${ATLASFILE_OLLAMA_MODEL:-gemma4:12b}"
BOOTSTRAP_ONLY=0
OPEN_BROWSER=1
ENABLE_AUTH=0
API_KEY_VALUE=""
UNINSTALL=0
PURGE_DATA=""      # ""=undecided, 1=remove the volume, 0=keep it
REMOVE_DEPS=0
FORCE=0
PLAN_ONLY=0
DELEGATED=0
HOST_EXTRA=""      # facts from the OTHER side of an OS boundary (install.ps1)
DOCTOR=0
DRY_RUN=0
VERBOSE=0
OLLAMA_DEPRECATED=0

# Exit codes. 0 = done, 1 = failed, 10 = the user said no. `exit` in bash is
# truncated to 8 bits, which is why this is 10 and not an MSI code (1602 would
# arrive as 66).
#
# Reached only by a DIRECT `--uninstall`: under --delegated the question belongs
# to install.ps1, which always passes --yes here, so this side never asks. The
# MSI codes (1602 = user cancelled, 3010 = reboot pending) are install.ps1's own
# verdict about its own screen — it does not translate this one, and it does not
# need to: any non-zero here already reads as "the WSL side did not confirm",
# which is the conservative answer.
RC_CANCELLED=10

# Machine-readable last word of an uninstall. install.ps1 requires BOTH this
# line AND a zero exit code before it touches a single Windows package: there is
# no official documentation that wsl.exe propagates the Linux exit code, and a
# swallowed code must never be read as "the user confirmed".
# Só no modo de PROTOCOLO. Numa desinstalação direta quem lê a tela é uma
# pessoa, e a linha-sentinela é conversa entre os dois instaladores.
sentinel() {
  { [ "$DELEGATED" = "1" ] || [ "$PLAN_ONLY" = "1" ]; } || return 0
  printf 'ATLASFILE_UNINSTALL: %s\n' "$1"
}
LOG_FILE="${TMPDIR:-/tmp}/atlasfile-install-$(date +%s).log"
START_TS=$(date +%s)
TTY_DEV="${TTY_DEV:-/dev/tty}"

# Written as a heredoc instead of scraping the header comments with
# `grep '^#' "$0"`: under `curl | bash` there is no script file to scrape
# ($0 is "bash"), so the old --help printed nothing on the one-liner path.
usage() {
  cat <<EOF
AtlasFile installer

Usage:
  bash install.sh [options]
  curl -fsSL https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.sh | bash -s -- [options]

With no options: installs the latest release into ~/AtlasFile (downloads the
release bundle and pulls the published image — no compiler, no git), asks
where your documents should live and starts the stack. Re-running updates the
install to the latest release and restarts it — the installer is idempotent.
Docker (with Compose v2) is detected and, with your confirmation, installed
for you. curl and tar are required too, but not installed for you.

Install options:
  --dir PATH            Where to install                 (default: ~/AtlasFile)
  --projects-root PATH  Where your documents live        (default: ~/Documents/AtlasFileProjects)
  --port N              Host port for the interface/API  (default: 8000; the
                        .env key is ATLASFILE_PORT — OPENSEARCH_PORT and
                        DASHBOARDS_PORT live there too)
  --version X.Y.Z       Install this release instead of the latest stable one
                        (prereleases like 1.1.0-rc.1 are accepted)
  --from-source         Contributor path: clone the repository and build the
                        image locally instead of using the published release
                        (needs git; existing git installs stay on this path)
  --repo-url URL        Repository to clone (only with --from-source; env ATLASFILE_REPO_URL)
  --branch NAME         Branch to clone     (only with --from-source; default: main)
  --yes, -y             Non-interactive: accept defaults. On its own it NEVER
                        installs system dependencies — see --install-deps
  --install-deps        Authorize installing missing prerequisites without
                        asking (Homebrew/Docker/git; sudo on Linux)
  --enable-auth         Enable API authentication (generates a key in
                        config/api_keys.json)
  --no-open             Do not open the browser at the end

Uninstall options:
  --uninstall           Print a removal plan and, after your confirmation,
                        revert what this installer created. What already
                        existed on the machine is preserved
  --purge-data          Uninstall: also remove the OpenSearch volume (the search
                        index; your documents are never touched)
  --keep-data           Uninstall: keep the OpenSearch volume
  --remove-deps         Uninstall: also remove the system dependencies that the
                        manifest records as installed by AtlasFile
  --force               Uninstall: remove the clone even with local changes

Deprecated (accepted and ignored, so a published command line never breaks):
  --with-ollama         Ollama is no longer installed here — pulling a model is
  --no-ollama           several GB and made the install take an unpredictable
  --ollama-model NAME   amount of time. The final panel shows how to enable a
                        local model afterwards, in one command

Diagnostics:
  --doctor              Read-only report of this machine: prerequisites, the
                        install manifest, the stack and the folders. Installs
                        nothing, changes nothing
  --dry-run             Show, do not do. On its own: what an install would find
                        and do on this machine. With --uninstall: the removal
                        plan, and nothing is touched
  --verbose             Show the output of every tool as it runs, instead of
                        hiding it in the log

Other:
  -h, --help            This help

Environment: ATLASFILE_REPO_URL, ATLASFILE_API_BASE, ATLASFILE_DOWNLOAD_BASE,
             ATLASFILE_OLLAMA_MODEL, NO_COLOR, CI, COLORTERM, DOCKER_APP_PATH,
             BREW_BIN, TTY_DEV
Log of this run: ${LOG_FILE}
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --repo-url) REPO_URL="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    # `--version` consome um VALOR; sem esta guarda, `--version --help` engoliria
    # a flag seguinte e um `--version` solto morreria num erro mudo do shift.
    # (if, e nao um case aninhado: o fechamento de um case interno — ate citado
    # em comentario — encerraria a fatia do parser que o check_flags analisa.)
    --version)
      if [ -z "${2:-}" ] || [ "${2#-}" != "${2:-}" ]; then
        echo "--version needs a release number, e.g. --version 1.0.0 (see https://github.com/aleonnet/atlasfile/releases)"; exit 1
      fi
      AF_PIN_VERSION="$2"; shift 2 ;;
    # Mesma disciplina do --version: consome valor, valida o shape AQUI (o
    # valor flui para lsof, curl e sed — lixo nao pode virar argumento) e a
    # falha custa segundos, nao uma instalacao. Via grep, e nao case aninhado:
    # o fechamento de um case interno (ate escrito por extenso num comentario)
    # encerra a fatia do parser que o check_flags analisa — armadilha que o
    # comentario do --version ja registra.
    --port)
      if [ -z "${2:-}" ] || [ "${2#-}" != "${2:-}" ]; then
        echo "--port needs a port number, e.g. --port 8090"; exit 1
      fi
      if ! printf '%s' "$2" | LC_ALL=C grep -qE '^[0-9]{1,5}$' || [ "$2" -lt 1 ] || [ "$2" -gt 65535 ]; then
        echo "--port \"$2\" is not a valid TCP port (1-65535)"; exit 1
      fi
      AF_PORT_FLAG="$2"; shift 2 ;;
    --from-source) FROM_SOURCE=1; shift ;;
    --dir) INSTALL_DIR="$2"; shift 2 ;;
    --projects-root) PROJECTS_ROOT="$2"; shift 2 ;;
    --yes|-y) ASSUME_YES=1; shift ;;
    --install-deps) INSTALL_DEPS=1; shift ;;
    --bootstrap-only) BOOTSTRAP_ONLY=1; shift ;;  # hidden: prereqs only, then exit (CI/support)
    --no-open) OPEN_BROWSER=0; shift ;;
    --enable-auth) ENABLE_AUTH=1; shift ;;
    # Depreciadas: aceitas e IGNORADAS. O site, o histórico do shell e as
    # anotações de quem já instalou continuam trazendo estas flags; um
    # instalador público que responde "Unknown flag" a um comando que ele mesmo
    # publicou quebra o usuário na primeira linha. Elas avisam e seguem.
    --with-ollama|--no-ollama) OLLAMA_DEPRECATED=1; shift ;;
    --ollama-model) OLLAMA_DEPRECATED=1; shift 2 ;;
    --uninstall) UNINSTALL=1; shift ;;
    --purge-data) PURGE_DATA=1; shift ;;
    --keep-data) PURGE_DATA=0; shift ;;
    --remove-deps) REMOVE_DEPS=1; shift ;;
    --force) FORCE=1; shift ;;
    --plan-only) PLAN_ONLY=1; shift ;;              # hidden: nome de protocolo usado pelo install.ps1; --uninstall --dry-run e o publico
    --doctor) DOCTOR=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --verbose) VERBOSE=1; shift ;;
    --delegated) DELEGATED=1; shift ;;             # hidden: called by install.ps1 — no banner, no closing verdict
    --host-extra) HOST_EXTRA="$2"; shift 2 ;;      # hidden: k=v,… facts from the Windows side, rendered in the plan
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown flag: $1 (use --help)"; exit 1 ;;
  esac
done

# ── Palette and UI primitives ───────────────────────────────────────────────
# IS_TTY drives interactivity, COLOR_OK drives color (NO_COLOR is honoured),
# TRUECOLOR picks the 24-bit ramp only when the terminal announces support,
# ANIM_OK gates the animated banner (never in CI, never without tput).
if [ -t 1 ]; then IS_TTY=1; else IS_TTY=0; fi
# ATLASFILE_FORCE_COLOR: o install.ps1 CAPTURA a saida desta execucao para ler
# o plano e a linha-sentinela, e sob captura `[ -t 1 ]` e falso — a cor sumia
# inteira, e a desinstalacao saia branca do "Execute the plan above?" em diante.
# Quem tem o console e o orquestrador, e e ele quem sabe se ha cor: entao ele
# informa. Forca so a COR; a INTERATIVIDADE continua medida por IS_TTY, que e o
# que ela sempre mediu — barra e spinner seguem exigindo terminal de verdade.
COLOR_OK=0
if { [ "$IS_TTY" = "1" ] || [ "${ATLASFILE_FORCE_COLOR:-}" = "1" ]; } \
   && [ -z "${NO_COLOR:-}" ] && [ "${TERM:-dumb}" != "dumb" ]; then COLOR_OK=1; fi
TRUECOLOR=0
if [ "$COLOR_OK" = "1" ]; then
  case "${COLORTERM:-}" in truecolor|24bit) TRUECOLOR=1 ;; esac
fi
ANIM_OK=0
if [ "$COLOR_OK" = "1" ] && [ -z "${CI:-}" ] && command -v tput >/dev/null 2>&1; then ANIM_OK=1; fi
if [ "$COLOR_OK" = "1" ]; then
  ORANGE=$'\033[38;5;202m'; PURPLE=$'\033[38;5;177m'
  GREEN=$'\033[32m'; RED=$'\033[31m'; DIM=$'\033[2m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
else
  ORANGE=""; PURPLE=""; GREEN=""; RED=""; DIM=""; BOLD=""; RESET=""
fi

step_now() { date +%s; }
fmt_secs() { local s=$1; if [ "$s" -ge 60 ]; then printf '%dm%02ds' $((s/60)) $((s%60)); else printf '%ds' "$s"; fi; }

term_cols() {
  local c
  # COLUMNS primeiro. Delegado pelo install.ps1, o `tput cols` daqui nao ve a
  # mesma largura que o orquestrador usou para desenhar as reguas DELE, e as
  # duas metades da tela saiam com trilhos de larguras diferentes - o handover
  # ficava com cara de dois produtos. Com COLUMNS exportado na delegacao, os
  # dois lados desenham o MESMO trilho. Fora da delegacao nada muda: COLUMNS
  # vazio cai no tput, como antes.
  c="${COLUMNS:-}"
  [ -n "$c" ] || c="$(tput cols 2>/dev/null || echo 72)"
  case "$c" in ''|*[!0-9]*) c=72 ;; esac
  [ "$c" -gt 92 ] && c=92
  [ "$c" -lt 60 ] && c=60
  printf '%s' "$c"
}

# ── Calha vertical (│) ──────────────────────────────────────────────────────
# Toda mensagem pendura numa trilha contínua, como no mac_env_install.sh. Antes
# eram linhas soltas com dois espaços de recuo: a mesma informação lida como
# lista, e não como fluxo. O install.ps1 usa exatamente o mesmo desenho — dois
# instaladores com duas gramáticas visuais era o defeito, não o estilo.
GUT="${DIM}│${RESET} "

# ── Barra de fase, viva na última linha ─────────────────────────────────────
# O mac-env conta ITENS porque instala N pacotes discretos; aqui o que existe de
# discreto e conhecido são as 5 fases, e inventar um total de passos daria um
# número arbitrário — que é pior que não ter barra. Numa instalação onde o
# `docker compose build` leva ~1-2 min (medido: 48s numa VM ARM64, 94s no runner
# x86 do CI, 1m05s num Windows 11 real); saber "fase 4 de 5" é o que falta.
BAR_TOTAL=4
BAR_DONE=0
BAR_VISIBLE=0
# Placar e relatório da execução, no espírito do write_run_log do mac-env: o que
# aconteceu, com tempo por passo, espelhado num arquivo. Tínhamos log da saída
# das ferramentas e nenhum relatório do que o instalador fez.
RUN_STEPS=""

bar_capable() { [ "$COLOR_OK" = "1" ] && [ "$IS_TTY" = "1" ] && [ "$TRUECOLOR" = "1" ]; }

bar_render() {
  local width=24 filled i out="" pos
  filled=$(( BAR_DONE * width / BAR_TOTAL ))
  for (( i = 0; i < width; i++ )); do
    if [ "$i" -lt "$filled" ]; then
      pos=$(( i * 1000 / (width - 1) ))
      af_rgb_at "$pos"
      out="${out}$(printf '\033[38;2;%d;%d;%dm▰' "$AF_R" "$AF_G" "$AF_B")"
    else
      out="${out}$(printf '\033[38;5;240m▱')"
    fi
  done
  printf '%s%s%s %sfase %s/%s%s' "$GUT" "$out" "$RESET" "$DIM" "$BAR_DONE" "$BAR_TOTAL" "$RESET"
}

bar_show() {
  # A barra conta FASES da instalação. Nos fluxos que não têm fase — uninstall,
  # doctor, dry-run — ela aparecia como `fase 0/5` depois da última mensagem,
  # que é ruído puro. Antes da primeira fase, não existe barra.
  [ "$BAR_DONE" -gt 0 ] || return 0
  bar_capable || return 0
  bar_render
  BAR_VISIBLE=1
  return 0
}

# Apagar ANTES de qualquer mensagem é o que impede a barra de virar sujeira no
# meio do texto — e é a mesma disciplina que mantém o spinner longe da saída de
# terceiro, que foi como o desinstalador do Docker embaralhou a tela.
bar_clear() {
  if [ "$BAR_VISIBLE" = "1" ]; then
    # `\033[2K` apaga a linha INTEIRA e não depende do TERM estar definido — o
    # `tput el` falha calado quando não está, e sobrava rastro da barra por
    # baixo do que viesse em seguida. Com um prompt do readline logo depois,
    # esse rastro virava caractere duplicado na tela.
    printf '\r\033[2K\r'
    BAR_VISIBLE=0
  fi
  return 0
}

# Assina uma falha de REDE a partir do que a ferramenta escreveu. As frases sao
# as que docker/buildkit/curl/git realmente emitem — nao um palpite sobre o que
# elas talvez digam.
af_falha_de_rede() { # <arquivo de log>
  [ -s "$1" ] || return 1
  LC_ALL=C tail -40 "$1" | LC_ALL=C grep -qiE \
    'network is unreachable|no such host|temporary failure in name resolution|i/o timeout|TLS handshake timeout|connection refused|could not resolve host|failed to fetch anonymous token|dial tcp'
}

fail_with_log() {
  bar_clear
  printf '\r%s%s✘%s %s\n' "$GUT" "$RED" "$RESET" "$1"
  # Rede fora nao e defeito da maquina de quem instala, e despejar doze linhas
  # de Dockerfile e stack de Go faz parecer que e. Diz o que aconteceu, em uma
  # frase, e lembra que reexecutar e seguro — o instalador e idempotente.
  if af_falha_de_rede "$LOG_FILE"; then
    warn "this looks like a NETWORK problem, not a problem with your machine:"
    info "the images are downloaded from the registries (ghcr.io and Docker Hub), and the connection failed"
    info "check your internet (VPN, proxy or firewall are the usual suspects), then run the same command again"
    info "nothing was left half-done: re-running continues from where it stopped"
  fi
  if [ -s "$LOG_FILE" ]; then
    printf '%s%s── last log lines (%s) ──%s\n' "$GUT" "$DIM" "$LOG_FILE" "$RESET"
    tail -12 "$LOG_FILE" | sed "s/^/$(printf '%s' "  | ")/"
  fi
  exit 1
}

# run_step "message" cmd... — animated spinner while it runs; ✔ with timing at the end
run_step() {
  local msg="$1"; shift
  local t0; t0=$(step_now)
  bar_clear
  # --verbose troca o spinner pela saída ao vivo. Esconder a saída de terceiro é
  # a regra (é o que separa uma tela limpa de uma colcha de retalhos), mas
  # quando algo dá errado ver o que a ferramenta diz, na hora, vale mais.
  if [ "$VERBOSE" = "1" ]; then
    printf '%s· %s...\n' "$GUT" "$msg"
    if "$@" 2>&1 | tee -a "$LOG_FILE" | sed "s/^/$(printf '%s' "  | ")/"; then
      :
    fi
    if [ "${PIPESTATUS[0]}" != "0" ]; then fail_with_log "$msg"; fi
    printf '%s%s✔%s %s %s(%s)%s\n' "$GUT" "$GREEN" "$RESET" "$msg" "$DIM" "$(fmt_secs $(( $(step_now) - t0 )))" "$RESET"
    RUN_STEPS="${RUN_STEPS}${msg}|$(( $(step_now) - t0 ))
"
    return 0
  fi
  if [ "$IS_TTY" = "1" ]; then
    "$@" >>"$LOG_FILE" 2>&1 &
    local pid=$!
    local frames='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏' i=0
    while kill -0 "$pid" 2>/dev/null; do
      i=$(( (i + 1) % 10 ))
      printf '\r%s%s%s%s %s %s' "$GUT" "$ORANGE" "${frames:$i:1}" "$RESET" "$msg" "$DIM$(fmt_secs $(( $(step_now) - t0 )))$RESET "
      sleep 0.12
    done
    wait "$pid" || fail_with_log "$msg"
    printf '\r%s%s✔%s %s %s(%s)%s          \n' "$GUT" "$GREEN" "$RESET" "$msg" "$DIM" "$(fmt_secs $(( $(step_now) - t0 )))" "$RESET"
  else
    printf '%s· %s...\n' "$GUT" "$msg"
    "$@" >>"$LOG_FILE" 2>&1 || fail_with_log "$msg"
    printf '%s✔ %s (%s)\n' "$GUT" "$msg" "$(fmt_secs $(( $(step_now) - t0 )))"
  fi
  RUN_STEPS="${RUN_STEPS}${msg}|$(( $(step_now) - t0 ))
"
  bar_show
}

check() {
  local msg="$1"; shift
  if "$@" >>"$LOG_FILE" 2>&1; then
    ok "$msg"
  else
    return 1
  fi
}

ok()    { bar_clear; af_wrap "${GUT}${GREEN}✔${RESET} " "${GUT}  " 4 "$*"; bar_show; }
fail()  { bar_clear; af_wrap "${GUT}${RED}✘${RESET} " "${GUT}  " 4 "$*"; exit 1; }
warn()  { bar_clear; af_wrap "${GUT}${ORANGE}!${RESET} " "${GUT}  " 4 "$*"; bar_show; }
info()  { bar_clear; af_wrap "${GUT}${PURPLE}·${RESET} " "${GUT}  " 4 "$*"; bar_show; }
# Pergunta: sem newline, e sem redesenhar a barra por cima do cursor de leitura.
# ask MONTA o prompt; nao imprime. Quem imprime e o readline, dentro do
# af_read_line — e e isso que faz o backspace funcionar (ver la embaixo).
# Mensagem FORA da calha: depois que o trilho FECHA (╰──) o relatorio nao pode
# continuar pendurado nele. E o desenho do mac-env, onde o resumo final vive do
# lado de fora.
note()  { printf '  %s\n' "$*"; }

ask()   { printf '%s%s?%s %s' "$GUT" "$ORANGE" "$RESET" "$*"; }

# Lê UMA linha do terminal, sem lixo de tecla.
#
# Medido na máquina do usuário: com `read -r` puro, as setas do teclado viram
# bytes de escape DENTRO da resposta. A pasta de projetos foi gravada no .env
# como `PROJECTS_HOST_ROOT=\033[C\033[D\033[C…` e o `${PROJECTS_HOST_ROOT}:/projects`
# do compose derrubou a instalação com "service api refers to undefined volume :".
#
# `-e` liga o readline, e aí seta, backspace e Home/End EDITAM a linha em vez de
# entrarem nela. O `tr` é cinto e suspensórios: mesmo com readline, um terminal
# exótico pode entregar controle, e nenhum byte de controle pode sobreviver numa
# resposta que vai virar caminho de diretório.
# UM portão para o caminho da pasta de projetos, qualquer que seja a origem:
# --projects-root, o .env de uma instalação anterior, a resposta da pergunta ou
# o default. Validar só a resposta não bastou e derrubou duas instalações
# seguidas: na primeira o lixo entrou no .env, e na segunda ele foi LIDO DE
# VOLTA do próprio .env, sem passar por pergunta nenhuma.
#
# Devolve o caminho utilizável, ou falha. Faz três coisas, nesta ordem:
#   1. tira sequência CSI e byte de controle (tecla de seta, colagem suja);
#   2. expande `~`, que NÃO expande dentro de variável — `mkdir -p "~/x"` cria
#      uma pasta chamada literalmente `~` dentro do diretório atual;
#   3. exige caminho absoluto: relativo aqui vira montagem errada no compose.
af_sane_path() { # <caminho>
  local p="$1"
  p="$(printf '%s' "$p" | LC_ALL=C sed $'s/\033\\[[0-9;?]*[A-Za-z~]//g' | LC_ALL=C tr -d '\000-\037\177')"
  # shellcheck disable=SC2088  # o til aqui é LITERAL de propósito: é o texto que
  # o usuário digitou, e é justamente o que precisa ser expandido à mão.
  case "$p" in
    "~")   p="$HOME" ;;
    "~/"*) p="${HOME}/${p#\~/}" ;;
  esac
  case "$p" in
    /*) ;;
    *)  return 1 ;;
  esac
  printf '%s' "$p"
}

# O resultado sai em $AF_LINE, NÃO em stdout, e isso é o ponto.
#
# Com `read -e` o readline escreve o eco do que você digita no STDOUT. Chamando
# a função dentro de `$( )`, esse stdout é capturado pela substituição — e a
# digitação simplesmente não aparece na tela. Foi o que aconteceu na terceira
# tentativa: o cursor ficava parado depois dos dois-pontos.
AF_LINE=""

# O readline precisa saber a LARGURA VISIVEL do prompt para redesenhar a linha.
# Sequencia de cor nao ocupa coluna: sem marcar isso, ele conta os bytes do
# escape como caracteres e o apagar sai torto. \001..\002 sao os marcadores
# de "nao imprimivel" que o readline entende.
af_rl_prompt() {
  printf '%s' "$1" | LC_ALL=C sed $'s/\033\\[[0-9;?]*[A-Za-z]/\001&\002/g'
}

# <prompt ja montado, pode ter cor>. O resultado sai em $AF_LINE.
af_read_line() {
  AF_LINE=""
  local resposta="" prompt="${1:-}"
  bar_clear
  # O prompt vai PARA o readline (-p), e nao impresso antes por um printf solto.
  # Impresso por fora, o readline acha que a linha comeca na coluna 0 e, ao
  # apagar, redesenha por cima do proprio prompt — a linha inteira sumia.
  #
  # E SEM `2>/dev/null`: o readline escreve o eco no STDERR (e assim que ele
  # evita sujar o stdout). Silenciar apagava a digitacao da tela.
  if ! read -e -r -p "$(af_rl_prompt "$prompt")" resposta < "$TTY_DEV"; then
    printf '%s' "$prompt"
    read -r resposta < "$TTY_DEV" || resposta=""
  fi
  # Tirar só os bytes de controle NÃO basta: numa seta o ESC é de controle, mas
  # o `[C` que vem atrás é ASCII imprimível e sobreviveria. A sequência CSI
  # inteira sai primeiro; o `tr` limpa o que restar.
  AF_LINE="$(printf '%s' "$resposta" \
    | LC_ALL=C sed $'s/\033\\[[0-9;?]*[A-Za-z~]//g' \
    | LC_ALL=C tr -d '\000-\037\177')"
  return 0
}

# Régua de fase que varre da esquerda para a direita, com a rampa do produto.
# `[1/5] Título` continha a mesma informação em texto plano; a régua dá a ela o
# peso de um cabeçalho e reusa a paleta que até aqui só o banner conhecia.
# NADA aqui indexa string com ${s:i:1}: sob LC_ALL=C isso conta BYTES, e cada
# ─ ocupa três. É a mesma armadilha que o banner documenta, e ela transformaria
# a régua em lixo. O conector `├── ` tem largura FIXA e conhecida (4 colunas),
# então entra na conta como constante, e os traços são gerados por repetição —
# a contagem é minha, nunca do interpretador.
AF_RULE_CONNECTOR_COLS=4
# Largura em COLUNAS, independente de locale. `${#s}` conta bytes sob LC_ALL=C e
# caracteres sob UTF-8: com o cabeçalho do plano trazendo um `—` (3 bytes), a
# régua encolhia 2 colunas em quem roda sem locale UTF-8. Aqui é sempre bytes
# menos os bytes de continuação (10xxxxxx), que dá caracteres nos dois casos.
af_strwidth() { # <texto>
  local b c
  b=$(printf '%s' "$1" | LC_ALL=C wc -c | tr -d ' ')
  c=$(printf '%s' "$1" | LC_ALL=C tr -dc '\200-\277' | LC_ALL=C wc -c | tr -d ' ')
  printf '%s' $(( b - c ))
}

# Quebra o texto na largura do trilho, reprefixando a CALHA em cada linha.
#
# Medido numa desinstalacao real: 9 das 11 linhas do plano passavam de 80
# colunas — `/Users/.../config/api_keys.json` sozinho ja leva 107 com o texto
# minimo. O terminal quebrava sozinho, e a continuacao saia sem `│`: o trilho
# ficava com buracos no meio do bloco mais importante da tela.
#
# Encurtar frase nao resolveria, porque o que estoura sao CAMINHOS. O
# mac_env_install.sh nao tem essa primitiva porque nomeia pacotes (`git`,
# `iterm2`), que cabem; nos nomeamos caminhos, que nao.
#
# A largura vem do term_cols — a MESMA fonte que desenha as reguas, senao o
# texto quebraria numa coluna e a regua terminaria em outra.
af_wrap() { # <prefixo_1a_linha> <prefixo_continuacao> <colunas_do_prefixo> <texto>
  local p1="$1" p2="$2" pw="$3" texto="$4" linha="" palavra util glob_ligado=1
  util=$(( $(term_cols) - pw ))
  [ "$util" -lt 20 ] && util=20
  # O plano contem literalmente `opensearchproject/*`. Sem desligar o glob, a
  # divisao em palavras expandiria isso contra o diretorio atual e o plano
  # passaria a listar arquivos aleatorios de quem rodou o instalador.
  case "$-" in *f*) glob_ligado=0 ;; esac
  set -f
  for palavra in $texto; do
    if [ -z "$linha" ]; then
      linha="$palavra"
    elif [ "$(af_strwidth "${linha} ${palavra}")" -le "$util" ]; then
      linha="${linha} ${palavra}"
    else
      # Palavra sozinha maior que a largura (um caminho longo) transborda em vez
      # de ser partida: caminho quebrado no meio nao pode ser copiado e colado.
      printf '%s%s\n' "$p1" "$linha"; p1="$p2"; linha="$palavra"
    fi
  done
  [ "$glob_ligado" = "1" ] && set +f
  printf '%s%s\n' "$p1" "$linha"
}
# O `├── ` É a calha, não vem DEPOIS dela — no mac_env_install.sh a régua não
# leva prefixo nenhum, e era por isso que a nossa saía como `│ ├──`, com dois
# trilhos desenhados um ao lado do outro. E o gradiente cobre a linha INTEIRA,
# cabeçalho incluído (o `reveal_sweep` de lá pinta a string toda), em vez de só
# os traços.
rule_sweep() { # <cabeçalho ASCII>
  local head="$1" w fill pad i segs=8 ini fim n bloco pos ch largura
  w="$(term_cols)"
  largura="$(af_strwidth "$head")"
  fill=$(( w - largura - AF_RULE_CONNECTOR_COLS - 1 ))
  [ "$fill" -lt 4 ] && fill=4

  # O preenchimento é gerado como no mac_env_install.sh: um printf faz N espaços
  # e uma substituição troca todos por traço. Eu tinha inventado uma
  # distribuição em blocos com `fill / segs`, e o resto da divisão inteira (até
  # 7 traços, variando com o tamanho do cabeçalho) era descartado — era por isso
  # que cada régua terminava numa coluna diferente.
  printf -v pad '%*s' "$fill" ''
  pad=${pad// /─}

  if [ "$COLOR_OK" != "1" ] || [ "$TRUECOLOR" != "1" ]; then
    printf '├── %s%s%s %s\n' "$BOLD" "$head" "$RESET" "$pad"
    return 0
  fi

  af_rgb_at 0
  printf '\033[38;2;%d;%d;%dm├── ' "$AF_R" "$AF_G" "$AF_B"
  # Cabeçalho é ASCII, então indexar caractere a caractere aqui é seguro.
  for (( i = 0; i < ${#head}; i++ )); do
    ch="${head:$i:1}"
    pos=$(( i * 1000 / (largura + fill - 1) ))
    af_rgb_at "$pos"
    printf '\033[38;2;%d;%d;%dm%s' "$AF_R" "$AF_G" "$AF_B" "$ch"
  done
  printf ' '
  # A rampa nos traços é aplicada por SEGMENTOS, e cada segmento é gerado pelo
  # mesmo printf: os limites saem de i*fill/segs, cujas diferenças somam fill
  # exatamente — nada se perde. Traço é multibyte e não pode ser fatiado por
  # índice, que é o motivo de não colorir caractere a caractere aqui.
  for (( i = 0; i < segs; i++ )); do
    ini=$(( i * fill / segs ))
    fim=$(( (i + 1) * fill / segs ))
    n=$(( fim - ini ))
    [ "$n" -gt 0 ] || continue
    printf -v bloco '%*s' "$n" ''
    bloco=${bloco// /─}
    pos=$(( (largura + ini) * 1000 / (largura + fill - 1) ))
    af_rgb_at "$pos"
    printf '\033[38;2;%d;%d;%dm%s' "$AF_R" "$AF_G" "$AF_B" "$bloco"
  done
  printf '%s\n' "$RESET"
}

# Fecha o bloco, como o `╰──` do mac-env: sem isso a última fase fica aberta e a
# calha some no meio do nada.
rule_close() {
  local w linha
  w="$(term_cols)"
  printf -v linha '%*s' "$(( w - 3 ))" ''
  linha=${linha// /─}
  if [ "$COLOR_OK" = "1" ] && [ "$TRUECOLOR" = "1" ]; then
    af_rgb_at 1000
    printf '\033[38;2;%d;%d;%dm╰──%s%s\n' "$AF_R" "$AF_G" "$AF_B" "$linha" "$RESET"
  else
    printf '╰──%s\n' "$linha"
  fi
}

title() {
  bar_clear
  printf '%s\n' "$GUT"
  rule_sweep "[$1] $2"
  BAR_DONE=${1%%/*}
  bar_show
}

# Cursor de volta e barra apagada em QUALQUER saída, não só na do banner: um
# Ctrl-C no meio de um passo deixava o terminal sem cursor. É o trap global do
# mac-env-setup (cleanup_tmpfiles), pelo mesmo motivo.
af_restore_terminal() {
  [ "$BAR_VISIBLE" = "1" ] && printf '\r%*s\r' 60 ''
  [ "$IS_TTY" = "1" ] && { tput cnorm 2>/dev/null || true; }
  return 0
}
# O `trap` é REGISTRADO só depois da guarda de biblioteca, mais abaixo: instalar
# um trap de EXIT aqui vazaria para quem faz `source` deste arquivo (a bancada),
# e um EXIT trap num shell que já morreu por SIGPIPE vira ruído de "write error"
# no meio dos testes. A função é da biblioteca; o trap é do instalador rodando.

wait_http() {
  local url="$1" tries="$2"
  for _ in $(seq 1 "$tries"); do
    curl -fsS "$url" >/dev/null 2>&1 && return 0
    sleep 2
  done
  return 1
}

# ── Prerequisite bootstrap ──────────────────────────────────────────────────
# Contract (borrowed from mac-env-setup): presence check FIRST; ensure_* return
# 0 = installed now, 100 = already present, 1 = failed. Never sudo on macOS;
# sudo on Linux only after explicit consent (or --install-deps).

# confirm "question" — 0 = yes. Reads the real terminal (curl|bash pipe-safe).
# Headless (--yes or no tty): --install-deps decides; otherwise the answer is no.
confirm() {
  local q="$1" answer=""
  if [ "$ASSUME_YES" = "1" ] || [ ! -r "$TTY_DEV" ]; then
    [ "$INSTALL_DEPS" = "1" ] && return 0
    return 1
  fi
  [ "$INSTALL_DEPS" = "1" ] && return 0
  af_read_line "$(ask "$q ${DIM}[y/N]${RESET} ")"; answer="$AF_LINE"
  case "$answer" in y|Y|yes|YES|s|S) return 0 ;; *) return 1 ;; esac
}

detect_os() {
  OS_KIND="linux"; PKG="none"; BREW_PREFIX="/usr/local"
  if [ "$(uname -s)" = "Darwin" ]; then
    OS_KIND="mac"
    [ "$(uname -m)" = "arm64" ] && BREW_PREFIX="/opt/homebrew"
    # Medido numa maquina real: o --doctor dizia "package manager: none" com o
    # Homebrew 6.0.13 em /opt/homebrew/bin/brew. O ramo Darwin nunca tocava em
    # PKG, entao ele ficava no "none" da inicializacao — em QUALQUER Mac. E o
    # brew e justamente quem instalaria Docker e git se faltassem, ou seja, a
    # linha negava a capacidade que a maquina tem.
    #
    # A sonda e a MESMA do ensure_homebrew, na mesma ordem: PATH primeiro,
    # depois o prefixo. Sem isso um brew instalado mas fora do PATH (shell
    # recem-aberto) reproduziria o mesmo erro de diagnostico.
    # BREW_BIN e sobrescrevivel so para teste, como DOCKER_APP_PATH: sem essa
    # costura o ramo do prefixo seria intestavel (o caminho e absoluto e a
    # bancada nao manda em /opt/homebrew), e o teste viraria uma copia da
    # logica — verde pelo motivo errado.
    if command -v brew >/dev/null 2>&1 || [ -x "${BREW_BIN:-${BREW_PREFIX}/bin/brew}" ]; then
      PKG="brew"
    fi
  else
    if command -v apt-get >/dev/null 2>&1; then PKG="apt"
    elif command -v dnf >/dev/null 2>&1; then PKG="dnf"
    fi
  fi
}

# sudo primer for Linux: cache credentials interactively BEFORE run_step
# backgrounds commands (a password prompt inside a spinner would hang).
# Running as root (e.g. containers/CI) needs no sudo at all — as_root covers both.
as_root() { if [ "$(id -u)" = "0" ]; then "$@"; else sudo "$@"; fi; }
ensure_sudo() {
  [ "$(id -u)" = "0" ] && return 0
  command -v sudo >/dev/null 2>&1 || fail "sudo not found — run as root or install sudo"
  if ! sudo -n true 2>/dev/null; then
    if [ -r "$TTY_DEV" ]; then
      info "administrator password needed for the next step"
      sudo -v < "$TTY_DEV" || return 1
    else
      fail "sudo needs a password but there is no interactive terminal — run 'sudo -v' first or run as root"
    fi
  fi
  return 0
}

ensure_homebrew() {
  if command -v brew >/dev/null 2>&1; then
    eval "$(brew shellenv)" 2>/dev/null || true
    host_set homebrew preexisting
    return 100
  fi
  if [ -x "${BREW_PREFIX}/bin/brew" ]; then
    eval "$("${BREW_PREFIX}/bin/brew" shellenv)"
    host_set homebrew preexisting
    return 100
  fi
  # `pending` ANTES de tentar: se o processo morrer entre o comando e o registro
  # (ou se o run_step abortar o script), fica a prova de que ESTE instalador
  # mexeu aqui. Sem isso o artefato ficava orfao para sempre — a execucao
  # seguinte o veria presente e gravaria `preexisting`, apagando a nossa
  # digital. `pending` nunca autoriza remover nada: ele vira uma FRASE no plano.
  host_set homebrew pending
  run_step "installing Homebrew" env NONINTERACTIVE=1 /bin/bash -c \
    "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || return 1
  [ -x "${BREW_PREFIX}/bin/brew" ] && eval "$("${BREW_PREFIX}/bin/brew" shellenv)"
  host_set homebrew created
  return 0
}

ensure_git() {
  command -v git >/dev/null 2>&1 && { host_set git preexisting; return 100; }
  # `pending` ANTES de tentar: se o processo morrer entre o comando e o registro
  # (ou se o run_step abortar o script), fica a prova de que ESTE instalador
  # mexeu aqui. Sem isso o artefato ficava orfao para sempre — a execucao
  # seguinte o veria presente e gravaria `preexisting`, apagando a nossa
  # digital. `pending` nunca autoriza remover nada: ele vira uma FRASE no plano.
  host_set git pending
  if [ "$OS_KIND" = "mac" ]; then
    ensure_homebrew || return 1
    run_step "installing git (Homebrew)" brew install git || return 1
  else
    [ "$PKG" = "none" ] && return 1
    ensure_sudo || return 1
    if [ "$PKG" = "apt" ]; then
      run_step "updating apt indexes" as_root apt-get update -qq
      run_step "installing git (apt)" as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y git || return 1
    else
      run_step "installing git (dnf)" as_root dnf install -y git || return 1
    fi
  fi
  host_set git created
  return 0
}

ensure_docker_mac() {
  # double check: app in /Applications OR either cask name (it changed over time)
  # DOCKER_APP_PATH is overridable for tests only
  if [ -d "${DOCKER_APP_PATH:-/Applications/Docker.app}" ] \
    || brew list --cask docker-desktop >/dev/null 2>&1 \
    || brew list --cask docker >/dev/null 2>&1; then
    host_set docker preexisting
    return 100
  fi
  # `pending` ANTES de tentar: se o processo morrer entre o comando e o registro
  # (ou se o run_step abortar o script), fica a prova de que ESTE instalador
  # mexeu aqui. Sem isso o artefato ficava orfao para sempre — a execucao
  # seguinte o veria presente e gravaria `preexisting`, apagando a nossa
  # digital. `pending` nunca autoriza remover nada: ele vira uma FRASE no plano.
  host_set docker pending
  ensure_homebrew || return 1
  run_step "installing Docker Desktop (Homebrew cask)" brew install --cask docker-desktop || return 1
  host_set docker created
  return 0
}

ensure_docker_linux() {
  command -v docker >/dev/null 2>&1 && { host_set docker preexisting; return 100; }
  # `pending` ANTES de tentar: se o processo morrer entre o comando e o registro
  # (ou se o run_step abortar o script), fica a prova de que ESTE instalador
  # mexeu aqui. Sem isso o artefato ficava orfao para sempre — a execucao
  # seguinte o veria presente e gravaria `preexisting`, apagando a nossa
  # digital. `pending` nunca autoriza remover nada: ele vira uma FRASE no plano.
  host_set docker pending
  ensure_sudo || return 1
  run_step "installing Docker Engine (get.docker.com official script)" \
    sh -c "curl -fsSL https://get.docker.com | sh" || return 1
  # non-fatal: containers/CI have no systemd; the daemon check below decides
  as_root systemctl enable --now docker >>"$LOG_FILE" 2>&1 \
    || info "could not start the daemon via systemd (no systemd here?)"
  host_set docker created
  return 0
}

launch_docker_desktop_mac() {
  open -g -a Docker >/dev/null 2>&1 || open -g -a "Docker Desktop" >/dev/null 2>&1 || true
  info "if this is Docker Desktop's first launch, accept the terms and authorize the"
  info "privileged helper in the window that just opened — the installer will wait"
}

wait_docker_daemon() {
  local timeout_s="$1" t0; t0=$(step_now)
  while [ $(( $(step_now) - t0 )) -lt "$timeout_s" ]; do
    docker info >/dev/null 2>&1 && return 0
    sleep 2
  done
  return 1
}

# Linux: docker installed but the current user is not in the docker group yet.
# A bash function shim covers every `docker ...` call in the REST of this script;
# group membership is fixed for future logins.
# Só o SHIM, sem efeito colateral nenhum: nada de usermod, nada de manifesto,
# nada de pedir senha. Existe separado porque a DESINSTALAÇÃO também precisa
# alcançar o socket, e ela não pode adicionar ninguém a grupo nenhum nem
# registrar artefato — desinstalar que cria coisa é o oposto do contrato.
#
# Devolve 0 quando o `docker` passa a responder nesta sessão.
af_docker_shim_linux() {
  docker info >/dev/null 2>&1 && return 0
  command -v docker >/dev/null 2>&1 || return 1
  command -v sudo >/dev/null 2>&1 || return 1
  # shellcheck disable=SC2033  # `docker` aqui é o binário real, não o shim
  sudo -n docker info >/dev/null 2>&1 || return 1
  # Resolve the real binary BEFORE the shim shadows the name. The previous
  # form was `sudo command docker "$@"`, which looks right but there is no
  # /usr/bin/command on Debian/Ubuntu (verified in ubuntu:24.04) — every
  # later `docker ...` would have died with "sudo: command: command not
  # found" on exactly the platform this shim exists for.
  AF_DOCKER_BIN="$(command -v docker)"
  docker() { sudo "$AF_DOCKER_BIN" "$@"; }
  return 0
}

ensure_docker_group_linux() {
  docker info >/dev/null 2>&1 && return 0
  # O `ensure_sudo` fica AQUI e não dentro do shim: no caminho de INSTALAÇÃO
  # não ter privilégio é fatal (sem daemon não há o que instalar), e ali pedir
  # a senha é legítimo. O shim, que a desinstalação também usa, não pergunta
  # nada e nunca aborta.
  if ! af_docker_shim_linux; then
    ensure_sudo || return 1
    af_docker_shim_linux || return 1
  fi
  if sudo usermod -aG docker "$USER" 2>/dev/null; then host_set docker_group created; fi
  info "added ${USER} to the docker group — takes effect on your next login"
  return 0
}

# Ollama saiu do instalador: puxar um modelo e um download de varios GB e
# transformava uma instalacao de minutos em algo sem duracao previsivel. O
# painel final ensina a habilitar um modelo local depois, em um comando. O
# UNINSTALL continua sabendo reverter um Ollama instalado por versoes
# anteriores — o manifesto daquelas instalacoes segue valendo.

# Non-blocking upgrade hints for already-installed prerequisites. Docker Desktop
# and Ollama self-update through their own apps — brew receipts lag behind and
# would give false positives (mac-env-setup lesson), so they are excluded.
hint_upgrades() {
  if [ "$OS_KIND" = "mac" ] && command -v brew >/dev/null 2>&1; then
    local out; out="$(brew outdated --quiet git 2>/dev/null || true)"
    [ -n "$out" ] && info "upgrade available: git — run: brew upgrade git"
    if [ -d "${DOCKER_APP_PATH:-/Applications/Docker.app}" ]; then
      info "Docker Desktop updates itself (check the whale menu for updates)"
    fi
  elif [ "$PKG" = "apt" ]; then
    local up; up="$(apt list --upgradable 2>/dev/null | grep -E '^(docker-ce|docker-compose-plugin|git)/' | cut -d/ -f1 | tr '\n' ' ' || true)"
    [ -n "$up" ] && info "upgrades available via apt: ${up}— run: sudo apt-get install --only-upgrade ${up}"
  elif [ "$PKG" = "dnf" ]; then
    local up; up="$(dnf -q check-update docker-ce docker-compose-plugin git 2>/dev/null | awk 'NF>=3 {printf "%s ", $1}' || true)"
    [ -n "$up" ] && info "upgrades available via dnf: ${up}— run: sudo dnf upgrade ${up}"
  fi
  # Sem isto o instalador ABORTA aqui em qualquer máquina apt/dnf que não tenha
  # upgrade pendente: a última linha do ramo é um teste falso, a função devolve
  # 1 e o `set -e` derruba tudo antes mesmo de clonar. Achado pelo CI num runner
  # Ubuntu; no macOS nunca aparecia porque aquele ramo termina num `if`.
  return 0
}

# ── Install manifest: what THIS installer created on THIS host ──────────────
# Two files, because the two scopes really are different:
#   ~/.atlasfile/host-prereqs   host-wide singletons (there is one Docker per
#                               host). Written the moment each ensure_* returns,
#                               so a run that dies after installing Docker still
#                               leaves the record behind — otherwise the next
#                               run would see Docker present and record the lie
#                               "preexisting".
#   <install dir>/.atlasfile-install-manifest   facts of this one install.
# Values: created | preexisting. `created` is NEVER downgraded on a re-run, and
# a missing or unknown key always reads as preexisting — the conservative
# answer, so --uninstall can only ever remove what it can prove it made.
AF_STATE_DIR="${HOME}/.atlasfile"
AF_HOST_MANIFEST="${AF_STATE_DIR}/host-prereqs"
# Volumes que uma desinstalação preservou DE PROPÓSITO.
#
# Existe porque o plano promete, em letras, "a future reinstall reuses it" — e a
# instalação seguinte recusava o volume como se fosse de outra instância, com
# dois remédios que não devolvem o dado: `--dir` diferente muda o nome do
# projeto compose (e o volume preservado fica órfão) e `docker volume rm` apaga
# justamente o que se pediu para guardar. O `--keep-data` era um beco sem saída.
#
# Fica FORA do manifesto porque o `rm-state` apaga o manifesto no fim da
# desinstalação, e este registro precisa sobreviver exatamente para a próxima
# instalação. O `rmdir` do rm-state falha com ele dentro, que é o desejado.
AF_KEPT_VOLUMES="${AF_STATE_DIR}/kept-volumes"
AF_MANIFEST_NAME=".atlasfile-install-manifest"
# Declarados aqui porque a BIBLIOTECA os referencia: só ganham valor na fase 2
# (o caminho da instalação) e na fase 3 (se o .env já existia). Sem isto, sob
# `set -u`, a bancada quebra ao carregar o arquivo como biblioteca.
AF_MANIFEST=""
ENV_STATE=""

manifest_get() { # <file> <key> -> value ("" when absent)
  [ -f "$1" ] || return 0
  awk -F'\t' -v k="$2" '$1 == k { print $2 }' "$1" 2>/dev/null || true
}

manifest_set() { # <file> <key> <value> — merge, never downgrading `created`
  local file="$1" key="$2" value="$3" cur tmp
  cur="$(manifest_get "$file" "$key")"
  [ "$cur" = "created" ] && return 0
  [ "$cur" = "$value" ] && return 0
  mkdir -p "$(dirname "$file")" 2>/dev/null || return 0
  if [ ! -f "$file" ]; then
    { printf '# AtlasFile manifest — key<TAB>value. Consumed by install.sh --uninstall.\n'
      printf 'schema\t1\n'
    } > "$file" 2>/dev/null || return 0
  fi
  tmp="${file}.tmp.$$"
  { awk -F'\t' -v k="$key" '$1 != k' "$file" 2>/dev/null; printf '%s\t%s\n' "$key" "$value"; } > "$tmp" 2>/dev/null \
    && mv "$tmp" "$file" 2>/dev/null
  rm -f "$tmp" 2>/dev/null || true
  return 0   # state is best-effort: never fail an install over bookkeeping
}

host_get() { manifest_get "$AF_HOST_MANIFEST" "$1"; }
host_set() { manifest_set "$AF_HOST_MANIFEST" "$1" "$2"; }

# Anota que ESTA desinstalação preservou este volume, para este diretório.
# Best-effort como o resto da escrituração: nunca derruba uma desinstalação.
# A SENHA vai junto, e é obrigatório: o índice de segurança do OpenSearch nasce
# na primeira subida com a senha daquele momento e não muda depois. Preservar o
# volume sem ela produz uma instalação que SOBE e não funciona — cinco
# containers no ar e `Authentication finally failed for admin` no log, medido
# numa VM Ubuntu. Uma falha alta e clara é melhor que isso; um reuso que
# funciona é melhor que as duas.
#
# Guardar credencial em disco aqui não é novidade no produto: a própria
# desinstalação preserva backups de `.env` dizendo, no plano, que eles "hold the
# OpenSearch password and API key of earlier installs". O arquivo nasce 600.
af_kept_volume_record() { # <volume> <install dir> <senha do opensearch>
  [ -n "$1" ] || return 0
  mkdir -p "$AF_STATE_DIR" 2>/dev/null || return 0
  printf '%s\t%s\t%s\n' "$1" "$2" "${3:-}" >> "$AF_KEPT_VOLUMES" 2>/dev/null || true
  chmod 600 "$AF_KEPT_VOLUMES" 2>/dev/null || true
  return 0
}

# 0 quando este volume foi preservado por uma desinstalação NESTE diretório.
#
# O diretório entra na chave de propósito: um volume preservado por uma
# instalação em ~/AtlasFile não autoriza uma instalação nova em outro lugar a
# adotá-lo — isso seria a adoção silenciosa que a guarda existe para impedir.
#
# O registro é CONSUMIDO no reuso: uma instalação futura, sem desinstalação no
# meio, volta a esbarrar na guarda. Reuso é de uma vez, não permissão eterna.
# A senha que ESTE .env deve levar: a do volume reusado, se houver, senão uma
# nova. É função, e não código solto na fase 3, porque é justamente o ponto que
# a bancada precisa alcançar: sem isso o defeito que sobe cinco containers
# quebrados (senha nova contra índice de segurança antigo) fica sem guarda —
# testei o mutante com a lógica inline e ele passou verde.
# Aleatorio de fonte FINITA: le um bloco fixo de /dev/urandom e filtra.
#
# O padrao anterior era `(tr -dc ... < /dev/urandom) | head -c N`, em que o `tr`
# le /dev/urandom PARA SEMPRE e so termina quando o `head` fecha o pipe e ele
# leva SIGPIPE. Isso dependia de o SIGPIPE chegar e ser fatal — e no runner
# macOS do CI nao chegava: a bancada travava exatamente na primeira geracao de
# senha e o job batia o teto de 6h do GitHub (2026-07-29, tres execucoes
# seguidas; o ponto de parada foi provado com AF_BENCH_TRACE). Nao reproduz em
# macOS local (300 geracoes sem uma falha) nem no runner Linux, que roda a mesma
# bancada — por isso a correcao ataca a CLASSE do problema em vez do sintoma:
# com `head -c` na ENTRADA nenhum processo le sem fim e ninguem depende de sinal
# para terminar.
#
# 1024 bytes: para 'A-Za-z0-9' passam 62/256 dos bytes, ~248 esperados; para
# 'a-z0-9', 36/256, ~144. Os maiores consumidores pedem 48 e 32 — margem de mais
# de dez desvios-padrao, e o fallback openssl segue cobrindo o caso vazio.
af_random_token() { # <n de caracteres> [classe tr, default alfanumerica]
  LC_ALL=C head -c 1024 /dev/urandom 2>/dev/null \
    | LC_ALL=C tr -dc "${2:-A-Za-z0-9}" 2>/dev/null \
    | head -c "$1"
}

af_os_password() {
  if [ -n "${AF_REUSE_OS_PASS:-}" ]; then printf '%s' "$AF_REUSE_OS_PASS"; return 0; fi
  local r
  r="$(af_random_token 20)"
  [ -n "$r" ] || r="$(openssl rand -hex 10 2>/dev/null || date +%s)"
  printf 'Af!%s9' "$r"
}

AF_KEPT_VOLUME_PASS=""
af_kept_volume_claim() { # <volume> <install dir> — senha sai em AF_KEPT_VOLUME_PASS
  AF_KEPT_VOLUME_PASS=""
  [ -f "$AF_KEPT_VOLUMES" ] || return 1
  awk -F'\t' -v v="$1" -v d="$2" '$1 == v && $2 == d { achou = 1 } END { exit !achou }' \
    "$AF_KEPT_VOLUMES" 2>/dev/null || return 1
  AF_KEPT_VOLUME_PASS="$(awk -F'\t' -v v="$1" -v d="$2" \
    '$1 == v && $2 == d { print $3; exit }' "$AF_KEPT_VOLUMES" 2>/dev/null || true)"
  local tmp="${AF_KEPT_VOLUMES}.tmp.$$"
  if awk -F'\t' -v v="$1" -v d="$2" '!($1 == v && $2 == d)' "$AF_KEPT_VOLUMES" > "$tmp" 2>/dev/null; then
    mv "$tmp" "$AF_KEPT_VOLUMES" 2>/dev/null || true
  fi
  rm -f "$tmp" 2>/dev/null || true
  return 0
}

# O registro morre junto com o volume: apagado o índice, não há reuso a prometer.
af_kept_volume_forget() { # <volume>
  [ -f "$AF_KEPT_VOLUMES" ] || return 0
  local tmp="${AF_KEPT_VOLUMES}.tmp.$$"
  if awk -F'\t' -v v="$1" '$1 != v' "$AF_KEPT_VOLUMES" > "$tmp" 2>/dev/null; then
    mv "$tmp" "$AF_KEPT_VOLUMES" 2>/dev/null || true
  fi
  rm -f "$tmp" 2>/dev/null || true
  return 0
}

# Backup datado antes de mexer num .env que JÁ EXISTIA — a mesma disciplina do
# backup_and_install_file do mac_env_install.sh, que é a única coisa do modelo
# dele que faltava aqui. Sem isto, reinstalar sobre uma instalação existente
# reescrevia PROJECTS_HOST_ROOT, a chave do cookie do Dashboards e as variáveis
# de autenticação sem nenhum caminho de volta. Uma vez por execução.
AF_ENV_BACKED_UP=0
backup_env_once() {
  [ "$AF_ENV_BACKED_UP" = "1" ] && return 0
  [ "$ENV_STATE" = "created" ] && return 0   # nasceu agora: não há o que preservar
  [ -f .env ] || return 0
  local nome
  nome=".env.backup.$(date +%Y%m%d%H%M%S)"
  cp .env "$nome" 2>/dev/null || return 0
  # ACUMULA. A chave era sobrescrita a cada instalacao, entao o manifesto so
  # conhecia o backup mais novo e os anteriores ficavam sem dono: presentes na
  # pasta, ausentes do plano e sem ninguem para dizer que eram nossos.
  local anteriores
  anteriores="$(manifest_get "$AF_MANIFEST" env_backup)"
  [ -n "$anteriores" ] && nome="${anteriores},${nome}"
  manifest_set "$AF_MANIFEST" env_backup "$nome"
  AF_ENV_BACKED_UP=1
  info "your previous .env was copied to ${nome}"
  return 0
}

# set_env VAR VALUE — replace or append in .env. Vivia no meio da fase 3 e
# ficou ABAIXO do gate de biblioteca: a bancada nao a enxergava e nenhuma
# funcao testavel podia usa-la. Mora aqui, junto do backup_env_once que ela
# chama.
set_env() {
  backup_env_once
  if grep -q "^$1=" .env; then
    tmp_env="$(mktemp)"
    sed "s|^$1=.*|$1=$2|" .env > "${tmp_env}" && mv "${tmp_env}" .env
  else
    printf '%s=%s\n' "$1" "$2" >> .env
  fi
}

# ── Porta configuravel (ATLASFILE_PORT e familia) ───────────────────────────
# O compose interpola ${ATLASFILE_PORT:-8000}; estes resolvedores existem para
# a guarda de porta, as esperas e as URLs impressas falarem da MESMA porta que
# o compose vai usar. Precedencia: flag > env > .env > default. Shape estrito
# porque o valor flui para lsof, curl e para o sed do set_env.
af_valid_port() { # <valor>
  case "${1:-}" in ''|*[!0-9]*) return 1 ;; esac
  [ "$1" -ge 1 ] && [ "$1" -le 65535 ]
}

af_env_lookup() { # <chave> — valor da chave no .env do INSTALL_DIR, se houver
  [ -f "${INSTALL_DIR}/.env" ] || return 0
  # `|| true` porque chave AUSENTE e resultado normal: sem ele, o rc 1 do grep
  # atravessa o pipefail, a atribuicao `x="$(...)"` falha e o set -e mata o
  # instalador SEM UMA LINHA — pego pela bancada de forma real, nao pelos
  # testes de funcao (que so cobriam chave presente).
  grep "^$1=" "${INSTALL_DIR}/.env" 2>/dev/null | head -1 | cut -d= -f2- || true
}

af_resolve_app_port() {
  AF_PORT_EXPLICIT=0
  local cand
  for cand in "${AF_PORT_FLAG:-}" "${ATLASFILE_PORT:-}"; do
    if [ -n "$cand" ]; then
      af_valid_port "$cand" || fail "ATLASFILE_PORT \"$cand\" is not a valid TCP port (1-65535)"
      AF_PORT="$cand"; AF_PORT_EXPLICIT=1; return 0
    fi
  done
  # Valor herdado de instalacao anterior: um .env corrompido nao pode propagar
  # lixo — fora do shape, o default assume em silencio (a fonte nao e o
  # comando que o usuario acabou de digitar).
  cand="$(af_env_lookup ATLASFILE_PORT)"
  if af_valid_port "$cand"; then AF_PORT="$cand"; else AF_PORT=8000; fi
  return 0
}

af_resolve_os_port() {
  if af_valid_port "${OPENSEARCH_PORT:-}"; then AF_OS_PORT="${OPENSEARCH_PORT}"
  else
    AF_OS_PORT="$(af_env_lookup OPENSEARCH_PORT)"
    af_valid_port "$AF_OS_PORT" || AF_OS_PORT=9200
  fi
  return 0
}

# Alguem escuta nesta porta? `ss` primeiro: no Linux o lsof SEM root nao
# enxerga socket de outro usuario — medido no E2E da VM lima, onde a guarda
# deixou a porta 22 (sshd) passar e o conflito so apareceu no bind do Docker.
# O ss lista todos os listeners sem privilegio; o lsof fica de fallback (macOS
# nao tem ss, e la o lsof enxerga).
af_port_busy() { # <porta>
  if command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | grep -qE "[:.]$1[[:space:]]"
    return $?
  fi
  command -v lsof >/dev/null 2>&1 && lsof -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

# So persiste o que o usuario PEDIU (flag/env): pinar o default 8000 no .env
# impediria um default futuro de valer em quem nunca escolheu porta.
af_persist_port() {
  [ "${AF_PORT_EXPLICIT:-0}" = "1" ] || return 0
  set_env ATLASFILE_PORT "$AF_PORT"
  ok "ATLASFILE_PORT=${AF_PORT} written to .env (the host port the stack binds)"
}


# ── Uninstall ───────────────────────────────────────────────────────────────
# Facts first (all read-only), then a plan in text with a REMOVED and a
# PRESERVED section, then one confirmation, then execution. Every fact below is
# a variable so the plan builder can be unit-tested without a Docker daemon.
UN_DIR=""; UN_PROJECT=""; UN_COMPOSE_FILE=0
UN_CLONE_STATE="unknown"; UN_DIR_DIRTY=0; UN_DIRTY_LIST=""; UN_ENV=0
# O que a instalação registrou sobre si mesma. `install_dir` era gravado e nunca
# lido — a garantia documentada ("a pasta só some se bater com o install_dir
# registrado") não existia no código. `env_file`/`api_keys_file` idem, e o
# segundo guarda uma CHAVE DE API viva.
UN_DIR_RECORDED=""; UN_ENV_CREATED=""; UN_APIKEYS_CREATED=""; UN_ENV_BACKUP=""
UN_BUNDLE_FILES=""; UN_BUNDLE_BACKUPS=""
UN_CONTAINERS=0; UN_VOLUME=""; UN_IMAGES=""
UN_PROJECTS_ROOT=""; UN_PROJECTS_CREATED="preexisting"; UN_PROJECTS_FILES=0
UN_OTHER_ARTIFACTS=""; UN_OLLAMA_PRESENT=0
UN_PLAN_REMOVE=""; UN_PLAN_KEEP=""; UN_ACTIONS=""

# ── Facts from the other side of an OS boundary ─────────────────────────────
# On Windows the machine has TWO scopes with two manifests: this script owns the
# distro, install.ps1 owns Windows. Until this existed, the plan printed here
# described the distro ONLY, while install.ps1 removed Windows packages right
# after — so the plan said "Docker preserved" seconds before Docker was deleted,
# and Ollama appeared in NEITHER section. The caller now hands its facts over as
# data (`--host-extra docker=created,ollama=created,wsl=created`) and they are
# rendered in the single plan the user confirms. No action is emitted for them:
# the side that owns the package is the side that removes it.
host_extra_has() { # <key>
  case ",${HOST_EXTRA}," in
    *",$1="*) return 0 ;;
  esac
  return 1
}

host_extra_label() { # <key>
  case "$1" in
    docker)     printf 'Docker Desktop (Windows side)' ;;
    ollama)     printf 'Ollama (Windows side)' ;;
    wsl)        printf 'WSL2' ;;
    wsl_distro) printf 'the WSL distro this installer downloaded' ;;
    *)          printf '%s (Windows side)' "$1" ;;
  esac
}

# `pending` é o estado de uma instalação que começou e não se sabe se terminou:
# o processo pode ter morrido entre o comando e o registro, ou o próprio comando
# ter falhado (o run_step aborta o script). Nos dois casos NÃO dá para provar que
# criamos — então o plano PRESERVA e diz por quê, em vez de deixar o usuário sem
# nenhuma pista de que o instalador mexeu ali.
un_pending_note() { # <chave> <rótulo>
  [ "$(host_get "$1")" = "pending" ] || return 1
  un_add_keep "${2}: this installer was interrupted while installing it and cannot prove it created it — preserved. Remove it by hand if it is not yours"
  return 0
}

un_render_host_extra() { # <deps>
  local deps="$1" pair key val label old_ifs
  [ -n "$HOST_EXTRA" ] || return 0
  old_ifs="$IFS"; IFS=','
  # shellcheck disable=SC2086  # deliberate word split on the comma-separated list
  set -- $HOST_EXTRA
  IFS="$old_ifs"
  for pair in "$@"; do
    key="${pair%%=*}"; val="${pair#*=}"
    [ -n "$key" ] && [ "$key" != "$pair" ] || continue
    label="$(host_extra_label "$key")"
    if [ "$key" = "wsl" ] || [ "$key" = "wsl_distro" ]; then
      # Recurso do Windows do qual outras ferramentas dependem — e a distro, que
      # pode ter virado o ambiente de trabalho da pessoa. Nunca removidos, quem
      # quer que os tenha criado. O que muda é que agora eles APARECEM: antes o
      # plano falava do recurso e ficava calado sobre a distro baixada por nós.
      un_add_keep "${label} — never removed automatically (other tools may depend on it)"
      continue
    fi
    if [ "$val" != "created" ]; then
      un_add_keep "${label} was already on this machine before AtlasFile — preserved"
    elif [ "$deps" = "1" ]; then
      un_add_remove "${label}, installed by AtlasFile — removed by the Windows installer once you confirm this plan"
    else
      un_add_keep "${label}, installed by AtlasFile — pass --remove-deps to revert it too"
    fi
  done
  return 0
}

# Compose derives the project name from COMPOSE_PROJECT_NAME in .env, falling
# back to the sanitised directory name. install.sh:~420 only ever used the
# directory rule — which is wrong for any install that sets the variable.
un_project_name() { # <dir>
  local dir="$1" name=""
  if [ -f "${dir}/.env" ]; then
    name="$(grep '^COMPOSE_PROJECT_NAME=' "${dir}/.env" 2>/dev/null | head -1 | cut -d= -f2- || true)"
  fi
  [ -n "$name" ] || name="$(basename "$dir")"
  printf '%s' "$name" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_-]//g'
}

un_add_remove() { UN_PLAN_REMOVE="${UN_PLAN_REMOVE}$(af_wrap "${GUT}  • " "${GUT}    " 6 "$1")
"; }
un_add_keep()   { UN_PLAN_KEEP="${UN_PLAN_KEEP}$(af_wrap "${GUT}  • " "${GUT}    " 6 "$1")
"; }
un_act()        { UN_ACTIONS="${UN_ACTIONS}$1
"; }

un_collect() { # <dir>
  local dir="$1" f
  UN_DIR="$dir"
  UN_PROJECT="$(un_project_name "$dir")"
  [ -f "${dir}/docker-compose.yml" ] && UN_COMPOSE_FILE=1
  [ -f "${dir}/.env" ] && UN_ENV=1

  local mf="${dir}/${AF_MANIFEST_NAME}"
  UN_CLONE_STATE="$(manifest_get "$mf" repo_clone)"; [ -n "$UN_CLONE_STATE" ] || UN_CLONE_STATE="unknown"
  UN_DIR_RECORDED="$(manifest_get "$mf" install_dir)"
  UN_ENV_CREATED="$(manifest_get "$mf" env_file)"
  UN_APIKEYS_CREATED="$(manifest_get "$mf" api_keys_file)"
  UN_ENV_BACKUP="$(manifest_get "$mf" env_backup)"
  UN_PROJECTS_ROOT="$(manifest_get "$mf" projects_root)"
  UN_PROJECTS_CREATED="$(manifest_get "$mf" projects_root_created)"; [ -n "$UN_PROJECTS_CREATED" ] || UN_PROJECTS_CREATED="preexisting"
  if [ -z "$UN_PROJECTS_ROOT" ] && [ "$UN_ENV" = "1" ]; then
    UN_PROJECTS_ROOT="$(grep '^PROJECTS_HOST_ROOT=' "${dir}/.env" 2>/dev/null | head -1 | cut -d= -f2- || true)"
  fi
  # Mesmo portão do lado da instalação: um .env corrompido não pode fazer o
  # plano de remoção falar de um caminho que não existe — nem, pior, tentar
  # apagá-lo. E os placeholders do .env.example não são pasta de ninguém: o lado
  # da instalação já os descartava, o do uninstall não, e por isso um plano real
  # anunciou "seus documentos em /Users/your-user/Documents/Projects".
  case "$UN_PROJECTS_ROOT" in
    "/path/to/Projects"|"/Users/your-user/Documents/Projects") UN_PROJECTS_ROOT="" ;;
  esac
  if [ -n "$UN_PROJECTS_ROOT" ]; then
    UN_PROJECTS_ROOT="$(af_sane_path "$UN_PROJECTS_ROOT" || true)"
  fi
  if [ -n "$UN_PROJECTS_ROOT" ] && [ -d "$UN_PROJECTS_ROOT" ]; then
    UN_PROJECTS_FILES="$(find "$UN_PROJECTS_ROOT" -mindepth 1 2>/dev/null | wc -l | tr -d ' ')"
  fi

  if [ -d "${dir}/.git" ]; then
    UN_DIR_DIRTY=0
    # The installer's own artifacts must never make the clone un-removable.
    # Measured in a real install: .atlasfile-install-manifest showed up as
    # untracked (an install whose clone predates the .gitignore entry) and the
    # dirty guard kept the directory forever. Excluded explicitly, so the guard
    # only ever protects work that is actually the user's.
    #
    # config/api_keys.json is the same trap and it BIT ON A REAL WINDOWS 11:
    # --enable-auth (part of the recommended one-liner) writes that file, and a
    # broken .gitignore line left it untracked, so EVERY such install reported
    # "has local changes — NOT removed" and kept the clone forever. The ignore
    # rule is fixed, but a clone created before the fix still carries the file,
    # so the exclusion has to live here too.
    #
    # `.env.backup.*` fecha a serie, e era o pior dos tres: backup_env_once cria
    # um a cada instalacao que SOBRESCREVE um .env existente. Logo a primeira
    # instalacao da vida deixava a pasta removivel, e toda reinstalacao a
    # travava PARA SEMPRE — com a tela dizendo "has local changes", culpando o
    # usuario por um arquivo que o instalador escreveu. Medido na maquina dele:
    # dois backups, nenhum seu.
    # Pelos NOMES que o manifesto registra, nunca pelo padrao `.env.backup.*`:
    # um arquivo com esse nome que o USUARIO tenha posto aqui continua travando
    # a remocao, que e o comportamento conservador que o resto do plano segue.
    #
    # Guarda O QUE suja, nao so o sim/nao: "has local changes" sozinho nao e
    # acionavel. Numa maquina real o que travava a pasta era um backup do
    # PROPRIO instalador, e nao havia como o usuario descobrir isso pela tela.
    local sujo
    # shellcheck disable=SC2046,SC2086  # o split do pathspec e o objetivo aqui
    sujo="$(git -C "$dir" status --porcelain -- . $(af_own_pathspec "$dir") 2>/dev/null || true)"
    if [ -n "$sujo" ]; then
      UN_DIR_DIRTY=1
      # o porcelain traz duas colunas de estado antes do caminho
      UN_DIRTY_LIST="$(printf '%s\n' "$sujo" | LC_ALL=C sed 's/^...//')"
    fi
  fi

  # Instalacao bundle nao tem .git para responder "o que aqui nao e nosso?".
  # O manifesto responde: a lista dos arquivos da release (bundle_files) mais
  # os artefatos que o instalador escreve; qualquer OUTRO arquivo e trabalho do
  # usuario e trava a remocao da pasta — a mesma conserva do clone sujo.
  UN_BUNDLE_FILES="$(manifest_get "$mf" bundle_files)"
  UN_BUNDLE_BACKUPS="$(manifest_get "$mf" bundle_backups)"
  if [ ! -d "${dir}/.git" ] && [ "$UN_CLONE_STATE" = "bundle" ]; then
    UN_DIR_DIRTY=0
    local estranhos
    estranhos="$(un_bundle_strange "$dir")"
    if [ -n "$estranhos" ]; then
      UN_DIR_DIRTY=1
      UN_DIRTY_LIST="$estranhos"
    fi
  fi

  # Measured, not assumed: the plan may only speak about an Ollama that is
  # actually here. Same rule the mac-env-setup uninstaller follows — it asks
  # `brew list --cask X` before promising to remove anything.
  command -v ollama >/dev/null 2>&1 && UN_OLLAMA_PRESENT=1

  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    UN_CONTAINERS="$(docker ps -aq --filter "label=com.docker.compose.project=${UN_PROJECT}" 2>/dev/null | wc -l | tr -d ' ')"
    UN_VOLUME="$(docker volume ls -q --filter "label=com.docker.compose.project=${UN_PROJECT}" 2>/dev/null | tr '\n' ' ' | sed 's/ *$//')"
    # Exact service names only: a `${project}-` prefix match would also catch
    # `atlasfile-dev-*` when uninstalling the project named `atlasfile`.
    # `atlasfile` is the consolidated service; api/web/mcp stay for installs
    # upgraded from 0.56.x that still carry the old images.
    for f in atlasfile api web mcp; do
      if docker image inspect "${UN_PROJECT}-${f}" >/dev/null 2>&1; then
        UN_IMAGES="${UN_IMAGES}${UN_PROJECT}-${f} "
      fi
    done
    # v1.0.0: a stack roda a imagem publicada (ghcr.io/aleonnet/atlasfile:<v>)
    # ou a do overlay de build local (atlasfile-local:<tag>). `down --rmi
    # local` NÃO remove imagem com `image:` nomeado no compose — sem listar
    # aqui, o uninstall reportaria sucesso deixando ~700 MB no disco.
    for ref in $(docker images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null | grep -E '^(ghcr\.io/aleonnet/atlasfile|atlasfile-local):' || true); do
      UN_IMAGES="${UN_IMAGES}${ref} "
    done
    # Anything AtlasFile-shaped that does NOT belong to this project keeps the
    # shared system dependencies (Docker above all) off the removal list.
    UN_OTHER_ARTIFACTS="$(docker volume ls -q 2>/dev/null | grep -i atlasfile | grep -v "^${UN_PROJECT}_" | tr '\n' ' ' | sed 's/ *$//' || true)"
  fi
  return 0
}

# Builds UN_PLAN_REMOVE / UN_PLAN_KEEP / UN_ACTIONS from the facts above.
# purge_data: 1 remove the volume, 0 keep it. remove_deps: 1 allowed.
un_build_plan() { # <purge_data> <remove_deps> <force>
  local purge="$1" deps="$2" force="$3" st model bkp bkps
  UN_PLAN_REMOVE=""; UN_PLAN_KEEP=""; UN_ACTIONS=""

  # ── the stack (unambiguously ours) ──
  if [ "$UN_COMPOSE_FILE" = "1" ]; then
    un_add_remove "stack '${UN_PROJECT}': containers, network and the app images (${UN_CONTAINERS} container(s))"
    un_act "compose-down"
  else
    un_add_keep "no docker-compose.yml in ${UN_DIR} — the stack cannot be removed from here"
  fi
  if [ -n "$UN_VOLUME" ]; then
    if [ "$purge" = "1" ]; then
      un_add_remove "data volume ${UN_VOLUME} — THE SEARCH INDEX IS ERASED (rebuildable with Reconcile: your documents and the journal on disk are the source)"
      un_act "purge-volume"
    elif [ "$purge" = "ask" ]; then
      # --plan-only runs BEFORE anyone is asked anything: the honest rendering
      # is "still open", never a default dressed up as a decision.
      un_add_keep "data volume ${UN_VOLUME} — still your call (--purge-data erases the index, --keep-data keeps it)"
    else
      un_add_keep "data volume ${UN_VOLUME} — kept, with its admin password, so a reinstall in this same folder reuses it (the password is recorded in ${AF_KEPT_VOLUMES}, readable only by you)"
    fi
  fi
  [ -n "$UN_IMAGES" ] && un_add_keep "shared upstream images (opensearchproject/*) — remove them by hand if you want the disk back"

  # ── the clone (ou o dir do bundle — as guardas sao as MESMAS) ──
  # `bundle` e o dir que o proprio instalador criou no caminho sem clone: tao
  # removivel quanto o `created`, com as duas mesmas provas — o install_dir do
  # manifesto tem de bater, e trabalho do usuario dentro trava a remocao.
  if { [ "$UN_CLONE_STATE" = "created" ] || [ "$UN_CLONE_STATE" = "bundle" ]; } \
     && [ -n "$UN_DIR_RECORDED" ] && [ "$UN_DIR_RECORDED" != "$UN_DIR" ]; then
    # A garantia que o CHANGELOG anunciava desde a v0.54.0 e que o código não
    # tinha: a pasta só é apagada se ela for a MESMA que o manifesto registrou.
    # Um manifesto copiado, um --dir apontado para o lugar errado ou uma pasta
    # renomeada deixavam de ser detectáveis.
    un_add_keep "${UN_DIR} — NOT removed: the manifest here records the install at ${UN_DIR_RECORDED}, not this folder"
  elif [ "$UN_CLONE_STATE" = "created" ] || [ "$UN_CLONE_STATE" = "bundle" ]; then
    if [ "$UN_DIR_DIRTY" = "1" ] && [ "$force" != "1" ]; then
      if [ "$UN_CLONE_STATE" = "bundle" ]; then
        un_add_keep "${UN_DIR} has files this installer did not put there — NOT removed (re-run with --force to remove it anyway)"
      else
        un_add_keep "${UN_DIR} has local changes — NOT removed (re-run with --force to remove it anyway)"
      fi
      UN_PLAN_KEEP="${UN_PLAN_KEEP}$(un_dirty_lines)
"
    else
      if [ "$UN_CLONE_STATE" = "bundle" ]; then
        un_add_remove "install directory ${UN_DIR} (installed from the release bundle by this installer, with its .env)"
      else
        un_add_remove "install directory ${UN_DIR} (clone created by this installer, with its .env)"
      fi
      un_act "rm-clone"
    fi
  elif [ "$UN_COMPOSE_FILE" = "1" ]; then
    un_add_keep "${UN_DIR} was not created by this installer — preserved (only the stack above was touched)"
  else
    # No compose file means no stack was touched either: claiming otherwise
    # would make the plan describe something that did not happen.
    un_add_keep "${UN_DIR} was not created by this installer — preserved"
  fi

  # ── artefatos nossos dentro de uma pasta que vai SOBREVIVER ──
  # `config/api_keys.json` guarda uma CHAVE DE API VIVA. Como um clone que não
  # foi criado por nós é sempre preservado, a chave ficava em disco depois da
  # desinstalação — e as duas chaves do manifesto que provariam isso eram
  # gravadas e nunca lidas.
  if ! un_has_action "rm-clone"; then
    if [ "$UN_APIKEYS_CREATED" = "created" ] && [ -f "${UN_DIR}/config/api_keys.json" ]; then
      un_add_remove "${UN_DIR}/config/api_keys.json — created by this installer and holds a live API key"
      un_act "rm-apikeys"
    fi
    if [ "$UN_ENV_CREATED" = "created" ] && [ -f "${UN_DIR}/.env" ]; then
      un_add_remove "${UN_DIR}/.env — created by this installer (the folder itself is preserved)"
      un_act "rm-env"
    fi
    while IFS= read -r bkp; do
      [ -n "$bkp" ] || continue
      un_add_keep "${bkp} — a .env you had before an install, kept so you can restore it"
    done <<EOF
$(un_env_backups)
EOF
  else
    # A pasta inteira vai, e os backups estao dentro dela. Eles guardam a SENHA
    # do OpenSearch e a CHAVE DE API de instalacoes anteriores, entao sumir com
    # isso em silencio seria a mesma falta de prestacao de contas do volume.
    bkps="$(un_env_backups | wc -l | tr -d ' ')"
    if [ "${bkps:-0}" -gt 0 ]; then
      un_add_remove "${bkps} .env backup(s) inside ${UN_DIR} — they hold the OpenSearch password and API key of earlier installs"
    fi
  fi

  # ── the user's documents ──
  if [ -n "$UN_PROJECTS_ROOT" ]; then
    if [ "$UN_PROJECTS_CREATED" = "created" ] && [ "$UN_PROJECTS_FILES" = "0" ]; then
      un_add_remove "empty folder ${UN_PROJECTS_ROOT} (created by the installer and never used)"
      un_act "rm-projects-root"
    else
      un_add_keep "your documents in ${UN_PROJECTS_ROOT} (${UN_PROJECTS_FILES} item(s)), including the _ATLASFILE state — never touched"
    fi
  fi

  # ── system dependencies ──
  # Facts from the other side of the boundary go FIRST: on Windows they are the
  # ones the user recognises (Docker Desktop, Ollama), and they must be visible
  # in the same list, before the same confirmation.
  un_render_host_extra "$deps"

  if [ "$deps" != "1" ]; then
    un_add_keep "system dependencies (Docker, git, Ollama) — pass --remove-deps to revert the ones this installer created"
  else
    if host_extra_has docker; then
      # The docker CLI inside the distro is injected by Docker Desktop's WSL
      # integration; it is not a package this script installed. Saying anything
      # else here would contradict the Windows line printed just above.
      :
    elif [ -n "$UN_OTHER_ARTIFACTS" ]; then
      un_add_keep "Docker: another AtlasFile install still uses it here (${UN_OTHER_ARTIFACTS}) — preserved"
    else
      st="$(host_get docker)"
      if un_pending_note docker "Docker"; then
        :
      elif [ "$st" = "created" ]; then
        if [ "$OS_KIND" = "mac" ]; then
          un_add_remove "Docker Desktop, installed by AtlasFile — brew uninstall --cask docker-desktop (THIS DELETES THE APP FROM /Applications)"
          un_act "brew-cask:docker-desktop"
        else
          un_add_remove "Docker Engine, installed by AtlasFile — ${PKG} remove docker-ce docker-ce-cli containerd.io docker-compose-plugin"
          un_act "pkg-docker"
        fi
      else
        un_add_keep "Docker was already on this machine before AtlasFile — preserved"
      fi
    fi

    st="$(host_get git)"
    if un_pending_note git "git"; then
      :
    elif [ "$st" = "created" ]; then
      un_add_remove "git, installed by AtlasFile"
      un_act "pkg-git"
    else
      un_add_keep "git was already here — preserved"
    fi

    st="$(host_get ollama)"
    if [ "$st" = "created" ] && [ "$OS_KIND" = "mac" ]; then
      un_add_remove "Ollama, installed by AtlasFile — brew uninstall --cask (THIS DELETES THE APP)"
      un_act "rm-ollama"
    elif [ "$st" = "created" ]; then
      # Ollama's Linux installer ships no uninstaller; the vendor documents a
      # sequence of sudo rm/userdel that this installer will not run blind.
      un_add_keep "Ollama, installed by AtlasFile — remove it by hand (vendor steps): sudo systemctl disable --now ollama; sudo rm /etc/systemd/system/ollama.service; sudo rm \$(command -v ollama); sudo rm -r /usr/share/ollama; sudo userdel ollama"
    elif [ -n "$st" ]; then
      un_add_keep "Ollama was already here — preserved"
    elif host_extra_has ollama; then
      # Already stated, with the right scope, by un_render_host_extra above.
      :
    elif [ "$UN_OLLAMA_PRESENT" = "1" ]; then
      # The key is absent from the manifest and an ollama IS on this machine.
      # Silence here is how Ollama vanished from BOTH sections of a real plan
      # while the Windows side went ahead and tried to remove it: an unknown key
      # must produce a sentence, never nothing.
      un_add_keep "Ollama is on this machine but was not installed by AtlasFile — preserved"
    fi
    if [ "$(host_get ollama_model_state)" = "created" ]; then
      model="$(host_get ollama_model_name)"
      if [ -n "$model" ]; then
        un_add_remove "model ${model}, pulled by AtlasFile — ollama rm ${model}"
        un_act "ollama-rm:${model}"
      fi
    fi

    [ "$(host_get compose_plugin)" = "created" ] && { un_add_remove "docker-compose-plugin, installed by AtlasFile"; un_act "pkg-compose"; }
    [ "$(host_get docker_group)" = "created" ] && { un_add_remove "your membership in the docker group (added by AtlasFile)"; un_act "gpasswd-d"; }
    un_pending_note homebrew "Homebrew" || true
    [ "$(host_get homebrew)" = "created" ] && un_add_keep "Homebrew was installed by AtlasFile but is NEVER removed automatically — https://github.com/Homebrew/install#uninstall-homebrew"
  fi

  [ -n "$UN_ACTIONS" ] && un_act "rm-state"
  return 0
}

un_print_plan() {
  printf '%s\n' "$GUT"
  rule_sweep "Removal plan — ${UN_DIR}"
  printf '%s\n' "$GUT"
  if [ -n "$UN_PLAN_REMOVE" ]; then
    printf '%s%sWILL BE REMOVED%s\n%s%s\n' "$GUT" "$BOLD" "$RESET" "$UN_PLAN_REMOVE" "$GUT"
  else
    printf '%s%snothing to remove%s\n%s\n' "$GUT" "$DIM" "$RESET" "$GUT"
  fi
  if [ -n "$UN_PLAN_KEEP" ]; then
    printf '%s%sWILL BE PRESERVED%s\n%s%s\n' "$GUT" "$BOLD" "$RESET" "$UN_PLAN_KEEP" "$GUT"
  fi
  return 0
}

# Placar do final, no padrão do print_final_report do mac_env_install.sh: o que
# aconteceu, em números, e só os próximos passos que de fato se aplicam. O
# veredito anterior era uma frase fixa — dizia a mesma coisa tendo removido
# tudo ou quase nada.
# Fecha o trilho: uma linha de calha, o `╰──` e a folga antes do que vem fora
# dele. Estava solto em quatro lugares e faltava em tres — o --doctor e os dois
# --dry-run ABRIAM o trilho com `├──` e nunca o fechavam.
rail_end() { printf '%s\n' "$GUT"; rule_close; printf '\n'; }

un_report() {
  rail_end
  note "${BOLD}AtlasFile removed${RESET}"
  printf '  %s✔ %s removed%s' "$GREEN" "$UN_OK" "$RESET"
  [ "$UN_KO" -gt 0 ] && printf '   %s✘ %s failed%s' "$RED" "$UN_KO" "$RESET"
  printf '   %skept: what already existed on this machine%s\n\n' "$DIM" "$RESET"
  if [ -n "$UN_PROJECTS_ROOT" ] && [ "$UN_PROJECTS_FILES" != "0" ]; then
    note "your documents are untouched in ${UN_PROJECTS_ROOT}"
  fi
  [ "$UN_KO" -gt 0 ] && note "details of what failed: ${LOG_FILE}"
  printf '\n'
  return 0
}

un_has_action() { printf '%s' "$UN_ACTIONS" | grep -qx "$1"; }

# Todos os backups de .env que existem na pasta, nao so o do manifesto.
# O manifesto guarda UMA chave `env_backup`, sobrescrita a cada instalacao:
# o plano citava o mais novo e os anteriores ficavam sem dono na tela.
# Quantos caminhos mostrar antes de resumir. Teto explicito: um clone com 200
# arquivos mexidos nao pode empurrar o resto do plano para fora da tela.
UN_DIRTY_SHOW=5

# Emite as linhas que dizem O QUE suja o clone. Um so renderizador para o plano
# e o --doctor: dois textos para o mesmo fato divergem na primeira alteracao.
un_dirty_lines() {
  local n=0 caminho
  while IFS= read -r caminho; do
    [ -n "$caminho" ] || continue
    n=$(( n + 1 ))
    [ "$n" -le "$UN_DIRTY_SHOW" ] && af_wrap "${GUT}    - " "${GUT}      " 8 "$caminho"
  done <<EOF
$UN_DIRTY_LIST
EOF
  [ "$n" -gt "$UN_DIRTY_SHOW" ] && af_wrap "${GUT}    - " "${GUT}      " 8 "and $(( n - UN_DIRTY_SHOW )) more"
  return 0
}

# Os artefatos que o PROPRIO instalador escreve dentro do clone, em forma de
# pathspec do git. Uma lista so: a checagem de sujeira da desinstalacao e o
# realinhamento do clone precisam concordar sobre o que e "nosso", e duas listas
# separadas divergiriam na primeira alteracao.
af_own_pathspec() { # <dir>
  local dir="$1" n saida
  saida=":(exclude).env :(exclude)${AF_MANIFEST_NAME} :(exclude)config/api_keys.json"
  for n in $(printf '%s' "$(manifest_get "${dir}/${AF_MANIFEST_NAME}" env_backup)" | tr ',' ' '); do
    [ -n "$n" ] && saida="${saida} :(exclude)${n}"
  done
  printf '%s' "$saida"
}

# O equivalente do af_own_pathspec para o mundo bundle, onde nao ha git para
# perguntar: a lista dos artefatos NOSSOS, um por linha — os 4 arquivos da
# release (bundle_files, gravado na instalacao), o .env, o manifesto, a chave
# de API e os backups dos dois manifestos. Tudo fora dela e do usuario.
un_bundle_own_list() {
  printf '%s\n' ".env" "$AF_MANIFEST_NAME" "config/api_keys.json"
  printf '%s\n' "$UN_BUNDLE_FILES" | tr ',' '\n'
  printf '%s\n' "$UN_ENV_BACKUP" | tr ',' '\n'
  printf '%s\n' "$UN_BUNDLE_BACKUPS" | tr ',' '\n'
}

un_bundle_strange() { # <dir> — arquivos do dir que NAO sao artefatos nossos
  local dir="$1"
  ( cd "$dir" 2>/dev/null && find . -mindepth 1 \( -type f -o -type l \) | LC_ALL=C sed 's|^\./||' ) \
    | grep -vxF -f <(un_bundle_own_list | grep -v '^$') || true
}

un_env_backups() {
  local n
  [ -d "$UN_DIR" ] || return 0
  for n in $(printf '%s' "$UN_ENV_BACKUP" | tr ',' ' '); do
    [ -n "$n" ] && [ -f "${UN_DIR}/${n}" ] && printf '%s\n' "$n"
  done
  return 0
}

UN_FAILED=0
UN_OK=0
UN_KO=0
un_step() { # <label> <cmd...> — a failed step is reported, never fatal
  local label="$1"; shift
  if "$@" >>"$LOG_FILE" 2>&1; then
    ok "$label"
    UN_OK=$(( UN_OK + 1 ))
  else
    bar_clear
    printf '%s%s✘%s %s %s(details in %s)%s\n' "$GUT" "$RED" "$RESET" "$label" "$DIM" "$LOG_FILE" "$RESET"
    UN_FAILED=1
    UN_KO=$(( UN_KO + 1 ))
  fi
  return 0
}

# Guard against ever pointing rm -rf at something that is not an install.
un_dir_is_safe() { # <dir>
  case "$1" in
    /|"$HOME"|"") return 1 ;;
    /*) ;;
    *) return 1 ;;
  esac
  [ -d "$1" ] || return 1
  [ -d "$1/.git" ] || [ -f "$1/docker-compose.yml" ] || return 1
  return 0
}

un_compose_down() {
  local args="--remove-orphans --rmi local"
  un_has_action "purge-volume" && args="${args} --volumes"
  # Run from the install dir so compose resolves the project itself (it reads
  # COMPOSE_PROJECT_NAME from .env). Never remove containers by name: the
  # atlasfile-* names are fixed and may belong to a different install.
  # v1.0.0 supria so ATLASFILE_VERSION; o E2E da 4a provou a CLASSE numa VM
  # real, em DOIS tempos: (1) um uninstall parcial anterior (pasta suja
  # preservada) remove o .env, e a re-execucao com --force morria na
  # interpolacao de OUTRA variavel `:?` (OPENSEARCH_INITIAL_ADMIN_PASSWORD)
  # com zero containers no ar — a barreira parava por erro de interpolacao,
  # nao por stack viva; (2) a primeira correcao, por export, passou na bancada
  # e MORREU na VM: ali o docker roda atras do shim de sudo (grupo docker
  # ainda nao vale na sessao) e o sudo limpa o ambiente. A entrega e por
  # --env-file — o arquivo viaja com o comando e sobrevive ao sudo: copia do
  # .env (se houver) mais placeholder do que faltar. A do Dashboards interpola
  # mesmo com o profile desligado; um `down` nunca sobe nem puxa nada.
  # PROJECTS_HOST_ROOT entra na lista (3o tempo do mesmo E2E): nao e `:?`, mas
  # sem valor a spec do bind vira `:/projects` e o down morre em "invalid
  # spec". O placeholder dele e um CAMINHO — "0.0.0" seria lido como volume
  # nomeado inexistente e trocaria um erro por outro.
  ( cd "$UN_DIR" || exit 1
    local v envtmp rc_down
    envtmp="$(mktemp)"
    cat .env > "$envtmp" 2>/dev/null || true
    for v in ATLASFILE_VERSION OPENSEARCH_INITIAL_ADMIN_PASSWORD DASHBOARDS_COOKIE_PASSWORD; do
      grep -q "^${v}=" "$envtmp" || printf '%s=0.0.0\n' "$v" >> "$envtmp"
    done
    grep -q '^PROJECTS_HOST_ROOT=' "$envtmp" || printf 'PROJECTS_HOST_ROOT=/tmp\n' >> "$envtmp"
    rc_down=0
    docker compose --env-file "$envtmp" down $args || rc_down=$?
    rm -f "$envtmp"
    exit "$rc_down" )
}

un_remove_images() {
  # v1.0.0: `down --rmi local` só remove imagem SEM `image:` nomeado no
  # compose — a publicada (ghcr.io/...) e a do overlay (atlasfile-local)
  # ficariam para trás. Remove só o que o un_collect listou; imagem que o
  # --rmi já levou não é erro.
  local img
  for img in $UN_IMAGES; do
    if docker image inspect "$img" >/dev/null 2>&1; then
      docker rmi "$img" >/dev/null 2>&1 || return 1
    fi
  done
  return 0
}

un_execute() {
  local act model bkps_n
  while IFS= read -r act; do
    [ -n "$act" ] || continue
    case "$act" in
      compose-down)
        un_step "removing the stack (containers, network, local images)" un_compose_down
        # PARA AQUI se a stack não saiu, e isso não é zelo: as ações seguintes
        # apagam o clone — que contém o docker-compose.yml, a única forma de
        # descer a stack — e o manifesto, que é o registro do que criamos.
        #
        # Medido numa VM Ubuntu: o `docker compose down` falhou por permissão,
        # a execução seguiu, e o usuário ficou com CINCO containers no ar, um
        # volume e três imagens construídas, sem clone e sem manifesto para
        # removê-los. O desinstalador apagou os meios de reverter e falhou em
        # reverter — perder a ferramenta é pior do que não usá-la.
        if [ "$UN_FAILED" = "1" ]; then
          warn "the stack did not come down — stopping here, on purpose"
          info "nothing else was touched: the clone and the manifest are exactly what you need to retry"
          info "check 'docker ps'; on Linux a fresh login applies your docker group, then run the uninstall again"
          return 0
        fi
        # v1.0.0: images with a named `image:` survive `down --rmi local` —
        # explicit removal, as its own step so the screen accounts for it
        # (mesma regra do purge-volume: a ação acontece e a tela conta).
        if [ -n "$UN_IMAGES" ]; then
          un_step "removing the app images (${UN_IMAGES% })" un_remove_images
        fi ;;
      purge-volume)
        # `compose down --volumes` ja leva o volume junto quando a stack sai do
        # clone, entao aqui nao ha trabalho a fazer — mas HA conta a prestar.
        #
        # Medido numa desinstalacao real: o plano listava o volume em destaque
        # ("THE SEARCH INDEX IS ERASED"), o usuario confirmou, o volume sumiu e
        # NENHUMA das quatro linhas da execucao o citava. O unico passo que o
        # apagava tinha rotulo "containers, network, local images", que nao fala
        # de volume. Destruir o indice em silencio e a mesma classe do veredito
        # prematuro que o lado Windows tinha: a acao acontece e a tela nao conta.
        if [ -n "$UN_VOLUME" ]; then
          if un_has_action "compose-down"; then
            ok "volume ${UN_VOLUME} erased with the stack"
            UN_OK=$(( UN_OK + 1 ))
          else
            un_step "removing volume ${UN_VOLUME}" docker volume rm $UN_VOLUME
          fi
          af_kept_volume_forget "$UN_VOLUME"
        fi ;;
      rm-clone)
        if un_dir_is_safe "$UN_DIR"; then
          # contado ANTES de remover: depois nao ha o que contar. Mesma regra do
          # volume — item que o plano prometeu em separado se confirma em
          # separado, mesmo quando some junto com outra coisa.
          bkps_n="$(un_env_backups | wc -l | tr -d ' ')"
          un_step "removing ${UN_DIR}" rm -rf "$UN_DIR"
          if [ "${bkps_n:-0}" -gt 0 ] && [ ! -d "$UN_DIR" ]; then
            ok "${bkps_n} .env backup(s) removed with the folder"
            UN_OK=$(( UN_OK + 1 ))
          fi
        else
          warn "refusing to remove ${UN_DIR}: it does not look like an AtlasFile install"
        fi ;;
      rm-apikeys)
        un_step "removing ${UN_DIR}/config/api_keys.json" rm -f "${UN_DIR}/config/api_keys.json" ;;
      rm-env)
        un_step "removing ${UN_DIR}/.env" rm -f "${UN_DIR}/.env" ;;
      rm-projects-root)
        # rmdir on purpose: it refuses on a non-empty directory, so a race that
        # filled the folder between the plan and here cannot destroy documents.
        un_step "removing the empty folder ${UN_PROJECTS_ROOT}" rmdir "$UN_PROJECTS_ROOT" ;;
      brew-cask:*)
        un_step "removing ${act#brew-cask:} (Homebrew cask)" brew uninstall --cask "${act#brew-cask:}" ;;
      pkg-docker)
        if [ "$PKG" = "apt" ]; then
          un_step "removing Docker Engine (apt)" as_root env DEBIAN_FRONTEND=noninteractive apt-get remove -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
        else
          un_step "removing Docker Engine (dnf)" as_root dnf remove -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
        fi ;;
      pkg-git)
        if [ "$OS_KIND" = "mac" ]; then un_step "removing git (Homebrew)" brew uninstall git
        elif [ "$PKG" = "apt" ]; then un_step "removing git (apt)" as_root env DEBIAN_FRONTEND=noninteractive apt-get remove -y git
        else un_step "removing git (dnf)" as_root dnf remove -y git; fi ;;
      pkg-compose)
        if [ "$PKG" = "apt" ]; then un_step "removing docker-compose-plugin (apt)" as_root env DEBIAN_FRONTEND=noninteractive apt-get remove -y docker-compose-plugin
        else un_step "removing docker-compose-plugin (dnf)" as_root dnf remove -y docker-compose-plugin; fi ;;
      rm-ollama)
        # cask name changed over time — try the current one, then the legacy
        if ! brew uninstall --cask ollama-app >>"$LOG_FILE" 2>&1; then
          un_step "removing Ollama (Homebrew cask)" brew uninstall --cask ollama
        else
          ok "removing Ollama (Homebrew cask)"
          UN_OK=$(( UN_OK + 1 ))
        fi ;;
      ollama-rm:*)
        model="${act#ollama-rm:}"
        un_step "removing model ${model}" ollama rm "$model" ;;
      gpasswd-d)
        un_step "removing ${USER} from the docker group" as_root gpasswd -d "$USER" docker ;;
      rm-state)
        rm -f "$AF_HOST_MANIFEST" 2>/dev/null || true
        rmdir "$AF_STATE_DIR" 2>/dev/null || true
        ok "installer bookkeeping removed"
        UN_OK=$(( UN_OK + 1 )) ;;
    esac
  done <<EOF
$UN_ACTIONS
EOF
  return 0
}

run_uninstall() {
  detect_os
  # O retrato do Docker ANTES de coletar os fatos, senão ele sai vazio.
  #
  # Medido numa VM Ubuntu limpa: logo após a instalação o grupo `docker` ainda
  # não vale nesta sessão (só no próximo login — o próprio instalador avisa),
  # então `docker info` falha sem sudo. Como o un_collect trancava TODO o
  # retrato atrás dele, o plano saía cego: dizia "0 container(s)" com cinco no
  # ar e o VOLUME sumia das duas seções — junto com a garantia de que o usuário
  # decide sobre o índice, que é a única coisa nesta tela sem default.
  #
  # É exatamente a janela em que alguém desinstala: instalou, algo deu errado,
  # ainda não relogou.
  if [ "$OS_KIND" = "linux" ] && ! docker info >/dev/null 2>&1; then
    if ! af_docker_shim_linux && [ -r "$TTY_DEV" ] && command -v sudo >/dev/null 2>&1; then
      # Sem credencial em cache: pede uma vez, e só se houver terminal. NUNCA
      # aborta — um uninstall que não consegue elevar ainda tem trabalho a
      # fazer (a pasta, o manifesto, os documentos a preservar).
      info "administrator password needed to read the Docker state"
      sudo -v < "$TTY_DEV" >/dev/null 2>&1 || true
      af_docker_shim_linux || true
    fi
    docker info >/dev/null 2>&1 \
      || warn "docker is not reachable from this session — the plan below cannot see containers or volumes"
  fi
  un_collect "$INSTALL_DIR"

  # A run that installed Docker and then died BEFORE cloning leaves no install
  # directory but a perfectly good host manifest — that half-installed state is
  # exactly why the host manifest is written the moment each ensure_* decides.
  # Refusing here would strand the user with a Docker they did not have before
  # and no tool to revert it, so the deps-only plan is still offered.
  if [ "$UN_COMPOSE_FILE" = "0" ] && [ ! -d "${INSTALL_DIR}" ]; then
    if [ -f "$AF_HOST_MANIFEST" ]; then
      info "no install at ${INSTALL_DIR}, but this host has a prerequisite manifest — planning the system dependencies only"
    elif [ "$DELEGATED" = "1" ]; then
      # Delegado e sem nada deste lado: isto NAO e erro, e o fluxo SEGUE. O
      # outro lado tem o proprio manifesto e pode ter Docker Desktop para
      # remover; o plano ainda precisa ser montado para RENDERIZAR os fatos
      # dele. Abortar com codigo 1 fazia o orquestrador dizer "could not read
      # the removal plan" e parar, deixando o Docker instalado — medido num
      # Windows 11 real logo apos uma desinstalacao bem-sucedida.
      info "nothing of AtlasFile is left at ${INSTALL_DIR} on this side"
    else
      fail "no AtlasFile install found at ${INSTALL_DIR} — point --dir at the right folder"
    fi
  fi

  # Facts first, and nobody has been asked anything yet: --plan-only short-
  # circuits here so an orchestrator can read the plan of THIS side before
  # putting a single question to the user.
  if [ "$PLAN_ONLY" = "1" ] || [ "$DRY_RUN" = "1" ]; then
    un_build_plan "${PURGE_DATA:-ask}" "$REMOVE_DEPS" "$FORCE"
    un_print_plan
    # Fatos em forma legível por máquina, para o orquestrador não ter de
    # adivinhar lendo a prosa do plano: se há volume, ele sabe que precisa
    # perguntar; se não há ação alguma, sabe que não há o que confirmar.
    #
    # Só no modo de PROTOCOLO. Quem digitou `--uninstall --dry-run` é uma pessoa,
    # e essas linhas são ruído na tela dela.
    if [ "$PLAN_ONLY" = "1" ]; then
      printf 'ATLASFILE_FACT: volume=%s\n' "$UN_VOLUME"
      if [ -n "$UN_ACTIONS" ]; then
        printf 'ATLASFILE_FACT: actions=1\n'
      else
        printf 'ATLASFILE_FACT: actions=0\n'
      fi
      sentinel "plan-only"
    else
      info "--dry-run: nothing was touched."
      [ "$DELEGATED" = "1" ] || rail_end
    fi
    return 0
  fi

  # The data volume never has a default: the user decides, every time.
  if [ -n "$UN_VOLUME" ] && [ -z "$PURGE_DATA" ]; then
    if [ "$ASSUME_YES" = "1" ] || [ ! -r "$TTY_DEV" ]; then
      fail "the volume ${UN_VOLUME} holds the search index — decide explicitly: --purge-data (erase it) or --keep-data (keep it)"
    fi
    printf '%s\n' "$GUT"
    printf '%s' "$(ask "The volume ${BOLD}${UN_VOLUME}${RESET} holds the search index.")"
    printf '\n%s   Your documents and the _ATLASFILE journal live on disk and are NOT affected;\n' "$GUT"
    printf '%s   the index is rebuilt by Reconcile after a reinstall.\n' "$GUT"
    local ans=""
    af_read_line "$(ask "Erase the volume? ${DIM}[y/N]${RESET} ")"; ans="$AF_LINE"
    case "$ans" in y|Y|yes|YES|s|S) PURGE_DATA=1 ;; *) PURGE_DATA=0 ;; esac
  fi
  [ -n "$PURGE_DATA" ] || PURGE_DATA=0

  un_build_plan "$PURGE_DATA" "$REMOVE_DEPS" "$FORCE"
  # Delegado E ja autorizado: o orquestrador MOSTROU este plano (via --plan-only)
  # e o usuario ja o confirmou. Reimprimi-lo aqui faz a mesma lista aparecer duas
  # vezes na tela, com a pergunta no meio — foi o que o Windows real mostrou.
  # Quem nao delega continua vendo o plano, porque ele e a base da confirmacao.
  if [ "$DELEGATED" != "1" ] || [ "$ASSUME_YES" != "1" ]; then
    un_print_plan
  fi

  # Quem ABRE o trilho tem de fecha-lo, e o un_print_plan acima abriu. Estas
  # tres saidas (nada a fazer, cancelado, falhou) retornavam sem `╰──` e a tela
  # terminava pendurada numa calha — medido. A guarda da bancada so cobria
  # --doctor, --dry-run e --uninstall --dry-run, que sao justamente as que ja
  # tinham sido consertadas.
  #
  # `DELEGATED` continua mandando: delegado, o trilho e do install.ps1 e quem o
  # fecha e ele, depois de terminar o lado Windows.
  if [ -z "$UN_ACTIONS" ]; then
    info "nothing to do."
    [ "$DELEGATED" = "1" ] || rail_end
    sentinel "nothing-to-do"
    return 0
  fi
  if [ "$ASSUME_YES" != "1" ]; then
    if [ ! -r "$TTY_DEV" ]; then
      sentinel "cancelled"
      fail "no interactive terminal — re-run with --yes to confirm the plan above"
    fi
    local answer=""
    af_read_line "$(ask "Execute the plan above? ${DIM}[y/N]${RESET} ")"; answer="$AF_LINE"
    printf '%s\n' "$GUT"
    # A "no" here used to return 0, which any caller reads as success — and
    # install.ps1 went on to delete Docker Desktop from a machine whose owner
    # had just said no. Cancelling is its own outcome and gets its own code.
    case "$answer" in
      y|Y|yes|YES|s|S) ;;
      *) info "uninstall cancelled — nothing was touched."
         [ "$DELEGATED" = "1" ] || rail_end
         sentinel "cancelled"; return "$RC_CANCELLED" ;;
    esac
  fi

  # Anotado ANTES de executar: o rm-state apaga o manifesto no fim, e este
  # registro é o que faz a promessa "a future reinstall reuses it" valer.
  if [ -n "$UN_VOLUME" ] && [ "$PURGE_DATA" = "0" ]; then
    af_kept_volume_record "$UN_VOLUME" "$UN_DIR" \
      "$(grep '^OPENSEARCH_PASSWORD=' "${UN_DIR}/.env" 2>/dev/null | head -1 | cut -d= -f2- || true)"
  fi

  un_execute
  if [ "$UN_FAILED" = "1" ]; then
    warn "uninstall finished with failures — see ${LOG_FILE}"
    [ "$DELEGATED" = "1" ] || rail_end
    sentinel "failed"
    return 1
  fi
  # Under --delegated the last word belongs to the caller: it still has Windows
  # packages to remove, and a verdict printed here would be true only of this
  # half of the machine (it was, and the user read a success that had not
  # happened yet).
  if [ "$DELEGATED" != "1" ]; then
    un_report
  fi
  sentinel "confirmed"
  return 0
}

# ── --doctor: diagnóstico read-only ─────────────────────────────────────────
# Não existia, e era exatamente o que faltou quando o instalador falhou numa
# máquina Windows real: sem log, sem manifesto à mão, a conversa virou
# adivinhação. Instala nada, muda nada — só mede e conta o que achou. É o
# run_doctor do mac_env_install.sh, com o que faz sentido aqui.
DOC_OK=0; DOC_WARN=0; DOC_FAIL=0
# O QUE faltou, e nao so quantos: o --dry-run precisa nomear cada pendencia, e
# reperguntar ao sistema para descobrir isso era a origem da contradicao (duas
# fontes de verdade sobre o mesmo fato). Preenchidos por doc_prereqs.
#   DOC_MISSING  — o instalador resolve sozinho ("would be installed")
#   DOC_BLOCKERS — so o usuario resolve (daemon parado, curl ausente)
DOC_MISSING=""; DOC_BLOCKERS=""
doc_ok()   { DOC_OK=$(( DOC_OK + 1 ));     af_wrap "${GUT}${GREEN}✔${RESET} " "${GUT}  " 4 "$*"; }
doc_warn() { DOC_WARN=$(( DOC_WARN + 1 )); af_wrap "${GUT}${ORANGE}!${RESET} " "${GUT}  " 4 "$*"; }
doc_fail() { DOC_FAIL=$(( DOC_FAIL + 1 )); af_wrap "${GUT}${RED}✘${RESET} " "${GUT}  " 4 "$*"; }
doc_head() { printf '%s\n' "$GUT"; rule_sweep "$1"; }

doc_version() { # <cmd> <args...> — versão em uma linha; falha se o comando falhar
  local saida
  command -v "$1" >/dev/null 2>&1 || return 1
  # O `| head -1` mascarava o código de saída do comando (o status do pipeline é
  # o do head), então uma ferramenta presente mas QUEBRADA era relatada como ok.
  saida="$("$@" 2>/dev/null)" || return 1
  [ -n "$saida" ] || return 1
  printf '%s' "$saida" | head -1
}

# O retrato dos pre-requisitos serve ao --doctor E ao --dry-run: o dry run dizia
# so o que FALTA, e "o que ele ve" e metade da pergunta que ele responde.
doc_prereqs() {
  doc_head "Prerequisites"
  local v
  DOC_MISSING=""; DOC_BLOCKERS=""
  # git deixou de ser pre-requisito do caminho padrao (fase 4a): so o
  # --from-source precisa dele, entao a ausencia e aviso, nunca bloqueio.
  if v="$(doc_version git --version)"; then doc_ok "$v"; else doc_warn "git not found (only needed for --from-source installs)"; fi
  # curl nao entra em DOC_MISSING: nao ha ensure_curl — o instalador nao o instala.
  if command -v curl >/dev/null 2>&1; then doc_ok "curl"; else doc_fail "curl not found"; DOC_BLOCKERS="${DOC_BLOCKERS}curl "; fi
  # tar abre o bundle da release; como o curl, exigido e nunca instalado.
  if command -v tar >/dev/null 2>&1; then doc_ok "tar"; else doc_fail "tar not found"; DOC_BLOCKERS="${DOC_BLOCKERS}tar "; fi
  if v="$(doc_version docker --version)"; then
    doc_ok "$v"
    if docker info >/dev/null 2>&1; then
      doc_ok "the Docker daemon answers"
    else
      doc_fail "Docker is installed but the daemon does not answer — start it before installing"
      DOC_BLOCKERS="${DOC_BLOCKERS}docker-daemon "
    fi
    if docker compose version >/dev/null 2>&1; then
      doc_ok "docker compose $(docker compose version --short 2>/dev/null || echo v2)"
    else
      doc_fail "Docker Compose v2 not available"
      DOC_MISSING="${DOC_MISSING}docker-compose-plugin "
    fi
  else
    doc_fail "docker not found"
    DOC_MISSING="${DOC_MISSING}docker "
  fi
  if v="$(doc_version ollama --version)"; then doc_ok "$v"; else doc_warn "ollama not installed (optional, only for a 100% local model)"; fi

  return 0
}

run_doctor() {
  detect_os
  doc_head "System"
  doc_ok "$(uname -s) $(uname -r) ($(uname -m)) · package manager: ${PKG}"

  doc_prereqs

  doc_head "Install manifest (what this installer created here)"
  if [ -f "$AF_HOST_MANIFEST" ]; then
    doc_ok "$AF_HOST_MANIFEST"
    while IFS=$'\t' read -r chave valor; do
      case "$chave" in \#*|schema|"") continue ;; esac
      printf '%s    %s%-16s%s %s\n' "$GUT" "$DIM" "$chave" "$RESET" "$valor"
    done < "$AF_HOST_MANIFEST"
  else
    doc_warn "no host manifest — nothing here was installed by AtlasFile, or it was already removed"
  fi

  doc_head "Installation at ${INSTALL_DIR}"
  un_collect "$INSTALL_DIR"
  if [ -d "$INSTALL_DIR" ]; then
    doc_ok "the folder exists"
    [ "$UN_COMPOSE_FILE" = "1" ] && doc_ok "docker-compose.yml present (compose project: ${UN_PROJECT})" \
      || doc_fail "no docker-compose.yml — this does not look like an AtlasFile install"
    [ "$UN_ENV" = "1" ] && doc_ok ".env present" || doc_warn ".env missing — the stack has no configuration"
    case "$UN_CLONE_STATE" in
      created) doc_ok "the clone was created by this installer (it may be removed by --uninstall)" ;;
      # Sem este braco o doctor diria que o --uninstall PRESERVA exatamente o
      # dir que o plano de remocao considera removivel — diagnostico mentindo
      # sobre a acao.
      bundle)  doc_ok "installed from the release bundle by this installer (it may be removed by --uninstall)" ;;
      *)       doc_warn "the clone was NOT created by this installer — --uninstall preserves it" ;;
    esac
    if [ "$UN_DIR_DIRTY" = "1" ]; then
      doc_warn "there are local changes — --uninstall keeps the folder (use --force to remove it anyway)"
      un_dirty_lines
    else
      doc_ok "no local changes"
    fi
  else
    doc_warn "the folder does not exist"
  fi

  doc_head "Stack"
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    doc_ok "${UN_CONTAINERS} container(s) of project '${UN_PROJECT}'"
    [ -n "$UN_VOLUME" ] && doc_ok "data volume: ${UN_VOLUME}" || doc_warn "no data volume — the index has not been created yet"
    [ -n "$UN_OTHER_ARTIFACTS" ] && doc_warn "another AtlasFile install shares this Docker: ${UN_OTHER_ARTIFACTS}"
  else
    doc_warn "the daemon does not answer — nothing to say about the stack"
  fi
  local porta
  af_resolve_app_port
  af_resolve_os_port
  for porta in "$AF_PORT" "$AF_OS_PORT"; do
    if af_port_busy "$porta"; then
      if docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null | grep -q "atlasfile.*:${porta}"; then
        doc_ok "port ${porta} is AtlasFile's own"
      else
        doc_fail "port ${porta} is taken by another process"
      fi
    fi
  done

  doc_head "Documents"
  if [ -n "$UN_PROJECTS_ROOT" ]; then
    doc_ok "${UN_PROJECTS_ROOT} (${UN_PROJECTS_FILES} item(s)) — never touched by the installer"
  else
    doc_warn "projects folder unknown (no .env and no manifest)"
  fi

  printf '%s\n' "$GUT"
  rule_sweep "Diagnosis"
  printf '%s%s✔ %s ok%s   %s! %s to watch%s   %s✘ %s broken%s\n' \
    "$GUT" "$GREEN" "$DOC_OK" "$RESET" "$ORANGE" "$DOC_WARN" "$RESET" "$RED" "$DOC_FAIL" "$RESET"
  # Quem fecha o trilho e quem o ABRIU: delegado, o trilho e do install.ps1 e
  # este diagnostico roda dentro de uma regua dele. Um `╰──` aqui fecharia a
  # tela do orquestrador no meio. Mesma regra do banner e do veredito final.
  [ "$DELEGATED" = "1" ] || rail_end
  [ "$DOC_FAIL" = "0" ]
}

# ── --dry-run: o que uma instalação faria aqui ──────────────────────────────
run_dry_run() {
  detect_os
  doc_prereqs
  doc_head "Install plan"
  # Na CALHA, como todo o resto do trilho. Estas quatro linhas eram `printf
  # '    • …'` puro e abriam um buraco de quatro linhas no meio do bloco mais
  # importante da tela — medido. Escapavam da varredura da bancada porque ela
  # mirava o prefixo `printf '  %s`, e estas comecavam com espacos literais.
  #
  # O rotulo tem largura FIXA (13) para as quatro linhas fecharem na mesma
  # coluna; nao passa pelo af_wrap porque ele junta as palavras com um espaco so
  # e comeria justamente esse alinhamento.
  af_plan_row() { printf '%s  • %-13s%s\n' "$GUT" "$1" "$2"; }
  # O dry-run e READ-ONLY: no caminho bundle ele NAO resolve a release na API
  # (isso seria tocar a rede num modo que promete so olhar) — diz de onde ela
  # viria e qual pino foi pedido, se algum.
  if af_source_mode; then
    af_plan_row "repository" "${REPO_URL} (${BRANCH})"
    af_plan_row "install dir" "${INSTALL_DIR}$([ -d "${INSTALL_DIR}/.git" ] && printf ' (exists — would be UPDATED)' || printf ' (would be CLONED)')"
  else
    af_plan_row "release" "${AF_PIN_VERSION:-latest} — from github.com/aleonnet/atlasfile/releases"
    af_plan_row "install dir" "${INSTALL_DIR}$([ -d "${INSTALL_DIR}" ] && printf ' (exists — would be UPDATED from the release bundle)' || printf ' (would be INSTALLED from the release bundle)')"
  fi
  af_plan_row "documents" "${PROJECTS_ROOT:-$PROJECTS_ROOT_DEFAULT}"
  af_plan_row "options" "auth=$([ "$ENABLE_AUTH" = "1" ] && printf on || printf off) open-browser=$([ "$OPEN_BROWSER" = "1" ] && printf on || printf off)"
  # Sem linha de calha solta aqui: o doc_head abaixo ja abre com uma, e as duas
  # juntas davam um vao de duas linhas que nenhum outro bloco da tela tem.
  doc_head "Prerequisites this machine is missing"
  # UMA fonte de verdade: o doc_prereqs acima ja mediu esta maquina e registrou o
  # que achou. Reperguntar aqui com `command -v` era a origem da contradicao —
  # `command -v docker` tem sucesso com o daemon PARADO e ate com um binario que
  # nao responde --version, entao a tela dizia "✘ docker not found" e, quatro
  # linhas abaixo, "✔ none — everything needed is already here".
  #
  # A separacao importa para quem le: o instalador RESOLVE o que esta em
  # DOC_MISSING, e nao tem como resolver o que esta em DOC_BLOCKERS.
  local item
  # shellcheck disable=SC2086  # o split nos espacos e o objetivo: sao listas
  for item in $DOC_MISSING; do
    case "$item" in
      docker-compose-plugin) doc_warn "docker-compose-plugin would be installed" ;;
      docker)                doc_warn "Docker would be installed" ;;
      *)                     doc_warn "${item} would be installed" ;;
    esac
  done
  # shellcheck disable=SC2086
  for item in $DOC_BLOCKERS; do
    case "$item" in
      docker-daemon) doc_fail "the Docker daemon is not answering — start Docker before installing" ;;
      *)             doc_fail "${item} is required and is not on this machine" ;;
    esac
  done
  [ -z "${DOC_MISSING}${DOC_BLOCKERS}" ] && doc_ok "none — everything needed is already here"
  printf '%s\n' "$GUT"
  info "--dry-run: nothing was installed."
  [ "$DELEGATED" = "1" ] || rail_end
  return 0
}

# ── Banner: the orb, its two moons and the comet it fires ───────────────────
# Same identity as the product's CompanionOrb (frontend/src/components/
# CompanionOrb.tsx): a lit core, two moons on opposite Keplerian orbits and the
# comet it fires. No face.
#
# Canvas: 7 rows. The orb sits on rows 1..5 centred on (row 3, col 10); rows 0
# and 6 are the orbit corridor. Bash has no floating point, so the orbit is a
# table of 16 integer cells (an ellipse rx=9, ry=3) and none of them touches an
# orb glyph. The wordmark starts at col 24, clear of the widest orbit cell (19).
#
# Colors are product tokens (frontend/src/styles.css): --accent #ff5a36,
# --accent-light #ff8a6b, --accent-purple #c97bff, --orb-comet-head #ffffff.
# The truecolor ramp is accent at 35% luminance, accent, accent-light, and
# accent-light lifted 60% toward white. The 256 fallback is the xterm warm ramp
# (monotonic on purpose: a nearest-neighbour pick banded the sphere).
AF_RAMP="592013 ff5a36 ff8a6b ffd0c4"
AF_RAMP_256="52 88 130 166 202 209 216 223"
AF_MOON1="ff5a36"; AF_MOON1_FAR="b23f26"; AF_MOON1_256="203"; AF_MOON1_FAR_256="130"
AF_MOON2="c97bff"; AF_MOON2_FAR="8d56b2"; AF_MOON2_256="177"; AF_MOON2_FAR_256="97"
AF_COMET_HEAD_HEX="ffffff"; AF_COMET_HEAD_256="231"

AF_COLS=56
AF_ROWS=7
AF_ORBIT="3,19 4,18 5,16 6,13 6,10 6,7 5,4 4,2 3,1 2,2 1,4 0,7 0,10 0,13 1,16 2,18"
AF_ORBIT_N=16
AF_ORBIT_START=10          # so the last moving frame lands one step before rest
# The comet is ejected from the orb and climbs: by the time it reaches the
# wordmark column (24) it is already on rows 0-1, ABOVE the text on rows 2-3.
# Measured: a path crossing the text rows corrupted the letters ("y·ur ·ocs").
AF_COMET="4,17 3,20 2,22 1,25 1,31 0,38 0,46 0,54"
AF_COMET_N=8
AF_COMET_TAIL=3
AF_WORD="AtlasFile"
AF_TAG="Your documents have gravity."   # same call phrase as the website hero
AF_WORD_COL=24
AF_WORD_ROW=2
AF_TAG_ROW=3
AF_IGNITE_N=5
AF_ORBIT_FRAMES=12
AF_COMET_FIRST=$(( AF_IGNITE_N + AF_ORBIT_FRAMES ))
AF_LAST=$(( AF_COMET_FIRST + AF_COMET_N ))   # final frame = the still banner
AF_FRAMES=$(( AF_LAST + 1 ))
AF_DELAY="0.04"
AF_GLYPH_MOON_NEAR="●"; AF_GLYPH_MOON_FAR="•"
AF_GLYPH_COMET_HEAD="●"; AF_GLYPH_COMET_TAIL="·"
AF_MIN_COLS=60             # narrower than this, the redraw would wrap: no anim

AF_R=0; AF_G=0; AF_B=0
af_rgb_at() { # <pos 0..1000> -> AF_R/AF_G/AF_B interpolated on the ramp
  local pos="$1" n span scaled seg frac i h1 h2 r1 g1 b1 r2 g2 b2
  set -- $AF_RAMP
  n=$#; span=$(( n - 1 ))
  scaled=$(( pos * span )); seg=$(( scaled / 1000 )); frac=$(( scaled % 1000 ))
  if [ "$seg" -ge "$span" ]; then seg=$(( span - 1 )); frac=1000; fi
  i=$(( seg + 1 )); h1="${!i}"; i=$(( seg + 2 )); h2="${!i}"
  r1=$(( 16#${h1:0:2} )); g1=$(( 16#${h1:2:2} )); b1=$(( 16#${h1:4:2} ))
  r2=$(( 16#${h2:0:2} )); g2=$(( 16#${h2:2:2} )); b2=$(( 16#${h2:4:2} ))
  AF_R=$(( r1 + (r2 - r1) * frac / 1000 ))
  AF_G=$(( g1 + (g2 - g1) * frac / 1000 ))
  AF_B=$(( b1 + (b2 - b1) * frac / 1000 ))
}

AF_LUT_N=32
af_lut_init() {
  local i p seg n
  if [ "$COLOR_OK" != "1" ]; then
    for (( i = 0; i < AF_LUT_N; i++ )); do AF_LUT[$i]=""; done
    return 0
  fi
  for (( i = 0; i < AF_LUT_N; i++ )); do
    p=$(( i * 1000 / (AF_LUT_N - 1) ))
    if [ "$TRUECOLOR" = "1" ]; then
      af_rgb_at "$p"
      AF_LUT[$i]=$'\033[38;2;'"${AF_R};${AF_G};${AF_B}m"
    else
      set -- $AF_RAMP_256
      n=$#; seg=$(( p * (n - 1) / 1000 + 1 )); [ "$seg" -gt "$n" ] && seg=$n
      AF_LUT[$i]=$'\033[38;5;'"${!seg}m"
    fi
  done
}

af_fg() { # <hex> <256 index> -> escape (empty when color is off)
  [ "$COLOR_OK" = "1" ] || return 0
  if [ "$TRUECOLOR" = "1" ]; then
    printf '\033[38;2;%d;%d;%dm' "$(( 16#${1:0:2} ))" "$(( 16#${1:2:2} ))" "$(( 16#${1:4:2} ))"
  else
    printf '\033[38;5;%sm' "$2"
  fi
}

# Art is declared as space-separated glyph lists, never as strings: ${#s} and
# ${s:i:1} count BYTES under LC_ALL=C, which would wreck every column offset.
af_put_art() { # <row> <first col> <glyphs...>
  local row="$1" col="$2" g
  shift 2
  AF_ORB_C0[$row]=$col
  for g in "$@"; do AF_ORB[$(( row * AF_COLS + col ))]="$g"; col=$(( col + 1 )); done
  AF_ORB_C1[$row]=$(( col - 1 ))
}

AF_INIT_DONE=0
af_banner_init() {
  [ "$AF_INIT_DONE" = "1" ] && return 0
  local i
  for (( i = 0; i < AF_ROWS * AF_COLS; i++ )); do AF_ORB[$i]=""; done
  for (( i = 0; i < AF_ROWS; i++ )); do AF_ORB_C0[$i]=-1; AF_ORB_C1[$i]=-2; done
  af_put_art 1 8  ▄ ▄ ▄ ▄ ▄
  af_put_art 2 6  ▄ █ █ █ █ █ █ █ ▄
  af_put_art 3 5  ▐ █ █ █ █ █ █ █ █ █ ▌
  af_put_art 4 6  ▀ █ █ █ █ █ █ █ ▀
  af_put_art 5 8  ▀ ▀ ▀ ▀ ▀
  af_lut_init
  AF_COL_M1N="$(af_fg "$AF_MOON1" "$AF_MOON1_256")"
  AF_COL_M1F="$(af_fg "$AF_MOON1_FAR" "$AF_MOON1_FAR_256")"
  AF_COL_M2N="$(af_fg "$AF_MOON2" "$AF_MOON2_256")"
  AF_COL_M2F="$(af_fg "$AF_MOON2_FAR" "$AF_MOON2_FAR_256")"
  AF_COL_C0="${BOLD}$(af_fg "$AF_COMET_HEAD_HEX" "$AF_COMET_HEAD_256")"
  AF_COL_C1="$(af_fg ff8a6b 209)"
  AF_COL_C2="$(af_fg ff5a36 203)"
  AF_COL_C3="$(af_fg b23f26 130)"
  AF_COL_WORD="$(af_fg "$AF_MOON1" "$AF_MOON1_256")"
  AF_INIT_DONE=1
}

af_cell() { # <table> <index> -> AF_CELL_ROW / AF_CELL_COL
  local table="$1" idx="$2" i=0 pair
  for pair in $table; do
    if [ "$i" = "$idx" ]; then
      AF_CELL_ROW="${pair%,*}"; AF_CELL_COL="${pair#*,}"; return 0
    fi
    i=$(( i + 1 ))
  done
  AF_CELL_ROW=-1; AF_CELL_COL=-1
  return 1
}

af_frame_prepare() { # <frame> -> moon/comet cells, highlight and reveal width
  local n="$1" k idx hr hc pr pc dcol drow t tr tc tri
  AF_F_IGNITE_MAX=$AF_ROWS
  AF_M1R=-1; AF_M1C=-1; AF_M2R=-1; AF_M2C=-1
  AF_CN=0; AF_WN=0
  # Specular highlight. A horizontal ramp across the whole canvas barely varied
  # inside the orb's 11 columns (measured in a real terminal: the sphere came
  # out flat and washed). The light is a point sweeping the sphere on a
  # triangle wave, and each cell dims with its distance to it.
  tri=$(( n % 20 )); [ "$tri" -gt 10 ] && tri=$(( 20 - tri ))
  AF_HL_COL=$(( 5 + tri )); AF_HL_ROW=2

  # ignition: the orb spans rows 1..5, so frame n reveals up to row n+1
  if [ "$n" -lt "$AF_IGNITE_N" ]; then
    AF_F_IGNITE_MAX=$(( n + 2 ))
    return 0
  fi

  idx=$(( (AF_ORBIT_START + n - AF_IGNITE_N) % AF_ORBIT_N ))
  af_cell "$AF_ORBIT" "$idx";                          AF_M1R=$AF_CELL_ROW; AF_M1C=$AF_CELL_COL
  af_cell "$AF_ORBIT" "$(( (idx + 8) % AF_ORBIT_N ))"; AF_M2R=$AF_CELL_ROW; AF_M2C=$AF_CELL_COL

  if [ "$n" -ge "$AF_COMET_FIRST" ] && [ "$n" -lt "$AF_LAST" ]; then
    k=$(( n - AF_COMET_FIRST ))
    af_cell "$AF_COMET" "$k"; hr=$AF_CELL_ROW; hc=$AF_CELL_COL
    AF_CR[0]=$hr; AF_CC[0]=$hc; AF_CT[0]=0; AF_CN=1
    # The tail is CONTIGUOUS behind the head, along the direction of travel.
    # Sampling earlier path cells left 3-5 column gaps (measured) and read as
    # sparks rather than a comet.
    pr=$hr; pc=$(( hc - 1 ))
    if [ "$k" -gt 0 ]; then af_cell "$AF_COMET" "$(( k - 1 ))"; pr=$AF_CELL_ROW; pc=$AF_CELL_COL; fi
    dcol=$(( hc - pc )); drow=$(( hr - pr ))
    [ "$dcol" -le 0 ] && dcol=1
    for (( t = 1; t <= AF_COMET_TAIL; t++ )); do
      tc=$(( hc - t ))
      [ "$tc" -lt 0 ] && break
      tr=$(( hr - (drow * t) / dcol ))
      [ "$tr" -lt 0 ] && tr=0
      [ "$tr" -ge "$AF_ROWS" ] && tr=$(( AF_ROWS - 1 ))
      AF_CR[$AF_CN]=$tr; AF_CC[$AF_CN]=$tc; AF_CT[$AF_CN]=$t
      AF_CN=$(( AF_CN + 1 ))
    done
    AF_WN=$(( hc - AF_WORD_COL )); [ "$AF_WN" -lt 0 ] && AF_WN=0
  elif [ "$n" -ge "$AF_LAST" ]; then
    AF_WN=99
  fi
  # Explicit: under `set -e` a trailing false test would abort the installer.
  return 0
}

# Fills AF_RG (glyph) and AF_RK (class) for one row. THE WRITE ORDER IS THE
# PRECEDENCE: comet < orb < text < moons. So the comet is ejected from behind
# the orb, the orb glyph count is invariant across frames, and no wordmark
# letter can ever be overwritten.
af_row_cells() { # <row>
  local row="$1" c i n txt
  for (( c = 0; c < AF_COLS; c++ )); do AF_RG[$c]=" "; AF_RK[$c]=""; done

  for (( i = 0; i < AF_CN; i++ )); do
    if [ "${AF_CR[$i]}" = "$row" ]; then
      c=${AF_CC[$i]}
      if [ "$c" -ge 0 ] && [ "$c" -lt "$AF_COLS" ]; then
        if [ "${AF_CT[$i]}" = "0" ]; then AF_RG[$c]="$AF_GLYPH_COMET_HEAD"; else AF_RG[$c]="$AF_GLYPH_COMET_TAIL"; fi
        AF_RK[$c]="c${AF_CT[$i]}"
      fi
    fi
  done

  if [ "$row" -lt "$AF_F_IGNITE_MAX" ]; then
    for (( c = ${AF_ORB_C0[$row]}; c <= ${AF_ORB_C1[$row]}; c++ )); do
      [ "$c" -lt 0 ] && continue
      AF_RG[$c]="${AF_ORB[$(( row * AF_COLS + c ))]}"; AF_RK[$c]="orb"
    done
  fi

  if [ "$AF_WN" -gt 0 ]; then
    txt=""
    [ "$row" = "$AF_WORD_ROW" ] && txt="$AF_WORD"
    [ "$row" = "$AF_TAG_ROW" ] && txt="$AF_TAG"
    if [ -n "$txt" ]; then
      n=${#txt}; [ "$AF_WN" -lt "$n" ] && n=$AF_WN
      for (( i = 0; i < n; i++ )); do
        c=$(( AF_WORD_COL + i ))
        [ "$c" -ge "$AF_COLS" ] && break
        AF_RG[$c]="${txt:$i:1}"
        if [ "$row" = "$AF_WORD_ROW" ]; then AF_RK[$c]="word"; else AF_RK[$c]="tag"; fi
      done
    fi
  fi

  if [ "$row" = "$AF_M1R" ] && [ "$AF_M1C" -ge 0 ]; then
    if [ "$row" -le 2 ]; then AF_RG[$AF_M1C]="$AF_GLYPH_MOON_FAR"; AF_RK[$AF_M1C]="m1f"
    else AF_RG[$AF_M1C]="$AF_GLYPH_MOON_NEAR"; AF_RK[$AF_M1C]="m1n"; fi
  fi
  if [ "$row" = "$AF_M2R" ] && [ "$AF_M2C" -ge 0 ]; then
    if [ "$row" -le 2 ]; then AF_RG[$AF_M2C]="$AF_GLYPH_MOON_FAR"; AF_RK[$AF_M2C]="m2f"
    else AF_RG[$AF_M2C]="$AF_GLYPH_MOON_NEAR"; AF_RK[$AF_M2C]="m2n"; fi
  fi
  return 0
}

af_frame_plain() { # <frame> -> the frame as plain text (source of truth for tests)
  local n="$1" row col out
  af_banner_init
  af_frame_prepare "$n"
  for (( row = 0; row < AF_ROWS; row++ )); do
    af_row_cells "$row"
    out=""
    for (( col = 0; col < AF_COLS; col++ )); do out="${out}${AF_RG[$col]}"; done
    while [ "${out% }" != "$out" ]; do out="${out% }"; done
    printf '%s\n' "$out"
  done
}

af_frame_paint() { # <frame> -> the frame, colored
  local n="$1" row col out esc prev p d k
  af_banner_init
  af_frame_prepare "$n"
  for (( row = 0; row < AF_ROWS; row++ )); do
    af_row_cells "$row"
    out=""; prev="__none__"
    for (( col = 0; col < AF_COLS; col++ )); do
      k="${AF_RK[$col]}"
      if [ -z "$k" ]; then out="${out} "; continue; fi
      case "$k" in
        orb)  p=$(( col - AF_HL_COL )); [ "$p" -lt 0 ] && p=$(( -p ))
              d=$(( row - AF_HL_ROW )); [ "$d" -lt 0 ] && d=$(( -d ))
              p=$(( 1000 - p * 90 - d * 180 )); [ "$p" -lt 120 ] && p=120
              esc="${AF_LUT[$(( p * (AF_LUT_N - 1) / 1000 ))]}" ;;
        word) esc="${BOLD}${AF_COL_WORD}" ;;
        tag)  esc="$DIM" ;;
        m1n)  esc="$AF_COL_M1N" ;;
        m1f)  esc="$AF_COL_M1F" ;;
        m2n)  esc="$AF_COL_M2N" ;;
        m2f)  esc="$AF_COL_M2F" ;;
        c0)   esc="$AF_COL_C0" ;;
        c1)   esc="$AF_COL_C1" ;;
        c2)   esc="$AF_COL_C2" ;;
        *)    esc="$AF_COL_C3" ;;
      esac
      if [ "$esc" != "$prev" ]; then out="${out}${RESET}${esc}"; prev="$esc"; fi
      out="${out}${AF_RG[$col]}"
    done
    printf '%s%s\n' "$out" "$RESET"
  done
}

af_cursor_show() { [ "$IS_TTY" = "1" ] && tput cnorm 2>/dev/null || true; }

print_banner() {
  local n cols
  printf '\n'
  cols="$(tput cols 2>/dev/null || echo 0)"
  case "$cols" in ''|*[!0-9]*) cols=0 ;; esac
  if [ "$ANIM_OK" != "1" ] || [ "$cols" -lt "$AF_MIN_COLS" ]; then
    af_frame_paint "$AF_LAST"
    printf '\n'
    return 0
  fi
  # Ctrl-C during the animation must never leave an invisible cursor behind.
  trap 'af_cursor_show' EXIT INT TERM
  tput civis 2>/dev/null || true
  for (( n = 0; n < AF_FRAMES; n++ )); do
    [ "$n" -gt 0 ] && tput cuu "$AF_ROWS"
    af_frame_paint "$n"
    [ "$n" -lt "$AF_LAST" ] && sleep "$AF_DELAY"
  done
  af_cursor_show
  trap - EXIT INT TERM
  printf '\n'
}

# `pull --ff-only` recusa quando o historico local divergiu do remoto, e recusar
# esta CERTO. Morrer ali e que nao estava: o clone e nosso, e quem tem a
# informacao para decidir e este script.
#
# Aconteceu num Windows 11 real: o clone estava num commit de um historico que
# foi reescrito depois, e a instalacao parou com
#   "+ 3e579e6...f86f4bb main -> origin/main (forced update)"
#   "fatal: Not possible to fast-forward, aborting."
#
# Realinhar a forca so e aceitavel se NAO houver trabalho do usuario dentro — e
# quem responde isso e a mesma lista de artefatos nossos que o plano de remocao
# consulta antes de apagar a pasta.
AF_RESET_MARK=""
af_update_clone() { # <dir> <branch>
  local dir="$1" branch="$2" sujo
  # Refspec EXPLICITA: o clone raso nasce com refspec so de main, e `git fetch
  # origin outra-branch` NAO cria origin/outra-branch — o merge e o reset
  # abaixo morriam em "unknown revision" quando o update mirava outra branch
  # (achado 1 da Fase 3, medido na VM lima; a correcao prometida ficou para ca).
  git -C "$dir" fetch --prune origin "+refs/heads/${branch}:refs/remotes/origin/${branch}" || return 1
  git -C "$dir" merge --ff-only "origin/${branch}" && return 0
  # shellcheck disable=SC2046,SC2086
  sujo="$(git -C "$dir" status --porcelain -- . $(af_own_pathspec "$dir") 2>/dev/null || true)"
  if [ -n "$sujo" ]; then
    printf 'local history diverged from origin/%s AND this clone has local changes:\n' "$branch"
    printf '%s\n' "$sujo"
    printf 'refusing to reset — move or commit them, or use --dir to install elsewhere\n'
    return 1
  fi
  printf 'local history diverged from origin/%s and there are no local changes — realigning\n' "$branch"
  git -C "$dir" reset --hard "origin/${branch}" || return 1
  # O run_step roda o comando num subshell em BACKGROUND, entao nada que ele
  # defina volta para o shell principal: a marca em disco e o canal.
  [ -n "$AF_RESET_MARK" ] && : > "$AF_RESET_MARK"
  return 0
}

# ── Fase 4a: bundle da release + pull da imagem publicada ───────────────────
# O caminho padrao nao clona nem compila: resolve a versao, baixa o bundle da
# release (4 arquivos, ~10 KB), verifica o SHA256, valida o conteudo e faz
# `docker compose pull`. O clone continua vivo atras de --from-source (e do
# auto-despacho para instalacoes existentes com .git — a instancia de quem
# instalou por clone nunca e arrastada para o bundle).

# A versao tem o MESMO shape que o release.yml aceita numa tag. O valor flui
# para a URL do download, para o sed do set_env (que quebra com `|` e newline)
# e para a ref de imagem do pull: nada fora do shape passa deste portao — nem o
# que o usuario digitou em --version, nem o que a API devolveu.
af_validate_version() { # <valor>
  printf '%s' "$1" | LC_ALL=C grep -qE '^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?$'
}

# 0 quando a < b. So a parte X.Y.Z (sufixo de prerelease fora da conta): o uso
# e detectar DOWNGRADE, e 1.1.0-rc.1 -> 1.1.0 nao e downgrade.
af_version_lt() { # <a> <b>
  local a="${1%%-*}" b="${2%%-*}" a1 a2 a3 b1 b2 b3
  IFS=. read -r a1 a2 a3 <<EOF
$a
EOF
  IFS=. read -r b1 b2 b3 <<EOF
$b
EOF
  [ "$a1" != "$b1" ] && { [ "$a1" -lt "$b1" ]; return; }
  [ "$a2" != "$b2" ] && { [ "$a2" -lt "$b2" ]; return; }
  [ "$a3" -lt "$b3" ]
}

# Ultima release ESTAVEL, via API do GitHub (releases/latest nunca devolve
# prerelease). O parse por sed e deliberadamente burro; a defesa real contra
# casar campo errado (ou um 403 de rate-limit) e a validacao de shape acima.
af_resolve_version() { # -> ecoa X.Y.Z, ou rc!=0 sem ecoar nada
  local json tag
  json="$(curl -fsSL "${AF_API_BASE}/repos/aleonnet/atlasfile/releases/latest" 2>/dev/null)" || return 1
  tag="$(printf '%s' "$json" | LC_ALL=C sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"v\{0,1\}\([^"]*\)".*/\1/p' | head -1)"
  af_validate_version "$tag" || return 1
  printf '%s' "$tag"
}

# sha256 de UM arquivo, portavel (Linux: sha256sum; macOS: shasum -a 256).
af_file_sha() { # <arquivo>
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" 2>/dev/null | awk '{print $1}'
  else
    shasum -a 256 "$1" 2>/dev/null | awk '{print $1}'
  fi
}

# Confere o arquivo contra a linha correspondente do SHA256SUMS (pelo nome).
# O que isto mitiga DE FATO: download truncado e asset trocado por engano. O
# que NAO mitiga: comprometimento da release ou MITM no host — o SHA256SUMS vem
# do MESMO host que o bundle; a raiz de confianca e o TLS do GitHub, a mesma ja
# aceita para este proprio script chegar por curl | bash.
af_sha256_check() { # <arquivo> <SHA256SUMS>
  local nome esperado real
  nome="$(basename "$1")"
  esperado="$(awk -v n="$nome" '$NF == n || $NF == "*"n { print $1 }' "$2" 2>/dev/null | head -1)"
  [ -n "$esperado" ] || return 1
  real="$(af_file_sha "$1")"
  [ -n "$real" ] && [ "$real" = "$esperado" ]
}

# Decide o caminho da fase 2: fonte (clone+build) ou bundle (download+pull).
# `.git` presente = a instancia foi instalada por clone e ASSIM PERMANECE no
# re-run — migrar para bundle e decisao do usuario (--uninstall --keep-data +
# instalacao nova), nunca um efeito colateral de re-executar o instalador.
af_source_mode() {
  [ "$FROM_SOURCE" = "1" ] && return 0
  [ -d "${INSTALL_DIR}/.git" ] && return 0
  return 1
}

# 0 quando o dir NAO carrega uma instalacao nossa (nem .git, nem manifesto).
# O guard do volume orfao usava so `.git` como sinal de "instalacao existente";
# no mundo bundle o re-run nao tem .git e seria barrado como instancia
# estrangeira — o manifesto e o sinal que sobrevive aos dois mundos.
af_fresh_install_dir() { # <dir>
  [ -d "${1}/.git" ] && return 1
  [ -f "${1}/${AF_MANIFEST_NAME}" ] && return 1
  return 0
}

# Downgrade e decisao do usuario, nunca um default (mesma familia da escolha do
# volume no uninstall): headless FALHA em vez de adivinhar, e --yes nao pula
# esta confirmacao especifica — o indice do OpenSearch escrito pela versao mais
# nova pode ser incompativel com a app antiga.
af_downgrade_gate() { # <versao alvo> <versao instalada>
  local alvo="$1" atual="$2"
  af_version_lt "$alvo" "$atual" || return 0
  warn "downgrade: this install is at ${atual} and you asked for ${alvo}"
  info "data written by the newer version (the OpenSearch index) may be incompatible with the older app"
  if [ "$ASSUME_YES" = "1" ] || [ ! -r "$TTY_DEV" ]; then
    fail "downgrades need an interactive confirmation — re-run without --yes in a real terminal"
  fi
  af_read_line "$(ask "Downgrade to ${alvo}? ${DIM}[y/N]${RESET} ")"
  case "$AF_LINE" in
    y|Y|yes|YES|s|S) return 0 ;;
    *) fail "downgrade cancelled — nothing was changed" ;;
  esac
}

# Baixa, verifica, valida e instala os arquivos do bundle em <dir>. Roda no
# shell PRINCIPAL (nao sob run_step): os erros saem por AF_FETCH_ERR com a
# causa exata, e o chamador decide a mensagem. Ordem inegociavel: o SHA e
# verificado ANTES de o tar ser aberto — tar de origem nao verificada nunca e
# extraido, e o conteudo extraido e validado ANTES de tocar o dir de
# instalacao (exatamente os 4 arquivos esperados, nenhum symlink, nada fora da
# raiz — um tar hostil nao pode escrever atraves do move).
AF_FETCH_ERR=""
af_fetch_bundle() { # <versao> <dir>
  local v="$1" dir="$2" tmp nome base rc raiz f alvo links inesperado
  local mf shas registrado hash_atual backups backup agora novos_shas subdir
  AF_FETCH_ERR=""
  tmp="$(mktemp -d)" || { AF_FETCH_ERR="could not create a temporary folder"; return 1; }
  nome="atlasfile-${v}-bundle.tar.gz"
  base="${AF_DOWNLOAD_BASE}/aleonnet/atlasfile/releases/download/v${v}"
  rc=0
  curl -fsSL -o "${tmp}/${nome}" "${base}/${nome}" >>"$LOG_FILE" 2>&1 || rc=$?
  if [ "$rc" = "22" ]; then
    # curl -f devolve 22 para HTTP >= 400: a release (ou o asset) nao existe.
    AF_FETCH_ERR="release v${v} was not found — pick one that exists: https://github.com/aleonnet/atlasfile/releases"
    rm -rf "$tmp"; return 1
  elif [ "$rc" != "0" ]; then
    AF_FETCH_ERR="could not download the release bundle from ${base} — the download redirects to objects.githubusercontent.com, so a proxy or allowlist must permit that host too; check your connection and re-run"
    rm -rf "$tmp"; return 1
  fi
  curl -fsSL -o "${tmp}/SHA256SUMS" "${base}/SHA256SUMS" >>"$LOG_FILE" 2>&1 \
    || { AF_FETCH_ERR="could not download SHA256SUMS from ${base} — check your connection and re-run"; rm -rf "$tmp"; return 1; }
  if ! af_sha256_check "${tmp}/${nome}" "${tmp}/SHA256SUMS"; then
    AF_FETCH_ERR="checksum mismatch on ${nome} — the download is corrupt or truncated; nothing was extracted, re-running downloads it again"
    rm -rf "$tmp"; return 1
  fi
  mkdir -p "${tmp}/x"
  tar -xzf "${tmp}/${nome}" -C "${tmp}/x" >>"$LOG_FILE" 2>&1 \
    || { AF_FETCH_ERR="could not extract ${nome} (details: ${LOG_FILE})"; rm -rf "$tmp"; return 1; }
  raiz="${tmp}/x/atlasfile-${v}"
  links="$( (cd "${tmp}/x" && find . -type l | head -3) 2>/dev/null )"
  if [ -n "$links" ]; then
    AF_FETCH_ERR="the bundle contains symlinks ($(printf '%s' "$links" | tr '\n' ' ')) — refusing to install it"
    rm -rf "$tmp"; return 1
  fi
  inesperado="$( (cd "${tmp}/x" && find . -mindepth 1 | LC_ALL=C sed 's|^\./||') \
    | grep -vxF -e "atlasfile-${v}" -e "atlasfile-${v}/config" \
        -e "atlasfile-${v}/docker-compose.yml" -e "atlasfile-${v}/.env.example" \
        -e "atlasfile-${v}/config/opensearch_dashboards.yml" \
        -e "atlasfile-${v}/config/api_keys.example.json" || true)"
  if [ -n "$inesperado" ]; then
    AF_FETCH_ERR="the bundle contains unexpected entries ($(printf '%s' "$inesperado" | head -3 | tr '\n' ' ')) — refusing to install it"
    rm -rf "$tmp"; return 1
  fi
  for f in docker-compose.yml .env.example config/opensearch_dashboards.yml config/api_keys.example.json; do
    [ -f "${raiz}/${f}" ] || { AF_FETCH_ERR="the bundle is missing ${f} — refusing to install it"; rm -rf "$tmp"; return 1; }
  done
  # Instalacao arquivo a arquivo. Os 4 arquivos sao NOSSOS e sao substituidos
  # no update — mas "nosso" se prova, nao se presume: o hash gravado na
  # instalacao anterior diz se o arquivo em disco ainda e o que entregamos.
  # Divergiu (ou nao ha registro), o arquivo pode carregar trabalho do usuario:
  # ganha copia datada ao lado ANTES da substituicao, com aviso nomeando-o.
  # `.env`, api_keys.json, manifesto e qualquer outro arquivo nunca sao tocados.
  mf="${dir}/${AF_MANIFEST_NAME}"
  shas="$(manifest_get "$mf" bundle_sha)"
  backups="$(manifest_get "$mf" bundle_backups)"
  agora="$(date +%Y%m%d%H%M%S)"
  novos_shas=""
  mkdir -p "${dir}/config" || { AF_FETCH_ERR="could not write in ${dir}"; rm -rf "$tmp"; return 1; }
  for f in docker-compose.yml .env.example config/opensearch_dashboards.yml config/api_keys.example.json; do
    alvo="${dir}/${f}"
    if [ -f "$alvo" ] && ! cmp -s "${raiz}/${f}" "$alvo"; then
      registrado="$(printf '%s' "$shas" | tr ',' '\n' | awk -F= -v k="$f" '$1 == k { print $2 }')"
      hash_atual="$(af_file_sha "$alvo")"
      if [ -z "$registrado" ] || [ "$registrado" != "$hash_atual" ]; then
        subdir="$(dirname "$f")"
        if [ "$subdir" = "." ]; then backup="${f}.backup.${agora}"; else backup="${subdir}/$(basename "$f").backup.${agora}"; fi
        cp "$alvo" "${dir}/${backup}" 2>/dev/null || true
        warn "you edited ${f} — your version was copied to ${backup} before the update replaced it"
        if [ -n "$backups" ]; then backups="${backups},${backup}"; else backups="$backup"; fi
      fi
    fi
    mv -f "${raiz}/${f}" "$alvo" || { AF_FETCH_ERR="could not write ${alvo}"; rm -rf "$tmp"; return 1; }
    novos_shas="${novos_shas:+${novos_shas},}${f}=$(af_file_sha "$alvo")"
  done
  [ -n "$backups" ] && manifest_set "$mf" bundle_backups "$backups"
  manifest_set "$mf" bundle_sha "$novos_shas"
  rm -rf "$tmp"
  return 0
}

# A fase 4 em funcao, para a bancada alcancar a decisao build-vs-pull: o
# caminho bundle NUNCA compila, o caminho fonte NUNCA faz pull.
af_stack_up() {
  if [ "$AF_SOURCE_PATH" = "1" ]; then
    # o compose base consome a imagem publicada; o overlay devolve o build local
    run_step "building the app image" docker compose -f docker-compose.yml -f docker-compose.build.yml build
    run_step "starting the 2 services" docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --remove-orphans
  else
    run_step "pulling the app image (published on ghcr.io)" docker compose -f docker-compose.yml pull
    run_step "starting the 2 services" docker compose -f docker-compose.yml up -d --remove-orphans
  fi
}

# ── Test-library guard: `ATLASFILE_INSTALL_LIB=1 source install.sh` stops here ─
if [ -n "${ATLASFILE_INSTALL_LIB:-}" ]; then
  return 0 2>/dev/null || exit 0
fi

trap af_restore_terminal EXIT INT TERM

# One banner per run. Under --delegated the caller (install.ps1) has already
# drawn it seconds earlier: two banners in a row read as two products, and they
# were not even the same drawing. --plan-only is machine-facing output, so art
# would be noise in whatever is parsing it.
if [ "$DELEGATED" != "1" ] && [ "$PLAN_ONLY" != "1" ]; then
  print_banner
fi

# O aviso vem DEPOIS do banner e antes de qualquer trabalho, para quem colou o
# comando do site entender por que a flag não fez nada — e onde conseguir o que
# ela prometia.
if [ "$OLLAMA_DEPRECATED" = "1" ]; then
  warn "the Ollama flags are no longer used: pulling a model is several GB and made the install take an unpredictable amount of time"
  info "this run continues normally; the final panel shows how to enable a local model afterwards"
fi

if [ "$DOCTOR" = "1" ]; then
  doctor_rc=0
  run_doctor || doctor_rc=$?
  exit "$doctor_rc"
fi

if [ "$UNINSTALL" = "1" ]; then
  uninstall_rc=0
  run_uninstall || uninstall_rc=$?
  exit "$uninstall_rc"
fi

if [ "$DRY_RUN" = "1" ]; then
  run_dry_run
  exit 0
fi

# O despacho fonte-vs-bundle e decidido UMA vez, aqui, e vale para o resto da
# execucao: os pre-requisitos (git so no caminho fonte), a fase 2 (clone vs
# bundle) e a fase 4 (build vs pull) leem a mesma decisao.
if af_source_mode; then AF_SOURCE_PATH=1; else AF_SOURCE_PATH=0; fi

# ── 1. Prerequisites ────────────────────────────────────────────────────────
title "1/4" "Checking and preparing prerequisites"
detect_os

# git — so no caminho fonte (o bundle path nao toca git em momento nenhum)
if [ "$AF_SOURCE_PATH" = "1" ]; then
  if ! command -v git >/dev/null 2>&1; then
    if confirm "git not found — install it now?"; then
      ensure_git || fail "could not install git — install it manually: https://git-scm.com"
    else
      fail "git not found — install it from https://git-scm.com (or re-run with --install-deps)"
    fi
  else
    host_set git preexisting
  fi
  check "git $(git --version 2>/dev/null | awk '{print $3}')" command -v git \
    || fail "git not found — install it from https://git-scm.com"
fi
check "curl" command -v curl || fail "curl not found"
# tar abre o bundle da release; como o curl, e exigido e nunca instalado — todo
# sistema suportado o traz de fabrica.
check "tar" command -v tar || fail "tar not found — install it with your package manager and re-run"

# Docker — offer to install when missing
if ! command -v docker >/dev/null 2>&1; then
  if confirm "Docker not found — install it now? (Docker Desktop on macOS / Docker Engine on Linux)"; then
    # Only rc=1 is a failure. rc=100 means "already there" and is REACHABLE
    # here: `command -v docker` looks for the CLI, which Docker Desktop only
    # links after its first launch, while ensure_docker_mac looks for the app
    # itself. Measured on a clean macOS VM with Docker Desktop installed and
    # never opened: `ensure_docker_mac || fail` aborted the installer with
    # "could not install Docker Desktop" while the app sat in /Applications.
    docker_rc=0
    if [ "$OS_KIND" = "mac" ]; then
      ensure_docker_mac || docker_rc=$?
      [ "$docker_rc" = "1" ] && fail "could not install Docker Desktop — install it manually: https://docs.docker.com/get-docker/"
      [ "$docker_rc" = "100" ] && info "Docker Desktop is installed but has never been opened — starting it now"
    else
      ensure_docker_linux || docker_rc=$?
      [ "$docker_rc" = "1" ] && fail "could not install Docker Engine — install it manually: https://docs.docker.com/get-docker/"
    fi
  else
    fail "Docker not found — install Docker Desktop: https://docs.docker.com/get-docker/ (or re-run with --install-deps)"
  fi
else
  host_set docker preexisting
fi

# daemon — start it and wait instead of failing
if ! docker info >/dev/null 2>&1; then
  if [ "$OS_KIND" = "mac" ]; then
    launch_docker_desktop_mac
    run_step "waiting for the Docker daemon (up to 5 min on first launch)" wait_docker_daemon 300 \
      || fail "the Docker daemon did not come up — finish Docker Desktop's first-launch dialog and re-run this installer"
  else
    ensure_sudo && as_root systemctl start docker >/dev/null 2>&1 || true
    if ! wait_docker_daemon 30; then
      ensure_docker_group_linux || {
        # bootstrap-only validates INSTALLATION; a daemon needs a real host
        # (containers/CI have no systemd) — report and let the caller decide
        if [ "$BOOTSTRAP_ONLY" = "1" ]; then
          warn "prerequisites installed, but the daemon is not verifiable in this environment"
          info "bootstrap-only mode: done — exiting"
          exit 0
        fi
        fail "Docker is installed but the daemon is not reachable — check 'systemctl status docker'"
      }
    else
      ensure_docker_group_linux || true
    fi
  fi
fi
check "docker $(docker --version 2>/dev/null | sed 's/Docker version //;s/,.*//') (daemon running)" docker info \
  || fail "Docker is installed but the daemon is not running — start it and re-run"

# Compose v2
if ! docker compose version >/dev/null 2>&1; then
  if [ "$OS_KIND" = "linux" ] && [ "$PKG" != "none" ] && confirm "Docker Compose v2 not found — install the plugin now?"; then
    ensure_sudo || fail "Compose v2 missing and sudo unavailable"
    if [ "$PKG" = "apt" ]; then
      run_step "installing docker-compose-plugin (apt)" as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y docker-compose-plugin
    else
      run_step "installing docker-compose-plugin (dnf)" as_root dnf install -y docker-compose-plugin
    fi
    host_set compose_plugin created
  fi
else
  host_set compose_plugin preexisting
fi
check "docker compose $(docker compose version --short 2>/dev/null || echo v2)" docker compose version \
  || fail "Docker Compose v2 not found — update Docker Desktop (or install docker-compose-plugin)"
hint_upgrades

if [ "$BOOTSTRAP_ONLY" = "1" ]; then
  info "bootstrap-only mode: prerequisites are ready — exiting"
  exit 0
fi

# Compose derives the project name from the folder name — another AtlasFile
# instance whose directory has the same name would share containers AND VOLUMES
# (your data!). Detect and abort instead of silently adopting a foreign stack.
compose_project="$(basename "${INSTALL_DIR}" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_-]//g')"
other_dir="$(docker ps -a --filter "label=com.docker.compose.project=${compose_project}" \
  --format '{{.Label "com.docker.compose.project.working_dir"}}' 2>/dev/null | grep -vx "${INSTALL_DIR}" | sort -u | head -1 || true)"
if [ -n "${other_dir}" ]; then
  info "existing instance found at: ${other_dir}"
  fail "the directory ${INSTALL_DIR} would produce the same docker project name ('${compose_project}') as the instance above — they would share containers and volumes. Use --dir with a different name (e.g. --dir ~/AtlasFileNew) or remove the other instance first."
fi
# `af_fresh_install_dir` e nao `.git`: uma instalacao bundle re-executada nao
# tem .git, e so o manifesto prova que o volume encontrado e DESTA instalacao —
# sem isso o re-run seria barrado como se adotasse a instancia de outro.
if af_fresh_install_dir "${INSTALL_DIR}" && docker volume ls -q 2>/dev/null | grep -qx "${compose_project}_opensearch_data"; then
  # O volume pode ser NOSSO, guardado de propósito por um `--uninstall
  # --keep-data` neste mesmo diretório. Sem essa distinção o plano prometia "a
  # future reinstall reuses it" e a instalação seguinte recusava o dado como se
  # fosse de outra instância — com dois remédios que não o devolvem. Era um beco
  # sem saída, e foi medido numa VM Ubuntu.
  if af_kept_volume_claim "${compose_project}_opensearch_data" "${INSTALL_DIR}"; then
    info "reusing the data volume you kept on the last uninstall (${compose_project}_opensearch_data)"
    # A senha viaja com o volume até a fase 3. Sem ela o stack sobe e não
    # funciona: o índice de segurança do OpenSearch guarda a senha da PRIMEIRA
    # subida, e uma gerada agora só produz "Authentication finally failed".
    AF_REUSE_OS_PASS="$AF_KEPT_VOLUME_PASS"
  else
    fail "fresh install into ${INSTALL_DIR}, but the volume '${compose_project}_opensearch_data' already holds data from another instance. Use --dir with a different name (e.g. --dir ~/AtlasFileNew) or remove the volume (docker volume rm) if you are sure you no longer need it."
  fi
fi

# Container names are fixed (atlasfile-*): even with distinct project names,
# only one instance can exist at a time. If the containers belong to another
# directory, that stack must be stopped and removed first.
name_owner="$(docker inspect atlasfile --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' 2>/dev/null || true)"
# Instância 0.56.x ainda no ar usa os nomes antigos — mesmo bloqueio.
[ -n "${name_owner}" ] || name_owner="$(docker inspect atlasfile-api --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' 2>/dev/null || true)"
if [ -n "${name_owner}" ] && [ "${name_owner}" != "${INSTALL_DIR}" ]; then
  info "the atlasfile-* containers belong to the instance at: ${name_owner}"
  fail "AtlasFile container names are fixed — stop and remove the other stack before installing here: cd ${name_owner} && docker compose down (its data stays safe in the volumes)."
fi

# Portas EFETIVAS (flag > env > .env > default) — a mesma conta que o compose
# fara na interpolacao. Resolvidas aqui porque tudo daqui em diante (guarda,
# esperas, painel, browser) tem de falar da mesma porta.
af_resolve_app_port
af_resolve_os_port
for port in "$AF_PORT" "$AF_OS_PORT"; do
  if af_port_busy "$port"; then
    if docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null | grep -q "atlasfile.*:${port}"; then
      info "port ${port} is used by AtlasFile itself (it will be updated)"
    else
      # Conflito com saida ensinada, nao beco: era "free it before installing"
      # e pronto — benchmark de 8 produtos self-hosted: nenhum auto-incrementa
      # (quebra URL/bookmark/idempotencia); o estado da arte e falhar cedo com
      # o remedio na mensagem.
      if [ "$port" = "$AF_PORT" ]; then
        fail "port ${port} is already in use by another process — free it, or install on another port: re-run with --port N (the .env key is ATLASFILE_PORT)"
      else
        fail "port ${port} is already in use by another process — free it, or set OPENSEARCH_PORT in the .env and re-run"
      fi
    fi
  fi
done

# ── 2. Code ─────────────────────────────────────────────────────────────────
title "2/4" "Getting AtlasFile"
if [ "$AF_SOURCE_PATH" = "1" ]; then
  if [ "$FROM_SOURCE" != "1" ]; then
    # .git no dir e a instancia de quem instalou por clone: o re-run fica no
    # caminho fonte e diz isso, em vez de migrar a instalacao em silencio.
    info "existing git install detected — staying on the source path (clone + local build)"
  fi
  if [ -d "${INSTALL_DIR}/.git" ]; then
    CLONE_STATE="preexisting"
    AF_RESET_MARK="${LOG_FILE}.reset"
    run_step "updating existing install (${INSTALL_DIR})" \
      af_update_clone "${INSTALL_DIR}" "${BRANCH}"
    if [ -f "$AF_RESET_MARK" ]; then
      rm -f "$AF_RESET_MARK"
      info "the local history had diverged from origin/${BRANCH} — realigned to it (nothing of yours was here)"
    fi
  else
    CLONE_STATE="created"
    run_step "cloning ${REPO_URL} (${BRANCH})" \
      git clone --depth 1 --branch "${BRANCH}" "${REPO_URL}" "${INSTALL_DIR}"
  fi
else
  # Caminho bundle (o padrao): resolve a versao, avisa sobre flags que so valem
  # com --from-source, baixa e verifica o bundle. Nada de git daqui em diante.
  if [ -n "$AF_PIN_VERSION" ]; then
    af_validate_version "$AF_PIN_VERSION" \
      || fail "--version \"${AF_PIN_VERSION}\" is not a release number — use e.g. --version 1.0.0 (the list lives at https://github.com/aleonnet/atlasfile/releases)"
    AF_TARGET_VERSION="$AF_PIN_VERSION"
  else
    AF_TARGET_VERSION="$(af_resolve_version || true)"
    [ -n "$AF_TARGET_VERSION" ] \
      || fail "could not resolve the latest release from ${AF_API_BASE} — GitHub limits anonymous API calls (60/h per IP); pin one with --version X.Y.Z (the list lives at https://github.com/aleonnet/atlasfile/releases) and re-run"
  fi
  [ "$BRANCH" != "main" ] \
    && warn "--branch is only used with --from-source — ignored (installing release v${AF_TARGET_VERSION})"
  [ "$REPO_URL" != "https://github.com/aleonnet/atlasfile.git" ] \
    && warn "--repo-url is only used with --from-source — ignored (installing release v${AF_TARGET_VERSION})"
  cur_env_version="$(grep '^ATLASFILE_VERSION=' "${INSTALL_DIR}/.env" 2>/dev/null | head -1 | cut -d= -f2- || true)"
  if [ -n "$cur_env_version" ] && af_validate_version "$cur_env_version"; then
    af_downgrade_gate "$AF_TARGET_VERSION" "$cur_env_version"
  fi
  # `bundle` marca dir CRIADO por nos (removivel no uninstall, com as mesmas
  # guardas do clone `created`); dir preexistente segue `preexisting` — o
  # uninstall nunca remove pasta que nao pode provar que criou. Um re-run
  # sobre instalacao bundle relê o proprio valor para nao rebaixa-lo.
  AF_FRESH_INSTALL=0
  if [ ! -d "${INSTALL_DIR}" ]; then
    CLONE_STATE="bundle"
    AF_FRESH_INSTALL=1
    mkdir -p "${INSTALL_DIR}" || fail "could not create ${INSTALL_DIR} — check permissions and re-run"
  elif [ "$(manifest_get "${INSTALL_DIR}/${AF_MANIFEST_NAME}" repo_clone)" = "bundle" ]; then
    CLONE_STATE="bundle"
  else
    CLONE_STATE="preexisting"
  fi
  if ! af_fetch_bundle "$AF_TARGET_VERSION" "$INSTALL_DIR"; then
    fail "$AF_FETCH_ERR"
  fi
  ok "release bundle v${AF_TARGET_VERSION} downloaded and verified (checksum ok)"
fi
cd "${INSTALL_DIR}"
AF_MANIFEST="${INSTALL_DIR}/${AF_MANIFEST_NAME}"
manifest_set "$AF_MANIFEST" repo_clone "$CLONE_STATE"
manifest_set "$AF_MANIFEST" install_dir "$INSTALL_DIR"
if [ "$AF_SOURCE_PATH" != "1" ]; then
  manifest_set "$AF_MANIFEST" bundle_files "docker-compose.yml,.env.example,config/opensearch_dashboards.yml,config/api_keys.example.json"
fi

# ── 3. Configuration (.env) ─────────────────────────────────────────────────
title "3/4" "Configuring"
if [ -f .env ]; then ENV_STATE=preexisting; else ENV_STATE=created; fi
manifest_set "$AF_MANIFEST" env_file "$ENV_STATE"

if [ ! -f .env ]; then
  cp .env.example .env
  # One OpenSearch password per install — the template ships a public
  # placeholder; keeping a known default would be a factory-leaked credential.
  # (Creation-time only: changing it after first boot would break auth.)
  # Volume reusado exige a senha DELE — ver af_os_password.
  os_pass="$(af_os_password)"
  tmp_env="$(mktemp)"
  sed -e "s|^OPENSEARCH_PASSWORD=.*|OPENSEARCH_PASSWORD=${os_pass}|" \
      -e "s|^OPENSEARCH_INITIAL_ADMIN_PASSWORD=.*|OPENSEARCH_INITIAL_ADMIN_PASSWORD=${os_pass}|" \
      .env > "${tmp_env}" && mv "${tmp_env}" .env
  if [ -n "${AF_REUSE_OS_PASS:-}" ]; then
    ok ".env created (OpenSearch password restored from the volume you kept)"
  else
    ok ".env created (OpenSearch password generated for this install)"
  fi
else
  info ".env already exists — preserved"
fi

# set_env vive na zona de funcoes (junto do backup_env_once): aqui embaixo do
# gate de biblioteca a bancada nao a enxergava.

# v1.0.0: compose selects the app image by ATLASFILE_VERSION (no default on
# purpose — an implicit `latest` would make two installs drift apart).
# Caminho fonte: pina a versao do checkout (frontend/package.json, o unico
# registro de versao do repo; sed BSD-safe, sem jq), so quando ausente.
# Caminho bundle: o .env.example da release ja chega pinado; num re-run o pin
# e ATUALIZADO para a versao resolvida — re-executar o instalador E o ato
# deliberado de update, e o set_env preserva o resto do .env com backup.
if [ "$AF_SOURCE_PATH" = "1" ]; then
  if ! grep -q '^ATLASFILE_VERSION=' .env; then
    AF_VERSION="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' frontend/package.json | head -1)"
    printf 'ATLASFILE_VERSION=%s\n' "${AF_VERSION}" >> .env
    ok "ATLASFILE_VERSION=${AF_VERSION} written to .env (the image tag this stack runs)"
  fi
else
  if ! grep -q '^ATLASFILE_VERSION=' .env; then
    printf 'ATLASFILE_VERSION=%s\n' "${AF_TARGET_VERSION}" >> .env
    ok "ATLASFILE_VERSION=${AF_TARGET_VERSION} written to .env (the image tag this stack runs)"
  else
    cur_env_version="$(grep '^ATLASFILE_VERSION=' .env | head -1 | cut -d= -f2-)"
    if [ "$cur_env_version" != "$AF_TARGET_VERSION" ]; then
      set_env ATLASFILE_VERSION "$AF_TARGET_VERSION"
      ok "updating from ${cur_env_version} to ${AF_TARGET_VERSION} (ATLASFILE_VERSION in .env)"
    fi
  fi
fi

# A porta pedida pelo usuario (flag/env) persiste no .env — e o que faz o
# re-run e o compose falarem da mesma porta sem repetir a flag.
af_persist_port

current_root="$(grep '^PROJECTS_HOST_ROOT=' .env | head -1 | cut -d= -f2- || true)"
# .env.example placeholders do not count as user configuration
case "${current_root}" in
  "/path/to/Projects"|"/Users/your-user/Documents/Projects") current_root="" ;;
esac
if [ -z "${PROJECTS_ROOT}" ]; then
  if [ -n "${current_root}" ]; then
    PROJECTS_ROOT="${current_root}"
  elif [ "${ASSUME_YES}" = "1" ]; then
    PROJECTS_ROOT="${PROJECTS_ROOT_DEFAULT}"
  else
    # Under `curl | bash` stdin is the script itself — the prompt must read the
    # terminal. E é `ask`, não um printf solto: era a ÚNICA pergunta que não
    # passava pela calha, e por isso ela aparecia colada na barra de progresso
    # em vez de numa linha limpa.
    answer=""
    if [ -r "$TTY_DEV" ]; then
      af_read_line "$(ask "Folder where your projects/documents will live ${DIM}[${PROJECTS_ROOT_DEFAULT}]${RESET}: ")"
      answer="$AF_LINE"
    else
      info "no interactive terminal — using the default folder"
    fi
    PROJECTS_ROOT="${answer:-${PROJECTS_ROOT_DEFAULT}}"
  fi
fi

# O PORTÃO: aqui passam as quatro origens possíveis do caminho, e nenhuma escapa.
# Um valor inválido vindo de um .env anterior é o que derrubou a segunda
# instalação — o `.env already exists — preserved` releu o lixo da primeira e
# nem chegou a perguntar.
if ! PROJECTS_ROOT="$(af_sane_path "$PROJECTS_ROOT")"; then
  warn "the projects folder is not a usable absolute path — falling back to ${PROJECTS_ROOT_DEFAULT}"
  PROJECTS_ROOT="$PROJECTS_ROOT_DEFAULT"
fi

# Recorded BEFORE mkdir: only a folder this installer actually created may be
# removed later, and only while it is still empty.
if [ -d "${PROJECTS_ROOT}" ]; then
  manifest_set "$AF_MANIFEST" projects_root_created preexisting
else
  manifest_set "$AF_MANIFEST" projects_root_created created
fi
manifest_set "$AF_MANIFEST" projects_root "${PROJECTS_ROOT}"
# Falha aqui não pode virar compose quebrado três passos adiante: sem a pasta,
# o `${PROJECTS_HOST_ROOT}:/projects` não tem o que montar.
mkdir -p "${PROJECTS_ROOT}" || fail "could not create the projects folder ${PROJECTS_ROOT} — check permissions and re-run"
if grep -q '^PROJECTS_HOST_ROOT=' .env; then
  backup_env_once
  tmp_env="$(mktemp)"
  sed "s|^PROJECTS_HOST_ROOT=.*|PROJECTS_HOST_ROOT=${PROJECTS_ROOT}|" .env > "${tmp_env}" && mv "${tmp_env}" .env
else
  printf '\nPROJECTS_HOST_ROOT=%s\n' "${PROJECTS_ROOT}" >> .env
fi
ok "projects at: ${BOLD}${PROJECTS_ROOT}${RESET}"

# ── Dashboards session-cookie key (one per install) ─────────────────────────
# The default encryption key is identical across installs, so a session cookie
# from a previous instance decrypts fine but points to a session that does not
# exist — a 500 on a fresh install. A per-install key turns stale cookies into
# a clean login redirect. Generated only when missing or still the template
# placeholder (rotating an existing key just logs Dashboards users out).
cookie_current="$(grep '^DASHBOARDS_COOKIE_PASSWORD=' .env 2>/dev/null | head -1 | cut -d= -f2- || true)"
if [ -z "${cookie_current}" ] || [ "${cookie_current}" = "Troque-Esta-Senha-De-Cookie-Com-32-Ou-Mais-Chars" ]; then
  cookie_rand="$(af_random_token 48)"
  [ -n "${cookie_rand}" ] || cookie_rand="$(openssl rand -hex 24 2>/dev/null || printf 'Af%s%s0000000000000000' "$(date +%s)" "$$")"
  set_env DASHBOARDS_COOKIE_PASSWORD "${cookie_rand}"
  ok "Dashboards cookie key generated for this install"
fi

# ── API authentication (opt-in via --enable-auth) ───────────────────────────
# The keys file is BIND-MOUNTED into the container (compose), so key changes
# apply without rebuild. ATLASFILE_API_TOKEN goes to .env: it is the app's
# credential to itself (orchestrator→/mcp and tools→API). Re-running preserves
# the key.
if [ "${ENABLE_AUTH}" = "1" ]; then
  keys_file="config/api_keys.json"
  if [ -f "${keys_file}" ]; then
    API_KEY_VALUE="$(sed -n 's/.*"key"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "${keys_file}" | head -1)"
    [ -n "${API_KEY_VALUE}" ] && info "api_keys.json already exists — key preserved"
  fi
  if [ -z "${API_KEY_VALUE}" ]; then
    key_rand="$(af_random_token 32 'a-z0-9')"
    [ -n "${key_rand}" ] || key_rand="$(openssl rand -hex 16 2>/dev/null || date +%s)"
    API_KEY_VALUE="atlas_sk_${key_rand}"
    printf '{\n  "keys": [\n    {"key": "%s", "name": "installer", "projects": ["*"]}\n  ]\n}\n' "${API_KEY_VALUE}" > "${keys_file}"
    manifest_set "$AF_MANIFEST" api_keys_file created
    ok "api_keys.json created with a generated key"
  fi
  set_env API_AUTH_ENABLED true
  set_env ATLASFILE_API_TOKEN "${API_KEY_VALUE}"
  ok "API authentication enabled"
fi
# Sem --enable-auth o arquivo também PRECISA existir antes do `up`: o compose o
# monta como bind mount, e arquivo ausente vira um DIRETÓRIO criado pelo Docker
# — com auth ligado depois, toda key passaria a ser rejeitada em silêncio.
if [ ! -f config/api_keys.json ]; then
  printf '{"keys": []}\n' > config/api_keys.json
  manifest_set "$AF_MANIFEST" api_keys_file created
  ok "api_keys.json created empty (compose bind mount)"
fi

# ── 4. Images + launch ──────────────────────────────────────────────────────
# A frase depende do ESTADO, e não é decorativa: prometer café para uma espera
# curta é ruído (medido: 1m05s no primeiro build, 3s no segundo; pull da app
# 18,7s no rc.2). No bundle path não há promessa de segundos — o tamanho é
# medido (288/293 MB comprimidos no rc.2), o tempo depende da conexão.
if [ "$AF_SOURCE_PATH" = "1" ]; then
  title "4/4" "Building and starting the stack"
  if [ "${CLONE_STATE}" = "created" ]; then
    info "first run downloads images and compiles — takes a minute or two"
  else
    info "reusing the build cache — this is usually quick"
  fi
else
  title "4/4" "Getting the images and starting the stack"
  if [ "${AF_FRESH_INSTALL}" = "1" ]; then
    info "first run downloads the app image (~290 MB) and the OpenSearch images — time depends on your connection"
  else
    info "images already on this machine are reused — this is usually quick"
  fi
fi
# --remove-orphans (dentro do af_stack_up): reinstalar por cima de um checkout
# 0.56.x precisa derrubar os containers dos serviços antigos (api/mcp/web) — o
# api órfão segura a :8000.
af_stack_up

run_step "waiting for the API to become healthy" wait_http "http://localhost:${AF_PORT}/health" 90
run_step "waiting for the interface" wait_http "http://localhost:${AF_PORT}/" 30

# ── 5. Done ─────────────────────────────────────────────────────────────────
TOTAL_SECS=$(( $(step_now) - START_TS ))
TOTAL=$(fmt_secs "$TOTAL_SECS")
# O trilho FECHA aqui, depois do ultimo trabalho — e o relatorio sai do lado de
# fora dele. Antes o `[5/5]` abria um estagio que o `╰──` fechava na linha
# seguinte, como se a fase nao tivesse conteudo; e o resumo seguia pendurado na
# calha, que ja tinha acabado.
bar_clear
printf '%s\n' "$GUT"
rule_close
# AF-FIM-DO-TRILHO: daqui para baixo o trilho JA FECHOU e as mensagens saem sem
# calha, de proposito. A guarda da bancada so cobra a calha ACIMA desta marca.

printf '\n'
note "${BOLD}Install finished in ${TOTAL}${RESET} 🎉"
# Placar: o que de fato aconteceu, em números. A frase fixa de antes dizia a
# mesma coisa numa instalação limpa e numa reexecução que não mudou nada.
# Sem contador aqui, de proposito. A tela ACIMA ja mostra as quatro fases, cada
# uma com seus ✔ e seus tempos; qualquer numero novo no resumo compete com ela e
# vira pergunta ("4 fases mas 5 passos?"). Quem quiser o detalhe por operacao tem
# o relatorio da execucao, logo abaixo. O mac-env conta ITENS porque o usuario
# escolheu quais instalar — aqui as fases sao fixas e ja estao na tela.
# box_row LABEL VALUE — padded to the fixed inner width; long values get a
# leading ellipsis keeping the tail (the folder name is what matters)
box_row() {
  local label="$1" value="$2"
  if [ ${#value} -gt 43 ]; then value="…${value:$((${#value} - 42))}"; fi
  printf '  %s│%s  %s%-11s%s %-43s%s│%s\n' "$ORANGE" "$RESET" "$BOLD" "$label" "$RESET" "$value" "$ORANGE" "$RESET"
}
printf '  %s╭─────────────────────────────────────────────────────────╮%s\n' "$ORANGE" "$RESET"
box_row "Interface" "http://localhost:${AF_PORT}"
box_row "API" "http://localhost:${AF_PORT}/health"
box_row "MCP" "http://localhost:${AF_PORT}/mcp"
box_row "Projects" "${PROJECTS_ROOT}"
printf '  %s╰─────────────────────────────────────────────────────────╯%s\n\n' "$ORANGE" "$RESET"
if [ "${ENABLE_AUTH}" = "1" ] && [ -n "${API_KEY_VALUE}" ]; then
  printf '  %s🔑 API key%s (paste it in Settings → Access, in each browser):\n' "$BOLD" "$RESET"
  printf '     %s%s%s\n\n' "$ORANGE" "${API_KEY_VALUE}" "$RESET"
fi

# ── Próximos passos: só os que se aplicam ───────────────────────────────────
# O mac-env monta esta lista a partir do que REALMENTE aconteceu (`result_ok
# docker` → "abra o Docker.app uma vez"). Antes eram sempre as mesmas três
# linhas, inclusive as que não valiam para aquela execução.
printf '  %sNext steps%s\n' "$BOLD" "$RESET"
printf '    • the onboarding wizard opens by itself in the interface\n'
if [ "$(host_get docker_group)" = "created" ]; then
  printf '    • log out and back in: your docker group membership only applies to new sessions\n'
fi
# Modelo 100% local é um passo DEPOIS da instalação, e de propósito: o pull são
# vários GB e tiraria qualquer previsibilidade da duração aqui.
if command -v ollama >/dev/null 2>&1; then
  printf '    • local model: %sollama pull %s%s, then type %sollama/%s%s in the assistant settings\n' \
    "$BOLD" "${OLLAMA_MODEL}" "$RESET" "$BOLD" "${OLLAMA_MODEL}" "$RESET"
else
  printf '    • want a 100%% local model? install Ollama (https://ollama.com), then %sollama pull %s%s\n' \
    "$BOLD" "${OLLAMA_MODEL}" "$RESET"
fi
if [ "$OS_KIND" = "mac" ] && [ "$(host_get docker)" = "created" ]; then
  printf '    • Docker Desktop was installed now — keep it open for the stack to run\n'
fi
# Dashboards é opt-in desde a consolidação (1/3 do download de terceiros e o
# produto opera sem ele) — o passo só aparece porque é decisão pós-instalação.
printf '    • observability dashboard (optional): set %sDASHBOARDS_ENABLED=true%s and %sCOMPOSE_PROFILES=dashboards%s in .env, then %sdocker compose up -d%s\n' \
  "$BOLD" "$RESET" "$BOLD" "$RESET" "$BOLD" "$RESET"
printf '    • logs:  cd %s && docker compose logs -f\n' "${INSTALL_DIR}"
printf '    • stop:  cd %s && docker compose down\n' "${INSTALL_DIR}"
printf '\n'

# Espelho em arquivo: o log guarda a saída das ferramentas, não o que ESTE
# instalador fez. Sem isso, diagnosticar uma instalação de ontem é adivinhação.
write_run_log() {
  local f="${AF_STATE_DIR}/last-run.log" linha
  mkdir -p "$AF_STATE_DIR" 2>/dev/null || return 0
  {
    printf 'install.sh — %s\n' "$(date '+%Y-%m-%d %H:%M:%S')"
    printf 'dir: %s · projects: %s · duration: %s\n\n' "$INSTALL_DIR" "$PROJECTS_ROOT" "$TOTAL"
    printf '%s\n' "$RUN_STEPS" | while IFS='|' read -r linha secs; do
      [ -n "$linha" ] && printf '  %-52s %ss\n' "$linha" "$secs"
    done
    printf '\ntool output of this run: %s\n' "$LOG_FILE"
  } > "$f" 2>/dev/null || return 0
  note "run report: ${f}"
  return 0
}
write_run_log
printf '\n'

if [ "${OPEN_BROWSER}" = "1" ]; then
  if command -v open >/dev/null 2>&1; then open "http://localhost:${AF_PORT}" || true
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "http://localhost:${AF_PORT}" || true
  fi
fi

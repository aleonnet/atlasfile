#!/usr/bin/env bash
# AtlasFile — one-liner installer (macOS/Linux)
#
#   curl -fsSL https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.sh | bash
#
# Host requirements: Docker (with Compose v2), git, curl — and if any of them is
# missing, the installer OFFERS to install it for you (Homebrew/cask on macOS,
# official get.docker.com + apt/dnf on Linux). No make/node/python needed.
# Idempotent: re-running updates the clone and restarts the stack.
#
# Flags:
#   --repo-url URL        (default: https://github.com/aleonnet/atlasfile.git; env ATLASFILE_REPO_URL)
#   --branch NAME         (default: main)
#   --dir PATH            (default: ~/AtlasFile)
#   --projects-root PATH  (default: ~/Documents/AtlasFileProjects)
#   --yes                 non-interactive (accepts defaults; does NOT install
#                         missing system dependencies — see --install-deps)
#   --install-deps        authorize installing missing prerequisites without
#                         prompting (Homebrew/Docker/git; sudo on Linux)
#   --with-ollama         also install Ollama and pull a local model (opt-in)
#   --ollama-model NAME   model to pull with --with-ollama
#                         (default: gemma4:12b; env ATLASFILE_OLLAMA_MODEL)
#   --no-open             do not open the browser at the end
#   --enable-auth         enable API authentication (generates a key in
#                         config/api_keys.json, sets API_AUTH_ENABLED=true and
#                         ATLASFILE_API_TOKEN in .env). Re-running with this flag
#                         enables auth on an existing install without data loss.
set -euo pipefail

REPO_URL="${ATLASFILE_REPO_URL:-https://github.com/aleonnet/atlasfile.git}"
BRANCH="main"
INSTALL_DIR="${HOME}/AtlasFile"
PROJECTS_ROOT_DEFAULT="${HOME}/Documents/AtlasFileProjects"
PROJECTS_ROOT=""
ASSUME_YES=0
INSTALL_DEPS=0
WITH_OLLAMA=0
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
NO_OLLAMA=0
DELEGATED=0
HOST_EXTRA=""      # facts from the OTHER side of an OS boundary (install.ps1)

# Exit codes. 0 = done, 1 = failed, 10 = the user said no. `exit` in bash is
# truncated to 8 bits, so the Windows-world MSI codes (1602 = user cancelled,
# 3010 = reboot pending) live in install.ps1, which translates this one.
RC_CANCELLED=10

# Machine-readable last word of an uninstall. install.ps1 requires BOTH this
# line AND a zero exit code before it touches a single Windows package: there is
# no official documentation that wsl.exe propagates the Linux exit code, and a
# swallowed code must never be read as "the user confirmed".
sentinel() { printf 'ATLASFILE_UNINSTALL: %s\n' "$1"; }
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

With no options: installs into ~/AtlasFile, asks where your documents should
live and starts the stack. Re-running updates the clone and restarts it — the
installer is idempotent. Host requirements (Docker with Compose v2, git, curl)
are detected and, with your confirmation, installed for you.

Install options:
  --dir PATH            Where to install                 (default: ~/AtlasFile)
  --projects-root PATH  Where your documents live        (default: ~/Documents/AtlasFileProjects)
  --repo-url URL        Repository to clone              (env ATLASFILE_REPO_URL)
  --branch NAME         Branch to clone                  (default: main)
  --yes, -y             Non-interactive: accept defaults. On its own it NEVER
                        installs system dependencies — see --install-deps
  --install-deps        Authorize installing missing prerequisites without
                        asking (Homebrew/Docker/git; sudo on Linux)
  --with-ollama         Also install Ollama and pull a local model (opt-in)
  --no-ollama           Never offer nor install Ollama in this run. The Windows
                        installer always passes it: there, Ollama belongs to the
                        Windows side and the containers reach it through
                        host.docker.internal — a second copy inside WSL would be
                        several GB of duplicate
  --ollama-model NAME   Model to pull with --with-ollama (default: ${OLLAMA_MODEL})
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
  --plan-only           Uninstall: print the removal plan and exit. Asks nothing,
                        changes nothing — the dry run of the uninstall

Other:
  -h, --help            This help

Environment: ATLASFILE_REPO_URL, ATLASFILE_OLLAMA_MODEL, NO_COLOR, CI,
             COLORTERM, DOCKER_APP_PATH, TTY_DEV
Log of this run: ${LOG_FILE}
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --repo-url) REPO_URL="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --dir) INSTALL_DIR="$2"; shift 2 ;;
    --projects-root) PROJECTS_ROOT="$2"; shift 2 ;;
    --yes|-y) ASSUME_YES=1; shift ;;
    --install-deps) INSTALL_DEPS=1; shift ;;
    --with-ollama) WITH_OLLAMA=1; shift ;;
    --ollama-model) OLLAMA_MODEL="$2"; shift 2 ;;
    --bootstrap-only) BOOTSTRAP_ONLY=1; shift ;;  # hidden: prereqs only, then exit (CI/support)
    --no-open) OPEN_BROWSER=0; shift ;;
    --enable-auth) ENABLE_AUTH=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    --purge-data) PURGE_DATA=1; shift ;;
    --keep-data) PURGE_DATA=0; shift ;;
    --remove-deps) REMOVE_DEPS=1; shift ;;
    --force) FORCE=1; shift ;;
    --plan-only) PLAN_ONLY=1; shift ;;
    --no-ollama) NO_OLLAMA=1; shift ;;
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
COLOR_OK=0
if [ "$IS_TTY" = "1" ] && [ -z "${NO_COLOR:-}" ] && [ "${TERM:-dumb}" != "dumb" ]; then COLOR_OK=1; fi
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
  c="$(tput cols 2>/dev/null || echo 72)"
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
# `docker compose build` sozinho leva ~15 min, saber "fase 4 de 5" é o que falta.
BAR_TOTAL=5
BAR_DONE=0
BAR_VISIBLE=0
# Placar e relatório da execução, no espírito do write_run_log do mac-env: o que
# aconteceu, com tempo por passo, espelhado num arquivo. Tínhamos log da saída
# das ferramentas e nenhum relatório do que o instalador fez.
STEPS_DONE=0
CHECKS_OK=0
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
    printf '\r'
    tput el 2>/dev/null || printf '%*s\r' 60 ''
    BAR_VISIBLE=0
  fi
  return 0
}

fail_with_log() {
  bar_clear
  printf '\r%s%s✘%s %s\n' "$GUT" "$RED" "$RESET" "$1"
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
  STEPS_DONE=$(( STEPS_DONE + 1 ))
  bar_show
}

check() {
  local msg="$1"; shift
  if "$@" >>"$LOG_FILE" 2>&1; then
    ok "$msg"
    CHECKS_OK=$(( CHECKS_OK + 1 ))
  else
    return 1
  fi
}

ok()    { bar_clear; printf '%s%s✔%s %s\n' "$GUT" "$GREEN" "$RESET" "$*"; bar_show; }
fail()  { bar_clear; printf '%s%s✘%s %s\n' "$GUT" "$RED" "$RESET" "$*"; exit 1; }
warn()  { bar_clear; printf '%s%s!%s %s\n' "$GUT" "$ORANGE" "$RESET" "$*"; bar_show; }
info()  { bar_clear; printf '%s%s·%s %s\n' "$GUT" "$PURPLE" "$RESET" "$*"; bar_show; }
# Pergunta: sem newline, e sem redesenhar a barra por cima do cursor de leitura.
ask()   { bar_clear; printf '%s%s?%s %s' "$GUT" "$ORANGE" "$RESET" "$*"; }

# Régua de fase que varre da esquerda para a direita, com a rampa do produto.
# `[1/5] Título` continha a mesma informação em texto plano; a régua dá a ela o
# peso de um cabeçalho e reusa a paleta que até aqui só o banner conhecia.
# NADA aqui indexa string com ${s:i:1}: sob LC_ALL=C isso conta BYTES, e cada
# ─ ocupa três. É a mesma armadilha que o banner documenta, e ela transformaria
# a régua em lixo. O conector `├── ` tem largura FIXA e conhecida (4 colunas),
# então entra na conta como constante, e os traços são gerados por repetição —
# a contagem é minha, nunca do interpretador.
AF_RULE_CONNECTOR_COLS=4
rule_sweep() { # <cabeçalho ASCII>
  local head="$1" w fill i j pos chunk segs=8 per feitos=0
  w="$(term_cols)"
  fill=$(( w - ${#head} - AF_RULE_CONNECTOR_COLS - 3 ))
  [ "$fill" -lt 4 ] && fill=4
  if [ "$COLOR_OK" != "1" ] || [ "$TRUECOLOR" != "1" ]; then
    chunk=""
    for (( i = 0; i < fill; i++ )); do chunk="${chunk}─"; done
    printf '%s├── %s%s%s %s\n' "$GUT" "$BOLD" "$head" "$RESET" "$chunk"
    return 0
  fi
  printf '%s├── %s%s%s ' "$GUT" "$BOLD" "$head" "$RESET"
  per=$(( fill / segs )); [ "$per" -lt 1 ] && per=1
  for (( i = 0; i < segs && feitos < fill; i++ )); do
    pos=$(( i * 1000 / (segs - 1) ))
    af_rgb_at "$pos"
    chunk=""
    for (( j = 0; j < per && feitos < fill; j++ )); do chunk="${chunk}─"; feitos=$(( feitos + 1 )); done
    printf '\033[38;2;%d;%d;%dm%s' "$AF_R" "$AF_G" "$AF_B" "$chunk"
  done
  printf '%s\n' "$RESET"
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
  ask "$q ${DIM}[y/N]${RESET} "
  read -r answer < "$TTY_DEV" || answer=""
  case "$answer" in y|Y|yes|YES|s|S) return 0 ;; *) return 1 ;; esac
}

detect_os() {
  OS_KIND="linux"; PKG="none"; BREW_PREFIX="/usr/local"
  if [ "$(uname -s)" = "Darwin" ]; then
    OS_KIND="mac"
    [ "$(uname -m)" = "arm64" ] && BREW_PREFIX="/opt/homebrew"
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
  run_step "installing Homebrew" env NONINTERACTIVE=1 /bin/bash -c \
    "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || return 1
  [ -x "${BREW_PREFIX}/bin/brew" ] && eval "$("${BREW_PREFIX}/bin/brew" shellenv)"
  host_set homebrew created
  return 0
}

ensure_git() {
  command -v git >/dev/null 2>&1 && { host_set git preexisting; return 100; }
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
  ensure_homebrew || return 1
  run_step "installing Docker Desktop (Homebrew cask)" brew install --cask docker-desktop || return 1
  host_set docker created
  return 0
}

ensure_docker_linux() {
  command -v docker >/dev/null 2>&1 && { host_set docker preexisting; return 100; }
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
ensure_docker_group_linux() {
  docker info >/dev/null 2>&1 && return 0
  # shellcheck disable=SC2033  # `docker` below is the real binary, not the shim
  if sudo -n docker info >/dev/null 2>&1 || { ensure_sudo && sudo docker info >/dev/null 2>&1; }; then
    # Resolve the real binary BEFORE the shim shadows the name. The previous
    # form was `sudo command docker "$@"`, which looks right but there is no
    # /usr/bin/command on Debian/Ubuntu (verified in ubuntu:24.04) — every
    # later `docker ...` would have died with "sudo: command: command not
    # found" on exactly the platform this shim exists for.
    AF_DOCKER_BIN="$(command -v docker)"
    docker() { sudo "$AF_DOCKER_BIN" "$@"; }
    if sudo usermod -aG docker "$USER" 2>/dev/null; then host_set docker_group created; fi
    info "added ${USER} to the docker group — takes effect on your next login"
    return 0
  fi
  return 1
}

ensure_ollama() {
  if command -v ollama >/dev/null 2>&1; then host_set ollama preexisting; return 100; fi
  if [ "$OS_KIND" = "mac" ]; then
    ensure_homebrew || return 1
    # cask name changed over time: try the current one, then the legacy one
    run_step "installing Ollama (Homebrew cask)" brew install --cask ollama-app \
      || run_step "installing Ollama (Homebrew cask, legacy name)" brew install --cask ollama \
      || return 1
    open -g -a Ollama >/dev/null 2>&1 || true
  else
    ensure_sudo || return 1
    run_step "installing Ollama (official install.sh)" \
      sh -c "curl -fsSL https://ollama.com/install.sh | sh" || return 1
  fi
  wait_http http://localhost:11434/api/version 15 || warn "Ollama installed but the service did not answer yet — open the Ollama app once"
  host_set ollama created
  return 0
}

ollama_pull_model() {
  local model="$1"
  if ollama list 2>/dev/null | awk '{print $1}' | grep -qx "$model"; then
    ok "model ${model} already pulled"
    host_set ollama_model_state preexisting
    return 0
  fi
  info "pulling model ${model} — large download (several GB), one-time"
  if [ "$IS_TTY" = "1" ] && [ -r "$TTY_DEV" ]; then
    # foreground: ollama's native progress bar is worth it for a multi-GB pull
    if ! ollama pull "$model" < "$TTY_DEV"; then
      warn "could not pull ${model} — run manually later: ollama pull ${model}"
      return 0
    fi
  else
    run_step "pulling model ${model}" ollama pull "$model" || {
      warn "could not pull ${model} — run manually later: ollama pull ${model}"
      return 0
    }
  fi
  host_set ollama_model_state created
  host_set ollama_model_name "$model"
  ok "model ${model} ready"
}

# ── Ollama (opt-in): runs after the stack is up so it never delays first screen
# --no-ollama silences BOTH the offer and the install. install.ps1 always passes
# it: on Windows the Ollama belongs to the Windows side and the containers reach
# it through host.docker.internal. Without the flag this question came back a
# SECOND time inside the distro — where `command -v ollama` naturally fails,
# because the binary lives on the other operating system — and a "y" pulled
# several GB of duplicate. That intent used to live only in a comment in
# install.ps1; it is a contract now, and this function exists so the contract is
# reachable by the bench instead of being buried in the script's main flow.
maybe_setup_ollama() {
  local ollama_answer="" ollama_rc=0
  [ "$NO_OLLAMA" = "1" ] && return 0
  if [ "${WITH_OLLAMA}" = "0" ] && [ "$ASSUME_YES" = "0" ] && [ -r "$TTY_DEV" ] \
    && ! command -v ollama >/dev/null 2>&1; then
    ask "Also install Ollama for a 100% local model (${OLLAMA_MODEL}, several GB)? ${DIM}[y/N]${RESET} "
    read -r ollama_answer < "$TTY_DEV" || ollama_answer=""
    case "$ollama_answer" in y|Y|yes|YES|s|S) WITH_OLLAMA=1 ;; esac
  fi
  [ "${WITH_OLLAMA}" = "1" ] || return 0
  ensure_ollama || ollama_rc=$?
  if [ "$ollama_rc" = "100" ]; then
    ok "ollama $(ollama --version 2>/dev/null | sed 's/ollama version is //' || true) (already installed — the app updates itself)"
  fi
  if [ "$ollama_rc" != "1" ]; then
    ollama_pull_model "${OLLAMA_MODEL}"
    info "in the assistant settings, type ollama/${OLLAMA_MODEL} in the model box to use it"
  else
    warn "Ollama setup failed — the stack is up; install manually later (https://ollama.com)"
  fi
  return 0
}

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
AF_MANIFEST_NAME=".atlasfile-install-manifest"

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


# ── Uninstall ───────────────────────────────────────────────────────────────
# Facts first (all read-only), then a plan in text with a REMOVED and a
# PRESERVED section, then one confirmation, then execution. Every fact below is
# a variable so the plan builder can be unit-tested without a Docker daemon.
UN_DIR=""; UN_PROJECT=""; UN_COMPOSE_FILE=0
UN_CLONE_STATE="unknown"; UN_DIR_DIRTY=0; UN_ENV=0
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
    docker) printf 'Docker Desktop (Windows side)' ;;
    ollama) printf 'Ollama (Windows side)' ;;
    wsl)    printf 'WSL2' ;;
    *)      printf '%s (Windows side)' "$1" ;;
  esac
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
    if [ "$key" = "wsl" ]; then
      # A Windows feature other tools depend on. Never removed, whoever created it.
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

un_add_remove() { UN_PLAN_REMOVE="${UN_PLAN_REMOVE}${GUT}  • $1
"; }
un_add_keep()   { UN_PLAN_KEEP="${UN_PLAN_KEEP}${GUT}  • $1
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
  UN_PROJECTS_ROOT="$(manifest_get "$mf" projects_root)"
  UN_PROJECTS_CREATED="$(manifest_get "$mf" projects_root_created)"; [ -n "$UN_PROJECTS_CREATED" ] || UN_PROJECTS_CREATED="preexisting"
  if [ -z "$UN_PROJECTS_ROOT" ] && [ "$UN_ENV" = "1" ]; then
    UN_PROJECTS_ROOT="$(grep '^PROJECTS_HOST_ROOT=' "${dir}/.env" 2>/dev/null | head -1 | cut -d= -f2- || true)"
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
    if [ -n "$(git -C "$dir" status --porcelain -- . \
        ":(exclude).env" ":(exclude)${AF_MANIFEST_NAME}" \
        ":(exclude)config/api_keys.json" 2>/dev/null || true)" ]; then
      UN_DIR_DIRTY=1
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
    for f in api web mcp; do
      if docker image inspect "${UN_PROJECT}-${f}" >/dev/null 2>&1; then
        UN_IMAGES="${UN_IMAGES}${UN_PROJECT}-${f} "
      fi
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
  local purge="$1" deps="$2" force="$3" st model
  UN_PLAN_REMOVE=""; UN_PLAN_KEEP=""; UN_ACTIONS=""

  # ── the stack (unambiguously ours) ──
  if [ "$UN_COMPOSE_FILE" = "1" ]; then
    un_add_remove "stack '${UN_PROJECT}': containers, network and the images built here (${UN_CONTAINERS} container(s))"
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
      un_add_keep "data volume ${UN_VOLUME} (kept: a future reinstall reuses it)"
    fi
  fi
  [ -n "$UN_IMAGES" ] && un_add_keep "shared upstream images (opensearchproject/*) — remove them by hand if you want the disk back"

  # ── the clone ──
  if [ "$UN_CLONE_STATE" = "created" ]; then
    if [ "$UN_DIR_DIRTY" = "1" ] && [ "$force" != "1" ]; then
      un_add_keep "${UN_DIR} has local changes — NOT removed (re-run with --force to remove it anyway)"
    else
      un_add_remove "install directory ${UN_DIR} (clone created by this installer, with its .env)"
      un_act "rm-clone"
    fi
  elif [ "$UN_COMPOSE_FILE" = "1" ]; then
    un_add_keep "${UN_DIR} was not created by this installer — preserved (only the stack above was touched)"
  else
    # No compose file means no stack was touched either: claiming otherwise
    # would make the plan describe something that did not happen.
    un_add_keep "${UN_DIR} was not created by this installer — preserved"
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
      if [ "$st" = "created" ]; then
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
    if [ "$st" = "created" ]; then
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
un_report() {
  printf '%s\n' "$GUT"
  rule_sweep "AtlasFile removed"
  printf '%s%s✔ %s removed%s' "$GUT" "$GREEN" "$UN_OK" "$RESET"
  [ "$UN_KO" -gt 0 ] && printf '   %s✘ %s failed%s' "$RED" "$UN_KO" "$RESET"
  printf '   %skept: what already existed on this machine%s\n%s\n' "$DIM" "$RESET" "$GUT"
  if [ -n "$UN_PROJECTS_ROOT" ] && [ "$UN_PROJECTS_FILES" != "0" ]; then
    info "your documents are untouched in ${UN_PROJECTS_ROOT}"
  fi
  [ "$UN_KO" -gt 0 ] && info "details of what failed: ${LOG_FILE}"
  printf '\n'
  return 0
}

un_has_action() { printf '%s' "$UN_ACTIONS" | grep -qx "$1"; }

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
  ( cd "$UN_DIR" && docker compose down $args )
}

un_execute() {
  local act model
  printf '\n'
  while IFS= read -r act; do
    [ -n "$act" ] || continue
    case "$act" in
      compose-down)
        un_step "removing the stack (containers, network, local images)" un_compose_down ;;
      purge-volume)
        # Already covered by `compose down --volumes` when the stack was
        # removed from the clone; this is the fallback when it was not.
        if ! un_has_action "compose-down" && [ -n "$UN_VOLUME" ]; then
          un_step "removing volume ${UN_VOLUME}" docker volume rm $UN_VOLUME
        fi ;;
      rm-clone)
        if un_dir_is_safe "$UN_DIR"; then
          un_step "removing ${UN_DIR}" rm -rf "$UN_DIR"
        else
          warn "refusing to remove ${UN_DIR}: it does not look like an AtlasFile install"
        fi ;;
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
  un_collect "$INSTALL_DIR"

  # A run that installed Docker and then died BEFORE cloning leaves no install
  # directory but a perfectly good host manifest — that half-installed state is
  # exactly why the host manifest is written the moment each ensure_* decides.
  # Refusing here would strand the user with a Docker they did not have before
  # and no tool to revert it, so the deps-only plan is still offered.
  if [ "$UN_COMPOSE_FILE" = "0" ] && [ ! -d "${INSTALL_DIR}" ]; then
    if [ -f "$AF_HOST_MANIFEST" ]; then
      info "no install at ${INSTALL_DIR}, but this host has a prerequisite manifest — planning the system dependencies only"
    else
      fail "no AtlasFile install found at ${INSTALL_DIR} — point --dir at the right folder"
    fi
  fi

  # Facts first, and nobody has been asked anything yet: --plan-only short-
  # circuits here so an orchestrator can read the plan of THIS side before
  # putting a single question to the user.
  if [ "$PLAN_ONLY" = "1" ]; then
    un_build_plan "${PURGE_DATA:-ask}" "$REMOVE_DEPS" "$FORCE"
    un_print_plan
    # Fatos em forma legível por máquina, para o orquestrador não ter de
    # adivinhar lendo a prosa do plano: se há volume, ele sabe que precisa
    # perguntar; se não há ação alguma, sabe que não há o que confirmar.
    printf 'ATLASFILE_FACT: volume=%s\n' "$UN_VOLUME"
    if [ -n "$UN_ACTIONS" ]; then
      printf 'ATLASFILE_FACT: actions=1\n'
    else
      printf 'ATLASFILE_FACT: actions=0\n'
    fi
    sentinel "plan-only"
    return 0
  fi

  # The data volume never has a default: the user decides, every time.
  if [ -n "$UN_VOLUME" ] && [ -z "$PURGE_DATA" ]; then
    if [ "$ASSUME_YES" = "1" ] || [ ! -r "$TTY_DEV" ]; then
      fail "the volume ${UN_VOLUME} holds the search index — decide explicitly: --purge-data (erase it) or --keep-data (keep it)"
    fi
    printf '%s\n' "$GUT"
    ask "The volume ${BOLD}${UN_VOLUME}${RESET} holds the search index."
    printf '\n%s   Your documents and the _ATLASFILE journal live on disk and are NOT affected;\n' "$GUT"
    printf '%s   the index is rebuilt by Reconcile after a reinstall.\n' "$GUT"
    ask "Erase the volume? ${DIM}[y/N]${RESET} "
    local ans=""
    # `[ -r /dev/tty ]` is true even when the device cannot be opened (no
    # controlling terminal), so the redirection itself has to be silenced.
    { read -r ans < "$TTY_DEV"; } 2>/dev/null || ans=""
    case "$ans" in y|Y|yes|YES|s|S) PURGE_DATA=1 ;; *) PURGE_DATA=0 ;; esac
  fi
  [ -n "$PURGE_DATA" ] || PURGE_DATA=0

  un_build_plan "$PURGE_DATA" "$REMOVE_DEPS" "$FORCE"
  un_print_plan

  if [ -z "$UN_ACTIONS" ]; then
    info "nothing to do."
    sentinel "nothing-to-do"
    return 0
  fi
  if [ "$ASSUME_YES" != "1" ]; then
    if [ ! -r "$TTY_DEV" ]; then
      sentinel "cancelled"
      fail "no interactive terminal — re-run with --yes to confirm the plan above"
    fi
    ask "Execute the plan above? ${DIM}[y/N]${RESET} "
    local answer=""
    { read -r answer < "$TTY_DEV"; } 2>/dev/null || answer=""
    printf '\n'
    # A "no" here used to return 0, which any caller reads as success — and
    # install.ps1 went on to delete Docker Desktop from a machine whose owner
    # had just said no. Cancelling is its own outcome and gets its own code.
    case "$answer" in
      y|Y|yes|YES|s|S) ;;
      *) info "uninstall cancelled — nothing was touched."; sentinel "cancelled"; return "$RC_CANCELLED" ;;
    esac
  fi

  un_execute
  printf '\n'
  if [ "$UN_FAILED" = "1" ]; then
    warn "uninstall finished with failures — see ${LOG_FILE}"
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

if [ "$UNINSTALL" = "1" ]; then
  uninstall_rc=0
  run_uninstall || uninstall_rc=$?
  exit "$uninstall_rc"
fi

# ── 1. Prerequisites ────────────────────────────────────────────────────────
title "1/5" "Checking and preparing prerequisites"
detect_os

# git — offer to install when missing
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
check "curl" command -v curl || fail "curl not found"

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
if [ ! -d "${INSTALL_DIR}/.git" ] && docker volume ls -q 2>/dev/null | grep -qx "${compose_project}_opensearch_data"; then
  fail "fresh install into ${INSTALL_DIR}, but the volume '${compose_project}_opensearch_data' already holds data from another instance. Use --dir with a different name (e.g. --dir ~/AtlasFileNew) or remove the volume (docker volume rm) if you are sure you no longer need it."
fi

# Container names are fixed (atlasfile-*): even with distinct project names,
# only one instance can exist at a time. If the containers belong to another
# directory, that stack must be stopped and removed first.
name_owner="$(docker inspect atlasfile-api --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' 2>/dev/null || true)"
if [ -n "${name_owner}" ] && [ "${name_owner}" != "${INSTALL_DIR}" ]; then
  info "the atlasfile-* containers belong to the instance at: ${name_owner}"
  fail "AtlasFile container names are fixed — stop and remove the other stack before installing here: cd ${name_owner} && docker compose down (its data stays safe in the volumes)."
fi

for port in 5173 8000 9200; do
  if command -v lsof >/dev/null 2>&1 && lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    if docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null | grep -q "atlasfile.*:${port}"; then
      info "port ${port} is used by AtlasFile itself (it will be updated)"
    else
      fail "port ${port} is already in use by another process — free it before installing"
    fi
  fi
done

# ── 2. Code ─────────────────────────────────────────────────────────────────
title "2/5" "Getting AtlasFile"
if [ -d "${INSTALL_DIR}/.git" ]; then
  CLONE_STATE="preexisting"
  run_step "updating existing install (${INSTALL_DIR})" \
    git -C "${INSTALL_DIR}" pull --ff-only origin "${BRANCH}"
else
  CLONE_STATE="created"
  run_step "cloning ${REPO_URL} (${BRANCH})" \
    git clone --depth 1 --branch "${BRANCH}" "${REPO_URL}" "${INSTALL_DIR}"
fi
cd "${INSTALL_DIR}"
AF_MANIFEST="${INSTALL_DIR}/${AF_MANIFEST_NAME}"
manifest_set "$AF_MANIFEST" repo_clone "$CLONE_STATE"
manifest_set "$AF_MANIFEST" install_dir "$INSTALL_DIR"

# ── 3. Configuration (.env) ─────────────────────────────────────────────────
title "3/5" "Configuring"
if [ -f .env ]; then manifest_set "$AF_MANIFEST" env_file preexisting; else manifest_set "$AF_MANIFEST" env_file created; fi
if [ ! -f .env ]; then
  cp .env.example .env
  # One OpenSearch password per install — the template ships a public
  # placeholder; keeping a known default would be a factory-leaked credential.
  # (Creation-time only: changing it after first boot would break auth.)
  os_rand="$( (LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom || true) | head -c 20)"
  [ -n "${os_rand}" ] || os_rand="$(openssl rand -hex 10 2>/dev/null || date +%s)"
  os_pass="Af!${os_rand}9"
  tmp_env="$(mktemp)"
  sed -e "s|^OPENSEARCH_PASSWORD=.*|OPENSEARCH_PASSWORD=${os_pass}|" \
      -e "s|^OPENSEARCH_INITIAL_ADMIN_PASSWORD=.*|OPENSEARCH_INITIAL_ADMIN_PASSWORD=${os_pass}|" \
      .env > "${tmp_env}" && mv "${tmp_env}" .env
  printf '  %s✔%s .env created (OpenSearch password generated for this install)\n' "$GREEN" "$RESET"
else
  info ".env already exists — preserved"
fi

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
    # Under `curl | bash` stdin is the script itself — the prompt must read the terminal
    printf '  %s?%s Folder where your projects/documents will live %s[%s]%s: ' "$ORANGE" "$RESET" "$DIM" "${PROJECTS_ROOT_DEFAULT}" "$RESET"
    answer=""
    if [ -r "$TTY_DEV" ]; then
      read -r answer < "$TTY_DEV" || answer=""
    else
      printf '(no interactive terminal — using the default)\n'
    fi
    PROJECTS_ROOT="${answer:-${PROJECTS_ROOT_DEFAULT}}"
  fi
fi
# Recorded BEFORE mkdir: only a folder this installer actually created may be
# removed later, and only while it is still empty.
if [ -d "${PROJECTS_ROOT}" ]; then
  manifest_set "$AF_MANIFEST" projects_root_created preexisting
else
  manifest_set "$AF_MANIFEST" projects_root_created created
fi
manifest_set "$AF_MANIFEST" projects_root "${PROJECTS_ROOT}"
mkdir -p "${PROJECTS_ROOT}"
if grep -q '^PROJECTS_HOST_ROOT=' .env; then
  tmp_env="$(mktemp)"
  sed "s|^PROJECTS_HOST_ROOT=.*|PROJECTS_HOST_ROOT=${PROJECTS_ROOT}|" .env > "${tmp_env}" && mv "${tmp_env}" .env
else
  printf '\nPROJECTS_HOST_ROOT=%s\n' "${PROJECTS_ROOT}" >> .env
fi
printf '  %s✔%s projects at: %s%s%s\n' "$GREEN" "$RESET" "$BOLD" "${PROJECTS_ROOT}" "$RESET"

# set_env VAR VALUE — replace or append in .env
set_env() {
  if grep -q "^$1=" .env; then
    tmp_env="$(mktemp)"
    sed "s|^$1=.*|$1=$2|" .env > "${tmp_env}" && mv "${tmp_env}" .env
  else
    printf '%s=%s\n' "$1" "$2" >> .env
  fi
}

# ── Dashboards session-cookie key (one per install) ─────────────────────────
# The default encryption key is identical across installs, so a session cookie
# from a previous instance decrypts fine but points to a session that does not
# exist — a 500 on a fresh install. A per-install key turns stale cookies into
# a clean login redirect. Generated only when missing or still the template
# placeholder (rotating an existing key just logs Dashboards users out).
cookie_current="$(grep '^DASHBOARDS_COOKIE_PASSWORD=' .env 2>/dev/null | head -1 | cut -d= -f2- || true)"
if [ -z "${cookie_current}" ] || [ "${cookie_current}" = "Troque-Esta-Senha-De-Cookie-Com-32-Ou-Mais-Chars" ]; then
  cookie_rand="$( (LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom || true) | head -c 48)"
  [ -n "${cookie_rand}" ] || cookie_rand="$(openssl rand -hex 24 2>/dev/null || printf 'Af%s%s0000000000000000' "$(date +%s)" "$$")"
  set_env DASHBOARDS_COOKIE_PASSWORD "${cookie_rand}"
  printf '  %s✔%s Dashboards cookie key generated for this install\n' "$GREEN" "$RESET"
fi

# ── API authentication (opt-in via --enable-auth) ───────────────────────────
# The key is baked into the image at build time (config/api_keys.json) and into
# .env for the MCP server (ATLASFILE_API_TOKEN). Re-running preserves the key.
if [ "${ENABLE_AUTH}" = "1" ]; then
  keys_file="config/api_keys.json"
  if [ -f "${keys_file}" ]; then
    API_KEY_VALUE="$(sed -n 's/.*"key"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "${keys_file}" | head -1)"
    [ -n "${API_KEY_VALUE}" ] && info "api_keys.json already exists — key preserved"
  fi
  if [ -z "${API_KEY_VALUE}" ]; then
    key_rand="$( (LC_ALL=C tr -dc 'a-z0-9' < /dev/urandom || true) | head -c 32)"
    [ -n "${key_rand}" ] || key_rand="$(openssl rand -hex 16 2>/dev/null || date +%s)"
    API_KEY_VALUE="atlas_sk_${key_rand}"
    printf '{\n  "keys": [\n    {"key": "%s", "name": "installer", "projects": ["*"]}\n  ]\n}\n' "${API_KEY_VALUE}" > "${keys_file}"
    manifest_set "$AF_MANIFEST" api_keys_file created
    printf '  %s✔%s api_keys.json created with a generated key\n' "$GREEN" "$RESET"
  fi
  set_env API_AUTH_ENABLED true
  set_env ATLASFILE_API_TOKEN "${API_KEY_VALUE}"
  printf '  %s✔%s API authentication enabled\n' "$GREEN" "$RESET"
fi

# ── 4. Build + launch ───────────────────────────────────────────────────────
title "4/5" "Building and starting the stack"
info "first run downloads images and compiles — a good moment for a coffee ☕"
run_step "building images (api, web, mcp)" docker compose build
run_step "starting the 5 services" docker compose up -d

run_step "waiting for the API to become healthy" wait_http http://localhost:8000/health 90
run_step "waiting for the interface" wait_http http://localhost:5173/ 30

maybe_setup_ollama

# ── 5. Done ─────────────────────────────────────────────────────────────────
TOTAL_SECS=$(( $(step_now) - START_TS ))
TOTAL=$(fmt_secs "$TOTAL_SECS")
title "5/5" "Install finished in ${TOTAL} 🎉"
bar_clear
printf '%s\n' "$GUT"
# Placar: o que de fato aconteceu, em números. A frase fixa de antes dizia a
# mesma coisa numa instalação limpa e numa reexecução que não mudou nada.
printf '%s%s✔ %s steps%s   %s✔ %s prerequisites%s   %sin %s%s\n%s\n' \
  "$GUT" "$GREEN" "$STEPS_DONE" "$RESET" "$GREEN" "$CHECKS_OK" "$RESET" "$DIM" "$TOTAL" "$RESET" "$GUT"
# box_row LABEL VALUE — padded to the fixed inner width; long values get a
# leading ellipsis keeping the tail (the folder name is what matters)
box_row() {
  local label="$1" value="$2"
  if [ ${#value} -gt 43 ]; then value="…${value:$((${#value} - 42))}"; fi
  printf '%s%s│%s  %s%-11s%s %-43s%s│%s\n' "$GUT" "$ORANGE" "$RESET" "$BOLD" "$label" "$RESET" "$value" "$ORANGE" "$RESET"
}
printf '%s%s╭─────────────────────────────────────────────────────────╮%s\n' "$GUT" "$ORANGE" "$RESET"
box_row "Interface" "http://localhost:5173"
box_row "API" "http://localhost:8000/health"
box_row "Dashboards" "http://localhost:5601"
box_row "Projects" "${PROJECTS_ROOT}"
printf '%s%s╰─────────────────────────────────────────────────────────╯%s\n%s\n' "$GUT" "$ORANGE" "$RESET" "$GUT"
os_pass_now="$(grep '^OPENSEARCH_PASSWORD=' .env 2>/dev/null | head -1 | cut -d= -f2- || true)"
if [ -n "${os_pass_now}" ]; then
  printf '%s%s📊 OpenSearch Dashboards%s (operations dashboard "AtlasFile — Operação"):\n' "$GUT" "$BOLD" "$RESET"
  printf '%s   login %sadmin%s · password %s%s%s\n%s\n' "$GUT" "$BOLD" "$RESET" "$ORANGE" "${os_pass_now}" "$RESET" "$GUT"
fi
if [ "${ENABLE_AUTH}" = "1" ] && [ -n "${API_KEY_VALUE}" ]; then
  printf '%s%s🔑 API key%s (paste it in Settings → Access, in each browser):\n' "$GUT" "$BOLD" "$RESET"
  printf '%s   %s%s%s\n%s\n' "$GUT" "$ORANGE" "${API_KEY_VALUE}" "$RESET" "$GUT"
fi

# ── Próximos passos: só os que se aplicam ───────────────────────────────────
# O mac-env monta esta lista a partir do que REALMENTE aconteceu (`result_ok
# docker` → "abra o Docker.app uma vez"). Antes eram sempre as mesmas três
# linhas, inclusive as que não valiam para aquela execução.
printf '%s%sNext steps%s\n' "$GUT" "$BOLD" "$RESET"
printf '%s  • the onboarding wizard opens by itself in the interface\n' "$GUT"
if [ "$(host_get docker_group)" = "created" ]; then
  printf '%s  • log out and back in: your docker group membership only applies to new sessions\n' "$GUT"
fi
if [ "${WITH_OLLAMA}" = "1" ]; then
  printf '%s  • assistant settings: type ollama/%s in the model box\n' "$GUT" "${OLLAMA_MODEL}"
fi
if [ "$OS_KIND" = "mac" ] && [ "$(host_get docker)" = "created" ]; then
  printf '%s  • Docker Desktop was installed now — keep it open for the stack to run\n' "$GUT"
fi
printf '%s  • logs:  cd %s && docker compose logs -f\n' "$GUT" "${INSTALL_DIR}"
printf '%s  • stop:  cd %s && docker compose down\n' "$GUT" "${INSTALL_DIR}"
printf '%s\n' "$GUT"

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
  info "run report: ${f}"
  return 0
}
write_run_log
printf '\n'

if [ "${OPEN_BROWSER}" = "1" ]; then
  if command -v open >/dev/null 2>&1; then open http://localhost:5173 || true
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open http://localhost:5173 || true
  fi
fi

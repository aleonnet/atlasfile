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
LOG_FILE="${TMPDIR:-/tmp}/atlasfile-install-$(date +%s).log"
START_TS=$(date +%s)
TTY_DEV="${TTY_DEV:-/dev/tty}"

while [ $# -gt 0 ]; do
  case "$1" in
    --repo-url) REPO_URL="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --dir) INSTALL_DIR="$2"; shift 2 ;;
    --projects-root) PROJECTS_ROOT="$2"; shift 2 ;;
    --yes) ASSUME_YES=1; shift ;;
    --install-deps) INSTALL_DEPS=1; shift ;;
    --with-ollama) WITH_OLLAMA=1; shift ;;
    --ollama-model) OLLAMA_MODEL="$2"; shift 2 ;;
    --bootstrap-only) BOOTSTRAP_ONLY=1; shift ;;  # hidden: prereqs only, then exit (CI/support)
    --no-open) OPEN_BROWSER=0; shift ;;
    --enable-auth) ENABLE_AUTH=1; shift ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown flag: $1 (use --help)"; exit 1 ;;
  esac
done

# ── Palette and UI primitives ───────────────────────────────────────────────
if [ -t 1 ]; then
  ORANGE=$'\033[38;5;202m'; CORAL=$'\033[38;5;209m'; PURPLE=$'\033[38;5;177m'
  GREEN=$'\033[32m'; RED=$'\033[31m'; DIM=$'\033[2m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
  IS_TTY=1
else
  ORANGE=""; CORAL=""; PURPLE=""; GREEN=""; RED=""; DIM=""; BOLD=""; RESET=""
  IS_TTY=0
fi

step_now() { date +%s; }
fmt_secs() { local s=$1; if [ "$s" -ge 60 ]; then printf '%dm%02ds' $((s/60)) $((s%60)); else printf '%ds' "$s"; fi; }

fail_with_log() {
  printf '\r  %s✘%s %s\n' "$RED" "$RESET" "$1"
  if [ -s "$LOG_FILE" ]; then
    printf '%s── last log lines (%s) ──%s\n' "$DIM" "$LOG_FILE" "$RESET"
    tail -12 "$LOG_FILE" | sed 's/^/  /'
  fi
  exit 1
}

# run_step "message" cmd... — animated spinner while it runs; ✔ with timing at the end
run_step() {
  local msg="$1"; shift
  local t0; t0=$(step_now)
  if [ "$IS_TTY" = "1" ]; then
    "$@" >>"$LOG_FILE" 2>&1 &
    local pid=$!
    local frames='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏' i=0
    while kill -0 "$pid" 2>/dev/null; do
      i=$(( (i + 1) % 10 ))
      printf '\r  %s%s%s %s %s' "$ORANGE" "${frames:$i:1}" "$RESET" "$msg" "$DIM$(fmt_secs $(( $(step_now) - t0 )))$RESET "
      sleep 0.12
    done
    wait "$pid" || fail_with_log "$msg"
    printf '\r  %s✔%s %s %s(%s)%s          \n' "$GREEN" "$RESET" "$msg" "$DIM" "$(fmt_secs $(( $(step_now) - t0 )))" "$RESET"
  else
    printf '  · %s...\n' "$msg"
    "$@" >>"$LOG_FILE" 2>&1 || fail_with_log "$msg"
    printf '  ✔ %s (%s)\n' "$msg" "$(fmt_secs $(( $(step_now) - t0 )))"
  fi
}

check() {
  local msg="$1"; shift
  if "$@" >>"$LOG_FILE" 2>&1; then
    printf '  %s✔%s %s\n' "$GREEN" "$RESET" "$msg"
  else
    return 1
  fi
}

fail() { printf '  %s✘%s %s\n' "$RED" "$RESET" "$*"; exit 1; }
warn() { printf '  %s!%s %s\n' "$ORANGE" "$RESET" "$*"; }
info() { printf '  %s·%s %s\n' "$PURPLE" "$RESET" "$*"; }
title() { printf '\n%s%s[%s]%s %s%s%s\n' "$BOLD" "$ORANGE" "$1" "$RESET" "$BOLD" "$2" "$RESET"; }

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
  printf '  %s?%s %s %s[y/N]%s ' "$ORANGE" "$RESET" "$q" "$DIM" "$RESET"
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
    return 100
  fi
  if [ -x "${BREW_PREFIX}/bin/brew" ]; then
    eval "$("${BREW_PREFIX}/bin/brew" shellenv)"
    return 100
  fi
  run_step "installing Homebrew" env NONINTERACTIVE=1 /bin/bash -c \
    "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || return 1
  [ -x "${BREW_PREFIX}/bin/brew" ] && eval "$("${BREW_PREFIX}/bin/brew" shellenv)"
  return 0
}

ensure_git() {
  command -v git >/dev/null 2>&1 && return 100
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
  return 0
}

ensure_docker_mac() {
  # double check: app in /Applications OR either cask name (it changed over time)
  # DOCKER_APP_PATH is overridable for tests only
  if [ -d "${DOCKER_APP_PATH:-/Applications/Docker.app}" ] \
    || brew list --cask docker-desktop >/dev/null 2>&1 \
    || brew list --cask docker >/dev/null 2>&1; then
    return 100
  fi
  ensure_homebrew || return 1
  run_step "installing Docker Desktop (Homebrew cask)" brew install --cask docker-desktop || return 1
  return 0
}

ensure_docker_linux() {
  command -v docker >/dev/null 2>&1 && return 100
  ensure_sudo || return 1
  run_step "installing Docker Engine (get.docker.com official script)" \
    sh -c "curl -fsSL https://get.docker.com | sh" || return 1
  # non-fatal: containers/CI have no systemd; the daemon check below decides
  as_root systemctl enable --now docker >>"$LOG_FILE" 2>&1 \
    || info "could not start the daemon via systemd (no systemd here?)"
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
  if sudo -n docker info >/dev/null 2>&1 || { ensure_sudo && sudo docker info >/dev/null 2>&1; }; then
    docker() { sudo command docker "$@"; }
    sudo usermod -aG docker "$USER" 2>/dev/null || true
    info "added ${USER} to the docker group — takes effect on your next login"
    return 0
  fi
  return 1
}

ensure_ollama() {
  if command -v ollama >/dev/null 2>&1; then return 100; fi
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
  return 0
}

ollama_pull_model() {
  local model="$1"
  if ollama list 2>/dev/null | awk '{print $1}' | grep -qx "$model"; then
    printf '  %s✔%s model %s already pulled\n' "$GREEN" "$RESET" "$model"
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
  printf '  %s✔%s model %s ready\n' "$GREEN" "$RESET" "$model"
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
}

# ── Test-library guard: `ATLASFILE_INSTALL_LIB=1 source install.sh` stops here ─
if [ -n "${ATLASFILE_INSTALL_LIB:-}" ]; then
  return 0 2>/dev/null || exit 0
fi

# ── Banner: the orb (with a face) and the wordmark ──────────────────────────
printf '\n'
printf '%s        ▄▄▄▄▄%s        %s●%s\n' "$ORANGE" "$RESET" "$PURPLE" "$RESET"
printf '%s      ▄███████▄%s\n' "$ORANGE" "$RESET"
printf '%s     ▐██%s %s●%s %s●%s %s██▌%s   %s%sAtlasFile%s\n' "$CORAL" "$RESET" "$BOLD" "$RESET" "$BOLD" "$RESET" "$CORAL" "$RESET" "$BOLD" "$ORANGE" "$RESET"
printf '%s      ▀██%s ‿ %s██▀%s    %syour documents, alive%s\n' "$ORANGE" "$RESET" "$ORANGE" "$RESET" "$DIM" "$RESET"
printf '%s   ●%s    ▀▀▀▀▀\n' "$CORAL" "$RESET"

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
fi
check "git $(git --version 2>/dev/null | awk '{print $3}')" command -v git \
  || fail "git not found — install it from https://git-scm.com"
check "curl" command -v curl || fail "curl not found"

# Docker — offer to install when missing
if ! command -v docker >/dev/null 2>&1; then
  if confirm "Docker not found — install it now? (Docker Desktop on macOS / Docker Engine on Linux)"; then
    if [ "$OS_KIND" = "mac" ]; then
      ensure_docker_mac || fail "could not install Docker Desktop — install it manually: https://docs.docker.com/get-docker/"
    else
      ensure_docker_linux || fail "could not install Docker Engine — install it manually: https://docs.docker.com/get-docker/"
    fi
  else
    fail "Docker not found — install Docker Desktop: https://docs.docker.com/get-docker/ (or re-run with --install-deps)"
  fi
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
  fi
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
  run_step "updating existing install (${INSTALL_DIR})" \
    git -C "${INSTALL_DIR}" pull --ff-only origin "${BRANCH}"
else
  run_step "cloning ${REPO_URL} (${BRANCH})" \
    git clone --depth 1 --branch "${BRANCH}" "${REPO_URL}" "${INSTALL_DIR}"
fi
cd "${INSTALL_DIR}"

# ── 3. Configuration (.env) ─────────────────────────────────────────────────
title "3/5" "Configuring"
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

# ── Ollama (opt-in): after the stack is up so it never delays first screen ──
if [ "${WITH_OLLAMA}" = "0" ] && [ "$ASSUME_YES" = "0" ] && [ -r "$TTY_DEV" ] \
  && ! command -v ollama >/dev/null 2>&1; then
  printf '  %s?%s Also install Ollama for a 100%% local model (%s, several GB)? %s[y/N]%s ' \
    "$ORANGE" "$RESET" "${OLLAMA_MODEL}" "$DIM" "$RESET"
  ollama_answer=""
  read -r ollama_answer < "$TTY_DEV" || ollama_answer=""
  case "$ollama_answer" in y|Y|yes|YES|s|S) WITH_OLLAMA=1 ;; esac
fi
if [ "${WITH_OLLAMA}" = "1" ]; then
  ollama_rc=0; ensure_ollama || ollama_rc=$?
  if [ "$ollama_rc" = "100" ]; then
    printf '  %s✔%s ollama %s (already installed — the app updates itself)\n' \
      "$GREEN" "$RESET" "$(ollama --version 2>/dev/null | sed 's/ollama version is //' || true)"
  fi
  if [ "$ollama_rc" != "1" ]; then
    ollama_pull_model "${OLLAMA_MODEL}"
    info "in the assistant settings, type ollama/${OLLAMA_MODEL} in the model box to use it"
  else
    warn "Ollama setup failed — the stack is up; install manually later (https://ollama.com)"
  fi
fi

# ── 5. Done ─────────────────────────────────────────────────────────────────
TOTAL=$(fmt_secs $(( $(step_now) - START_TS )))
title "5/5" "Install finished in ${TOTAL} 🎉"
printf '\n'
printf '  %s╭─────────────────────────────────────────────────────────╮%s\n' "$ORANGE" "$RESET"
printf '  %s│%s  %sInterface%s   http://localhost:5173                      %s│%s\n' "$ORANGE" "$RESET" "$BOLD" "$RESET" "$ORANGE" "$RESET"
printf '  %s│%s  %sAPI%s         http://localhost:8000/health               %s│%s\n' "$ORANGE" "$RESET" "$BOLD" "$RESET" "$ORANGE" "$RESET"
printf '  %s│%s  %sProjects%s    %-40s %s│%s\n' "$ORANGE" "$RESET" "$BOLD" "$RESET" "$(printf '%.40s' "${PROJECTS_ROOT}")" "$ORANGE" "$RESET"
printf '  %s╰─────────────────────────────────────────────────────────╯%s\n' "$ORANGE" "$RESET"
printf '\n'
if [ "${ENABLE_AUTH}" = "1" ] && [ -n "${API_KEY_VALUE}" ]; then
  printf '  %s🔑 API key%s (paste it in Settings → Access, in each browser):\n' "$BOLD" "$RESET"
  printf '     %s%s%s\n' "$ORANGE" "${API_KEY_VALUE}" "$RESET"
  printf '\n'
fi
info "the onboarding wizard opens by itself in the interface"
info "logs:  cd ${INSTALL_DIR} && docker compose logs -f"
info "stop:  cd ${INSTALL_DIR} && docker compose down"
printf '\n'

if [ "${OPEN_BROWSER}" = "1" ]; then
  if command -v open >/dev/null 2>&1; then open http://localhost:5173 || true
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open http://localhost:5173 || true
  fi
fi

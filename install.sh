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
    printf '  %s✔%s model %s already pulled\n' "$GREEN" "$RESET" "$model"
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
UN_OTHER_ARTIFACTS=""
UN_PLAN_REMOVE=""; UN_PLAN_KEEP=""; UN_ACTIONS=""

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

un_add_remove() { UN_PLAN_REMOVE="${UN_PLAN_REMOVE}  • $1
"; }
un_add_keep()   { UN_PLAN_KEEP="${UN_PLAN_KEEP}  • $1
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
    if [ -n "$(git -C "$dir" status --porcelain -- . \
        ":(exclude).env" ":(exclude)${AF_MANIFEST_NAME}" 2>/dev/null || true)" ]; then
      UN_DIR_DIRTY=1
    fi
  fi

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
  if [ "$deps" != "1" ]; then
    un_add_keep "system dependencies (Docker, git, Ollama) — pass --remove-deps to revert the ones this installer created"
  else
    if [ -n "$UN_OTHER_ARTIFACTS" ]; then
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
  printf '\n  %s%sRemoval plan%s — %s\n\n' "$BOLD" "$ORANGE" "$RESET" "$UN_DIR"
  if [ -n "$UN_PLAN_REMOVE" ]; then
    printf '  %sWILL BE REMOVED%s\n%s\n' "$BOLD" "$RESET" "$UN_PLAN_REMOVE"
  else
    printf '  %snothing to remove%s\n\n' "$DIM" "$RESET"
  fi
  if [ -n "$UN_PLAN_KEEP" ]; then
    printf '  %sWILL BE PRESERVED%s\n%s\n' "$BOLD" "$RESET" "$UN_PLAN_KEEP"
  fi
  return 0
}

un_has_action() { printf '%s' "$UN_ACTIONS" | grep -qx "$1"; }

UN_FAILED=0
un_step() { # <label> <cmd...> — a failed step is reported, never fatal
  local label="$1"; shift
  if "$@" >>"$LOG_FILE" 2>&1; then
    printf '  %s✔%s %s\n' "$GREEN" "$RESET" "$label"
  else
    printf '  %s✘%s %s %s(details in %s)%s\n' "$RED" "$RESET" "$label" "$DIM" "$LOG_FILE" "$RESET"
    UN_FAILED=1
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
          printf '  %s✔%s removing Ollama (Homebrew cask)\n' "$GREEN" "$RESET"
        fi ;;
      ollama-rm:*)
        model="${act#ollama-rm:}"
        un_step "removing model ${model}" ollama rm "$model" ;;
      gpasswd-d)
        un_step "removing ${USER} from the docker group" as_root gpasswd -d "$USER" docker ;;
      rm-state)
        rm -f "$AF_HOST_MANIFEST" 2>/dev/null || true
        rmdir "$AF_STATE_DIR" 2>/dev/null || true
        printf '  %s✔%s installer bookkeeping removed\n' "$GREEN" "$RESET" ;;
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

  # The data volume never has a default: the user decides, every time.
  if [ -n "$UN_VOLUME" ] && [ -z "$PURGE_DATA" ]; then
    if [ "$ASSUME_YES" = "1" ] || [ ! -r "$TTY_DEV" ]; then
      fail "the volume ${UN_VOLUME} holds the search index — decide explicitly: --purge-data (erase it) or --keep-data (keep it)"
    fi
    printf '\n  %s?%s The volume %s%s%s holds the search index.\n' "$ORANGE" "$RESET" "$BOLD" "$UN_VOLUME" "$RESET"
    printf '    Your documents and the _ATLASFILE journal live on disk and are NOT affected;\n'
    printf '    the index is rebuilt by Reconcile after a reinstall.\n'
    printf '  %s?%s Erase the volume? %s[y/N]%s ' "$ORANGE" "$RESET" "$DIM" "$RESET"
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
    return 0
  fi
  if [ "$ASSUME_YES" != "1" ]; then
    if [ ! -r "$TTY_DEV" ]; then
      fail "no interactive terminal — re-run with --yes to confirm the plan above"
    fi
    printf '  %s?%s Execute the plan above? %s[y/N]%s ' "$ORANGE" "$RESET" "$DIM" "$RESET"
    local answer=""
    { read -r answer < "$TTY_DEV"; } 2>/dev/null || answer=""
    printf '\n'
    case "$answer" in y|Y|yes|YES|s|S) ;; *) info "uninstall cancelled — nothing was touched."; return 0 ;; esac
  fi

  un_execute
  printf '\n'
  if [ "$UN_FAILED" = "1" ]; then
    warn "uninstall finished with failures — see ${LOG_FILE}"
    return 1
  fi
  printf '  %s✔%s AtlasFile removed. What already existed on this machine was preserved.\n\n' "$GREEN" "$RESET"
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

print_banner

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
# box_row LABEL VALUE — padded to the fixed inner width; long values get a
# leading ellipsis keeping the tail (the folder name is what matters)
box_row() {
  local label="$1" value="$2"
  if [ ${#value} -gt 43 ]; then value="…${value:$((${#value} - 42))}"; fi
  printf '  %s│%s  %s%-11s%s %-43s%s│%s\n' "$ORANGE" "$RESET" "$BOLD" "$label" "$RESET" "$value" "$ORANGE" "$RESET"
}
printf '  %s╭─────────────────────────────────────────────────────────╮%s\n' "$ORANGE" "$RESET"
box_row "Interface" "http://localhost:5173"
box_row "API" "http://localhost:8000/health"
box_row "Dashboards" "http://localhost:5601"
box_row "Projects" "${PROJECTS_ROOT}"
printf '  %s╰─────────────────────────────────────────────────────────╯%s\n' "$ORANGE" "$RESET"
printf '\n'
os_pass_now="$(grep '^OPENSEARCH_PASSWORD=' .env 2>/dev/null | head -1 | cut -d= -f2- || true)"
if [ -n "${os_pass_now}" ]; then
  printf '  %s📊 OpenSearch Dashboards%s (operations dashboard "AtlasFile — Operação"):\n' "$BOLD" "$RESET"
  printf '     login %sadmin%s · password %s%s%s\n' "$BOLD" "$RESET" "$ORANGE" "${os_pass_now}" "$RESET"
  printf '\n'
fi
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

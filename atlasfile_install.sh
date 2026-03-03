#!/bin/bash
set -euo pipefail

# AtlasFile Installer (macOS + Linux)
# "Bells and whistles": colored UI, optional gum UI, OS checks,
# Docker checks/bootstrap, compose validation, project bootstrap, health checks.

BOLD='\033[1m'
ACCENT='\033[38;2;0;190;230m'
INFO='\033[38;2;136;146;176m'
SUCCESS='\033[38;2;0;229;204m'
WARN='\033[38;2;255;176;32m'
ERROR='\033[38;2;230;57;70m'
MUTED='\033[38;2;90;100;128m'
NC='\033[0m'

ORIGINAL_PATH="${PATH:-}"
TMPFILES=()

cleanup_tmpfiles() {
  local f
  for f in "${TMPFILES[@]:-}"; do
    rm -rf "$f" 2>/dev/null || true
  done
}
trap cleanup_tmpfiles EXIT

mktempfile() {
  local f
  f="$(mktemp)"
  TMPFILES+=("$f")
  echo "$f"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.yml"

DOWNLOADER=""
detect_downloader() {
  if command -v curl >/dev/null 2>&1; then
    DOWNLOADER="curl"
    return 0
  fi
  if command -v wget >/dev/null 2>&1; then
    DOWNLOADER="wget"
    return 0
  fi
  ui_error "Missing downloader (curl or wget required)"
  return 1
}

download_file() {
  local url="$1"
  local output="$2"
  if [[ -z "$DOWNLOADER" ]]; then
    detect_downloader
  fi
  if [[ "$DOWNLOADER" == "curl" ]]; then
    curl -fsSL --proto '=https' --tlsv1.2 --retry 3 --retry-delay 1 --retry-connrefused -o "$output" "$url"
  else
    wget -q --https-only --secure-protocol=TLSv1_2 --tries=3 --timeout=20 -O "$output" "$url"
  fi
}

GUM_VERSION="${ATLASFILE_GUM_VERSION:-0.17.0}"
GUM=""

gum_is_tty() {
  [[ -n "${NO_COLOR:-}" ]] && return 1
  [[ "${TERM:-dumb}" == "dumb" ]] && return 1
  ([[ -t 1 ]] || [[ -t 2 ]]) && return 0
  [[ -r /dev/tty && -w /dev/tty ]]
}

gum_detect_os() {
  case "$(uname -s 2>/dev/null || true)" in
    Darwin) echo "Darwin" ;;
    Linux) echo "Linux" ;;
    *) echo "unsupported" ;;
  esac
}

gum_detect_arch() {
  case "$(uname -m 2>/dev/null || true)" in
    x86_64|amd64) echo "x86_64" ;;
    arm64|aarch64) echo "arm64" ;;
    i386|i686) echo "i386" ;;
    armv7l|armv7) echo "armv7" ;;
    armv6l|armv6) echo "armv6" ;;
    *) echo "unknown" ;;
  esac
}

bootstrap_gum_temp() {
  [[ "${ATLASFILE_USE_GUM:-auto}" =~ ^(0|false|FALSE|off|OFF|no|NO)$ ]] && return 1
  gum_is_tty || return 1

  if command -v gum >/dev/null 2>&1; then
    GUM="gum"
    return 0
  fi

  command -v tar >/dev/null 2>&1 || return 1
  local os arch asset base tmpdir gum_path
  os="$(gum_detect_os)"
  arch="$(gum_detect_arch)"
  [[ "$os" == "unsupported" || "$arch" == "unknown" ]] && return 1

  asset="gum_${GUM_VERSION}_${os}_${arch}.tar.gz"
  base="https://github.com/charmbracelet/gum/releases/download/v${GUM_VERSION}"
  tmpdir="$(mktemp -d)"
  TMPFILES+=("$tmpdir")

  download_file "${base}/${asset}" "$tmpdir/$asset" || return 1
  tar -xzf "$tmpdir/$asset" -C "$tmpdir" >/dev/null 2>&1 || return 1
  gum_path="$(find "$tmpdir" -type f -name gum 2>/dev/null | head -n1 || true)"
  [[ -z "$gum_path" ]] && return 1

  chmod +x "$gum_path" >/dev/null 2>&1 || true
  [[ ! -x "$gum_path" ]] && return 1
  GUM="$gum_path"
}

ui_info() {
  local msg="$*"
  if [[ -n "$GUM" ]]; then "$GUM" log --level info "$msg"; else echo -e "${MUTED}·${NC} ${msg}"; fi
}
ui_warn() {
  local msg="$*"
  if [[ -n "$GUM" ]]; then "$GUM" log --level warn "$msg"; else echo -e "${WARN}!${NC} ${msg}"; fi
}
ui_success() {
  local msg="$*"
  if [[ -n "$GUM" ]]; then
    local mark; mark="$("$GUM" style --foreground "#00e5cc" --bold "✓")"
    echo "${mark} ${msg}"
  else
    echo -e "${SUCCESS}✓${NC} ${msg}"
  fi
}
ui_error() {
  local msg="$*"
  if [[ -n "$GUM" ]]; then "$GUM" log --level error "$msg"; else echo -e "${ERROR}✗${NC} ${msg}"; fi
}
ui_section() {
  local title="$1"
  if [[ -n "$GUM" ]]; then "$GUM" style --bold --foreground "#00bee6" --padding "1 0" "$title"
  else echo -e "\n${ACCENT}${BOLD}${title}${NC}"; fi
}
ui_kv() {
  local k="$1" v="$2"
  if [[ -n "$GUM" ]]; then
    local kp vp
    kp="$("$GUM" style --foreground "#5a6480" --width 24 "$k")"
    vp="$("$GUM" style --bold "$v")"
    "$GUM" join --horizontal "$kp" "$vp"
  else
    echo -e "${MUTED}${k}:${NC} ${v}"
  fi
}

run_with_spinner() {
  local title="$1"; shift
  if [[ -n "$GUM" ]] && gum_is_tty; then
    "$GUM" spin --spinner dot --title "$title" -- "$@"
  else
    "$@"
  fi
}

OS="unknown"
NO_PROMPT="${ATLASFILE_NO_PROMPT:-0}"
DRY_RUN="${ATLASFILE_DRY_RUN:-0}"
VERBOSE="${ATLASFILE_VERBOSE:-0}"
PROJECTS_HOST_ROOT="${ATLASFILE_PROJECTS_HOST_ROOT:-${PROJECTS_HOST_ROOT:-$HOME/Documents/Projects}}"
PROJECT_NAME="${ATLASFILE_PROJECT_NAME:-kaido_teste}"
PROJECT_ID="${ATLASFILE_PROJECT_ID:-kaido_teste}"
AUTO_CREATE_PROJECT="${ATLASFILE_AUTO_CREATE_PROJECT:-1}"

print_usage() {
  cat <<EOF
AtlasFile installer (macOS + Linux)

Usage:
  bash ./atlasfile_install.sh [options]

Options:
  --projects-root <path>      Host projects root to mount in /projects
  --project-name <name>       Project folder bootstrap name (default: kaido_teste)
  --project-id <id>           Project id in _PROJECT_PROFILE.md (default: kaido_teste)
  --no-create-project         Skip bootstrap_project call
  --dry-run                   Print planned actions only
  --verbose                   Verbose output
  --gum                       Force gum UI (if possible)
  --no-gum                    Disable gum UI
  --no-prompt                 Non-interactive mode
  --help, -h                  Show this help
EOF
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --projects-root) PROJECTS_HOST_ROOT="$2"; shift 2 ;;
      --project-name) PROJECT_NAME="$2"; shift 2 ;;
      --project-id) PROJECT_ID="$2"; shift 2 ;;
      --no-create-project) AUTO_CREATE_PROJECT=0; shift ;;
      --dry-run) DRY_RUN=1; shift ;;
      --verbose) VERBOSE=1; shift ;;
      --gum) export ATLASFILE_USE_GUM=1; shift ;;
      --no-gum) export ATLASFILE_USE_GUM=0; shift ;;
      --no-prompt) NO_PROMPT=1; shift ;;
      --help|-h) print_usage; exit 0 ;;
      *) ui_warn "Ignoring unknown option: $1"; shift ;;
    esac
  done
}

detect_os_or_die() {
  if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
  elif [[ "$OSTYPE" == "linux-gnu"* ]] || [[ -n "${WSL_DISTRO_NAME:-}" ]]; then
    OS="linux"
  else
    OS="unknown"
  fi
  if [[ "$OS" == "unknown" ]]; then
    ui_error "Unsupported OS for this script"
    echo "Use Docker Desktop on Windows and run from WSL/Git Bash."
    exit 1
  fi
  ui_success "Detected OS: $OS"
}

is_root() { [[ "$(id -u)" -eq 0 ]]; }

require_sudo_linux() {
  if [[ "$OS" != "linux" ]] || is_root; then return 0; fi
  if ! command -v sudo >/dev/null 2>&1; then
    ui_error "sudo required on Linux to install Docker"
    exit 1
  fi
  sudo -v
}

check_docker_cli() {
  command -v docker >/dev/null 2>&1
}

check_compose_cli() {
  docker compose version >/dev/null 2>&1
}

install_docker_if_missing() {
  if check_docker_cli && check_compose_cli; then
    ui_success "Docker CLI + Compose available"
    return 0
  fi

  ui_warn "Docker not fully available"
  if [[ "$NO_PROMPT" == "1" ]]; then
    ui_error "Non-interactive mode: cannot continue without Docker"
    exit 1
  fi

  if [[ "$OS" == "macos" ]]; then
    if ! command -v brew >/dev/null 2>&1; then
      ui_error "Homebrew not found. Install Docker Desktop manually:"
      echo "  https://www.docker.com/products/docker-desktop/"
      exit 1
    fi
    run_with_spinner "Installing Docker Desktop (brew cask)" brew install --cask docker
  else
    require_sudo_linux
    local tmp
    tmp="$(mktempfile)"
    download_file "https://get.docker.com" "$tmp"
    run_with_spinner "Installing Docker Engine" sudo sh "$tmp"
  fi
}

ensure_docker_running() {
  if docker info >/dev/null 2>&1; then
    ui_success "Docker daemon is running"
    return 0
  fi

  if [[ "$OS" == "macos" ]]; then
    ui_warn "Docker daemon not running. Trying to start Docker Desktop."
    open -a Docker >/dev/null 2>&1 || true
    for _ in $(seq 1 60); do
      if docker info >/dev/null 2>&1; then
        ui_success "Docker daemon is running"
        return 0
      fi
      sleep 2
    done
  fi

  ui_error "Docker daemon not running"
  echo "Start Docker Desktop and retry."
  exit 1
}

ensure_prereqs() {
  [[ -f "$COMPOSE_FILE" ]] || { ui_error "docker-compose.yml not found in ${SCRIPT_DIR}"; exit 1; }
  [[ -f "${SCRIPT_DIR}/scripts/bootstrap_project.py" ]] || { ui_error "scripts/bootstrap_project.py not found"; exit 1; }
}

show_plan() {
  ui_section "Install plan"
  ui_kv "Script dir" "$SCRIPT_DIR"
  ui_kv "OS" "$OS"
  ui_kv "Projects root" "$PROJECTS_HOST_ROOT"
  ui_kv "Project name" "$PROJECT_NAME"
  ui_kv "Project id" "$PROJECT_ID"
  ui_kv "Create project" "$AUTO_CREATE_PROJECT"
  ui_kv "Dry run" "$DRY_RUN"
}

run_compose_up() {
  export PROJECTS_HOST_ROOT
  run_with_spinner "Validating docker compose" docker compose -f "$COMPOSE_FILE" config >/dev/null
  run_with_spinner "Starting AtlasFile stack" docker compose -f "$COMPOSE_FILE" up -d --build
}

bootstrap_project_if_enabled() {
  if [[ "$AUTO_CREATE_PROJECT" != "1" ]]; then
    ui_info "Skipping project bootstrap"
    return
  fi
  run_with_spinner "Bootstrapping project ${PROJECT_NAME}" \
    python3 "${SCRIPT_DIR}/scripts/bootstrap_project.py" \
    --name "$PROJECT_NAME" \
    --id "$PROJECT_ID" \
    --projects-root "$PROJECTS_HOST_ROOT"
}

health_check() {
  ui_section "Health checks"

  docker compose -f "$COMPOSE_FILE" ps
  echo ""

  local ok=1
  if curl -fsS "http://localhost:8000/health" >/dev/null 2>&1; then
    ui_success "Backend OK: http://localhost:8000/health"
  else
    ui_error "Backend health failed"
    ok=0
  fi

  if curl -k -fsS -u "admin:${OPENSEARCH_INITIAL_ADMIN_PASSWORD:-Kaid0Search!2026X}" "https://localhost:9200" >/dev/null 2>&1; then
    ui_success "OpenSearch OK: https://localhost:9200"
  else
    ui_error "OpenSearch health failed"
    ok=0
  fi

  if curl -fsS "http://localhost:5173" >/dev/null 2>&1; then
    ui_success "Frontend OK: http://localhost:5173"
  else
    ui_error "Frontend health failed"
    ok=0
  fi

  if [[ "$ok" -ne 1 ]]; then
    ui_warn "Some health checks failed. Useful logs:"
    echo "  docker compose -f \"$COMPOSE_FILE\" logs --tail=200"
    exit 1
  fi
}

print_footer() {
  ui_section "Done"
  echo -e "${SUCCESS}${BOLD}AtlasFile is up and running.${NC}"
  echo ""
  echo "URLs:"
  echo "  - Frontend:   http://localhost:5173"
  echo "  - Backend:    http://localhost:8000"
  echo "  - OpenSearch: https://localhost:9200"
  echo "  - Dashboards: http://localhost:5601"
  echo ""
  echo "Project bootstrap:"
  echo "  - ${PROJECTS_HOST_ROOT}/${PROJECT_NAME}"
  echo "  - Drop files into: ${PROJECTS_HOST_ROOT}/${PROJECT_NAME}/_INBOX_DROP"
  echo ""
  echo "If you opened a new shell and docker commands disappear, reload PATH."
}

main() {
  parse_args "$@"
  bootstrap_gum_temp || true
  ui_section "AtlasFile Installer"
  detect_os_or_die
  ensure_prereqs
  detect_downloader
  install_docker_if_missing
  ensure_docker_running
  show_plan

  if [[ "$DRY_RUN" == "1" ]]; then
    ui_success "Dry run complete (no changes made)"
    exit 0
  fi

  bootstrap_project_if_enabled
  run_compose_up
  health_check
  print_footer
}

main "$@"

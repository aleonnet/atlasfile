#!/usr/bin/env bash
# AtlasFile — instalador one-liner (macOS/Linux)
#
#   curl -fsSL https://raw.githubusercontent.com/aleonnet/atlasfile/main/install.sh | bash
#
# Requisitos de host: Docker (com Compose v2), git, curl. Nada de make/node/python.
# Idempotente: re-executar atualiza o clone e religa a stack.
#
# Flags:
#   --repo-url URL        (default: https://github.com/aleonnet/atlasfile.git; env ATLASFILE_REPO_URL)
#   --branch NAME         (default: main)
#   --dir PATH            (default: ~/AtlasFile)
#   --projects-root PATH  (default: ~/Documents/AtlasFileProjects)
#   --yes                 não-interativo (aceita defaults)
#   --no-open             não abre o browser ao final
set -euo pipefail

REPO_URL="${ATLASFILE_REPO_URL:-https://github.com/aleonnet/atlasfile.git}"
BRANCH="main"
INSTALL_DIR="${HOME}/AtlasFile"
PROJECTS_ROOT_DEFAULT="${HOME}/Documents/AtlasFileProjects"
PROJECTS_ROOT=""
ASSUME_YES=0
OPEN_BROWSER=1
LOG_FILE="${TMPDIR:-/tmp}/atlasfile-install-$(date +%s).log"
START_TS=$(date +%s)

while [ $# -gt 0 ]; do
  case "$1" in
    --repo-url) REPO_URL="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --dir) INSTALL_DIR="$2"; shift 2 ;;
    --projects-root) PROJECTS_ROOT="$2"; shift 2 ;;
    --yes) ASSUME_YES=1; shift ;;
    --no-open) OPEN_BROWSER=0; shift ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Flag desconhecida: $1 (use --help)"; exit 1 ;;
  esac
done

# ── Paleta e primitivas de UI ───────────────────────────────────────────────
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
    printf '%s── últimas linhas do log (%s) ──%s\n' "$DIM" "$LOG_FILE" "$RESET"
    tail -12 "$LOG_FILE" | sed 's/^/  /'
  fi
  exit 1
}

# run_step "mensagem" cmd... — spinner animado enquanto roda; ✔ com tempo ao fim
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
info() { printf '  %s·%s %s\n' "$PURPLE" "$RESET" "$*"; }
title() { printf '\n%s%s[%s]%s %s%s%s\n' "$BOLD" "$ORANGE" "$1" "$RESET" "$BOLD" "$2" "$RESET"; }

# ── Banner: o orb e o wordmark ──────────────────────────────────────────────
printf '\n'
printf '%s        ▄▄▄▄▄%s        %s●%s\n' "$ORANGE" "$RESET" "$PURPLE" "$RESET"
printf '%s      ▄███████▄%s\n' "$ORANGE" "$RESET"
printf '%s     ▐█████████▌%s   %s%sAtlasFile%s\n' "$CORAL" "$RESET" "$BOLD" "$ORANGE" "$RESET"
printf '%s      ▀███████▀%s    %sseus documentos, vivos%s\n' "$ORANGE" "$RESET" "$DIM" "$RESET"
printf '%s   ●%s    ▀▀▀▀▀\n' "$CORAL" "$RESET"

# ── 1. Pré-requisitos ───────────────────────────────────────────────────────
title "1/5" "Verificando pré-requisitos"
check "git $(git --version 2>/dev/null | awk '{print $3}')" command -v git \
  || fail "git não encontrado — instale em https://git-scm.com"
check "curl" command -v curl || fail "curl não encontrado"
command -v docker >/dev/null 2>&1 \
  || fail "Docker não encontrado — instale o Docker Desktop: https://docs.docker.com/get-docker/"
check "docker $(docker --version 2>/dev/null | sed 's/Docker version //;s/,.*//') (daemon ativo)" docker info \
  || fail "Docker instalado mas o daemon não está rodando — abra o Docker Desktop e tente de novo"
check "docker compose $(docker compose version --short 2>/dev/null || echo v2)" docker compose version \
  || fail "Docker Compose v2 não encontrado — atualize o Docker Desktop"

for port in 5173 8000 9200; do
  if command -v lsof >/dev/null 2>&1 && lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    if docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null | grep -q "atlasfile.*:${port}"; then
      info "porta ${port} em uso pelo próprio AtlasFile (será atualizado)"
    else
      fail "porta ${port} já está em uso por outro processo — libere-a antes de instalar"
    fi
  fi
done

# ── 2. Código ───────────────────────────────────────────────────────────────
title "2/5" "Obtendo o AtlasFile"
if [ -d "${INSTALL_DIR}/.git" ]; then
  run_step "atualizando instalação existente (${INSTALL_DIR})" \
    git -C "${INSTALL_DIR}" pull --ff-only origin "${BRANCH}"
else
  run_step "clonando ${REPO_URL} (${BRANCH})" \
    git clone --depth 1 --branch "${BRANCH}" "${REPO_URL}" "${INSTALL_DIR}"
fi
cd "${INSTALL_DIR}"

# ── 3. Configuração (.env) ──────────────────────────────────────────────────
title "3/5" "Configurando"
if [ ! -f .env ]; then
  cp .env.example .env
  printf '  %s✔%s .env criado a partir do template\n' "$GREEN" "$RESET"
else
  info ".env já existe — preservado"
fi

current_root="$(grep '^PROJECTS_HOST_ROOT=' .env | head -1 | cut -d= -f2- || true)"
if [ -z "${PROJECTS_ROOT}" ]; then
  if [ -n "${current_root}" ] && [ "${current_root}" != "/path/to/Projects" ]; then
    PROJECTS_ROOT="${current_root}"
  elif [ "${ASSUME_YES}" = "1" ]; then
    PROJECTS_ROOT="${PROJECTS_ROOT_DEFAULT}"
  else
    # Via `curl | bash` o stdin é o próprio script — o prompt precisa ler do terminal
    printf '  %s?%s Pasta onde seus projetos/documentos vão morar %s[%s]%s: ' "$ORANGE" "$RESET" "$DIM" "${PROJECTS_ROOT_DEFAULT}" "$RESET"
    answer=""
    if [ -r /dev/tty ]; then
      read -r answer < /dev/tty || answer=""
    else
      printf '(sem terminal interativo — usando o default)\n'
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
printf '  %s✔%s projetos em: %s%s%s\n' "$GREEN" "$RESET" "$BOLD" "${PROJECTS_ROOT}" "$RESET"

# ── 4. Build + subida ───────────────────────────────────────────────────────
title "4/5" "Construindo e subindo a stack"
info "primeira vez baixa imagens e compila — bom momento para um café ☕"
run_step "construindo imagens (api, web, mcp)" docker compose build
run_step "subindo os 5 serviços" docker compose up -d

wait_http() {
  local url="$1" tries="$2"
  for _ in $(seq 1 "$tries"); do
    curl -fsS "$url" >/dev/null 2>&1 && return 0
    sleep 2
  done
  return 1
}
run_step "aguardando a API ficar saudável" wait_http http://localhost:8000/health 90
run_step "aguardando a interface" wait_http http://localhost:5173/ 30

# ── 5. Pronto ───────────────────────────────────────────────────────────────
TOTAL=$(fmt_secs $(( $(step_now) - START_TS )))
title "5/5" "Instalação concluída em ${TOTAL} 🎉"
printf '\n'
printf '  %s╭─────────────────────────────────────────────────────────╮%s\n' "$ORANGE" "$RESET"
printf '  %s│%s  %sInterface%s   http://localhost:5173                      %s│%s\n' "$ORANGE" "$RESET" "$BOLD" "$RESET" "$ORANGE" "$RESET"
printf '  %s│%s  %sAPI%s         http://localhost:8000/health               %s│%s\n' "$ORANGE" "$RESET" "$BOLD" "$RESET" "$ORANGE" "$RESET"
printf '  %s│%s  %sProjetos%s    %-40s %s│%s\n' "$ORANGE" "$RESET" "$BOLD" "$RESET" "$(printf '%.40s' "${PROJECTS_ROOT}")" "$ORANGE" "$RESET"
printf '  %s╰─────────────────────────────────────────────────────────╯%s\n' "$ORANGE" "$RESET"
printf '\n'
info "o assistente de primeiros passos abre sozinho na interface"
info "logs:  cd ${INSTALL_DIR} && docker compose logs -f"
info "parar: cd ${INSTALL_DIR} && docker compose down"
printf '\n'

if [ "${OPEN_BROWSER}" = "1" ]; then
  if command -v open >/dev/null 2>&1; then open http://localhost:5173 || true
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open http://localhost:5173 || true
  fi
fi

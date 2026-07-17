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

bold()  { printf '\033[1m%s\033[0m\n' "$*"; }
ok()    { printf '  \033[32m✔\033[0m %s\n' "$*"; }
fail()  { printf '  \033[31m✘\033[0m %s\n' "$*"; exit 1; }
info()  { printf '  \033[36m·\033[0m %s\n' "$*"; }

bold ""
bold "  AtlasFile — gestão documental inteligente"
bold "  ─────────────────────────────────────────"

# ── 1. Pré-requisitos ────────────────────────────────────────────────────────
bold ""
bold "[1/5] Verificando pré-requisitos"
command -v git >/dev/null 2>&1 || fail "git não encontrado — instale em https://git-scm.com"
ok "git $(git --version | awk '{print $3}')"
command -v curl >/dev/null 2>&1 || fail "curl não encontrado"
ok "curl"
command -v docker >/dev/null 2>&1 || fail "Docker não encontrado — instale o Docker Desktop: https://docs.docker.com/get-docker/"
docker info >/dev/null 2>&1 || fail "Docker instalado mas o daemon não está rodando — abra o Docker Desktop e tente de novo"
ok "docker $(docker --version | sed 's/Docker version //;s/,.*//')"
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 não encontrado (docker compose) — atualize o Docker Desktop"
ok "docker compose $(docker compose version --short 2>/dev/null || echo v2)"

for port in 5173 8000 9200; do
  if command -v lsof >/dev/null 2>&1 && lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    if docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null | grep -q "atlasfile.*:${port}"; then
      info "porta ${port} em uso pelo próprio AtlasFile (ok, será atualizado)"
    else
      fail "porta ${port} já está em uso por outro processo — libere-a antes de instalar"
    fi
  fi
done

# ── 2. Código ────────────────────────────────────────────────────────────────
bold ""
bold "[2/5] Obtendo o AtlasFile"
if [ -d "${INSTALL_DIR}/.git" ]; then
  info "instalação existente em ${INSTALL_DIR} — atualizando"
  git -C "${INSTALL_DIR}" pull --ff-only origin "${BRANCH}" >/dev/null
  ok "atualizado (branch ${BRANCH})"
else
  git clone --depth 1 --branch "${BRANCH}" "${REPO_URL}" "${INSTALL_DIR}" >/dev/null 2>&1 \
    || fail "clone falhou: ${REPO_URL}"
  ok "clonado em ${INSTALL_DIR}"
fi
cd "${INSTALL_DIR}"

# ── 3. Configuração (.env) ──────────────────────────────────────────────────
bold ""
bold "[3/5] Configurando"
if [ ! -f .env ]; then
  cp .env.example .env
  ok ".env criado a partir do template"
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
    printf '  Pasta onde seus projetos/documentos vão morar [%s]: ' "${PROJECTS_ROOT_DEFAULT}"
    read -r answer || true
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
ok "projetos em: ${PROJECTS_ROOT}"

# ── 4. Subir a stack ────────────────────────────────────────────────────────
bold ""
bold "[4/5] Construindo e subindo a stack (primeira vez pode levar alguns minutos)"
docker compose up -d --build

printf '  aguardando API'
healthy=0
for _ in $(seq 1 90); do
  if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then healthy=1; break; fi
  printf '.'
  sleep 2
done
printf '\n'
[ "${healthy}" = "1" ] || fail "API não respondeu em 180s — veja os logs: docker compose logs api"
ok "API saudável em http://localhost:8000"

for _ in $(seq 1 30); do
  curl -fsS http://localhost:5173/ >/dev/null 2>&1 && break
  sleep 1
done
ok "Interface em http://localhost:5173"

# ── 5. Pronto ───────────────────────────────────────────────────────────────
bold ""
bold "[5/5] Instalação concluída 🎉"
info "Interface:   http://localhost:5173  (o assistente de primeiros passos abre sozinho)"
info "API:         http://localhost:8000/health"
info "Logs:        cd ${INSTALL_DIR} && docker compose logs -f"
info "Parar:       cd ${INSTALL_DIR} && docker compose down"
info "Guia:        ${INSTALL_DIR}/INSTALL.md"
bold ""

if [ "${OPEN_BROWSER}" = "1" ]; then
  if command -v open >/dev/null 2>&1; then open http://localhost:5173 || true
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open http://localhost:5173 || true
  fi
fi

#!/bin/bash
###############################################################################
# Script de Backup Versionado - AtlasFile
#
# Gera backup tar.gz do repositório AtlasFile excluindo arquivos/pastas
# regeneráveis. Versão lida de frontend/package.json; data no formato YYYYMMDD.
# Baseado em backup-data-manager-and-scraper.sh.
#
# --- Uso ---
#   ./backup-atlasfile.sh [--extra_excludes PATTERN [PATTERN ...]]
#
# Saída: BASE_DIR/AtlasFile_v<versão>_YYYYMMDD.tar.gz
#
# --- Excludes ---
#   Sempre são aplicados os DEFAULT_EXCLUDES. Excludes adicionais: use a opção
#   --extra_excludes seguida de um ou mais padrões. O tar usa defaults + esses.
#
#   Exemplos:
#     ./backup-atlasfile.sh
#     ./backup-atlasfile.sh --extra_excludes "AtlasFile/outro" "AtlasFile/**/*.log"
#
#   Padrões com prefixo AtlasFile/ (como nos DEFAULT_EXCLUDES).
###############################################################################

set -euo pipefail

# Caminho absoluto do script (para --help após cd)
SCRIPT_PATH=""
SCRIPT_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  SCRIPT_PATH="${SCRIPT_DIR}/$(basename "${BASH_SOURCE[0]}")"
fi

# Cores para output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Data no formato YYYYMMDD (padrão do arquivo de referência)
DATE=$(date +%Y%m%d)

# Diretório do projeto derivado da localização do script; backups gravados no pai
# do repositório para não ficarem dentro do repo.
PROJECT_ROOT="${SCRIPT_DIR:-$(pwd)}"
BASE_DIR="$(cd "${PROJECT_ROOT}/.." && pwd)"
PROJECT_DIR="$(basename "${PROJECT_ROOT}")"
cd "$BASE_DIR"

# Excludes padrão: pastas/arquivos regeneráveis ou que não fazem sentido no backup
# (vide backup-projects.sh). São sempre aplicados; extras podem ser passados ao chamar backup_project.
DEFAULT_EXCLUDES=(
  "${PROJECT_DIR}/__pycache__"
  "${PROJECT_DIR}/**/__pycache__"
  "${PROJECT_DIR}/**/*.pyc"
  "${PROJECT_DIR}/backend/venv"
  "${PROJECT_DIR}/backend/.venv"
  "${PROJECT_DIR}/backend/env"
  "${PROJECT_DIR}/backend/ENV"
  "${PROJECT_DIR}/frontend/node_modules"
  "${PROJECT_DIR}/frontend/dist"
  "${PROJECT_DIR}/.pytest_cache"
  "${PROJECT_DIR}/**/.pytest_cache"
  "${PROJECT_DIR}/.DS_Store"
  "${PROJECT_DIR}/**/.DS_Store"
  "${PROJECT_DIR}/*.tar.gz"
)

# Parse argumentos do script (opção nomeada --extra_excludes)
extra_excludes=()
while [ $# -gt 0 ]; do
  case "$1" in
    --extra_excludes)
      shift
      while [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; do
        extra_excludes+=("$1")
        shift
      done
      ;;
    --help|-h)
      if [ -n "$SCRIPT_PATH" ] && [ -f "$SCRIPT_PATH" ]; then
        sed -n '2,26p' "$SCRIPT_PATH" | sed 's/^# \?//'
      else
        sed -n '2,26p' "$0" | sed 's/^# \?//'
      fi
      exit 0
      ;;
    *)
      echo "Erro: opção desconhecida: $1. Use --help ou --extra_excludes PATTERN [PATTERN ...]" >&2
      exit 1
      ;;
  esac
done

###############################################################################
# Funções auxiliares
###############################################################################

# Lê "version": "X.Y.Z" do frontend/package.json (compatível com macOS/BSD sed)
get_version_from_package_json() {
  local pkg_file="${BASE_DIR}/${PROJECT_DIR}/frontend/package.json"
  if [ -f "$pkg_file" ]; then
    local version
    version=$(sed -n 's/^[[:space:]]*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$pkg_file" 2>/dev/null | head -1)
    if [ -n "${version}" ]; then
      echo "${version}"
    else
      echo "unknown"
    fi
  else
    echo "unknown"
  fi
}

# Faz backup do projeto. Usa DEFAULT_EXCLUDES; aceita excludes extras como parâmetros.
# Uso: backup_project "AtlasFile" "AtlasFile" [ "AtlasFile/outro/exclude" ... ]
backup_project() {
  local project_dir="$1"
  local project_name="$2"
  shift 2
  # $@ = excludes extras (pode ser vazio); não usar array para evitar "unbound variable" com set -u

  echo -e "${YELLOW}[1/1] Backup: ${project_name}${NC}"

  if [ ! -d "${BASE_DIR}/${project_dir}" ]; then
    echo -e "${RED}❌ Diretório não encontrado: ${BASE_DIR}/${project_dir}${NC}"
    echo ""
    return 1
  fi

  local version
  version=$(get_version_from_package_json)

  if [ "$version" = "unknown" ]; then
    echo -e "${RED}⚠️  Aviso: Não foi possível ler version em ${project_dir}/frontend/package.json${NC}"
  fi

  local output_file="${BASE_DIR}/${project_name}_v${version}_${DATE}.tar.gz"

  # Default excludes + extras ($@) convertidos em --exclude=... para o tar
  local tar_args=()
  for pattern in "${DEFAULT_EXCLUDES[@]}"; do
    tar_args+=(--exclude="${pattern}")
  done
  for pattern in "$@"; do
    tar_args+=(--exclude="${pattern}")
  done

  cd "${BASE_DIR}"
  tar -czf "${output_file}" "${tar_args[@]}" "${project_dir}/"

  if [ $? -eq 0 ]; then
    local size
    size=$(du -h "${output_file}" | cut -f1)
    echo -e "${GREEN}✅ Sucesso! Versão: ${version} | Data: ${DATE} | Tamanho: ${size}${NC}"
  else
    echo -e "${RED}❌ Erro ao criar backup${NC}"
    return 1
  fi

  echo ""
}

###############################################################################
# Cabeçalho
###############################################################################
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Backup Versionado - AtlasFile                             ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Data: ${DATE}${NC}"
echo -e "${YELLOW}Projeto: ${PROJECT_DIR}${NC}"
echo ""

###############################################################################
# AtlasFile (DEFAULT_EXCLUDES + --extra_excludes quando informado)
###############################################################################
if [ ${#extra_excludes[@]} -gt 0 ]; then
  backup_project "${PROJECT_DIR}" "${PROJECT_DIR}" "${extra_excludes[@]}"
else
  backup_project "${PROJECT_DIR}" "${PROJECT_DIR}"
fi

###############################################################################
# Resumo final
###############################################################################
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  ✅ Backup Concluído                                       ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Arquivos criados:${NC}"
cd "${BASE_DIR}"
ls -lh "${PROJECT_DIR}"_*"_${DATE}.tar.gz" 2>/dev/null | awk '{print "  " $9 " - " $5}' || echo "  Nenhum arquivo encontrado"
echo ""
echo -e "${YELLOW}Total:${NC}"
du -ch "${PROJECT_DIR}"_*"_${DATE}.tar.gz" 2>/dev/null | awk 'END{print "  " $1}' || echo "  0"
echo ""

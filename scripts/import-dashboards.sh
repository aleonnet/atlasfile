#!/usr/bin/env bash
# Importa saved objects (index pattern, visualizações, dashboard) no OpenSearch Dashboards.
# Uso: ./scripts/import-dashboards.sh [arquivo.ndjson]
# Variáveis: DASHBOARDS_URL (default http://localhost:5601), OPENSEARCH_INITIAL_ADMIN_PASSWORD (ou DASHBOARDS_PASSWORD).
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FILE="${1:-$ROOT/dashboards/atlasfile.ndjson}"
URL="${DASHBOARDS_URL:-http://localhost:5601}"
USER="${DASHBOARDS_USER:-admin}"
PASS="${DASHBOARDS_PASSWORD:-${OPENSEARCH_INITIAL_ADMIN_PASSWORD:-Kaid0Search!2026X}}"

if [ ! -f "$FILE" ]; then
  echo "Arquivo não encontrado: $FILE"
  exit 1
fi

echo "Importando $FILE em $URL (tenant padrão do usuário, ex.: Private) ..."
curl -sS -X POST "$URL/api/saved_objects/_import?overwrite=true" \
  -u "$USER:$PASS" \
  -H "osd-xsrf: true" \
  -F "file=@$FILE"

echo ""
echo "Concluído. Para abrir o dashboard:"
echo "  Link direto: $URL/app/dashboards#/view/atlasfile-overview"
echo "  Ou: menu Dashboards > abra 'AtlasFile – Visão geral'."
echo "  Se não aparecer na lista: Stack Management > Saved Objects > busque 'AtlasFile' e abra a partir daí."

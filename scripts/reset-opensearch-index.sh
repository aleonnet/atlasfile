#!/usr/bin/env bash
# Remove o índice atlasfile_documents para que o backend o recrie com o mapping
# atualizado (document_type, correspondent, review_status, etc.) no próximo startup.
# Uso: após rodar este script, suba o stack e execute Reconcile na UI para repopular.
set -e
OPENSEARCH_HOST="${OPENSEARCH_HOST:-https://localhost:9200}"
OPENSEARCH_USER="${OPENSEARCH_USER:-admin}"
OPENSEARCH_PASSWORD="${OPENSEARCH_PASSWORD:-Kaid0Search!2026X}"
INDEX="${OPENSEARCH_INDEX:-atlasfile_documents}"
echo "Deletando índice ${INDEX} em ${OPENSEARCH_HOST}..."
code=$(curl -s -k -o /dev/null -w "%{http_code}" -u "${OPENSEARCH_USER}:${OPENSEARCH_PASSWORD}" -X DELETE "${OPENSEARCH_HOST}/${INDEX}")
if [[ "$code" == "200" || "$code" == "404" ]]; then
  echo "OK (${code}). Índice removido ou já inexistente."
else
  echo "Erro HTTP ${code}. Verifique host e credenciais."
  exit 1
fi
echo "Suba o stack (docker compose up -d) e rode Reconcile na UI para repopular."

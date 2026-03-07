#!/usr/bin/env bash
# Remove índices OpenSearch para que o backend os recrie com mapping atualizado.
# Uso:
#   ./reset-opensearch-index.sh                  → deleta índice de documentos
#   ./reset-opensearch-index.sh chat              → deleta índice de sessões de chat
#   ./reset-opensearch-index.sh all               → deleta ambos
set -e
OPENSEARCH_HOST="${OPENSEARCH_HOST:-https://localhost:9200}"
OPENSEARCH_USER="${OPENSEARCH_USER:-admin}"
OPENSEARCH_PASSWORD="${OPENSEARCH_PASSWORD:-Kaid0Search!2026X}"
DOCS_INDEX="${OPENSEARCH_INDEX:-atlasfile_documents}"
CHAT_INDEX="${OPENSEARCH_CHAT_INDEX:-atlasfile_chat_sessions}"

delete_index() {
  local idx="$1"
  echo "Deletando índice ${idx} em ${OPENSEARCH_HOST}..."
  code=$(curl -s -k -o /dev/null -w "%{http_code}" -u "${OPENSEARCH_USER}:${OPENSEARCH_PASSWORD}" -X DELETE "${OPENSEARCH_HOST}/${idx}")
  if [[ "$code" == "200" || "$code" == "404" ]]; then
    echo "  OK (${code}). Índice ${idx} removido ou já inexistente."
  else
    echo "  Erro HTTP ${code} ao deletar ${idx}. Verifique host e credenciais."
    exit 1
  fi
}

MODE="${1:-docs}"
case "$MODE" in
  chat)
    delete_index "$CHAT_INDEX"
    ;;
  all)
    delete_index "$DOCS_INDEX"
    delete_index "$CHAT_INDEX"
    ;;
  *)
    delete_index "$DOCS_INDEX"
    ;;
esac
echo "Suba o stack (docker compose up -d) e rode Reconcile na UI para repopular."

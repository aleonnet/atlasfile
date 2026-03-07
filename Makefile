# AtlasFile - test and build targets
# Recomendado: make docker-update (testa e sobe api + web + mcp).

.PHONY: test test-backend test-frontend docker-build docker-up docker-update docker-smoke-init reset-index reset-chat

test: test-backend test-frontend
	@echo "All tests passed."

test-backend:
	@cd backend && if test -x .venv/bin/python; then .venv/bin/python -m pytest tests/ -v; else python3 -m pytest tests/ -v; fi

test-frontend:
	cd frontend && npm run test

docker-build: test
	docker compose build

# Sobe todos os serviços (opensearch, api, mcp, web). Não roda test antes.
docker-up:
	docker compose up -d --build

# Roda test, depois sobe opensearch + dashboards + api + mcp + web com rebuild. Remove imagens <none>.
# Por padrão NÃO reseta índices. Opções:
#   make docker-update RESET_INDEX=1        → reseta índice de documentos
#   make docker-update RESET_CHAT=1         → reseta índice de sessões de chat
#   make docker-update RESET_INDEX=1 RESET_CHAT=1  → reseta ambos
docker-update: test
	@if [ -n "$${RESET_INDEX}" ] && [ -n "$${RESET_CHAT}" ]; then ./scripts/reset-opensearch-index.sh all; \
	elif [ -n "$${RESET_INDEX}" ]; then $(MAKE) reset-index; \
	elif [ -n "$${RESET_CHAT}" ]; then $(MAKE) reset-chat; fi
	docker compose up -d --build opensearch opensearch-dashboards api mcp web
	$(MAKE) docker-smoke-init
	docker image prune -f
	@echo "OpenSearch, Dashboards, API, MCP e Web atualizados."

docker-smoke-init:
	@bash ./scripts/smoke-project-init.sh

# Deleta o índice de documentos; depois rode Reconcile na UI para repopular.
reset-index:
	@./scripts/reset-opensearch-index.sh docs

# Deleta o índice de sessões de chat.
reset-chat:
	@./scripts/reset-opensearch-index.sh chat

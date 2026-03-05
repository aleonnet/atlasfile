# AtlasFile - test and build targets
# Recomendado: make docker-update (testa e sobe api + web + mcp).

.PHONY: test test-backend test-frontend docker-build docker-up docker-update docker-smoke-init reset-index

test: test-backend test-frontend
	@echo "All tests passed."

test-backend:
	@cd backend && (test -x .venv/bin/python && .venv/bin/python -m pytest tests/ -v || python3 -m pytest tests/ -v)

test-frontend:
	cd frontend && npm run test

docker-build: test
	docker compose build

# Sobe todos os serviços (opensearch, api, mcp, web). Não roda test antes.
docker-up:
	docker compose up -d --build

# Roda test, depois sobe opensearch + dashboards + api + mcp + web com rebuild. Remove imagens <none>.
# Por padrão NÃO reseta índices OpenSearch. Para resetar: make docker-update RESET_INDEX=1
docker-update: test
	@if [ -n "$${RESET_INDEX}" ]; then $(MAKE) reset-index; fi
	docker compose up -d --build opensearch opensearch-dashboards api mcp web
	$(MAKE) docker-smoke-init
	docker image prune -f
	@echo "OpenSearch, Dashboards, API, MCP e Web atualizados."

docker-smoke-init:
	@bash ./scripts/smoke-project-init.sh

# Deleta o índice OpenSearch para recriar com mapping atualizado; depois rode Reconcile na UI.
# Chamado automaticamente por docker-update apenas se RESET_INDEX=1.
reset-index:
	@./scripts/reset-opensearch-index.sh

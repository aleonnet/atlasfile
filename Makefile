# AtlasFile - test and build targets
# Recomendado para rebuild do stack base: make docker-update.
# O smoke funcional completo do ciclo (ingestão, triagem, busca/highlight e assistente)
# fica documentado em docs/plano_teste_e2e_v0.36.0.md.

.PHONY: test test-backend test-frontend test-installer docker-build docker-up docker-update docker-smoke-init reset-index reset-chat ensure-dashboards-cookie uninstall

test: test-backend test-frontend test-installer
	@echo "All tests passed."

test-installer:
	@bash -n install.sh
	@if command -v shellcheck >/dev/null 2>&1; then shellcheck -S warning install.sh; else echo "shellcheck not installed - skipped"; fi
	@bash tests/installer/run.sh

test-backend:
	@cd backend && if test -x .venv/bin/python; then .venv/bin/python -m pytest tests/ -v; else python3 -m pytest tests/ -v; fi

test-frontend:
	cd frontend && npm run test

docker-build: test
	docker compose build

# DASHBOARDS_COOKIE_PASSWORD é por instalação (cookie de instância anterior
# causa 500 com a chave default); quem atualiza via git pull sem reinstalar
# ganha a var aqui, sem precisar rodar o install.sh de novo.
ensure-dashboards-cookie:
	@if [ -f .env ] && ! grep -q '^DASHBOARDS_COOKIE_PASSWORD=' .env; then \
	  printf 'DASHBOARDS_COOKIE_PASSWORD=%s\n' "$$( (LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom || true) | head -c 48)" >> .env; \
	  echo "DASHBOARDS_COOKIE_PASSWORD gerada no .env (chave de cookie por instalação)"; \
	fi

# Sobe todos os serviços (opensearch, api, mcp, web). Não roda test antes.
# Faxina automática pós-build: o build cache cresce a cada rebuild e NUNCA deve
# ser tarefa do usuário (caso real 2026-07-25: 36GB acumulados derrubaram a
# ingestão por disco cheio). Teto de 2GB ≈ 2 ciclos completos de build (um ciclo
# medido gera ~1GB) — mantém rebuilds rápidos sem crescer sem limite.
docker-up: ensure-dashboards-cookie
	docker compose up -d --build
	docker image prune -f
	docker builder prune -f --keep-storage=2GB

# Roda test, depois sobe opensearch + dashboards + api + mcp + web com rebuild. Remove imagens <none>.
# O smoke embutido aqui é curto: template -> initialize -> profile.
# Por padrão NÃO reseta índices. Opções:
#   make docker-update RESET_INDEX=1        → reseta índice de documentos
#   make docker-update RESET_CHAT=1         → reseta índice de sessões de chat
#   make docker-update RESET_INDEX=1 RESET_CHAT=1  → reseta ambos
docker-update: test ensure-dashboards-cookie
	@if [ -n "$${RESET_INDEX}" ] && [ -n "$${RESET_CHAT}" ]; then ./scripts/reset-opensearch-index.sh all; \
	elif [ -n "$${RESET_INDEX}" ]; then $(MAKE) reset-index; \
	elif [ -n "$${RESET_CHAT}" ]; then $(MAKE) reset-chat; fi
	docker compose up -d --build opensearch opensearch-dashboards api mcp web
	$(MAKE) docker-smoke-init
	docker image prune -f
	docker builder prune -f --keep-storage=2GB
	@echo "OpenSearch, Dashboards, API, MCP e Web atualizados."

docker-smoke-init:
	@bash ./scripts/smoke-project-init.sh

# Deleta o índice de documentos; depois rode Reconcile na UI para repopular.
reset-index:
	@./scripts/reset-opensearch-index.sh docs

# Deleta o índice de sessões de chat.
reset-chat:
	@./scripts/reset-opensearch-index.sh chat

# Desinstala ESTA instalação: imprime o plano e pede confirmação antes de agir.
# Reverte só o que o install.sh criou (manifesto .atlasfile-install-manifest +
# ~/.atlasfile/host-prereqs); um clone que não veio do instalador é preservado,
# então rodar isto num checkout de desenvolvimento remove o stack e nada mais.
#   make uninstall                    → pergunta o que fazer com o volume
#   make uninstall ARGS="--purge-data --remove-deps"
uninstall:
	@bash install.sh --uninstall --dir "$(CURDIR)" $(ARGS)

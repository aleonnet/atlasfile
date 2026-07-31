# AtlasFile - test and build targets
# Recomendado para rebuild do stack base: make docker-update.
# O smoke funcional completo do ciclo (ingestão, triagem, busca/highlight e assistente)
# fica documentado em docs/plano_teste_e2e_v0.36.0.md.

.PHONY: test test-backend test-frontend test-installer docker-build docker-up docker-update docker-smoke-init reset-index reset-chat ensure-dashboards-cookie ensure-api-keys-file ensure-atlasfile-version uninstall

# v1.0.0: o compose base consome a imagem do GHCR; o overlay devolve o build
# local (contribuidor). Todos os alvos de stack deste Makefile compilam da
# fonte — consumir a imagem publicada é papel do instalador/bundle.
COMPOSE_DEV := docker compose -f docker-compose.yml -f docker-compose.build.yml

test: test-backend test-frontend test-installer
	@echo "All tests passed."

# check_consistency.py so rodava no job Linux do CI: a paridade entre os dois
# instaladores era invisivel para quem roda `make test` na propria maquina, e
# era justamente ali que as divergencias moravam. Com pwsh instalado ele tambem
# compara os QUADROS do banner; sem pwsh ele se anuncia pulado.
# O parse do install.ps1 entra junto quando ha pwsh: um erro de sintaxe la so
# aparecia no job Windows, a minutos de distancia.
test-installer:
	@bash -n install.sh
	@if command -v shellcheck >/dev/null 2>&1; then shellcheck -S warning install.sh; else echo "shellcheck not installed - skipped"; fi
	@bash tests/installer/run.sh
	@python3 tests/installer/check_consistency.py
	@if command -v pwsh >/dev/null 2>&1; then \
		pwsh -NoProfile -Command '$$e=$$null; $$null=[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path ./install.ps1).Path,[ref]$$null,[ref]$$e); if($$e){$$e|ForEach-Object{"install.ps1:$$($$_.Extent.StartLineNumber) $$($$_.Message)"};exit 1}; "install.ps1 parseia limpo"'; \
	else echo "pwsh not installed - install.ps1 parse skipped"; fi

test-backend:
	@cd backend && if test -x .venv/bin/python; then .venv/bin/python -m pytest tests/ -v; else python3 -m pytest tests/ -v; fi

test-frontend:
	cd frontend && npm run test

docker-build: test ensure-atlasfile-version
	$(COMPOSE_DEV) build

# DASHBOARDS_COOKIE_PASSWORD é por instalação (cookie de instância anterior
# causa 500 com a chave default); quem atualiza via git pull sem reinstalar
# ganha a var aqui, sem precisar rodar o install.sh de novo.
ensure-dashboards-cookie:
	@if [ -f .env ] && ! grep -q '^DASHBOARDS_COOKIE_PASSWORD=' .env; then \
	  printf 'DASHBOARDS_COOKIE_PASSWORD=%s\n' "$$( (LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom || true) | head -c 48)" >> .env; \
	  echo "DASHBOARDS_COOKIE_PASSWORD gerada no .env (chave de cookie por instalação)"; \
	fi

# O compose monta ./config/api_keys.json como bind mount; se o arquivo não
# existir no host, o Docker cria um DIRETÓRIO no destino e o auth passa a
# rejeitar toda key (com API_AUTH_ENABLED=true). Materializa vazio antes do up.
ensure-api-keys-file:
	@if [ ! -f config/api_keys.json ]; then \
	  printf '{"keys": []}\n' > config/api_keys.json; \
	  echo "config/api_keys.json criado vazio (bind mount do compose)"; \
	fi

# v1.0.0: o image: do compose exige ATLASFILE_VERSION (sem default, para
# `latest` implícito não existir) e a interpolação roda MESMO com o overlay de
# build — quem atualiza via git pull ganha a var aqui, sem reinstalar. Fonte:
# frontend/package.json (única fonte de versão do repo). sed BSD-safe, sem jq.
ensure-atlasfile-version:
	@if [ -f .env ] && ! grep -q '^ATLASFILE_VERSION=' .env; then \
	  v="$$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' frontend/package.json | head -1)"; \
	  printf 'ATLASFILE_VERSION=%s\n' "$$v" >> .env; \
	  echo "ATLASFILE_VERSION=$$v gravada no .env (versao do frontend/package.json)"; \
	fi

# Sobe os serviços (opensearch + atlasfile; Dashboards entra com
# COMPOSE_PROFILES=dashboards no .env). Não roda test antes.
# Faxina automática pós-build: o build cache cresce a cada rebuild e NUNCA deve
# ser tarefa do usuário (caso real 2026-07-25: 36GB acumulados derrubaram a
# ingestão por disco cheio). Teto de 2GB ≈ 2 ciclos completos de build (um ciclo
# medido gera ~1GB) — mantém rebuilds rápidos sem crescer sem limite.
# --remove-orphans: a consolidação renomeou os serviços — sem isso, um checkout
# vindo de 0.56.x mantém os containers antigos (api/mcp/web) vivos e o
# atlasfile-api órfão segura a porta 8000 contra o serviço novo.
docker-up: ensure-dashboards-cookie ensure-api-keys-file ensure-atlasfile-version
	$(COMPOSE_DEV) up -d --build --remove-orphans
	docker image prune -f
	docker builder prune -f --keep-storage=2GB

# Roda test, depois sobe opensearch + atlasfile com rebuild (Dashboards entra
# com COMPOSE_PROFILES=dashboards no .env — por isso o up sem lista de
# serviços: nomear um serviço com profile o ligaria mesmo desativado).
# Remove imagens <none>. O smoke embutido aqui é curto: template -> initialize -> profile.
# Por padrão NÃO reseta índices. Opções:
#   make docker-update RESET_INDEX=1        → reseta índice de documentos
#   make docker-update RESET_CHAT=1         → reseta índice de sessões de chat
#   make docker-update RESET_INDEX=1 RESET_CHAT=1  → reseta ambos
docker-update: test ensure-dashboards-cookie ensure-api-keys-file ensure-atlasfile-version
	@if [ -n "$${RESET_INDEX}" ] && [ -n "$${RESET_CHAT}" ]; then ./scripts/reset-opensearch-index.sh all; \
	elif [ -n "$${RESET_INDEX}" ]; then $(MAKE) reset-index; \
	elif [ -n "$${RESET_CHAT}" ]; then $(MAKE) reset-chat; fi
	$(COMPOSE_DEV) up -d --build --remove-orphans
	$(MAKE) docker-smoke-init
	docker image prune -f
	docker builder prune -f --keep-storage=2GB
	@echo "OpenSearch e AtlasFile atualizados."

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

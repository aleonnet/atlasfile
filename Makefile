# AtlasFile - test and build targets
# Recomendado: make docker-update (testa e atualiza api + web).

.PHONY: test test-backend test-frontend docker-build docker-update

test: test-backend test-frontend
	@echo "All tests passed."

test-backend:
	@cd backend && (test -x .venv/bin/python && .venv/bin/python -m pytest tests/ -v || python3 -m pytest tests/ -v)

test-frontend:
	cd frontend && npm run test

docker-build: test
	docker compose build

# Testa e atualiza sempre api e web para usar as ultimas versoes.
# Remove imagens pendentes (<none>) deixadas apos rebuild para evitar acúmulo.
docker-update: test
	docker compose up -d --build api web
	docker image prune -f
	@echo "API e Web atualizados."

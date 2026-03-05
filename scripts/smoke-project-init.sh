#!/usr/bin/env bash
# Smoke check: validates project initialize/profile after docker update.
set -euo pipefail

API_URL="${ATLASFILE_SMOKE_API_URL:-http://localhost:8000}"
API_CONTAINER="${ATLASFILE_SMOKE_API_CONTAINER:-atlasfile-api}"
PROJECTS_ROOT_IN_CONTAINER="${ATLASFILE_SMOKE_PROJECTS_ROOT:-/projects}"
SMOKE_PROJECT_ID="smoke_init_$(date +%Y%m%d_%H%M%S)_$RANDOM"

cleanup() {
  docker exec "${API_CONTAINER}" rm -rf "${PROJECTS_ROOT_IN_CONTAINER}/${SMOKE_PROJECT_ID}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[smoke-init] Verificando template no container ${API_CONTAINER}..."
docker exec "${API_CONTAINER}" python - <<'PY'
from pathlib import Path
import json
import sys

template = Path("/workspace/config/templates/default.json")
if not template.exists():
    print(f"Template ausente: {template}")
    sys.exit(1)
json.loads(template.read_text(encoding="utf-8"))
print("Template OK")
PY

echo "[smoke-init] Aguardando API em ${API_URL}/health..."
for _ in $(seq 1 30); do
  if curl -sS "${API_URL}/health" >/dev/null; then
    break
  fi
  sleep 1
done
curl -sS "${API_URL}/health" >/dev/null

echo "[smoke-init] Criando diretório de projeto de smoke (${SMOKE_PROJECT_ID})..."
docker exec "${API_CONTAINER}" mkdir -p "${PROJECTS_ROOT_IN_CONTAINER}/${SMOKE_PROJECT_ID}"

echo "[smoke-init] Chamando initialize..."
init_json="$(curl -sS -X POST "${API_URL}/api/projects/${SMOKE_PROJECT_ID}/initialize")"
python - "${init_json}" <<'PY'
import json
import sys

data = json.loads(sys.argv[1])
if data.get("status") != "ok":
    raise SystemExit(f"initialize falhou: {data}")
project = data.get("project") or {}
if project.get("initialized") is not True:
    raise SystemExit(f"initialize não marcou projeto como inicializado: {data}")
print("Initialize OK")
PY

echo "[smoke-init] Validando endpoint de profile..."
profile_json="$(curl -sS "${API_URL}/api/projects/${SMOKE_PROJECT_ID}/profile")"
python - "${profile_json}" <<'PY'
import json
import sys

data = json.loads(sys.argv[1])
profile = data.get("profile") or {}
project_id = profile.get("project_id")
if not project_id:
    raise SystemExit(f"profile inválido: {data}")
print("Profile OK")
PY

echo "[smoke-init] Smoke de inicialização concluído com sucesso."

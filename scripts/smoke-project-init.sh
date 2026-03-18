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

echo "[smoke-init] Chamando initialize com template default..."
init_json="$(curl -sS -X POST "${API_URL}/api/projects/${SMOKE_PROJECT_ID}/initialize?template=default")"
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
paths = profile.get("paths") or {}
classification = profile.get("classification") or {}
layout = profile.get("layout") or {}
if paths.get("inbox") != "_INBOX_DROP":
    raise SystemExit(f"inbox inesperado: {paths.get('inbox')}")
business_domains = classification.get("business_domains") or []
domain_keys = {str(item.get("key") or "").strip() for item in business_domains}
expected_domains = {
    "societario",
    "juridico",
    "ativos",
    "financeiro",
    "fiscal",
    "pessoas",
    "ti",
    "operacoes",
    "regulatorio",
    "compliance",
    "suprimentos",
}
missing_domains = sorted(expected_domains - domain_keys)
if missing_domains:
    raise SystemExit(f"business_domains ausentes: {missing_domains}")
document_types = classification.get("document_types") or []
document_type_keys = {str(item.get("key") or "").strip() for item in document_types}
expected_document_types = {"contrato", "aditivo", "fato_relevante", "relatorio", "apresentacao", "planilha", "email", "edital", "plano"}
missing_document_types = sorted(expected_document_types - document_type_keys)
if missing_document_types:
    raise SystemExit(f"document_types ausentes: {missing_document_types}")
if (layout.get("areas_root") or "").strip() != "02_AREAS":
    raise SystemExit(f"areas_root inesperado: {layout.get('areas_root')}")
print("Profile OK")
PY

echo "[smoke-init] Validando pastas materializadas no container..."
docker exec "${API_CONTAINER}" python - "${SMOKE_PROJECT_ID}" "${PROJECTS_ROOT_IN_CONTAINER}" <<'PY'
from pathlib import Path
import sys

project_id = sys.argv[1]
projects_root = Path(sys.argv[2])
project_root = projects_root / project_id
required_paths = [
    project_root / "_PROFILE" / "profile.json",
    project_root / "_PROFILE" / "history",
    project_root / "_INBOX_DROP",
    project_root / "_TRIAGE_REVIEW" / "pending",
    project_root / "_TRIAGE_REVIEW" / "resolved",
    project_root / "_TRIAGE_REVIEW" / "rejected",
    project_root / "02_AREAS",
    project_root / "02_AREAS" / "juridico",
    project_root / "02_AREAS" / "financeiro",
    project_root / "02_AREAS" / "suprimentos",
    project_root / "03_RESOURCES",
    project_root / "04_ARCHIVE",
    project_root / "_INDEX.md",
]
missing = [str(path) for path in required_paths if not path.exists()]
if missing:
    raise SystemExit(f"paths ausentes: {missing}")
print("Filesystem OK")
PY

echo "[smoke-init] Smoke de inicialização concluído com sucesso."

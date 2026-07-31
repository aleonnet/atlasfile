#!/usr/bin/env bash
# Smoke E2E de release (Fase 3): exercita a IMAGEM PUBLICADA de ponta a ponta —
# versão, ingestão de PDF nativo, OCR de PDF escaneado (tesseract DA IMAGEM,
# não do runner), triagem aprovada (o único caminho que indexa), busca com
# highlight e /mcp com auth dos dois lados. É o gate das tags do GHCR: se este
# script falha, latest/X.Y.Z não são aplicadas.
#
# Parâmetros (env):
#   ATLASFILE_SMOKE_API_URL         default http://localhost:8000
#   ATLASFILE_SMOKE_API_KEY         obrigatória (API_AUTH_ENABLED=true no smoke)
#   ATLASFILE_SMOKE_EXPECT_VERSION  se setada, exige /api/setup/status.version igual
#   ATLASFILE_SMOKE_API_CONTAINER   default atlasfile (cleanup via docker exec)
#   ATLASFILE_SMOKE_IMAGE           se setada, prova que a imagem NÃO contém
#                                   config/api_keys.json (benefício do roadmap)
#
# A key vai por HEADER, nunca por ?api_key= (a query pararia no access log).
set -euo pipefail

API_URL="${ATLASFILE_SMOKE_API_URL:-http://localhost:8000}"
API_KEY="${ATLASFILE_SMOKE_API_KEY:?defina ATLASFILE_SMOKE_API_KEY (o smoke de release roda com auth ligado)}"
EXPECT_VERSION="${ATLASFILE_SMOKE_EXPECT_VERSION:-}"
API_CONTAINER="${ATLASFILE_SMOKE_API_CONTAINER:-atlasfile}"
SMOKE_IMAGE="${ATLASFILE_SMOKE_IMAGE:-}"
PROJECTS_ROOT_IN_CONTAINER="${ATLASFILE_SMOKE_PROJECTS_ROOT:-/projects}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PDF_NATIVO="${REPO_ROOT}/backend/tests/fixtures/classifier_datasets/validation_set/files/FATO RELEVANTE_Oferta Vinculante Torres_Venus.pdf"
PDF_ESCANEADO="${REPO_ROOT}/backend/tests/fixtures/ocr/Relatório Escaneado — Prova de OCR.pdf"
# 4 tokens de propósito: >=6 tokens e >=35 chars ligariam o strict_mode da
# busca (minimum_should_match 2 no bool de topo) — fora do que o smoke prova.
SENTINELA="SENTINELA QUARENTA E DOIS"

PROJ="smoke_e2e_$(date +%Y%m%d_%H%M%S)_$RANDOM"

log()  { printf '[smoke-e2e] %s\n' "$*"; }
fail() { printf '[smoke-e2e] FALHA: %s\n' "$*" >&2; exit 1; }

acurl() { curl -sS -H "X-API-Key: ${API_KEY}" "$@"; }

cleanup() {
  docker exec "${API_CONTAINER}" rm -rf "${PROJECTS_ROOT_IN_CONTAINER}/${PROJ}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# ── 1. health (isento de auth) ──────────────────────────────────────────────
log "aguardando ${API_URL}/health..."
for _ in $(seq 1 30); do
  curl -sS "${API_URL}/health" >/dev/null 2>&1 && break
  sleep 2
done
curl -sS "${API_URL}/health" >/dev/null

# ── 2. gate de versão: imagem publicada == tag ──────────────────────────────
if [ -n "${EXPECT_VERSION}" ]; then
  got="$(acurl "${API_URL}/api/setup/status" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("version",""))')"
  [ "${got}" = "${EXPECT_VERSION}" ] || fail "versão da imagem='${got}' != esperada='${EXPECT_VERSION}'"
  log "versão OK: ${got}"
fi

# ── 3. projeto ──────────────────────────────────────────────────────────────
log "inicializando projeto ${PROJ}..."
docker exec "${API_CONTAINER}" mkdir -p "${PROJECTS_ROOT_IN_CONTAINER}/${PROJ}"
acurl -X POST "${API_URL}/api/projects/${PROJ}/initialize?template=default" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("status")=="ok", d'

# ── 4/5. upload + scan (auto-ingest desligado no smoke → scan determinístico) ─
log "upload dos 2 PDFs (nativo + escaneado)..."
acurl -X POST -F "files=@\"${PDF_NATIVO}\"" -F "files=@\"${PDF_ESCANEADO}\"" \
  "${API_URL}/api/ingest/upload/${PROJ}" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); assert len(d.get("uploaded",[]))==2, d'

log "scan da inbox (extração + OCR + classificação acontecem AQUI, na imagem)..."
scan_json="$(acurl -X POST "${API_URL}/api/ingest/scan/${PROJ}")"
python3 - "${scan_json}" <<'PY'
import json, sys
d = json.loads(sys.argv[1])
assert d.get("failed_count") == 0, f"ingestão falhou: {d.get('errors')}"
assert d.get("processed_count") == 2, f"esperava 2 processados: {d}"
for item in d["items"]:
    assert item.get("doc_id"), f"item sem doc_id: {item}"
    assert item.get("classifier_mode"), f"item sem classifier_mode: {item}"
    assert item.get("decision") in {"auto", "triage_pending"}, f"decision inesperada: {item}"
print("scan OK:", [(i["original_filename"], i["decision"]) for i in d["items"]])
PY

# ── 6. triagem: aprovar o que ficou pendente (é o que indexa) ───────────────
log "resolvendo a triagem (fluxo humano real)..."
pend="$(acurl "${API_URL}/api/triage/${PROJ}")"
python3 - "${pend}" "${API_URL}" "${PROJ}" "${API_KEY}" <<'PY'
import json, sys, urllib.request

items, api, proj, key = json.loads(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
if isinstance(items, dict):
    items = items.get("items") or items.get("documents") or []
for it in items:
    doc_id = it["doc_id"]
    # OCR provado aqui: o doc escaneado só chega à triagem COM texto (a
    # classificação rodou sobre o OCR); "sem_texto_extraivel" seria OCR morto.
    assert it.get("reason") != "sem_texto_extraivel" or it.get("no_text_cause") == "", \
        f"OCR não produziu texto: {it}"
    if it.get("suggested_business_domain"):
        body = {"action": "approve"}
    else:
        body = {"action": "correct", "target_business_domain": "operacoes",
                "target_document_type": "relatorio"}
    req = urllib.request.Request(
        f"{api}/api/triage/{proj}/{doc_id}/decision",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-API-Key": key},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200, f"decision {doc_id}: HTTP {resp.status}"
    print("triagem resolvida:", doc_id, body["action"])
PY

# ── 7. busca com highlight: prova o OCR da imagem publicada ─────────────────
log "buscando a sentinela do PDF escaneado..."
found=0
for _ in $(seq 1 15); do
  res="$(acurl --get --data-urlencode "q=${SENTINELA}" --data-urlencode "project_id=${PROJ}" "${API_URL}/api/search")"
  if python3 - "${res}" <<'PY'
import json, re, sys

# Exigir os TRES termos de conteudo MARCADOS pelo highlighter (<em>), nao a
# substring no snippet: mutante provou que a busca lexical casa token parcial
# e o snippet carrega o resto da frase do documento — asserir "SENTINELA" no
# texto passava ate com query errada. O que o highlighter marcou e o que a
# query de fato encontrou.
d = json.loads(sys.argv[1])
need = {"SENTINELA", "QUARENTA", "DOIS"}
for h in d.get("hits") or []:
    blobs = list(h.get("highlights") or [])
    blobs += [e.get("snippet", "") for e in (h.get("evidences") or [])]
    marked: set = set()
    for frag in re.findall(r"<em>(.*?)</em>", " ".join(blobs), flags=re.I):
        marked.update(w.upper() for w in re.findall(r"\w+", frag))
    if need <= marked:
        print("highlight OK:", h.get("original_filename"))
        sys.exit(0)
sys.exit(1)
PY
  then found=1; break; fi
  sleep 2
done
[ "${found}" = "1" ] || fail "sentinela '${SENTINELA}' sem hit/highlight — OCR ou indexação quebrados"

log "buscando termo do PDF nativo..."
acurl --get --data-urlencode "q=oferta vinculante" --data-urlencode "project_id=${PROJ}" "${API_URL}/api/search" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); assert (d.get("hits") or []), "PDF nativo sem hit"'

# ── 8. /mcp: auth dos dois lados + tool call de verdade ─────────────────────
log "provando /mcp (sem key → 401; com key → sessão + get_stats)..."
INIT_BODY='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke-e2e","version":"0"}}}'
code="$(curl -s -o /dev/null -w '%{http_code}' -X POST "${API_URL}/mcp" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d "${INIT_BODY}")"
[ "${code}" = "401" ] || fail "/mcp sem key devolveu ${code}, esperava 401"

SID="$(curl -siS -X POST "${API_URL}/mcp" \
  -H "Authorization: Bearer ${API_KEY}" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d "${INIT_BODY}" | tr -d '\r' | awk 'tolower($1)=="mcp-session-id:"{print $2}')"
[ -n "${SID}" ] || fail "initialize com key não devolveu mcp-session-id"

code="$(curl -s -o /dev/null -w '%{http_code}' -X POST "${API_URL}/mcp" \
  -H "Authorization: Bearer ${API_KEY}" -H "mcp-session-id: ${SID}" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}')"
[ "${code}" = "202" ] || fail "notifications/initialized devolveu ${code}, esperava 202"

# HTTP 200 sozinho é gate furado: falha de tool volta 200 com result.isError.
acurl -X POST "${API_URL}/mcp" \
  -H "Authorization: Bearer ${API_KEY}" -H "mcp-session-id: ${SID}" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_stats","arguments":{}}}' \
  | python3 -c '
import json, sys
d = json.load(sys.stdin)
r = d.get("result") or {}
assert not r.get("isError"), f"get_stats retornou isError: {d}"
content = r.get("content") or []
assert content and content[0].get("text"), f"get_stats sem conteúdo: {d}"
print("get_stats OK (loop tool -> loopback -> API fechado)")
'

# ── 9. imagem limpa: a key nunca é assada na imagem publicada ───────────────
if [ -n "${SMOKE_IMAGE}" ]; then
  log "provando que a imagem não contém config/api_keys.json..."
  docker run --rm --entrypoint sh "${SMOKE_IMAGE}" -c '! test -f /workspace/config/api_keys.json' \
    || fail "a imagem publicada CONTÉM config/api_keys.json"
fi

log "smoke E2E concluído com sucesso."

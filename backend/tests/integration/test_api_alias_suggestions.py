"""Integração do sugeridor de aliases: GET sugestões, POST aliases (append) e dismiss."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import taxonomy
from app.config import settings
from app.main import app
from app.triage import triage_resolved_dir


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    templates_dir = tmp_path / "_ATLASFILE" / "templates"
    templates_dir.mkdir(parents=True)
    monkeypatch.setenv("PROJECTS_ROOT", str(tmp_path))
    monkeypatch.setattr(settings, "projects_root", str(tmp_path), raising=False)
    monkeypatch.setattr(taxonomy.settings, "projects_root", str(tmp_path), raising=False)

    base_template = {
        "template_meta": {"slug": "default", "name": "Default"},
        "project_id": "__PROJECT_ID__",
        "project_label": "__PROJECT_LABEL__",
        "project_root": "__PROJECT_ROOT__",
        "version": 1,
        "updated_at": "2026-01-01T00:00:00+00:00",
        "classification": {
            "business_domains": [
                {"key": "juridico", "label": "Jurídico", "aliases": ["legal"]},
                {"key": "operacoes", "label": "Operações", "aliases": ["sla"]},
            ],
            "document_types": [
                {"key": "contrato", "label": "Contrato", "aliases": ["contract"], "extensions": [], "folder": "contrato"}
            ],
        },
        "layout": {"business_domain_folders": [{"business_domain": "juridico", "folder": "juridico"}]},
    }
    (templates_dir / "default.json").write_text(json.dumps(base_template), encoding="utf-8")

    from app.profile_store import ensure_profile

    project_root = tmp_path / "proj_a"
    project_root.mkdir()
    ensure_profile(project_root=project_root, project_id="proj_a", project_label="Projeto A")

    def resolved(doc_id: str, final_bd: str, text: str, filename: str) -> None:
        f = project_root / "files" / f"{doc_id}__{filename}"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
        rd = triage_resolved_dir(project_root)
        rd.mkdir(parents=True, exist_ok=True)
        (rd / f"{doc_id}.json").write_text(json.dumps({
            "doc_id": doc_id,
            "original_filename": filename,
            "suggested_business_domain": "operacoes",
            "business_domain": final_bd,
            "suggested_document_type": "contrato",
            "document_type": "contrato",
            "final_path": str(f),
        }), encoding="utf-8")

    resolved("d1", "juridico", "escritura publica lavrada em cartorio", "a.txt")
    resolved("d2", "juridico", "escritura registrada pelo tabeliao", "b.txt")
    resolved("d3", "operacoes", "indicadores mensais de atendimento", "c.txt")
    return tmp_path


def test_fluxo_completo_sugerir_aplicar_e_dispensar(client: TestClient, sandbox) -> None:
    # 1. GET: minera e propõe "escritura" para juridico
    r = client.get("/api/projects/proj_a/alias-suggestions")
    assert r.status_code == 200
    body = r.json()
    assert body["corpus"]["corrected_total"] == 2
    bd = [s for s in body["suggestions"] if s["kind"] == "business_domain"]
    assert bd and bd[0]["key"] == "juridico"
    terms = {t["term"] for t in bd[0]["terms"]}
    assert "escritura" in terms

    # 2. POST aliases: aprova o termo → template + profile do projeto
    r2 = client.post("/api/taxonomy/aliases", json={
        "kind": "business_domain", "key": "juridico",
        "aliases": ["escritura"], "created_from": "alias-suggest:proj_a",
    })
    assert r2.status_code == 200
    assert r2.json()["template_updated"] is True
    assert "proj_a" in r2.json()["updated_projects"]

    # 3. Aplicado não é mais proposto (agora é alias existente)
    r3 = client.get("/api/projects/proj_a/alias-suggestions")
    terms3 = {t["term"] for s in r3.json()["suggestions"] for t in s["terms"]}
    assert "escritura" not in terms3

    # 4. Dismiss persiste no profile e filtra a sugestão
    remaining = sorted(terms3)
    if remaining:
        target = next(s for s in r3.json()["suggestions"] if s["terms"])
        term = target["terms"][0]["term"]
        r4 = client.post("/api/projects/proj_a/alias-suggestions/dismiss", json={
            "kind": target["kind"], "key": target["key"], "term": term,
        })
        assert r4.status_code == 200
        assert f"{target['kind']}:{target['key']}:{term}" in r4.json()["dismissed"]
        r5 = client.get("/api/projects/proj_a/alias-suggestions")
        terms5 = {t["term"] for s in r5.json()["suggestions"] for t in s["terms"]}
        assert term not in terms5


def test_post_aliases_entrada_inexistente_da_400(client: TestClient, sandbox) -> None:
    r = client.post("/api/taxonomy/aliases", json={
        "kind": "business_domain", "key": "nao_existe", "aliases": ["x"],
    })
    assert r.status_code == 400


def test_projeto_inexistente_da_404(client: TestClient, sandbox) -> None:
    r = client.get("/api/projects/fantasma/alias-suggestions")
    assert r.status_code == 404

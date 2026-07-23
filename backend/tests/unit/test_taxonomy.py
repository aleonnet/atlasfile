"""Testes da criação governada de taxonomia (template + propagação a profiles)."""
from __future__ import annotations

import json

import pytest

from app import taxonomy


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    # template default do usuário (sobrepõe builtin) + 1 projeto inicializado
    templates_dir = tmp_path / "_ATLASFILE" / "templates"
    templates_dir.mkdir(parents=True)
    monkeypatch.setenv("PROJECTS_ROOT", str(tmp_path))
    monkeypatch.setattr(taxonomy.settings, "projects_root", str(tmp_path), raising=False)

    base_template = {
        "template_meta": {"slug": "default", "name": "Default"},
        "project_id": "__PROJECT_ID__",
        "project_label": "__PROJECT_LABEL__",
        "project_root": "__PROJECT_ROOT__",
        "version": 1,
        "updated_at": "2026-01-01T00:00:00+00:00",
        "classification": {
            "business_domains": [{"key": "juridico", "label": "Jurídico", "aliases": ["legal"]}],
            "document_types": [
                {"key": "contrato", "label": "Contrato", "aliases": ["contract"], "extensions": ["pdf"], "folder": "contrato"}
            ],
        },
        "layout": {"business_domain_folders": [{"business_domain": "juridico", "folder": "juridico"}]},
    }
    (templates_dir / "default.json").write_text(json.dumps(base_template), encoding="utf-8")

    from app.profile_store import ensure_profile

    project_root = tmp_path / "proj_a"
    project_root.mkdir()
    ensure_profile(project_root=project_root, project_id="proj_a", project_label="Projeto A")
    return tmp_path


def test_cria_document_type_no_template_e_propaga(sandbox):
    result = taxonomy.create_taxonomy_entry(
        kind="document_type", key="memorando", label="Memorando", aliases=["memo"], created_from="teste"
    )
    assert result["template_updated"] is True
    assert "proj_a" in result["updated_projects"]
    assert result["entry"]["folder"] == "memorando"
    assert "memo" in result["entry"]["aliases"] and "memorando" in result["entry"]["aliases"]

    template = json.loads((sandbox / "_ATLASFILE" / "templates" / "default.json").read_text(encoding="utf-8"))
    keys = [t["key"] for t in template["classification"]["document_types"]]
    assert "memorando" in keys

    from app.profile_store import load_profile

    profile = load_profile(sandbox / "proj_a")
    assert any(t.key == "memorando" for t in profile.classification.document_types)


def test_cria_business_domain_com_folder_no_layout(sandbox):
    result = taxonomy.create_taxonomy_entry(kind="business_domain", key="Compliance", created_from="teste")
    assert result["key"] == "compliance"
    from app.profile_store import load_profile

    profile = load_profile(sandbox / "proj_a")
    assert any(d.key == "compliance" for d in profile.classification.business_domains)
    raw = profile.model_dump(mode="json")
    assert any(f["business_domain"] == "compliance" for f in raw["layout"]["business_domain_folders"])


def test_idempotente_por_key(sandbox):
    taxonomy.create_taxonomy_entry(kind="document_type", key="memorando")
    result = taxonomy.create_taxonomy_entry(kind="document_type", key="memorando")
    assert result["template_updated"] is False
    assert result["updated_projects"] == []


def test_add_aliases_em_entrada_existente_propaga_e_e_idempotente(sandbox):
    result = taxonomy.add_taxonomy_aliases(
        kind="business_domain", key="juridico", aliases=["Escritura", "tabelionato"], created_from="alias-suggest"
    )
    assert result["template_updated"] is True
    assert "proj_a" in result["updated_projects"]
    assert result["aliases"] == ["escritura", "tabelionato"]

    template = json.loads((sandbox / "_ATLASFILE" / "templates" / "default.json").read_text(encoding="utf-8"))
    entry = next(d for d in template["classification"]["business_domains"] if d["key"] == "juridico")
    # merge preserva os existentes e ordena
    assert entry["aliases"] == ["escritura", "legal", "tabelionato"]
    assert "alias-suggest" in (template["template_meta"].get("notes") or "")

    from app.profile_store import load_profile

    profile = load_profile(sandbox / "proj_a")
    domain = next(d for d in profile.classification.business_domains if d.key == "juridico")
    assert "escritura" in domain.aliases

    # idempotente: aplicar de novo não muda nada
    again = taxonomy.add_taxonomy_aliases(kind="business_domain", key="juridico", aliases=["escritura"])
    assert again["template_updated"] is False
    assert again["updated_projects"] == []


def test_add_aliases_exige_entrada_existente_e_valida_input(sandbox):
    with pytest.raises(ValueError, match="não existe"):
        taxonomy.add_taxonomy_aliases(kind="business_domain", key="inexistente", aliases=["x"])
    with pytest.raises(ValueError, match="obrigatórios"):
        taxonomy.add_taxonomy_aliases(kind="document_type", key="contrato", aliases=["   "])
    with pytest.raises(ValueError, match="kind inválido"):
        taxonomy.add_taxonomy_aliases(kind="tag", key="contrato", aliases=["x"])


def test_rejeita_outro_e_kind_invalido(sandbox):
    with pytest.raises(ValueError):
        taxonomy.create_taxonomy_entry(kind="document_type", key="outro")
    with pytest.raises(ValueError):
        taxonomy.create_taxonomy_entry(kind="tipo", key="x")

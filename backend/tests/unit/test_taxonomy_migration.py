"""Migração/remoção governada de taxonomia: rewrite por rótulo, pendências,
templates/profiles com alias herdado, guardas e apply sem hold-out."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import app.taxonomy_migration as tm
from app.evaluation_dataset import (
    TrainingPoolRecord,
    ValidationSetEntry,
    classifier_datasets_root,
    save_training_pool_records,
    save_validation_set,
)
from app.taxonomy_migration import (
    TaxonomyMigrationError,
    _rename_in_raw,
    apply_taxonomy_migration,
    plan_taxonomy_migration,
    remove_taxonomy_entry,
    rewrite_dataset_labels,
    rewrite_pending_suggestions,
)
from app.template_store import get_template


@pytest.fixture()
def roots(tmp_path, monkeypatch):
    """projects_root + datasets isolados em tmp (templates builtin reais seguem visíveis)."""
    projects = tmp_path / "projects"
    projects.mkdir()
    monkeypatch.setattr(tm.settings, "projects_root", str(projects), raising=False)
    # template_store resolve o user dir via env PROJECTS_ROOT
    monkeypatch.setenv("PROJECTS_ROOT", str(projects))
    monkeypatch.setenv("CLASSIFIER_DATASETS_ROOT", str(tmp_path / "datasets"))
    return projects


def _fake_os(count_by_project: dict[str, int] | None = None, hits: list[dict] | None = None):
    client = MagicMock()
    buckets = [{"key": k, "doc_count": v} for k, v in (count_by_project or {}).items()]

    def search(index=None, body=None):
        if body and "aggs" in body:
            return {"aggregations": {"por_projeto": {"buckets": buckets}}}
        # paginação de _iter_index_docs: devolve tudo na primeira página
        if body and body.get("from", 0) == 0:
            return {"hits": {"hits": hits or []}}
        return {"hits": {"hits": []}}

    client.search.side_effect = search
    return client


def test_valida_kind_e_keys():
    with pytest.raises(TaxonomyMigrationError, match="kind"):
        tm._validate_kind_and_keys("banana", "a", "b")
    with pytest.raises(TaxonomyMigrationError, match="mesma key"):
        tm._validate_kind_and_keys("document_type", "a", "a")
    with pytest.raises(TaxonomyMigrationError, match="destino"):
        tm._validate_kind_and_keys("document_type", "a", "outro")


def test_rewrite_dataset_labels_por_rotulo(roots):
    save_training_pool_records([
        TrainingPoolRecord(doc_id="d1", project_id="p", original_filename="a.pdf", path="x",
                           business_domain="juridico", document_type="memorando", decision="approved", sha256="s1"),
        TrainingPoolRecord(doc_id="d2", project_id="p", original_filename="b.pdf", path="y",
                           business_domain="juridico", document_type="contrato", decision="approved", sha256="s2"),
    ])
    save_validation_set([
        ValidationSetEntry(file="v1.pdf", business_domain="juridico", document_type="memorando"),
    ])
    ds = classifier_datasets_root()
    (ds / "splits").mkdir(parents=True, exist_ok=True)
    (ds / "corpus.jsonl").write_text(
        json.dumps({"sha256": "s1", "business_domain": "juridico", "document_type": "memorando"}) + "\n"
        + json.dumps({"sha256": "s2", "business_domain": "juridico", "document_type": "contrato"}) + "\n",
        encoding="utf-8",
    )
    (ds / "splits" / "train.jsonl").write_text(
        json.dumps({"sha256": "s1", "business_domain": "juridico", "document_type": "memorando"}) + "\n",
        encoding="utf-8",
    )

    counts = rewrite_dataset_labels("document_type", "memorando", "comunicado")
    assert counts["training_pool"] == 1
    assert counts["validation_set"] == 1
    assert counts["corpus"] == 1
    assert counts["split_train"] == 1

    from app.evaluation_dataset import load_training_pool_records, load_validation_set

    records = load_training_pool_records()
    by_id = {r.doc_id: r for r in records}
    assert by_id["d1"].document_type == "comunicado"
    assert "taxonomy-migrated" in by_id["d1"].notes
    assert by_id["d2"].document_type == "contrato"  # não tocado
    assert by_id["d1"].sha256 == "s1"  # sha imutável
    assert load_validation_set()[0].document_type == "comunicado"


def test_rewrite_pending_suggestions(roots):
    project = roots / "proj_a"
    pending = project / "_TRIAGE_REVIEW" / "pending"
    pending.mkdir(parents=True)
    (pending / "doc1.json").write_text(json.dumps({
        "doc_id": "doc1", "business_domain": "memorando_dom", "suggested_business_domain": "juridico",
        "suggested_document_type": "memorando",
    }), encoding="utf-8")
    (pending / "doc2.json").write_text(json.dumps({
        "doc_id": "doc2", "suggested_document_type": "contrato",
    }), encoding="utf-8")

    changed = rewrite_pending_suggestions("document_type", "memorando", "comunicado")
    assert changed == 1
    data = json.loads((pending / "doc1.json").read_text(encoding="utf-8"))
    assert data["suggested_document_type"] == "comunicado"
    assert "taxonomy_migrated_at" in data
    data2 = json.loads((pending / "doc2.json").read_text(encoding="utf-8"))
    assert data2["suggested_document_type"] == "contrato"


def test_rename_in_raw_herda_aliases_e_reescreve_rules():
    raw = {
        "classification": {
            "business_domains": [
                {"key": "velho", "label": "Velho", "aliases": ["velho", "antigo"]},
                {"key": "novo", "label": "Novo", "aliases": ["novo"]},
            ],
            "routing_rules": [{"route_to": "velho", "keywords": ["x"]}, {"route_to": "outro_dom"}],
        },
        "layout": {"business_domain_folders": [
            {"business_domain": "velho", "folder": "velho"},
            {"business_domain": "novo", "folder": "novo"},
        ]},
    }
    changed = _rename_in_raw(raw, "business_domain", "velho", "novo", remove_old=True)
    assert changed is True
    bds = raw["classification"]["business_domains"]
    assert [b["key"] for b in bds] == ["novo"]
    # destino herdou aliases da origem, incluindo a própria key antiga
    assert set(bds[0]["aliases"]) >= {"novo", "velho", "antigo"}
    # routing rule apontando para a origem foi reescrita ANTES do filtro silencioso
    assert raw["classification"]["routing_rules"][0]["route_to"] == "novo"
    assert raw["classification"]["routing_rules"][1]["route_to"] == "outro_dom"
    # layout: linha da origem removida
    assert [f["business_domain"] for f in raw["layout"]["business_domain_folders"]] == ["novo"]


def test_rename_in_raw_document_type_herda_extensions():
    raw = {"classification": {"document_types": [
        {"key": "memo", "label": "Memo", "aliases": ["memo"], "extensions": ["msg"]},
        {"key": "comunicado", "label": "Comunicado", "aliases": ["comunicado"], "extensions": ["pdf"]},
    ]}}
    assert _rename_in_raw(raw, "document_type", "memo", "comunicado", remove_old=True) is True
    dts = raw["classification"]["document_types"]
    assert [d["key"] for d in dts] == ["comunicado"]
    assert set(dts[0]["extensions"]) == {"msg", "pdf"}
    assert "memo" in dts[0]["aliases"]


def test_plan_exige_destino_existente(roots):
    client = _fake_os()
    with pytest.raises(TaxonomyMigrationError, match="não existe"):
        plan_taxonomy_migration(
            kind="document_type", from_key="contrato", to_key="tipo_inexistente_xyz", os_client=client
        )


def test_plan_conta_documentos_e_datasets(roots):
    save_training_pool_records([
        TrainingPoolRecord(doc_id="d1", project_id="p", original_filename="a.pdf", path="x",
                           business_domain="juridico", document_type="memorando", decision="approved", sha256="s1"),
    ])
    client = _fake_os(count_by_project={"proj_a": 3, "proj_b": 1})
    # default template builtin tem 'contrato' como destino válido
    plan = plan_taxonomy_migration(
        kind="document_type", from_key="memorando", to_key="contrato", os_client=client
    )
    assert plan["documents_total"] == 4
    assert plan["documents_by_project"] == {"proj_a": 3, "proj_b": 1}
    assert plan["datasets"]["training_pool"] == 1


def test_apply_move_docs_sem_holdout_e_index_only_fora_de_areas(roots, tmp_path):
    project = roots / "proj_a"
    areas = project / "02_AREAS" / "juridico" / "parecer"
    areas.mkdir(parents=True)
    doc_file = areas / "doc_em_areas.pdf"
    doc_file.write_text("conteudo", encoding="utf-8")
    archive_file = project / "04_ARCHIVE" / "arquivado.pdf"
    archive_file.parent.mkdir(parents=True)
    archive_file.write_text("velho", encoding="utf-8")

    hits = [
        {"_id": "doc-areas", "_source": {
            "project_id": "proj_a", "path": str(doc_file), "original_filename": "doc_em_areas.pdf",
            "business_domain": "juridico", "document_type": "parecer",
        }},
        {"_id": "doc-archive", "_source": {
            "project_id": "proj_a", "path": str(archive_file), "original_filename": "arquivado.pdf",
            "business_domain": "juridico", "document_type": "parecer",
        }},
    ]
    client = _fake_os(count_by_project={"proj_a": 2}, hits=hits)
    relocate = MagicMock(return_value={"doc_id": "doc-areas"})
    profile = {"layout": {"areas_root": "02_AREAS"}}

    result = apply_taxonomy_migration(
        kind="document_type",
        from_key="parecer",
        to_key="contrato",
        os_client=client,
        relocate=relocate,
        load_project_context=lambda pid: (project, profile),
    )

    # doc em 02_AREAS → relocate (que no main vai com dataset_routing=False)
    relocate.assert_called_once()
    kwargs = relocate.call_args.kwargs
    assert kwargs["doc_id"] == "doc-areas"
    assert kwargs["target_document_type"] == "contrato"
    assert kwargs["target_business_domain"] == "juridico"
    assert kwargs["decision"] == "moved"
    # doc no archive → só metadados no índice
    client.update.assert_called_once()
    update_kwargs = client.update.call_args.kwargs
    assert update_kwargs["id"] == "doc-archive"
    assert update_kwargs["body"]["doc"]["document_type"] == "contrato"
    assert result["moved_total"] == 1
    assert result["index_only"] == 1
    assert any("índice" in w for w in result["warnings"])
    # taxonomia: default template (builtin→override em tmp) sem a origem, alias herdado
    raw = get_template("default")["profile"]
    dts = {d["key"]: d for d in raw["classification"]["document_types"]}
    assert "parecer" not in dts
    assert "parecer" in dts["contrato"]["aliases"]


def test_apply_e_idempotente(roots):
    client = _fake_os(count_by_project={})
    result1 = apply_taxonomy_migration(
        kind="document_type", from_key="parecer", to_key="contrato",
        os_client=client, relocate=MagicMock(), load_project_context=lambda pid: (roots, {}),
    )
    # segunda execução: origem já não existe em lugar nenhum — zero efeitos
    result2 = apply_taxonomy_migration(
        kind="document_type", from_key="parecer", to_key="contrato",
        os_client=client, relocate=MagicMock(), load_project_context=lambda pid: (roots, {}),
    )
    assert result2["moved_total"] == 0
    assert result2["datasets"]["training_pool"] == 0
    assert result2["templates_updated"] == []
    assert result1["templates_updated"] != []


def test_remove_recusa_com_uso_ativo(roots):
    client = _fake_os(count_by_project={"proj_a": 2})
    with pytest.raises(TaxonomyMigrationError, match="ainda é usada"):
        remove_taxonomy_entry(kind="document_type", key="contrato", os_client=client)


def test_remove_limpa_templates_quando_sem_uso(roots):
    client = _fake_os(count_by_project={})
    result = remove_taxonomy_entry(kind="document_type", key="parecer", os_client=client)
    assert "default" in result["templates_updated"]
    raw = get_template("default")["profile"]
    assert all(d["key"] != "parecer" for d in raw["classification"]["document_types"])

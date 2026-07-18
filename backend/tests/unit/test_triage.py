from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import app.dataset_holdout as holdout_module
import app.main as main_module
from app.auth import AuthContext
from app.ingestion import _append_index_md
from app.models import TriageDecisionRequest
from app.profile_store import create_default_profile, save_profile
from app.triage import list_pending


def test_list_pending_ignores_real_json_documents_in_pending(tmp_path: Path) -> None:
    project_root = tmp_path / "proj"
    pending_dir = project_root / "_TRIAGE_REVIEW" / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)

    real_json_doc = pending_dir / "mapeamento_visoes_analiticas.json"
    real_json_doc.write_text(
        json.dumps({"descricao": "documento json real", "campos": ["a", "b"]}, ensure_ascii=False),
        encoding="utf-8",
    )

    metadata_path = pending_dir / "doc-1.json"
    metadata_path.write_text(
        json.dumps(
            {
                "doc_id": "doc-1",
                "filename": real_json_doc.name,
                "project_id": "proj",
                "suggested_business_domain": "operacoes",
                "suggested_document_type": "relatorio",
                "confidence_score": 0.72,
                "reason": "triage_pending",
                "top_candidates": [{"business_domain": "operacoes", "score": 0.72}],
                "source_path": str(real_json_doc),
                "metadata_path": str(metadata_path),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    items = list_pending(project_root)

    assert len(items) == 1
    assert items[0].doc_id == "doc-1"
    assert items[0].filename == "mapeamento_visoes_analiticas.json"
    assert real_json_doc.exists()


def _prepare_pending_triage_item(
    *,
    tmp_path: Path,
    project_id: str,
    doc_id: str,
    naming_pattern: str,
    original_filename: str,
    canonical_filename: str,
    suggested_business_domain: str,
    suggested_document_type: str,
) -> tuple[Path, Path]:
    project_root = tmp_path / project_id
    project_root.mkdir(parents=True, exist_ok=True)

    profile = create_default_profile(
        project_root=project_root,
        project_id=project_id,
        project_label=project_id,
    )
    profile.naming.canonical_pattern = naming_pattern
    save_profile(project_root=project_root, profile=profile, updated_by="tests")

    pending_dir = project_root / "_TRIAGE_REVIEW" / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)
    source_path = pending_dir / f"{doc_id[:8]}__{original_filename}"
    source_path.write_text("conteudo de teste", encoding="utf-8")

    metadata_path = pending_dir / f"{doc_id}.json"
    metadata = {
        "doc_id": doc_id,
        "filename": source_path.name,
        "project_id": project_id,
        "suggested_business_domain": suggested_business_domain,
        "suggested_document_type": suggested_document_type,
        "suggested_path": f"02_AREAS/{suggested_business_domain}/{suggested_document_type}",
        "confidence_score": 0.72,
        "reason": "triage_pending",
        "top_candidates": [{"business_domain": suggested_business_domain, "score": 0.72}],
        "top_document_type_candidates": [{"document_type": suggested_document_type, "score": 0.72}],
        "source_path": str(source_path),
        "metadata_path": str(metadata_path),
        "original_filename": original_filename,
        "canonical_filename": canonical_filename,
        "document_type": suggested_document_type,
        "topics": [],
        "entities": [],
        "sha256": "triage_sha",
        "ingested_at": "2026-03-19T12:00:00+00:00",
        "naming_pattern": naming_pattern,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    _append_index_md(
        project_root,
        {
            "doc_id": doc_id,
            "project_id": project_id,
            "business_domain": suggested_business_domain,
            "original_filename": original_filename,
            "canonical_filename": canonical_filename,
            "decision": "triage_pending",
            "confidence_score": 0.72,
            "path": str(source_path),
            "naming_pattern": naming_pattern,
            "sha256": "triage_sha",
        },
    )
    return project_root, source_path


def _patch_triage_dependencies(monkeypatch, tmp_path: Path) -> tuple[MagicMock, MagicMock]:
    monkeypatch.setattr(main_module.settings, "projects_root", str(tmp_path), raising=False)
    monkeypatch.setattr(main_module.settings, "classifier_datasets_root", str(tmp_path / "datasets"), raising=False)
    # Holdout desligado: estes testes cobrem o caminho de treino do roteador
    monkeypatch.setattr(main_module.settings, "classifier_holdout_modulus", 0, raising=False)
    index_mock = MagicMock()
    training_pool_mock = MagicMock()
    monkeypatch.setattr(main_module, "index_document", index_mock)
    monkeypatch.setattr(holdout_module, "append_training_pool_record", training_pool_mock)
    return index_mock, training_pool_mock


def test_decide_triage_correct_recomputes_canonical_filename_and_upserts_index(
    monkeypatch,
    tmp_path: Path,
) -> None:
    project_id = "triage_project_a"
    doc_id = "doc-correct-a"
    naming_pattern = "{date}__{project}__{business_domain}__{original_name}"
    original_filename = "E2E080_Relatorio_Fiscal_Beta.txt"
    initial_canonical = "20260319__triage_project_a__operacoes__E2E080_Relatorio_Fiscal_Beta__v03.txt"
    expected_canonical = "20260319__triage_project_a__fiscal__E2E080_Relatorio_Fiscal_Beta__v03.txt"

    project_root, source_path = _prepare_pending_triage_item(
        tmp_path=tmp_path,
        project_id=project_id,
        doc_id=doc_id,
        naming_pattern=naming_pattern,
        original_filename=original_filename,
        canonical_filename=initial_canonical,
        suggested_business_domain="operacoes",
        suggested_document_type="relatorio",
    )
    index_mock, training_pool_mock = _patch_triage_dependencies(monkeypatch, tmp_path)

    result = main_module.decide_triage(
        project_id,
        doc_id,
        TriageDecisionRequest(
            action="correct",
            target_business_domain="fiscal",
            target_document_type="relatorio",
        ),
        auth=AuthContext(name="test", allowed_projects=("*",)),
    )

    assert result == {"status": "ok", "action": "corrected", "doc_id": doc_id}
    final_path = project_root / "02_AREAS" / "fiscal" / "relatorio" / expected_canonical
    assert final_path.exists()
    assert not source_path.exists()

    index_mock.assert_called_once()
    indexed_payload = index_mock.call_args.args[1]
    assert indexed_payload["canonical_filename"] == expected_canonical
    assert indexed_payload["path"] == str(final_path)
    assert indexed_payload["naming_pattern"] == naming_pattern
    training_pool_mock.assert_called_once()

    resolved_meta = json.loads(
        (project_root / "_TRIAGE_REVIEW" / "resolved" / f"{doc_id}.json").read_text(encoding="utf-8")
    )
    assert resolved_meta["canonical_filename"] == expected_canonical
    assert resolved_meta["filename"] == expected_canonical
    assert resolved_meta["source_path"] == str(final_path)
    assert resolved_meta["path"] == str(final_path)
    assert resolved_meta["final_path"] == str(final_path)
    assert resolved_meta["business_domain"] == "fiscal"
    assert resolved_meta["document_type"] == "relatorio"

    index_text = (project_root / "_INDEX.md").read_text(encoding="utf-8")
    assert expected_canonical in index_text
    assert initial_canonical not in index_text
    assert " | corrected | " in index_text
    assert " | triage_pending | " not in index_text
    assert resolved_meta["training_pool_status"] == "appended"
    assert resolved_meta["training_pool_record_path"].startswith("training_pool/files/")
    assert resolved_meta["training_pool_sha256"]


def test_decide_triage_correct_updates_document_type_token_and_preserves_ingest_date(
    monkeypatch,
    tmp_path: Path,
) -> None:
    project_id = "triage_project_b"
    doc_id = "doc-correct-b"
    naming_pattern = "{date}__{project}__{business_domain}__{document_type}__{original_name}"
    original_filename = "E2E080_Status_Executivo_Twist.txt"
    initial_canonical = "20260319__triage_project_b__operacoes__apresentacao__E2E080_Status_Executivo_Twist__v02.txt"
    expected_canonical = "20260319__triage_project_b__fiscal__relatorio__E2E080_Status_Executivo_Twist__v02.txt"

    project_root, _source_path = _prepare_pending_triage_item(
        tmp_path=tmp_path,
        project_id=project_id,
        doc_id=doc_id,
        naming_pattern=naming_pattern,
        original_filename=original_filename,
        canonical_filename=initial_canonical,
        suggested_business_domain="operacoes",
        suggested_document_type="apresentacao",
    )
    index_mock, _training_pool_mock = _patch_triage_dependencies(monkeypatch, tmp_path)

    main_module.decide_triage(
        project_id,
        doc_id,
        TriageDecisionRequest(
            action="correct",
            target_business_domain="fiscal",
            target_document_type="relatorio",
        ),
        auth=AuthContext(name="test", allowed_projects=("*",)),
    )

    final_path = project_root / "02_AREAS" / "fiscal" / "relatorio" / expected_canonical
    assert final_path.exists()

    indexed_payload = index_mock.call_args.args[1]
    assert indexed_payload["canonical_filename"] == expected_canonical
    assert indexed_payload["canonical_filename"].startswith("20260319__")
    assert indexed_payload["canonical_filename"].endswith("__v02.txt")

    resolved_meta = json.loads(
        (project_root / "_TRIAGE_REVIEW" / "resolved" / f"{doc_id}.json").read_text(encoding="utf-8")
    )
    assert resolved_meta["canonical_filename"] == expected_canonical
    assert resolved_meta["document_type"] == "relatorio"

    index_text = (project_root / "_INDEX.md").read_text(encoding="utf-8")
    assert expected_canonical in index_text
    assert initial_canonical not in index_text


def test_decide_triage_skips_training_pool_when_document_overlaps_validation_set(
    monkeypatch,
    tmp_path: Path,
) -> None:
    project_id = "triage_project_overlap"
    doc_id = "doc-overlap-a"
    naming_pattern = "{date}__{project}__{business_domain}__{original_name}"
    original_filename = "Contrato_Validacao.pdf"
    canonical_filename = "20260319__triage_project_overlap__juridico__Contrato_Validacao__v01.pdf"

    project_root, source_path = _prepare_pending_triage_item(
        tmp_path=tmp_path,
        project_id=project_id,
        doc_id=doc_id,
        naming_pattern=naming_pattern,
        original_filename=original_filename,
        canonical_filename=canonical_filename,
        suggested_business_domain="juridico",
        suggested_document_type="contrato",
    )
    index_mock, training_pool_mock = _patch_triage_dependencies(monkeypatch, tmp_path)
    snapshot_mock = MagicMock()
    monkeypatch.setattr(holdout_module, "materialize_training_pool_snapshot", snapshot_mock)
    monkeypatch.setattr(
        holdout_module, "_update_validation_labels_by_sha", lambda *_args, **_kwargs: ["validation.pdf"]
    )

    result = main_module.decide_triage(
        project_id,
        doc_id,
        TriageDecisionRequest(
            action="approve",
        ),
        auth=AuthContext(name="test", allowed_projects=("*",)),
    )

    assert result == {"status": "ok", "action": "approved", "doc_id": doc_id}
    final_path = project_root / "02_AREAS" / "juridico" / "contrato" / canonical_filename
    assert final_path.exists()
    assert not source_path.exists()
    index_mock.assert_called_once()
    training_pool_mock.assert_not_called()
    snapshot_mock.assert_not_called()

    resolved_meta = json.loads(
        (project_root / "_TRIAGE_REVIEW" / "resolved" / f"{doc_id}.json").read_text(encoding="utf-8")
    )
    assert resolved_meta["training_pool_status"] == "skipped_overlap_with_validation_set"
    assert resolved_meta["training_pool_validation_files"] == ["validation.pdf"]


def test_decisao_concorrente_recebe_409_e_claim_restaura_em_erro(monkeypatch, tmp_path: Path) -> None:
    project_id = "triage_race"
    doc_id = "doc-race"
    project_root, _source = _prepare_pending_triage_item(
        tmp_path=tmp_path, project_id=project_id, doc_id=doc_id,
        naming_pattern="{date}__{project}__{business_domain}__{original_name}",
        original_filename="a.txt", canonical_filename="a.txt",
        suggested_business_domain="juridico", suggested_document_type="contrato",
    )
    _patch_triage_dependencies(monkeypatch, tmp_path)
    pending = project_root / "_TRIAGE_REVIEW" / "pending"

    # Simula claim em andamento por outra requisição
    (pending / f"{doc_id}.json").rename(pending / f"{doc_id}.json.processing")
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        main_module.decide_triage(project_id, doc_id, TriageDecisionRequest(action="approve"),
                                  auth=AuthContext(name="t", allowed_projects=("*",)))
    assert exc.value.status_code == 409
    # desfaz para o próximo cenário
    (pending / f"{doc_id}.json.processing").rename(pending / f"{doc_id}.json")

    # Ação inválida: o claim deve ser DEVOLVIDO à fila (item não some)
    with pytest.raises(HTTPException) as exc2:
        main_module.decide_triage(project_id, doc_id, TriageDecisionRequest(action="banana"),
                                  auth=AuthContext(name="t", allowed_projects=("*",)))
    assert exc2.value.status_code == 400
    assert (pending / f"{doc_id}.json").exists()
    assert not (pending / f"{doc_id}.json.processing").exists()


def test_rejeitados_listar_restaurar_excluir(monkeypatch, tmp_path: Path) -> None:
    project_id = "triage_rej"
    doc_id = "doc-rej"
    project_root, _source = _prepare_pending_triage_item(
        tmp_path=tmp_path, project_id=project_id, doc_id=doc_id,
        naming_pattern="{date}__{project}__{business_domain}__{original_name}",
        original_filename="rejeitavel.txt", canonical_filename="rejeitavel.txt",
        suggested_business_domain="juridico", suggested_document_type="contrato",
    )
    _patch_triage_dependencies(monkeypatch, tmp_path)
    auth = AuthContext(name="t", allowed_projects=("*",))

    result = main_module.decide_triage(project_id, doc_id, TriageDecisionRequest(action="reject", note="teste"), auth=auth)
    assert result["action"] == "rejected"

    listed = main_module.list_rejected_triage(project_id, auth=auth)
    assert len(listed) == 1
    assert listed[0]["doc_id"] == doc_id
    assert listed[0]["decision"] == "rejected"
    assert listed[0]["file_exists"] is True

    restored = main_module.restore_rejected_triage(project_id, doc_id, auth=auth)
    assert restored["action"] == "restored"
    pending = project_root / "_TRIAGE_REVIEW" / "pending"
    assert (pending / f"{doc_id}.json").exists()
    assert any(p.name.startswith(doc_id[:8]) for p in pending.iterdir() if p.suffix == ".txt")
    assert main_module.list_rejected_triage(project_id, auth=auth) == []

    # rejeita de novo e exclui definitivamente
    main_module.decide_triage(project_id, doc_id, TriageDecisionRequest(action="reject"), auth=auth)
    deleted = main_module.delete_rejected_triage(project_id, doc_id, auth=auth)
    assert deleted["action"] == "deleted"
    rejected_dir = project_root / "_TRIAGE_REVIEW" / "rejected"
    assert list(rejected_dir.glob("*.json")) == []
    assert not any(p.suffix == ".txt" for p in rejected_dir.iterdir())


def test_excluir_rejeitado_marca_deleted_no_historico(monkeypatch, tmp_path: Path) -> None:
    """A linha do Processamentos vira trilha de auditoria: rejeitar grava
    'rejected' e excluir grava 'deleted' — a UI mostra o badge fiel."""
    from app.ingest_history import append_ingest_entry, load_ingest_history

    project_id = "triage_hist"
    doc_id = "doc-hist"
    project_root, _source = _prepare_pending_triage_item(
        tmp_path=tmp_path, project_id=project_id, doc_id=doc_id,
        naming_pattern="{date}__{project}__{business_domain}__{original_name}",
        original_filename="auditavel.txt", canonical_filename="auditavel.txt",
        suggested_business_domain="juridico", suggested_document_type="contrato",
    )
    _patch_triage_dependencies(monkeypatch, tmp_path)
    auth = AuthContext(name="t", allowed_projects=("*",))
    append_ingest_entry(project_root, scan_result={
        "project_id": project_id, "processed_count": 1, "failed_count": 0,
        "items": [{"doc_id": doc_id, "original_filename": "auditavel.txt", "decision": "triage_pending"}],
        "errors": [],
    })

    main_module.decide_triage(project_id, doc_id, TriageDecisionRequest(action="reject"), auth=auth)
    entries = load_ingest_history(project_root)
    assert entries[0]["items"][0]["decision"] == "rejected"

    main_module.delete_rejected_triage(project_id, doc_id, auth=auth)
    entries = load_ingest_history(project_root)
    assert entries[0]["items"][0]["decision"] == "deleted"

from __future__ import annotations

import json
from pathlib import Path

from app.evaluation_dataset import TrainingPoolRecord, training_pool_files_dir
from app.utils import sha256_file
from scripts.backfill_training_pool import collect_training_pool_records_from_resolved, merge_training_pool_records


def _configure_dataset_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.classifier_registry.repo_root", lambda: tmp_path)
    monkeypatch.setenv("CLASSIFIER_DATASETS_ROOT", str(tmp_path / "datasets"))


def test_collect_training_pool_records_from_resolved_reads_only_reviewed_docs(tmp_path: Path, monkeypatch) -> None:
    _configure_dataset_paths(monkeypatch, tmp_path)
    project_root = tmp_path / "proj"
    resolved_dir = project_root / "_TRIAGE_REVIEW" / "resolved"
    resolved_dir.mkdir(parents=True, exist_ok=True)
    approved_file = project_root / "02_AREAS" / "juridico" / "contrato.pdf"
    approved_file.parent.mkdir(parents=True, exist_ok=True)
    approved_file.write_bytes(b"pdf")

    (resolved_dir / "doc-1.json").write_text(
        json.dumps(
            {
                "doc_id": "doc-1",
                "decision": "approved",
                "processed_at": "2026-03-18T12:00:00+00:00",
                "original_filename": "Contrato.pdf",
                "final_path": str(approved_file),
                "business_domain": "juridico",
                "document_type": "contrato",
                "topics": ["contratos"],
                "entities": [{"type": "contrato", "value": "123"}],
                "decision_note": "revisado",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (resolved_dir / "doc-2.json").write_text(
        json.dumps(
            {
                "doc_id": "doc-2",
                "decision": "rejected",
                "original_filename": "Ignorar.pdf",
                "final_path": str(project_root / "missing.pdf"),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("scripts.backfill_training_pool.load_project_profile", lambda *_args: {"project_id": "proj-1"})
    monkeypatch.setattr("scripts.backfill_training_pool.triage_resolved_dir", lambda *_args: resolved_dir)
    monkeypatch.setattr("scripts.backfill_training_pool._validation_sha_index", lambda: {})

    records, skipped = collect_training_pool_records_from_resolved(project_root)

    assert len(records) == 1
    assert records[0].project_id == "proj-1"
    assert records[0].doc_id == "doc-1"
    assert records[0].path == "training_pool/files/doc-1__Contrato.pdf"
    assert records[0].source_path == str(approved_file)
    assert (training_pool_files_dir() / "doc-1__Contrato.pdf").exists()
    assert records[0].notes == "backfill_resolved_triage: revisado"
    assert skipped == [{"metadata": str(resolved_dir / "doc-2.json"), "reason": "unsupported_decision:rejected"}]


def test_collect_training_pool_records_from_resolved_skips_validation_overlap(tmp_path: Path, monkeypatch) -> None:
    _configure_dataset_paths(monkeypatch, tmp_path)
    project_root = tmp_path / "proj"
    resolved_dir = project_root / "_TRIAGE_REVIEW" / "resolved"
    resolved_dir.mkdir(parents=True, exist_ok=True)
    approved_file = project_root / "02_AREAS" / "juridico" / "contrato.pdf"
    approved_file.parent.mkdir(parents=True, exist_ok=True)
    approved_file.write_bytes(b"same-content")

    meta_path = resolved_dir / "doc-1.json"
    meta_path.write_text(
        json.dumps(
            {
                "doc_id": "doc-1",
                "decision": "approved",
                "original_filename": "Contrato.pdf",
                "final_path": str(approved_file),
                "business_domain": "juridico",
                "document_type": "contrato",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("scripts.backfill_training_pool.load_project_profile", lambda *_args: {"project_id": "proj-1"})
    monkeypatch.setattr("scripts.backfill_training_pool.triage_resolved_dir", lambda *_args: resolved_dir)
    monkeypatch.setattr(
        "scripts.backfill_training_pool._validation_sha_index",
        lambda: {sha256_file(approved_file): ["validation.pdf"]},
    )

    records, skipped = collect_training_pool_records_from_resolved(project_root)

    assert records == []
    assert skipped == [
        {
            "metadata": str(meta_path),
            "reason": "overlap_with_validation_set",
            "validation_files": ["validation.pdf"],
        }
    ]


def test_merge_training_pool_records_can_replace_project_records() -> None:
    existing = [
        TrainingPoolRecord(
            doc_id="old-1",
            project_id="proj-1",
            original_filename="Old.pdf",
            path="/tmp/old.pdf",
            business_domain="juridico",
            document_type="contrato",
            decision="approved",
        ),
        TrainingPoolRecord(
            doc_id="keep-1",
            project_id="proj-2",
            original_filename="Keep.pdf",
            path="/tmp/keep.pdf",
            business_domain="financeiro",
            document_type="relatorio",
            decision="approved",
        ),
    ]
    incoming = [
        TrainingPoolRecord(
            doc_id="new-1",
            project_id="proj-1",
            original_filename="New.pdf",
            path="/tmp/new.pdf",
            business_domain="ti",
            document_type="contrato",
            decision="corrected",
        )
    ]

    merged = merge_training_pool_records(existing, incoming, replace_project_ids={"proj-1"})

    assert [(record.project_id, record.doc_id) for record in merged] == [("proj-1", "new-1"), ("proj-2", "keep-1")]


def test_collect_training_pool_records_from_resolved_uses_project_fallback_path(tmp_path: Path, monkeypatch) -> None:
    _configure_dataset_paths(monkeypatch, tmp_path)
    project_root = tmp_path / "proj"
    resolved_dir = project_root / "_TRIAGE_REVIEW" / "resolved"
    resolved_dir.mkdir(parents=True, exist_ok=True)
    approved_file = project_root / "02_AREAS" / "operacoes" / "contrato" / "20260318__proj__arquivo__v01.pdf"
    approved_file.parent.mkdir(parents=True, exist_ok=True)
    approved_file.write_bytes(b"pdf")

    (resolved_dir / "doc-1.json").write_text(
        json.dumps(
            {
                "doc_id": "doc-1",
                "decision": "corrected",
                "original_filename": "arquivo.pdf",
                "final_path": "/projects/proj/02_AREAS/operacoes/contrato/20260318__proj__arquivo__v01.pdf",
                "canonical_filename": "20260318__proj__arquivo__v01.pdf",
                "business_domain": "operacoes",
                "document_type": "contrato",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("scripts.backfill_training_pool.load_project_profile", lambda *_args: {"project_id": "proj-1"})
    monkeypatch.setattr("scripts.backfill_training_pool.triage_resolved_dir", lambda *_args: resolved_dir)
    monkeypatch.setattr("scripts.backfill_training_pool._validation_sha_index", lambda: {})

    records, skipped = collect_training_pool_records_from_resolved(project_root)

    assert skipped == []
    assert len(records) == 1
    assert records[0].path == "training_pool/files/doc-1__arquivo.pdf"
    assert records[0].source_path == str(approved_file)

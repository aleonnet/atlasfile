from __future__ import annotations

import json
from pathlib import Path

from app.evaluation_dataset import (
    TrainingPoolRecord,
    append_training_pool_record,
    dataset_relative_path,
    load_validation_set,
    load_training_pool_records,
    materialize_training_pool_snapshot,
    save_training_pool_records,
    sync_validation_entries_from_files,
    training_pool_files_dir,
    training_pool_records_path,
    validation_set_expected_path,
)
from app.utils import sha256_file


def _configure_dataset_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.classifier_registry.repo_root", lambda: tmp_path)
    monkeypatch.setenv("CLASSIFIER_DATASETS_ROOT", str(tmp_path / "datasets"))


def test_sync_validation_entries_from_files_creates_empty_entries(tmp_path: Path, monkeypatch) -> None:
    _configure_dataset_paths(monkeypatch, tmp_path)
    files_dir = tmp_path / "datasets" / "validation_set" / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    (files_dir / "Contrato_X.pdf").write_bytes(b"pdf")

    entries = sync_validation_entries_from_files()

    assert len(entries) == 1
    assert entries[0].file == "Contrato_X.pdf"
    saved = json.loads(validation_set_expected_path().read_text(encoding="utf-8"))
    assert saved[0]["document_type"] == ""
    assert saved[0]["business_domain"] == ""


def test_append_training_pool_record_writes_jsonl(tmp_path: Path, monkeypatch) -> None:
    _configure_dataset_paths(monkeypatch, tmp_path)

    append_training_pool_record(
        TrainingPoolRecord(
            doc_id="doc-1",
            project_id="proj-1",
            original_filename="Contrato_X.pdf",
            path="/tmp/Contrato_X.pdf",
            business_domain="juridico",
            document_type="contrato",
            decision="corrected",
            topics=["contratos"],
            entities=[{"type": "contrato", "value": "4600052462"}],
            notes="revisado manualmente",
        )
    )

    lines = training_pool_records_path().read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["business_domain"] == "juridico"
    assert payload["document_type"] == "contrato"
    assert payload["decision"] == "corrected"


def test_save_training_pool_records_roundtrips_jsonl(tmp_path: Path, monkeypatch) -> None:
    _configure_dataset_paths(monkeypatch, tmp_path)
    records = [
        TrainingPoolRecord(
            doc_id="doc-1",
            project_id="proj-1",
            original_filename="Contrato_X.pdf",
            path="/tmp/Contrato_X.pdf",
            business_domain="juridico",
            document_type="contrato",
            decision="approved",
        ),
        TrainingPoolRecord(
            doc_id="doc-2",
            project_id="proj-1",
            original_filename="Relatorio_Y.pdf",
            path="/tmp/Relatorio_Y.pdf",
            business_domain="financeiro",
            document_type="relatorio",
            decision="corrected",
        ),
    ]

    save_training_pool_records(records)

    loaded = load_training_pool_records()
    assert [record.doc_id for record in loaded] == ["doc-1", "doc-2"]


def test_load_training_pool_records_normalizes_legacy_config_paths(tmp_path: Path, monkeypatch) -> None:
    _configure_dataset_paths(monkeypatch, tmp_path)
    operational_file = training_pool_files_dir() / "doc-1__Contrato_X.pdf"
    operational_file.parent.mkdir(parents=True, exist_ok=True)
    operational_file.write_bytes(b"pdf-content")
    legacy_record = TrainingPoolRecord(
        doc_id="doc-1",
        project_id="proj-1",
        original_filename="Contrato_X.pdf",
        path="/workspace/config/training_pool/files/doc-1__Contrato_X.pdf",
        business_domain="juridico",
        document_type="contrato",
        decision="approved",
    )
    training_pool_records_path().write_text(
        json.dumps(legacy_record.model_dump(mode="json"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    loaded = load_training_pool_records()

    assert loaded[0].path == "training_pool/files/doc-1__Contrato_X.pdf"
    persisted = training_pool_records_path().read_text(encoding="utf-8")
    assert "/workspace/config/training_pool/files" not in persisted


def test_materialize_training_pool_snapshot_copies_to_operational_root(tmp_path: Path, monkeypatch) -> None:
    _configure_dataset_paths(monkeypatch, tmp_path)
    source = tmp_path / "project" / "Contrato_X.pdf"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"pdf-content")

    snapshot_path, digest = materialize_training_pool_snapshot(
        source_path=source,
        doc_id="doc-1",
        original_filename="Contrato_X.pdf",
    )

    assert snapshot_path.parent == training_pool_files_dir()
    assert snapshot_path.read_bytes() == b"pdf-content"
    assert digest == sha256_file(source)
    assert dataset_relative_path(snapshot_path) == f"training_pool/files/doc-1__Contrato_X.pdf"


def test_load_validation_set_starts_empty_without_repo_seed(tmp_path: Path, monkeypatch) -> None:
    _configure_dataset_paths(monkeypatch, tmp_path)
    seed_expected = tmp_path / "config" / "validation_set" / "expected.json"
    seed_files_dir = tmp_path / "config" / "validation_set" / "files"
    seed_expected.parent.mkdir(parents=True, exist_ok=True)
    seed_files_dir.mkdir(parents=True, exist_ok=True)
    seed_expected.write_text(
        json.dumps(
            [{"file": "Contrato_X.pdf", "business_domain": "juridico", "document_type": "contrato"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (seed_files_dir / "Contrato_X.pdf").write_bytes(b"seed-pdf")

    entries = load_validation_set()
    assert entries == []
    assert validation_set_expected_path().read_text(encoding="utf-8") == "[]\n"
    assert not (tmp_path / "datasets" / "validation_set" / "files" / "Contrato_X.pdf").exists()

from __future__ import annotations

import json
from pathlib import Path

from app.evaluation_dataset import (
    TrainingPoolRecord,
    append_training_pool_record,
    load_training_pool_records,
    save_training_pool_records,
    sync_validation_entries_from_files,
    training_pool_records_path,
    validation_set_expected_path,
)


def test_sync_validation_entries_from_files_creates_empty_entries(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("app.evaluation_dataset.repo_root", lambda: tmp_path)
    files_dir = tmp_path / "config" / "validation_set" / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    (files_dir / "Contrato_X.pdf").write_bytes(b"pdf")

    entries = sync_validation_entries_from_files()

    assert len(entries) == 1
    assert entries[0].file == "Contrato_X.pdf"
    saved = json.loads(validation_set_expected_path().read_text(encoding="utf-8"))
    assert saved[0]["document_type"] == ""
    assert saved[0]["business_domain"] == ""


def test_append_training_pool_record_writes_jsonl(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("app.evaluation_dataset.repo_root", lambda: tmp_path)

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
    monkeypatch.setattr("app.evaluation_dataset.repo_root", lambda: tmp_path)
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

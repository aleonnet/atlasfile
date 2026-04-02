from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def dataset_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Set up a minimal dataset scaffold in tmp_path."""
    ds_root = tmp_path / "datasets"
    val_dir = ds_root / "validation_set" / "files"
    val_dir.mkdir(parents=True)
    tp_dir = ds_root / "training_pool" / "files"
    tp_dir.mkdir(parents=True)
    (ds_root / "validation_set" / "expected.json").write_text("[]", encoding="utf-8")
    (ds_root / "training_pool" / "records.jsonl").write_text("", encoding="utf-8")

    monkeypatch.setenv("CLASSIFIER_DATASETS_ROOT", str(ds_root))
    monkeypatch.setenv("PROJECTS_ROOT", str(tmp_path))
    return ds_root


def _write_file(ds_root: Path, pool: str, name: str, content: str = "test") -> Path:
    path = ds_root / pool / "files" / name
    path.write_text(content, encoding="utf-8")
    return path


def test_inject_creates_valid_record(dataset_env: Path) -> None:
    from scripts.inject_training_records import inject

    _write_file(dataset_env, "training_pool", "doc_a.pdf", "content of doc a")

    injected, skipped = inject(
        ["doc_a.pdf"],
        business_domain="juridico",
        document_type="contrato",
    )

    assert injected == 1
    assert skipped == 0

    lines = (dataset_env / "training_pool" / "records.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["business_domain"] == "juridico"
    assert record["document_type"] == "contrato"
    assert record["decision"] == "manual_inject"
    assert record["sha256"]
    assert record["doc_id"].startswith("inject_")


def test_inject_skips_duplicate_sha256(dataset_env: Path) -> None:
    from scripts.inject_training_records import inject

    _write_file(dataset_env, "training_pool", "doc_b.pdf", "same content")

    inject(["doc_b.pdf"], business_domain="ti", document_type="ata")
    injected, skipped = inject(["doc_b.pdf"], business_domain="ti", document_type="ata")

    assert injected == 0
    assert skipped == 1

    lines = (dataset_env / "training_pool" / "records.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1


def test_inject_aborts_on_validation_overlap(dataset_env: Path) -> None:
    from scripts.inject_training_records import inject

    content = "shared content between val and train"
    _write_file(dataset_env, "validation_set", "val_doc.pdf", content)

    val_entry = {
        "file": "val_doc.pdf",
        "business_domain": "juridico",
        "document_type": "contrato",
    }
    (dataset_env / "validation_set" / "expected.json").write_text(
        json.dumps([val_entry]), encoding="utf-8",
    )

    _write_file(dataset_env, "training_pool", "train_doc.pdf", content)

    with pytest.raises(SystemExit):
        inject(["train_doc.pdf"], business_domain="juridico", document_type="contrato")

    lines = (dataset_env / "training_pool" / "records.jsonl").read_text(encoding="utf-8").strip()
    assert lines == ""


def test_inject_dry_run_does_not_write(dataset_env: Path) -> None:
    from scripts.inject_training_records import inject

    _write_file(dataset_env, "training_pool", "doc_dry.pdf", "dry run content")

    injected, skipped = inject(
        ["doc_dry.pdf"],
        business_domain="fiscal",
        document_type="nota_fiscal",
        dry_run=True,
    )

    assert injected == 1
    lines = (dataset_env / "training_pool" / "records.jsonl").read_text(encoding="utf-8").strip()
    assert lines == ""


def test_inject_file_not_found_skips(dataset_env: Path) -> None:
    from scripts.inject_training_records import inject

    injected, skipped = inject(
        ["nonexistent.pdf"],
        business_domain="ti",
        document_type="especificacao",
    )

    assert injected == 0
    assert skipped == 1

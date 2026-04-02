"""Tests for corpus splits loading and classifier_cycle integration with splits."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evaluation_dataset import (
    ValidationSetEntry,
    load_split_as_training_records,
    load_split_as_validation_entries,
    splits_available,
)


def _setup_corpus_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Create a minimal corpus + splits structure in tmp_path."""
    monkeypatch.setattr("app.classifier_registry.repo_root", lambda: tmp_path)
    monkeypatch.setenv("CLASSIFIER_DATASETS_ROOT", str(tmp_path / "datasets"))

    corpus_dir = tmp_path / "datasets" / "corpus_files"
    corpus_dir.mkdir(parents=True)
    splits_dir = tmp_path / "datasets" / "splits"
    splits_dir.mkdir(parents=True)

    # Create sample corpus files
    for i in range(1, 6):
        (corpus_dir / f"doc_{i:04d}__test_{i}.txt").write_text(f"content {i}", encoding="utf-8")

    # Create train split (3 docs)
    train = [
        {"doc_id": f"doc_{i:04d}", "corpus_file": f"doc_{i:04d}__test_{i}.txt",
         "original_filename": f"test_{i}.txt", "sha256": f"sha{i}",
         "business_domain": "juridico" if i <= 2 else "financeiro",
         "document_type": "contrato" if i <= 2 else "planilha"}
        for i in range(1, 4)
    ]
    (splits_dir / "train.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in train) + "\n",
        encoding="utf-8",
    )

    # Create validation split (2 docs)
    val = [
        {"doc_id": f"doc_{i:04d}", "corpus_file": f"doc_{i:04d}__test_{i}.txt",
         "original_filename": f"test_{i}.txt", "sha256": f"sha{i}",
         "business_domain": "juridico", "document_type": "contrato"}
        for i in range(4, 6)
    ]
    (splits_dir / "validation.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in val) + "\n",
        encoding="utf-8",
    )

    return tmp_path


def test_splits_available_true(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_corpus_env(monkeypatch, tmp_path)
    assert splits_available() is True


def test_splits_available_false(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.classifier_registry.repo_root", lambda: tmp_path)
    monkeypatch.setenv("CLASSIFIER_DATASETS_ROOT", str(tmp_path / "datasets"))
    (tmp_path / "datasets").mkdir(parents=True)
    assert splits_available() is False


def test_load_split_as_validation_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_corpus_env(monkeypatch, tmp_path)
    entries = load_split_as_validation_entries("validation")

    assert len(entries) == 2
    assert all(isinstance(e, ValidationSetEntry) for e in entries)
    assert entries[0].file == "doc_0004__test_4.txt"
    assert entries[0].business_domain == "juridico"
    assert entries[0].document_type == "contrato"
    assert entries[0].is_labeled()


def test_load_split_as_training_records(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_corpus_env(monkeypatch, tmp_path)
    records = load_split_as_training_records("train")

    assert len(records) == 3
    assert records[0].doc_id == "doc_0001"
    assert records[0].business_domain == "juridico"
    assert records[0].original_filename == "test_1.txt"
    assert "corpus_files/" in records[0].path


def test_train_val_no_overlap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_corpus_env(monkeypatch, tmp_path)
    train = load_split_as_training_records("train")
    val = load_split_as_validation_entries("validation")

    train_ids = {r.doc_id for r in train}
    val_ids = {e.file for e in val}  # file = corpus_file = unique per doc

    # doc_ids should be disjoint
    train_doc_ids = {r.doc_id for r in train}
    val_doc_ids = set()
    for e in val:
        # Extract doc_id from corpus_file pattern "doc_NNNN__name.ext"
        parts = e.file.split("__", 1)
        if parts:
            val_doc_ids.add(parts[0])

    assert not (train_doc_ids & val_doc_ids)


def test_benchmark_llm_skipped_without_api_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM benchmark must skip gracefully when OPENAI_API_KEY is not set."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from app.classifier_cycle import benchmark_llm_candidate

    profile = {"classification": {"business_domains": [], "document_types": []}}
    examples = [
        {
            "entry": ValidationSetEntry(file="test.txt", business_domain="juridico", document_type="contrato"),
            "file_path": str(tmp_path / "test.txt"),
            "text": "test content",
        }
    ]

    result = benchmark_llm_candidate(profile=profile, validation_examples=examples)

    assert result["summary"]["mode"] == "llm"
    assert result["summary"]["skipped"] is True
    assert "llm_api_key_not_configured" in result["summary"]["skip_reason"]
    assert result["results"] == []

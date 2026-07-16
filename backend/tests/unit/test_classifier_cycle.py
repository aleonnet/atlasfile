from __future__ import annotations

from pathlib import Path

from app.classifier_cycle import build_dataset_manifest, choose_champion_mode
from app.classifier_registry import ClassifierRegistry
from app.evaluation_dataset import (
    TrainingPoolRecord,
    ValidationSetEntry,
    load_training_pool_records,
    save_training_pool_records,
    save_validation_set,
)
from scripts.run_classifier_cycle import resolve_profile_arg


def test_choose_champion_mode_prefers_best_exact_match() -> None:
    registry = ClassifierRegistry(champion_mode="bootstrap")
    mode, summary = choose_champion_mode(
        registry=registry,
        training_pool_records=120,
        benchmarks={
            "bootstrap": {
                "summary": {
                    "mode": "bootstrap",
                    "total_labeled": 50,
                    "business_domain_accuracy": 0.52,
                    "document_type_accuracy": 0.80,
                    "exact_match_accuracy": 0.48,
                }
            },
            "sparse_logreg": {
                "summary": {
                    "mode": "sparse_logreg",
                    "total_labeled": 50,
                    "business_domain_accuracy": 0.58,
                    "document_type_accuracy": 0.82,
                    "exact_match_accuracy": 0.50,
                }
            },
        },
    )

    assert mode == "sparse_logreg"
    assert summary.exact_match_accuracy == 0.50


def test_choose_champion_mode_keeps_current_on_full_tie() -> None:
    registry = ClassifierRegistry(champion_mode="bootstrap")
    mode, _summary = choose_champion_mode(
        registry=registry,
        training_pool_records=120,
        benchmarks={
            "bootstrap": {
                "summary": {
                    "mode": "bootstrap",
                    "total_labeled": 50,
                    "business_domain_accuracy": 0.52,
                    "document_type_accuracy": 0.80,
                    "exact_match_accuracy": 0.48,
                }
            },
        },
    )

    assert mode == "bootstrap"


def test_choose_champion_mode_considers_llm() -> None:
    registry = ClassifierRegistry(champion_mode="bootstrap")
    mode, summary = choose_champion_mode(
        registry=registry,
        training_pool_records=50,
        benchmarks={
            "bootstrap": {
                "summary": {
                    "mode": "bootstrap",
                    "total_labeled": 50,
                    "business_domain_accuracy": 0.52,
                    "document_type_accuracy": 0.80,
                    "exact_match_accuracy": 0.48,
                }
            },
            "sparse_logreg": {
                "summary": {
                    "mode": "sparse_logreg",
                    "total_labeled": 50,
                    "business_domain_accuracy": 0.58,
                    "document_type_accuracy": 0.82,
                    "exact_match_accuracy": 0.50,
                }
            },
            "llm": {
                "summary": {
                    "mode": "llm",
                    "total_labeled": 50,
                    "business_domain_accuracy": 0.70,
                    "document_type_accuracy": 0.88,
                    "exact_match_accuracy": 0.65,
                }
            },
        },
    )

    assert mode == "llm"
    assert summary.exact_match_accuracy == 0.65


def test_run_classifier_cycle_cli_resolves_default_template_alias() -> None:
    resolved = Path(resolve_profile_arg("default"))
    assert resolved.name == "default.json"
    assert resolved.exists()


def test_build_dataset_manifest_tracks_operational_validation_and_training_pool(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.classifier_registry.repo_root", lambda: tmp_path)
    monkeypatch.setenv("CLASSIFIER_DATASETS_ROOT", str(tmp_path / "datasets"))

    save_validation_set(
        [
            ValidationSetEntry(
                file="validation.pdf",
                business_domain="juridico",
                document_type="contrato",
            )
        ]
    )
    validation_file = tmp_path / "datasets" / "validation_set" / "files" / "validation.pdf"
    validation_file.parent.mkdir(parents=True, exist_ok=True)
    validation_file.write_bytes(b"validation-content")

    save_training_pool_records(
        [
            TrainingPoolRecord(
                doc_id="doc-1",
                project_id="proj-1",
                original_filename="approved.pdf",
                path="training_pool/files/doc-1__approved.pdf",
                source_path="/projects/proj-1/02_AREAS/juridico/contrato/approved.pdf",
                business_domain="juridico",
                document_type="contrato",
                decision="approved",
                sha256="abc123",
            )
        ]
    )

    manifest = build_dataset_manifest(
        profile_path=tmp_path / "config" / "templates" / "default.json",
        validation_examples=[
            {
                "entry": ValidationSetEntry(
                    file="validation.pdf",
                    business_domain="juridico",
                    document_type="contrato",
                ),
                "file_path": validation_file,
                "sha256": "validation-sha",
            }
        ],
        training_records=load_training_pool_records(),
        resolved_training_examples=[
            {
                "record": TrainingPoolRecord(
                    doc_id="doc-1",
                    project_id="proj-1",
                    original_filename="approved.pdf",
                    path="training_pool/files/doc-1__approved.pdf",
                    source_path="/projects/proj-1/02_AREAS/juridico/contrato/approved.pdf",
                    business_domain="juridico",
                    document_type="contrato",
                    decision="approved",
                    sha256="abc123",
                ),
                "file_path": tmp_path / "datasets" / "training_pool" / "files" / "doc-1__approved.pdf",
                "sha256": "abc123",
            }
        ],
        skipped_training_examples=["missing_file:legacy.pdf"],
    )

    assert manifest["datasets_root"] == str(tmp_path / "datasets")
    assert manifest["validation_set"]["files"][0]["file"] == "validation.pdf"
    assert manifest["training_pool"]["jsonl_records"] == 1
    assert manifest["training_pool"]["resolved_examples"] == 1
    assert manifest["training_pool"]["skipped_examples"] == 1

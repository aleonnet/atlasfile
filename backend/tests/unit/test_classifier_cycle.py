from __future__ import annotations

from pathlib import Path

from app.classifier_cycle import choose_champion_mode
from app.classifier_registry import ClassifierRegistry
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
            "sparse_linear_svc": {
                "summary": {
                    "mode": "sparse_linear_svc",
                    "total_labeled": 50,
                    "business_domain_accuracy": 0.52,
                    "document_type_accuracy": 0.80,
                    "exact_match_accuracy": 0.48,
                }
            },
        },
    )

    assert mode == "bootstrap"


def test_run_classifier_cycle_cli_resolves_default_template_alias() -> None:
    resolved = Path(resolve_profile_arg("default"))
    assert resolved.name == "default.json"
    assert resolved.exists()

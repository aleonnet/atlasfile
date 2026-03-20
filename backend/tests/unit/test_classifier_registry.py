from __future__ import annotations

from app.classifier_registry import (
    classifier_registry_path,
    list_classifier_reports,
    load_classifier_registry,
    save_classifier_report,
)


def test_load_classifier_registry_bootstraps_default_state(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROJECTS_HOST_ROOT", str(tmp_path))

    registry = load_classifier_registry()

    assert registry.champion_mode == "bootstrap"
    assert classifier_registry_path() == tmp_path / "_ATLASFILE" / "classifier" / "registry.json"
    assert classifier_registry_path().exists()


def test_save_classifier_report_is_listed_from_runtime_state(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROJECTS_HOST_ROOT", str(tmp_path))

    report_id = save_classifier_report(
        {
            "generated_at": "2026-03-19T00:00:00+00:00",
            "operational_classifier_mode": "bootstrap",
            "champion": {
                "mode": "bootstrap",
                "summary": {
                    "mode": "bootstrap",
                    "total_labeled": 10,
                    "business_domain_accuracy": 0.5,
                    "document_type_accuracy": 0.8,
                    "exact_match_accuracy": 0.4,
                },
            },
        },
        report_id="test_cycle_001",
    )

    reports = list_classifier_reports(limit=5)

    assert report_id == "test_cycle_001"
    assert reports[0]["report_id"] == "test_cycle_001"
    assert reports[0]["champion"]["mode"] == "bootstrap"

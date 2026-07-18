from __future__ import annotations

import json

from app.classifier_registry import (
    classifier_registry_path,
    list_classifier_reports,
    load_classifier_registry,
    save_classifier_registry,
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


def test_load_classifier_registry_sanitizes_legacy_setfit_entries(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROJECTS_HOST_ROOT", str(tmp_path))
    registry_path = tmp_path / "_ATLASFILE" / "classifier" / "registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "champion_mode": "setfit",
                "fallback_mode": "setfit",
                "benchmark_enabled_modes": ["bootstrap", "sparse_logreg", "setfit"],
                "champion_summary": {"mode": "setfit", "total_labeled": 10},
            }
        ),
        encoding="utf-8",
    )

    registry = load_classifier_registry()

    assert registry.champion_mode == "bootstrap"
    assert registry.fallback_mode == "bootstrap"
    assert registry.benchmark_enabled_modes == ["bootstrap", "sparse_logreg"]
    assert registry.champion_summary is None

    persisted = json.loads(registry_path.read_text(encoding="utf-8"))
    assert persisted["champion_mode"] == "bootstrap"


def test_load_classifier_registry_downgrades_setfit_to_sparse_when_artifact_exists(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROJECTS_HOST_ROOT", str(tmp_path))
    classifier_root = tmp_path / "_ATLASFILE" / "classifier"
    (classifier_root / "models").mkdir(parents=True, exist_ok=True)
    (classifier_root / "models" / "sparse_logreg.pkl").write_bytes(b"artifact")
    (classifier_root / "registry.json").write_text(
        json.dumps({"champion_mode": "setfit"}),
        encoding="utf-8",
    )

    registry = load_classifier_registry()

    assert registry.champion_mode == "sparse_logreg"


def test_benchmark_enabled_modes_default_and_persistence(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROJECTS_HOST_ROOT", str(tmp_path))

    registry = load_classifier_registry()

    assert registry.benchmark_enabled_modes == ["bootstrap", "sparse_logreg"]

    registry.benchmark_enabled_modes = ["bootstrap", "sparse_logreg", "llm"]
    save_classifier_registry(registry)

    reloaded = load_classifier_registry()

    assert reloaded.benchmark_enabled_modes == ["bootstrap", "sparse_logreg", "llm"]


def test_benchmark_enabled_modes_rejects_unsupported_mode() -> None:
    import pytest

    from app.classifier_registry import ClassifierRegistry

    with pytest.raises(ValueError, match="unsupported benchmark mode"):
        ClassifierRegistry(benchmark_enabled_modes=["bootstrap", "invalid_mode"])


def test_load_classifier_registry_persists_dataset_manifest_fields(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROJECTS_HOST_ROOT", str(tmp_path))

    registry = load_classifier_registry()
    registry.latest_dataset_manifest = {"datasets_root": str(tmp_path / "_ATLASFILE" / "classifier" / "datasets")}
    registry.champion_dataset_manifest = {"training_pool": {"jsonl_records": 10}}
    save_classifier_registry(registry)

    reloaded = load_classifier_registry()

    assert reloaded.latest_dataset_manifest["datasets_root"].endswith("/_ATLASFILE/classifier/datasets")
    assert reloaded.champion_dataset_manifest["training_pool"]["jsonl_records"] == 10


def test_classifier_state_base_root_prefere_candidato_existente(tmp_path, monkeypatch) -> None:
    """Dentro do container, PROJECTS_HOST_ROOT (path do host) não existe — o
    estado deve ir para o caminho montado que existe, senão registry/campeão
    são gravados no filesystem efêmero do container e somem a cada rebuild."""
    from app.classifier_registry import classifier_state_base_root

    host_path = tmp_path / "host-only-inexistente"
    mounted = tmp_path / "projects"
    mounted.mkdir()
    monkeypatch.setenv("PROJECTS_HOST_ROOT", str(host_path))
    monkeypatch.setenv("PROJECTS_ROOT", str(mounted))
    assert classifier_state_base_root() == mounted

    # Quando o primeiro candidato existe (execução no host), ele continua valendo
    host_path.mkdir()
    assert classifier_state_base_root() == host_path

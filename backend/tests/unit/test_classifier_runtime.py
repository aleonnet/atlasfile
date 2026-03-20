from __future__ import annotations

import json
from pathlib import Path

from app.classifier_registry import load_classifier_registry, save_classifier_registry
from app.classifier_runtime import classify_with_operational_mode, resolve_classifier_mode
from app.profile_schema_v2 import ProjectProfileV2
from app.project_profile import profile_v2_to_runtime

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TEMPLATE_PATH = REPO_ROOT / "config" / "templates" / "default.json"


def _load_runtime_profile() -> dict:
    raw = json.loads(DEFAULT_TEMPLATE_PATH.read_text(encoding="utf-8"))
    model = ProjectProfileV2.model_validate(raw)
    return profile_v2_to_runtime(model, Path(raw["project_root"]))


def test_resolve_classifier_mode_prefers_project_override(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROJECTS_HOST_ROOT", str(tmp_path))
    registry = load_classifier_registry()
    registry.champion_mode = "bootstrap"
    save_classifier_registry(registry)

    profile = _load_runtime_profile()
    profile["classification"]["operational"] = {"override_mode": "sparse_logreg"}

    status = resolve_classifier_mode(profile)

    assert status["override_mode"] == "sparse_logreg"
    assert status["effective_mode"] == "sparse_logreg"


def test_runtime_falls_back_to_bootstrap_when_supervised_artifact_is_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROJECTS_HOST_ROOT", str(tmp_path))
    registry = load_classifier_registry()
    registry.champion_mode = "bootstrap"
    save_classifier_registry(registry)

    profile = _load_runtime_profile()
    profile["classification"]["operational"] = {"override_mode": "sparse_linear_svc"}

    result = classify_with_operational_mode(
        profile=profile,
        source_path=Path("Contrato_Servicos_TI.pdf"),
        text_excerpt="CONTRATO de serviços SAP Business One para implantação e suporte.",
    )

    assert result["classifier_requested_mode"] == "sparse_linear_svc"
    assert result["classifier_mode"] == "bootstrap"
    assert result["classifier_fallback_reason"] == "artifact_missing"
    assert result["business_domain"]
    assert result["document_type"]

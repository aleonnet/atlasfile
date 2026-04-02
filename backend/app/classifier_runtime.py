from __future__ import annotations

from pathlib import Path
from typing import Any

from .classification_bootstrap import classify_bootstrap
from .classifier_registry import (
    SUPPORTED_CLASSIFIER_MODES,
    classifier_model_path,
    load_classifier_registry,
    load_classifier_report,
)
from .classifier_setfit import classify_with_setfit_artifact, load_setfit_artifact
from .classifier_supervised import classify_with_supervised_artifact, load_sparse_artifact


def project_classifier_override(profile: dict[str, Any]) -> str | None:
    operational = ((profile.get("classification") or {}).get("operational") or {})
    override_mode = str(operational.get("override_mode") or "").strip()
    if override_mode in SUPPORTED_CLASSIFIER_MODES:
        return override_mode
    return None


def resolve_classifier_mode(profile: dict[str, Any]) -> dict[str, Any]:
    registry = load_classifier_registry()
    override_mode = project_classifier_override(profile)
    effective_mode = (
        override_mode
        if override_mode and bool(registry.project_override_allowed)
        else registry.champion_mode
    )
    latest_report = load_classifier_report(registry.latest_report_id)
    return {
        "registry": registry,
        "override_mode": override_mode,
        "effective_mode": effective_mode,
        "latest_report": latest_report,
    }


def _with_runtime_metadata(
    result: dict[str, Any],
    *,
    requested_mode: str,
    served_mode: str,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    enriched = dict(result)
    enriched["classifier_requested_mode"] = requested_mode
    enriched["classifier_mode"] = served_mode
    if fallback_reason:
        enriched["classifier_fallback_reason"] = fallback_reason
    return enriched


def classify_with_operational_mode(
    *,
    profile: dict[str, Any],
    source_path: Path,
    text_excerpt: str,
) -> dict[str, Any]:
    status = resolve_classifier_mode(profile)
    requested_mode = str(status["effective_mode"] or "bootstrap")
    if requested_mode == "bootstrap":
        return _with_runtime_metadata(
            classify_bootstrap(profile=profile, source_path=source_path, text_excerpt=text_excerpt),
            requested_mode=requested_mode,
            served_mode="bootstrap",
        )

    artifact_path = classifier_model_path(requested_mode)
    if requested_mode == "setfit":
        artifact_exists = (artifact_path / "metadata.json").exists()
    else:
        artifact_exists = artifact_path.exists()

    if not artifact_exists:
        return _with_runtime_metadata(
            classify_bootstrap(profile=profile, source_path=source_path, text_excerpt=text_excerpt),
            requested_mode=requested_mode,
            served_mode="bootstrap",
            fallback_reason="artifact_missing",
        )

    try:
        if requested_mode == "setfit":
            artifact = load_setfit_artifact(artifact_path)
            return _with_runtime_metadata(
                classify_with_setfit_artifact(
                    artifact=artifact,
                    profile=profile,
                    source_path=source_path,
                    text_excerpt=text_excerpt,
                ),
                requested_mode=requested_mode,
                served_mode=requested_mode,
            )
        artifact = load_sparse_artifact(artifact_path)
        return _with_runtime_metadata(
            classify_with_supervised_artifact(
                artifact=artifact,
                profile=profile,
                source_path=source_path,
                text_excerpt=text_excerpt,
            ),
            requested_mode=requested_mode,
            served_mode=requested_mode,
        )
    except Exception:
        return _with_runtime_metadata(
            classify_bootstrap(profile=profile, source_path=source_path, text_excerpt=text_excerpt),
            requested_mode=requested_mode,
            served_mode="bootstrap",
            fallback_reason="runtime_error",
        )

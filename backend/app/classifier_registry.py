from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from .config import settings

SUPPORTED_CLASSIFIER_MODES = ("bootstrap", "sparse_logreg", "setfit", "llm")
DEFAULT_CLASSIFIER_MODE = "bootstrap"
DEFAULT_PROMOTION_POLICY = "auto_best_with_ui_override"
DEFAULT_BENCHMARK_ENABLED_MODES = ["bootstrap", "sparse_logreg"]
_DEFAULT_PROJECTS_ROOT = "/projects"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _candidate_projects_roots() -> list[Path]:
    seen: set[str] = set()
    candidates: list[Path] = []
    for raw in (
        os.environ.get("PROJECTS_HOST_ROOT"),
        os.environ.get("PROJECTS_ROOT"),
        getattr(settings, "projects_root", None),
    ):
        if not raw:
            continue
        path = Path(str(raw)).expanduser()
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(path)
    return candidates


def classifier_state_base_root() -> Path:
    for candidate in _candidate_projects_roots():
        if str(candidate) == _DEFAULT_PROJECTS_ROOT and not candidate.exists():
            continue
        return candidate
    return repo_root()


def classifier_state_root() -> Path:
    return classifier_state_base_root() / "_ATLASFILE" / "classifier"


def classifier_registry_path() -> Path:
    return classifier_state_root() / "registry.json"


def classifier_reports_dir() -> Path:
    return classifier_state_root() / "reports"


def classifier_models_dir() -> Path:
    return classifier_state_root() / "models"


def ensure_classifier_runtime_dirs() -> None:
    classifier_reports_dir().mkdir(parents=True, exist_ok=True)
    classifier_models_dir().mkdir(parents=True, exist_ok=True)


class ClassifierPromotionGates(BaseModel):
    primary_metric: Literal["exact_match_accuracy"] = "exact_match_accuracy"
    min_business_domain_accuracy: float = 0.0
    min_document_type_accuracy: float = 0.0
    min_exact_match_accuracy: float = 0.0
    prefer_current_champion_on_tie: bool = True

    @model_validator(mode="after")
    def _validate(self) -> "ClassifierPromotionGates":
        for field_name in (
            "min_business_domain_accuracy",
            "min_document_type_accuracy",
            "min_exact_match_accuracy",
        ):
            value = float(getattr(self, field_name))
            if not (0.0 <= value <= 1.0):
                raise ValueError(f"{field_name} must be between 0 and 1")
        return self


class ClassifierSummary(BaseModel):
    mode: str
    role: str = ""
    total_labeled: int = 0
    business_domain_accuracy: float = 0.0
    document_type_accuracy: float = 0.0
    exact_match_accuracy: float = 0.0
    training_pool_records: int = 0
    validation_records: int = 0
    vectorizer: str | None = None
    skipped: bool = False
    skip_reason: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate(self) -> "ClassifierSummary":
        if self.mode not in SUPPORTED_CLASSIFIER_MODES:
            raise ValueError(f"unsupported classifier mode: {self.mode}")
        for field_name in (
            "business_domain_accuracy",
            "document_type_accuracy",
            "exact_match_accuracy",
        ):
            value = float(getattr(self, field_name))
            if not (0.0 <= value <= 1.0):
                raise ValueError(f"{field_name} must be between 0 and 1")
        return self


class ClassifierRegistry(BaseModel):
    schema_version: int = 1
    champion_mode: str = DEFAULT_CLASSIFIER_MODE
    fallback_mode: str = DEFAULT_CLASSIFIER_MODE
    promotion_policy: Literal["auto_best_with_ui_override"] = DEFAULT_PROMOTION_POLICY
    project_override_allowed: bool = True
    promotion_gates: ClassifierPromotionGates = Field(default_factory=ClassifierPromotionGates)
    latest_report_id: str | None = None
    champion_report_id: str | None = None
    champion_summary: ClassifierSummary | None = None
    latest_dataset_manifest: dict[str, Any] | None = None
    champion_dataset_manifest: dict[str, Any] | None = None
    latest_cycle_status: Literal["never_run", "running", "succeeded", "failed"] = "never_run"
    latest_cycle_started_at: str | None = None
    latest_cycle_finished_at: str | None = None
    latest_cycle_error: str | None = None
    benchmark_enabled_modes: list[str] = Field(default_factory=lambda: list(DEFAULT_BENCHMARK_ENABLED_MODES))
    updated_at: str = Field(default_factory=_utc_now_iso)

    @model_validator(mode="after")
    def _validate(self) -> "ClassifierRegistry":
        if self.champion_mode not in SUPPORTED_CLASSIFIER_MODES:
            raise ValueError(f"unsupported champion_mode: {self.champion_mode}")
        if self.fallback_mode not in SUPPORTED_CLASSIFIER_MODES:
            raise ValueError(f"unsupported fallback_mode: {self.fallback_mode}")
        if self.champion_summary and self.champion_summary.mode != self.champion_mode:
            raise ValueError("champion_summary.mode must match champion_mode")
        for mode in self.benchmark_enabled_modes:
            if mode not in SUPPORTED_CLASSIFIER_MODES:
                raise ValueError(f"unsupported benchmark mode: {mode}")
        return self


def load_classifier_registry() -> ClassifierRegistry:
    ensure_classifier_runtime_dirs()
    path = classifier_registry_path()
    if not path.exists():
        registry = ClassifierRegistry()
        save_classifier_registry(registry)
        return registry
    raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    registry = ClassifierRegistry.model_validate(raw)
    if not registry.updated_at:
        registry.updated_at = _utc_now_iso()
    return registry


def save_classifier_registry(registry: ClassifierRegistry) -> ClassifierRegistry:
    ensure_classifier_runtime_dirs()
    registry.updated_at = _utc_now_iso()
    classifier_registry_path().write_text(
        json.dumps(registry.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return registry


def classifier_model_path(mode: str) -> Path:
    if mode not in SUPPORTED_CLASSIFIER_MODES:
        raise ValueError(f"unsupported classifier mode: {mode}")
    if mode == "setfit":
        return classifier_models_dir() / "setfit"
    return classifier_models_dir() / f"{mode}.pkl"


def build_classifier_report_id(prefix: str = "cycle") -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    return f"{prefix}_{ts}"


def classifier_report_path(report_id: str) -> Path:
    return classifier_reports_dir() / f"{report_id}.json"


def save_classifier_report(payload: dict[str, Any], *, report_id: str | None = None) -> str:
    ensure_classifier_runtime_dirs()
    rid = str(report_id or build_classifier_report_id()).strip()
    if not rid:
        raise ValueError("report_id must not be empty")
    report = dict(payload)
    report.setdefault("report_id", rid)
    report.setdefault("saved_at", _utc_now_iso())
    classifier_report_path(rid).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return rid


def load_classifier_report(report_id: str | None) -> dict[str, Any] | None:
    rid = str(report_id or "").strip()
    if not rid:
        return None
    path = classifier_report_path(rid)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8") or "{}")


def list_classifier_reports(*, limit: int = 20) -> list[dict[str, Any]]:
    ensure_classifier_runtime_dirs()
    items: list[dict[str, Any]] = []
    for path in sorted(
        classifier_reports_dir().glob("*.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )[:limit]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8") or "{}")
        except Exception:
            continue
        payload.setdefault("report_id", path.stem)
        items.append(payload)
    return items


def summary_from_benchmark(mode: str, summary: dict[str, Any], *, training_pool_records: int = 0) -> ClassifierSummary:
    return ClassifierSummary(
        mode=mode,
        role=str(summary.get("role") or ""),
        total_labeled=int(summary.get("total_labeled") or 0),
        business_domain_accuracy=float(summary.get("business_domain_accuracy") or 0.0),
        document_type_accuracy=float(summary.get("document_type_accuracy") or 0.0),
        exact_match_accuracy=float(summary.get("exact_match_accuracy") or 0.0),
        training_pool_records=int(summary.get("training_pool_records") or training_pool_records or 0),
        validation_records=int(summary.get("validation_records") or summary.get("total_labeled") or 0),
        vectorizer=str(summary.get("vectorizer") or "") or None,
        skipped=bool(summary.get("skipped") or False),
        skip_reason=[str(item) for item in (summary.get("skip_reason") or []) if str(item).strip()],
    )

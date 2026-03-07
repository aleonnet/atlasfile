from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .profile_schema_v2 import ProjectProfileV2
from .utils import normalize_text

PROFILE_DIR = "_PROFILE"
PROFILE_FILE = "profile.json"
HISTORY_DIR = "history"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _template_path(slug: str = "default") -> Path:
    return _repo_root() / "config" / "templates" / f"{slug}.json"


def _profile_dir(project_root: Path) -> Path:
    return project_root / PROFILE_DIR


def _profile_file(project_root: Path) -> Path:
    return _profile_dir(project_root) / PROFILE_FILE


def _history_dir(project_root: Path) -> Path:
    return _profile_dir(project_root) / HISTORY_DIR


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _semantic_profile_payload(profile: ProjectProfileV2 | dict[str, Any]) -> dict[str, Any]:
    payload = profile.model_dump(mode="json") if isinstance(profile, ProjectProfileV2) else dict(profile)
    payload.pop("version", None)
    payload.pop("updated_at", None)
    payload.pop("updated_by", None)
    return payload


def compute_profile_etag(profile: ProjectProfileV2 | dict[str, Any]) -> str:
    payload = profile.model_dump(mode="json") if isinstance(profile, ProjectProfileV2) else dict(profile)
    canonical = _canonical_json(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"JSON profile inválido em {path}")
    return data


def create_default_profile(
    *,
    project_root: Path,
    project_id: str | None = None,
    project_label: str | None = None,
    template_slug: str = "default",
) -> ProjectProfileV2:
    template = _read_json(_template_path(template_slug))
    template.pop("template_meta", None)
    template["project_id"] = normalize_text(project_id or project_root.name)
    template["project_label"] = project_label or project_root.name
    template["project_root"] = str(project_root)
    template["version"] = int(template.get("version", 1) or 1)
    return ProjectProfileV2.model_validate(template)


def load_profile(project_root: Path) -> ProjectProfileV2:
    path = _profile_file(project_root)
    if not path.exists():
        raise FileNotFoundError(f"{PROFILE_DIR}/{PROFILE_FILE} não encontrado em {project_root}")
    data = _read_json(path)
    return ProjectProfileV2.model_validate(data)


def list_profile_history(project_root: Path) -> list[dict[str, Any]]:
    history = _history_dir(project_root)
    if not history.exists():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(history.glob("*.json"), key=lambda x: x.name, reverse=True):
        try:
            data = _read_json(p)
            out.append(
                {
                    "entry": p.name,
                    "version": data.get("version"),
                    "updated_at": data.get("updated_at"),
                    "updated_by": data.get("updated_by"),
                    "etag": hashlib.sha256(p.read_bytes()).hexdigest(),
                }
            )
        except Exception:
            continue
    return out


def save_profile(
    *,
    project_root: Path,
    profile: ProjectProfileV2 | dict[str, Any],
    if_match_version: int | None = None,
    updated_by: str | None = None,
) -> ProjectProfileV2:
    profile_file = _profile_file(project_root)
    current: ProjectProfileV2 | None = None
    if profile_file.exists():
        current = load_profile(project_root)
        if if_match_version is not None and current.version != if_match_version:
            raise ValueError(f"profile version conflict: expected={if_match_version} current={current.version}")

    model = profile if isinstance(profile, ProjectProfileV2) else ProjectProfileV2.model_validate(profile)
    if current:
        current_semantic = _semantic_profile_payload(current)
        incoming_semantic = _semantic_profile_payload(model)
        if _canonical_json(current_semantic) == _canonical_json(incoming_semantic):
            return current

    if current:
        model.version = current.version + 1
    elif model.version <= 0:
        model.version = 1
    model.updated_at = _utc_now()
    if updated_by:
        model.updated_by = updated_by

    payload = model.model_dump(mode="json")
    _write_json(profile_file, payload)

    ts = model.updated_at.strftime("%Y%m%dT%H%M%SZ") if model.updated_at else _utc_now().strftime("%Y%m%dT%H%M%SZ")
    history_entry = _history_dir(project_root) / f"{ts}__v{int(model.version):02d}.json"
    _write_json(history_entry, payload)
    return model


def ensure_profile(
    *,
    project_root: Path,
    project_id: str | None = None,
    project_label: str | None = None,
    template_slug: str = "default",
) -> tuple[ProjectProfileV2, bool]:
    try:
        return load_profile(project_root), False
    except FileNotFoundError:
        created = create_default_profile(
            project_root=project_root,
            project_id=project_id,
            project_label=project_label,
            template_slug=template_slug,
        )
        saved = save_profile(project_root=project_root, profile=created, if_match_version=None, updated_by="system:init")
        return saved, True


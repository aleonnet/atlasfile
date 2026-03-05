"""Template CRUD operations for project initialization templates.

Two template directories:
  - BUILTIN: config/templates/ (ships with code, read-only at runtime)
  - USER: PROJECTS_ROOT/_ATLASFILE/templates/ (user-created, persisted via volume)
Listing merges both; user templates override builtin when slugs collide.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .profile_schema_v2 import ProjectProfileV2

BUILTIN_DIR = Path(__file__).resolve().parents[2] / "config" / "templates"
DEFAULT_SLUG = "default"


def _projects_root() -> Path:
    return Path(os.environ.get("PROJECTS_ROOT", "/projects"))


def _user_dir() -> Path:
    return _projects_root() / "_ATLASFILE" / "templates"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_meta(data: dict[str, Any], slug: str, *, source: str = "builtin") -> dict[str, Any]:
    meta = data.get("template_meta", {})
    areas = data.get("classification", {}).get("work_areas", [])
    return {
        "slug": meta.get("slug", slug),
        "name": meta.get("name", slug),
        "description": meta.get("description", ""),
        "areas_count": len(areas),
        "created_at": meta.get("created_at", ""),
        "updated_at": meta.get("updated_at", ""),
        "source": source,
    }


def _scan_dir(directory: Path, source: str) -> dict[str, dict[str, Any]]:
    """Scan a directory for template JSON files, return {slug: meta}."""
    result: dict[str, dict[str, Any]] = {}
    if not directory.exists():
        return result
    for path in sorted(directory.glob("*.json")):
        slug = path.stem
        try:
            data = _read_json(path)
            result[slug] = _extract_meta(data, slug, source=source)
        except Exception:
            continue
    return result


def list_templates() -> list[dict[str, Any]]:
    builtin = _scan_dir(BUILTIN_DIR, "builtin")
    user = _scan_dir(_user_dir(), "user")
    merged = {**builtin, **user}
    return list(merged.values())


def _resolve_template_path(slug: str) -> tuple[Path, str]:
    """Find template by slug: user dir first, then builtin. Returns (path, source)."""
    user_path = _user_dir() / f"{slug}.json"
    if user_path.exists():
        return user_path, "user"
    builtin_path = BUILTIN_DIR / f"{slug}.json"
    if builtin_path.exists():
        return builtin_path, "builtin"
    raise FileNotFoundError(f"Template not found: {slug}")


def get_template(slug: str) -> dict[str, Any]:
    path, source = _resolve_template_path(slug)
    data = _read_json(path)
    meta = _extract_meta(data, slug, source=source)
    return {**meta, "profile": data}


def save_template(slug: str, data: dict[str, Any]) -> dict[str, Any]:
    """Save template to user dir (never to builtin dir)."""
    user = _user_dir()
    user.mkdir(parents=True, exist_ok=True)
    now = _utc_now_iso()
    meta = data.get("template_meta", {})
    meta.setdefault("slug", slug)
    meta.setdefault("name", slug)
    meta.setdefault("description", "")
    meta.setdefault("created_at", now)
    meta["updated_at"] = now
    data["template_meta"] = meta
    path = user / f"{slug}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return _extract_meta(data, slug, source="user")


def delete_template(slug: str) -> None:
    if slug == DEFAULT_SLUG:
        raise ValueError("Cannot delete the default template")
    user_path = _user_dir() / f"{slug}.json"
    if user_path.exists():
        user_path.unlink()
        return
    builtin_path = BUILTIN_DIR / f"{slug}.json"
    if builtin_path.exists():
        raise ValueError("Cannot delete a built-in template")
    raise FileNotFoundError(f"Template not found: {slug}")


def create_profile_from_template(
    slug: str,
    project_root: Path,
    project_id: str,
    project_label: str,
) -> ProjectProfileV2:
    path, _source = _resolve_template_path(slug)
    data = _read_json(path)
    data.pop("template_meta", None)
    data["project_id"] = project_id
    data["project_label"] = project_label
    data["project_root"] = str(project_root)
    data["version"] = 1
    return ProjectProfileV2.model_validate(data)

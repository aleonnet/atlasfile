"""Template CRUD operations for project initialization templates.

Two template directories:
  - BUILTIN: config/templates/ (ships with code, read-only at runtime)
  - USER: PROJECTS_ROOT/_ATLASFILE/templates/ (user-created, persisted via volume)
Listing merges both; user templates override builtin when slugs collide.
"""
from __future__ import annotations

import copy
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

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


def _validate_template_profile(data: dict[str, Any]) -> None:
    try:
        ProjectProfileV2.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"Template profile inválido: {e}") from e


def _baseline_template_profile(slug: str) -> dict[str, Any]:
    try:
        path, _source = _resolve_template_path(slug)
    except FileNotFoundError:
        path = BUILTIN_DIR / f"{DEFAULT_SLUG}.json"
    data = _read_json(path)
    data.pop("template_meta", None)
    return data


def _normalized_string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if item:
            normalized.append(item)
    return normalized


def _materialize_domain_folders(
    *,
    business_domains: list[dict[str, Any]],
    layout: dict[str, Any],
) -> list[dict[str, str]]:
    existing_rows = layout.get("business_domain_folders") or []
    existing_by_key = {
        str(row.get("business_domain") or "").strip(): str(row.get("folder") or "").strip()
        for row in existing_rows
        if str(row.get("business_domain") or "").strip()
    }
    materialized: list[dict[str, str]] = []
    for domain in business_domains:
        key = str(domain.get("key") or "").strip()
        if not key:
            continue
        folder = str(
            domain.get("folder")
            or existing_by_key.get(key)
            or key
        ).strip()
        materialized.append({"business_domain": key, "folder": folder or key})
    return materialized


def _filter_routing_rules(routing_rules: Any, *, business_domain_keys: set[str]) -> list[dict[str, Any]]:
    if not isinstance(routing_rules, list):
        return []
    filtered: list[dict[str, Any]] = []
    for row in routing_rules:
        if not isinstance(row, dict):
            continue
        route_to = str(row.get("route_to") or "").strip()
        if route_to and route_to not in business_domain_keys:
            continue
        filtered.append(copy.deepcopy(row))
    return filtered


def _materialize_template_profile(data: dict[str, Any], *, slug: str) -> dict[str, Any]:
    profile_data = copy.deepcopy(data)
    profile_data.pop("template_meta", None)
    baseline = _baseline_template_profile(slug)
    materialized = copy.deepcopy(baseline)

    for key, value in profile_data.items():
        if key in {"classification", "layout"}:
            continue
        materialized[key] = copy.deepcopy(value)

    classification = copy.deepcopy((baseline.get("classification") or {}))
    classification.update(copy.deepcopy(profile_data.get("classification") or {}))
    layout = copy.deepcopy((baseline.get("layout") or {}))
    layout.update(copy.deepcopy(profile_data.get("layout") or {}))

    business_domains = classification.get("business_domains") or []
    classification["business_domains"] = copy.deepcopy(business_domains)

    domain_folder_rows = _materialize_domain_folders(
        business_domains=classification["business_domains"],
        layout=layout,
    )
    layout["business_domain_folders"] = domain_folder_rows

    document_types = classification.get("document_types") or []
    classification["document_types"] = copy.deepcopy(document_types)
    business_domain_keys = [
        str(domain.get("key") or "").strip()
        for domain in classification["business_domains"]
        if str(domain.get("key") or "").strip()
    ]
    business_domain_key_set = set(business_domain_keys)
    classification["routing_rules"] = _filter_routing_rules(
        classification.get("routing_rules"),
        business_domain_keys=business_domain_key_set,
    )

    materialized["layout"] = layout
    materialized["classification"] = classification
    return ProjectProfileV2.model_validate(materialized).model_dump(mode="json")


def _extract_meta(data: dict[str, Any], slug: str, *, source: str = "builtin") -> dict[str, Any]:
    meta = data.get("template_meta", {})
    classification = data.get("classification", {})
    areas = classification.get("business_domains") or []
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
    materialized_profile = _materialize_template_profile(data, slug=slug)
    meta = data.get("template_meta", {})
    meta.setdefault("slug", slug)
    meta.setdefault("name", slug)
    meta.setdefault("description", "")
    meta.setdefault("created_at", now)
    meta["updated_at"] = now
    payload = {**materialized_profile, "template_meta": meta}
    _validate_template_profile(materialized_profile)
    path = user / f"{slug}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return _extract_meta(payload, slug, source="user")


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
    data = _materialize_template_profile(data, slug=slug)
    data["project_id"] = project_id
    data["project_label"] = project_label
    data["project_root"] = str(project_root)
    data["version"] = 1
    return ProjectProfileV2.model_validate(data)

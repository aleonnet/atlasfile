from __future__ import annotations

from typing import Any

from .utils import sanitize_token


def inbox_rel(profile: dict[str, Any]) -> str:
    paths = profile.get("paths") or {}
    return str(paths.get("inbox") or profile.get("inbox_path") or "_INBOX_DROP")


def triage_paths(profile: dict[str, Any]) -> dict[str, str]:
    paths = profile.get("paths") or {}
    triage = paths.get("triage") or profile.get("triage_paths") or {}
    pending = str(triage.get("pending") or profile.get("triage_path") or "_TRIAGE_REVIEW/pending")
    resolved = str(triage.get("resolved") or "_TRIAGE_REVIEW/resolved")
    rejected = str(triage.get("rejected") or "_TRIAGE_REVIEW/rejected")
    return {"pending": pending, "resolved": resolved, "rejected": rejected}


def areas_root_rel(profile: dict[str, Any]) -> str:
    layout = profile.get("layout") or {}
    return str(layout.get("areas_root") or profile.get("work_root") or "_WORK")


def para_scan_roots(profile: dict[str, Any]) -> list[tuple[str, str]]:
    """Return ``(folder, category)`` pairs for all PARA roots in ``layout.roots``.

    Falls back to ``[(areas_root, "areas")]`` when ``layout.roots`` is absent.
    """
    layout = profile.get("layout") or {}
    roots = layout.get("roots") or {}
    if not roots:
        return [(areas_root_rel(profile), "areas")]
    return [(folder, category) for category, folder in roots.items() if folder]


def area_folder_map(profile: dict[str, Any]) -> dict[str, str]:
    layout = profile.get("layout") or {}
    mapped: dict[str, str] = {}
    for row in layout.get("area_folders") or []:
        area_key = str(row.get("area_key") or "").strip()
        folder = str(row.get("folder") or "").strip()
        if area_key and folder:
            mapped[area_key] = folder
    return mapped


def resolve_area_folder_name(profile: dict[str, Any], area_key: str) -> str:
    mapped = area_folder_map(profile)
    if area_key in mapped:
        return mapped[area_key]

    for area in profile.get("work_areas", []):
        if str(area.get("key") or "") != area_key:
            continue
        explicit = str(area.get("folder") or "").strip()
        if explicit:
            return explicit
        jd = area.get("jd_number")
        if isinstance(jd, int) and 1 <= jd <= 99:
            return f"{jd:02d}_{sanitize_token(area_key)}"
        break
    return sanitize_token(area_key)


from __future__ import annotations

from typing import Any


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
    return str(layout.get("areas_root") or profile.get("areas_root") or "02_AREAS")


def para_scan_roots(profile: dict[str, Any]) -> list[tuple[str, str]]:
    """Return ``(folder, category)`` pairs for all PARA roots in ``layout.roots``.

    Falls back to ``[(areas_root, "areas")]`` when ``layout.roots`` is absent.
    """
    layout = profile.get("layout") or {}
    roots = layout.get("roots") or {}
    if not roots:
        return [(areas_root_rel(profile), "areas")]
    return [(folder, category) for category, folder in roots.items() if folder]


def business_domain_folder_map(profile: dict[str, Any]) -> dict[str, str]:
    layout = profile.get("layout") or {}
    mapped: dict[str, str] = {}
    for row in layout.get("business_domain_folders") or []:
        business_domain = str(row.get("business_domain") or "").strip()
        folder = str(row.get("folder") or "").strip()
        if business_domain and folder:
            mapped[business_domain] = folder
    return mapped


def resolve_business_domain_folder_name(profile: dict[str, Any], business_domain: str) -> str:
    mapped = business_domain_folder_map(profile)
    if business_domain in mapped:
        return mapped[business_domain]

    for domain in profile.get("business_domains", []):
        if str(domain.get("key") or "") != business_domain:
            continue
        explicit = str(domain.get("folder") or "").strip()
        if explicit:
            return explicit
        break
    raise ValueError(f"business_domain folder is not configured: {business_domain}")


def resolve_document_type_folder_name(profile: dict[str, Any], document_type: str) -> str:
    classification = profile.get("classification") or {}
    for doc_type in classification.get("document_types") or []:
        if str(doc_type.get("key") or "") != document_type:
            continue
        explicit = str(doc_type.get("folder") or "").strip()
        if explicit:
            return explicit
        break
    raise ValueError(f"document_type folder is not configured: {document_type}")


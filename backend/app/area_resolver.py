from __future__ import annotations

from pathlib import Path
from typing import Any

from .profile_runtime import (
    areas_root_rel,
    resolve_business_domain_folder_name,
    resolve_document_type_folder_name,
)


def resolve_classification_path(
    *,
    project_root: Path,
    profile: dict[str, Any],
    business_domain: str,
    document_type: str,
    create_if_missing: bool = True,
) -> str:
    domain_folder = resolve_business_domain_folder_name(profile, business_domain)
    document_type_folder = resolve_document_type_folder_name(profile, document_type)
    rel = f"{areas_root_rel(profile)}/{domain_folder}/{document_type_folder}"
    folder_path = project_root / rel
    if create_if_missing:
        folder_path.mkdir(parents=True, exist_ok=True)
    return rel

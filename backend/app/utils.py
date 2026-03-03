from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sanitize_token(value: str) -> str:
    lowered = normalize_text(value).strip()
    lowered = re.sub(r"\s+", "_", lowered)
    lowered = re.sub(r"[^a-z0-9_\-]+", "", lowered)
    lowered = re.sub(r"_+", "_", lowered)
    return lowered.strip("_")


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_like = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return ascii_like.lower()


def build_canonical_filename(
    *,
    project_id: str,
    area_key: str,
    short_title: str,
    original_suffix: str,
    version: int = 1,
) -> str:
    date_prefix = datetime.now().strftime("%Y%m%d")
    title_token = sanitize_token(short_title) or "documento"
    return (
        f"{date_prefix}__{sanitize_token(project_id)}__{sanitize_token(area_key)}__"
        f"{title_token}__v{version:02d}{original_suffix.lower()}"
    )

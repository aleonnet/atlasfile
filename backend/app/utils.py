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


_OCR_SPACED_WORD_RE = re.compile(r"(?<![a-z0-9])(?:[a-z0-9]\s+){2,}[a-z0-9](?![a-z0-9])")


def fold_ocr_spacing(value: str) -> str:
    """Normalize OCR text and fold words split into single-letter tokens.

    Example: ``"c o n t r a t o" -> "contrato"``.
    """
    normalized = normalize_text(value).strip()
    if not normalized:
        return ""

    # Preserve explicit wider gaps before collapsing whitespace so adjacent
    # OCR-noisy words do not collapse into a single token.
    protected = re.sub(r"\s{2,}", " <ocr_gap> ", normalized)
    folded = re.sub(r"\s+", " ", protected).strip()
    if not folded:
        return ""

    for _ in range(4):
        updated = _OCR_SPACED_WORD_RE.sub(lambda m: m.group(0).replace(" ", ""), folded)
        updated = re.sub(r"\s+", " ", updated).strip()
        if updated == folded:
            break
        folded = updated
    return re.sub(r"\s+", " ", folded.replace("<ocr_gap>", " ")).strip()


_FS_INVALID_RE = re.compile(r'[/\\:*?"<>|\x00-\x1f]')
_CANONICAL_TAIL_RE = re.compile(r"__v(\d{2})(\.\w+)$")
DEFAULT_CANONICAL_PATTERN = "{date}__{project}__{original_name}"


def fs_safe(value: str) -> str:
    """Remove only filesystem-invalid chars. Preserves case, accents and underscores."""
    return _FS_INVALID_RE.sub("", value).strip()


def build_canonical_filename(
    *,
    pattern: str = DEFAULT_CANONICAL_PATTERN,
    date_format: str = "%Y%m%d",
    fields: dict[str, str],
    original_suffix: str,
    version: int = 1,
    date_override: str | None = None,
) -> str:
    """Build a canonical filename from *pattern* and *fields*.

    ``pattern`` is the user-configurable prefix (from profile ``naming.canonical_pattern``).
    The mandatory suffix ``__v{version:02d}{ext}`` is always appended by the system.
    """
    resolved: dict[str, str] = {
        "date": date_override if date_override is not None else datetime.now().strftime(date_format),
        "project": sanitize_token(fields.get("project", "")),
        "business_domain": sanitize_token(fields.get("business_domain", "")),
        "original_name": fs_safe(fields.get("original_name", "")) or "documento",
        "document_type": sanitize_token(fields.get("document_type", "")),
    }
    prefix = pattern.format_map(resolved)
    return f"{prefix}__v{version:02d}{original_suffix.lower()}"


_PATTERN_FIELD_RE = re.compile(r"\{(\w+)\}")


def canonical_prefix_fields(pattern: str) -> list[str]:
    """Field names that come BEFORE ``{original_name}`` in *pattern*, in order.

    These are exactly the segments the parser skips, so this is the single source
    of truth for both the count (``split_canonical``) and the identity of each
    segment (callers that need to validate what a segment should look like).
    """
    return _PATTERN_FIELD_RE.findall(pattern.split("{original_name}")[0])


def split_canonical(
    canonical: str,
    pattern: str = DEFAULT_CANONICAL_PATTERN,
) -> tuple[list[str], str] | None:
    """Split a canonical filename into ``(prefix segments, original name + ext)``.

    Returns ``None`` when *canonical* doesn't match the expected structure.
    Purely structural: it counts ``__``-separated segments and does NOT judge
    whether the prefix really is canonical — a name that merely *looks* like one
    splits just fine here. Callers that need that proof must check the segments
    against the pattern fields themselves (see ``canonical_prefix_fields``).
    """
    tail = _CANONICAL_TAIL_RE.search(canonical)
    if not tail:
        return None
    ext = tail.group(2)
    without_tail = canonical[: tail.start()]
    prefix_part = pattern.split("{original_name}")[0]
    # Count separators before {original_name} to know how many segments to skip
    n_sep = prefix_part.count("__")
    n_skip = n_sep + (1 if prefix_part and not prefix_part.endswith("__") else 0)
    parts = without_tail.split("__", n_skip)
    if len(parts) <= n_skip:
        return None
    return parts[:n_skip], parts[n_skip] + ext


def extract_original_name_from_canonical(
    canonical: str,
    pattern: str = DEFAULT_CANONICAL_PATTERN,
) -> str | None:
    """Extract the original filename (with extension) from a canonical filename.

    Returns ``None`` when *canonical* doesn't match the expected structure.
    Uses *pattern* to determine how many ``__``-separated prefix segments to skip
    before reaching ``{original_name}``.
    """
    split = split_canonical(canonical, pattern)
    return split[1] if split else None

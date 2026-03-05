from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

import yaml
from opensearchpy import OpenSearch
from opensearchpy.helpers import bulk, scan

from .config import settings
from .document_extractor import extract_document_content
from .utils import normalize_text, sha256_file

try:
    # Optional import; indexer works even if profile_v2 isn't wired yet.
    from .profile_v2 import ProjectProfileV2  # type: ignore
except Exception:  # pragma: no cover
    ProjectProfileV2 = None  # type: ignore


# -------------------------------------------------------------------
# Topics (controlled) - topics_v1.yaml
# -------------------------------------------------------------------

# Cache per resolved topics path (string)
_TOPICS_CACHE_BY_PATH: dict[str, dict[str, Any]] = {}


def _repo_root() -> Path:
    # indexer.py lives at: AtlasFile/backend/app/indexer.py => repo_root == parents[2]
    return Path(__file__).resolve().parents[2]


def _default_topics_path() -> Path:
    return _repo_root() / "config" / "topics_v1.yaml"


def _resolve_topics_path(profile: Any | None) -> Path:
    """
    Resolution order (keeps backward compatibility):
    1) ATLASFILE_TOPICS_V1_PATH env var (global override)
    2) profile.indexing.topics_path (per project)
    3) <repo_root>/config/topics_v1.yaml (default)
    """
    env_path = os.environ.get("ATLASFILE_TOPICS_V1_PATH", "").strip()
    if env_path:
        return Path(env_path)

    # Profile may be pydantic model or dict-like
    try:
        topics_path = getattr(getattr(profile, "indexing", None), "topics_path", None)
    except Exception:
        topics_path = None
    if not topics_path and isinstance(profile, dict):
        topics_path = (profile.get("indexing") or {}).get("topics_path")

    if isinstance(topics_path, str) and topics_path.strip():
        # Allow repo-relative paths (e.g. "config/topics_v1.yaml")
        tp = topics_path.strip()
        p = Path(tp)
        if not p.is_absolute():
            return _repo_root() / tp
        return p

    return _default_topics_path()


def _load_topics_config(profile: Any | None = None) -> dict[str, Any]:
    path = _resolve_topics_path(profile)
    key = str(path.resolve())
    cached = _TOPICS_CACHE_BY_PATH.get(key)
    if cached is not None:
        return cached

    try:
        raw = path.read_text(encoding="utf-8")
        cfg = yaml.safe_load(raw) or {}
        if not isinstance(cfg, dict):
            cfg = {}
    except Exception:
        cfg = {}

    topics = cfg.get("topics") or []
    normalized_topics: list[dict[str, Any]] = []
    if isinstance(topics, list):
        for t in topics:
            if not isinstance(t, dict):
                continue
            topic_key = str(t.get("key", "")).strip()
            if not topic_key:
                continue
            synonyms = t.get("synonyms") or []
            if not isinstance(synonyms, list):
                synonyms = []
            syn_norm: list[str] = []
            for s in synonyms:
                s2 = str(s).strip()
                if not s2:
                    continue
                syn_norm.append(normalize_text(s2))
            area_bias = t.get("area_bias") or []
            if not isinstance(area_bias, list):
                area_bias = []
            normalized_topics.append(
                {
                    "key": topic_key,
                    "label": str(t.get("label", "")).strip() or topic_key,
                    "synonyms_norm": [sn for sn in syn_norm if sn],
                    "area_bias": [str(a).strip() for a in area_bias if str(a).strip()],
                }
            )

    cfg["_topics_norm"] = normalized_topics
    _TOPICS_CACHE_BY_PATH[key] = cfg
    return cfg


def _match_topics(*, text: str, area_key: str | None, profile: Any | None = None) -> tuple[list[str], str]:
    cfg = _load_topics_config(profile)
    topics_norm = cfg.get("_topics_norm") or []
    if not topics_norm:
        return ([], "none")

    text_norm = normalize_text(text or "")
    if not text_norm:
        return ([], "none")

    # Max topics per doc (yaml can set, fallback 8)
    max_topics = 8
    try:
        mt = cfg.get("max_topics_per_document")
        if isinstance(mt, int) and 1 <= mt <= 50:
            max_topics = mt
    except Exception:
        pass

    def hit(syn: str) -> int:
        if not syn:
            return 0
        if len(syn) <= 4:
            return 1 if re.search(rf"(^|[^a-z0-9]){re.escape(syn)}([^a-z0-9]|$)", text_norm) else 0
        return 1 if syn in text_norm else 0

    scored: list[tuple[int, str]] = []
    for t in topics_norm:
        key = t["key"]
        score = 0
        for syn in t.get("synonyms_norm") or []:
            score += hit(syn)
        if score <= 0:
            continue
        if area_key and area_key in (t.get("area_bias") or []):
            score += 2
        scored.append((score, key))

    scored.sort(key=lambda x: (-x[0], x[1]))
    keys = [k for _, k in scored[:max_topics]]
    return (keys, "synonym_match")


# -------------------------------------------------------------------
# Existing helpers
# -------------------------------------------------------------------

def read_text_excerpt(path: Path, limit: int = 20000) -> str:
    result = extract_document_content(path, max_chars=limit)
    return result.text_excerpt


def _json_size_bytes(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))


def _indexing_pressure_limit_bytes(client: OpenSearch) -> int | None:
    try:
        stats = client.nodes.stats(metric="indexing_pressure")
        nodes = (stats or {}).get("nodes", {})
        limits: list[int] = []
        for node in nodes.values():
            limit = (
                (node.get("indexing_pressure") or {})
                .get("memory", {})
                .get("limit_in_bytes")
            )
            if isinstance(limit, int) and limit > 0:
                limits.append(limit)
        return min(limits) if limits else None
    except Exception:
        return None


def _rebuild_chunk_fields(enriched: dict[str, Any], chunks: list[dict[str, Any]]) -> None:
    enriched["content_chunks"] = chunks
    enriched["chunk_locations"] = [str(c.get("location", "")) for c in chunks if c.get("location")]
    enriched["content_chunks_text"] = ""
    enriched["content_chunks_normalized"] = ""
    enriched["content"] = ""
    enriched["content_normalized"] = ""


def _trim_payload_to_limit(enriched: dict[str, Any], limit_bytes: int) -> dict[str, Any]:
    if _json_size_bytes(enriched) <= limit_bytes:
        return enriched

    trimmed = dict(enriched)
    all_chunks = list(trimmed.get("content_chunks") or [])
    total_chunks = len(all_chunks)

    # Step 1: drop duplicate aggregate text fields first, keep all chunks.
    no_aggregate = dict(trimmed)
    no_aggregate["content"] = ""
    no_aggregate["content_normalized"] = ""
    no_aggregate["content_chunks_text"] = ""
    no_aggregate["content_chunks_normalized"] = ""
    if _json_size_bytes(no_aggregate) <= limit_bytes:
        metadata = dict(no_aggregate.get("extraction_metadata", {}) or {})
        metadata["payload_reduction_mode"] = "drop_aggregate_fields"
        metadata["content_truncated_for_indexing_pressure"] = False
        metadata["chunks_kept"] = total_chunks
        metadata["chunks_total"] = total_chunks
        no_aggregate["extraction_metadata"] = metadata
        return no_aggregate

    base = dict(trimmed)
    base["content"] = ""
    base["content_normalized"] = ""
    base["content_chunks_text"] = ""
    base["content_chunks_normalized"] = ""
    base["chunk_locations"] = []
    base["content_chunks"] = []

    # If even metadata alone is too large, keep only minimal text fields.
    while _json_size_bytes(base) > limit_bytes and len(base.get("title_guess", base.get("title", ""))) > 20:
        tg = str(base.get("title_guess", base.get("title", "")) or "")
        base["title_guess"] = tg[: max(20, len(tg) // 2)]
        base["title_guess_normalized"] = normalize_text(base["title_guess"])

    if total_chunks == 0:
        return base

    lo, hi = 0, total_chunks
    best = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        trial = dict(base)
        _rebuild_chunk_fields(trial, all_chunks[:mid])
        if _json_size_bytes(trial) <= limit_bytes:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1

    final = dict(base)
    _rebuild_chunk_fields(final, all_chunks[:best])

    metadata = dict(final.get("extraction_metadata", {}) or {})
    metadata["payload_reduction_mode"] = "chunk_truncation"
    metadata["content_truncated_for_indexing_pressure"] = best < total_chunks
    metadata["chunks_kept"] = best
    metadata["chunks_total"] = total_chunks
    final["extraction_metadata"] = metadata
    return final


def index_document(client: OpenSearch, payload: dict[str, Any], *, refresh: bool = True, profile: Any | None = None) -> None:
    """
    Backward compatible: existing callers can keep calling index_document(client, payload).
    New: optionally pass a per-project profile_v2 to drive topics_path and extraction settings.
    """
    enriched = _enrich_search_fields(payload, profile=profile)
    limit_bytes = _indexing_pressure_limit_bytes(client)
    if isinstance(limit_bytes, int) and limit_bytes > 0:
        enriched = _trim_payload_to_limit(enriched, limit_bytes)
    client.index(
        index=settings.opensearch_index,
        id=enriched["doc_id"],
        body=enriched,
        refresh=refresh,
    )


def _derive_doc_kind_from_extension(ext: str) -> str:
    ext = (ext or "").lower()
    if ext == ".pdf":
        return "pdf"
    if ext == ".docx":
        return "docx"
    if ext in {".xlsx", ".xlsm", ".xltx", ".xltm"}:
        return "xlsx"
    if ext == ".pptx":
        return "pptx"
    if ext == ".msg":
        return "msg"
    if ext in {".html", ".htm"}:
        return "html"
    if ext in {".txt", ".md", ".csv", ".json", ".log", ".eml", ".xml", ".yaml", ".yml"}:
        return "plain_text"
    if ext in {".doc", ".xls", ".ppt"}:
        return "legacy_office_binary"
    if ext in {".zip", ".rar"}:
        return "archive_listing"
    return "unsupported"


def _guess_title(*, doc_kind: str, extraction_metadata: dict[str, Any], extracted_text: str, fallback: str) -> str:
    if doc_kind == "html":
        t = str((extraction_metadata or {}).get("title", "") or "").strip()
        if t:
            return t

    if doc_kind == "msg":
        first_line = (extracted_text or "").splitlines()[0].strip() if extracted_text else ""
        m = re.match(r"(?i)^subject:\s*(.+)$", first_line)
        if m:
            subj = m.group(1).strip()
            if subj:
                return subj

    return fallback


def _profile_extraction_settings(profile: Any | None) -> tuple[str | None, int | None]:
    """
    Returns (mode, max_chars) where:
      - mode: "all" or "excerpt" or None
      - max_chars: int or None
    Backward compatible: if no profile provided, we use settings.
    """
    mode = None
    max_chars = None

    # Profile may be pydantic model or dict-like
    try:
        idx = getattr(profile, "indexing", None)
        mode = getattr(idx, "extraction_mode", None)
        max_chars = getattr(idx, "extraction_max_chars", None)
    except Exception:
        pass

    if isinstance(profile, dict):
        idx = profile.get("indexing") or {}
        mode = mode or idx.get("extraction_mode")
        max_chars = max_chars or idx.get("extraction_max_chars")

    # Normalize profile values
    if isinstance(mode, str):
        mode = mode.strip().lower()
        if mode not in {"all", "excerpt"}:
            mode = None
    else:
        mode = None

    if isinstance(max_chars, int) and max_chars > 0:
        pass
    else:
        max_chars = None

    # Fall back to settings if missing
    if mode is None:
        try:
            mode = str(getattr(settings, "extraction_mode", "excerpt")).strip().lower()
        except Exception:
            mode = "excerpt"
        if mode not in {"all", "excerpt"}:
            mode = "excerpt"

    if max_chars is None:
        try:
            max_chars = int(getattr(settings, "extraction_max_chars", 20000))
        except Exception:
            max_chars = 20000

    return (mode, max_chars)


def _enrich_search_fields(payload: dict[str, Any], *, profile: Any | None = None) -> dict[str, Any]:
    """
    Minimal scope change vs indexer_v2:
    - If profile is provided, uses:
        - profile.indexing.topics_path
        - profile.indexing.extraction_mode / extraction_max_chars
      Otherwise keeps current settings/env defaults.
    """
    enriched = dict(payload)
    extracted_text = str(enriched.get("content", "") or "")
    chunk_text = ""
    chunk_locations: list[str] = []
    content_type = "unknown"
    extraction_status = "not_extracted"
    extraction_metadata: dict[str, Any] = {}

    path_value = str(enriched.get("path", "") or "")
    extraction_metadata = dict(enriched.get("extraction_metadata", {}) or {})
    current_extractor_version = "5"  # 5 = profile-aware topics/extraction
    extraction_metadata["extractor_version"] = current_extractor_version

    # Ensure sha256 for incremental reconcile/dedupe
    if path_value and (not enriched.get("sha256") or str(enriched.get("sha256", "")).strip() == ""):
        path_obj_for_sha = Path(path_value)
        if path_obj_for_sha.exists() and path_obj_for_sha.is_file():
            enriched["sha256"] = sha256_file(path_obj_for_sha)

    extracted = None
    ext = Path(path_value).suffix.lower() if path_value else ""
    doc_kind = _derive_doc_kind_from_extension(ext)
    enriched["extension"] = ext
    enriched["doc_kind"] = doc_kind

    if path_value:
        path_obj = Path(path_value)
        if path_obj.exists() and path_obj.is_file():
            mode, max_chars_cfg = _profile_extraction_settings(profile)
            max_chars = None if mode == "all" else max_chars_cfg
            extracted = extract_document_content(path_obj, max_chars=max_chars)
            extracted_text = extracted.text_excerpt or extracted_text
            chunk_text = extracted.chunk_text
            chunk_locations = extracted.chunk_locations
            content_type = extracted.content_type
            extraction_status = extracted.extraction_status
            extraction_metadata = extracted.metadata
            extraction_metadata["extractor_version"] = current_extractor_version

    enriched["content"] = extracted_text
    enriched["content_chunks_text"] = chunk_text
    enriched["chunk_locations"] = chunk_locations
    chunks_raw = getattr(extracted, "chunks", None) if extracted else None
    if chunks_raw:
        enriched["content_chunks"] = [
            {
                "location": c["location"],
                "text": c["text"],
                "text_normalized": normalize_text(c.get("text", "")),
            }
            for c in chunks_raw
        ]
    else:
        enriched["content_chunks"] = []
    enriched["content_type"] = content_type
    enriched["extraction_status"] = extraction_status
    enriched["extraction_metadata"] = extraction_metadata

    # Title + normalized fields
    original_filename = str(enriched.get("original_filename", ""))
    canonical_filename = str(enriched.get("canonical_filename", ""))
    fallback_title = str(enriched.get("title", "")) or (Path(original_filename).stem if original_filename else "") or canonical_filename

    title_guess = _guess_title(
        doc_kind=doc_kind,
        extraction_metadata=extraction_metadata,
        extracted_text=extracted_text,
        fallback=fallback_title,
    )
    enriched["title_guess"] = title_guess
    enriched["title_guess_normalized"] = normalize_text(title_guess)

    # Keep backwards compat: set "title" = title_guess (so existing mapping/boosts work)
    enriched["title"] = title_guess
    enriched["title_normalized"] = normalize_text(title_guess)

    content = str(enriched.get("content", ""))
    content_chunks_text = str(enriched.get("content_chunks_text", ""))

    enriched["content_normalized"] = normalize_text(content)
    enriched["content_chunks_normalized"] = normalize_text(content_chunks_text)

    enriched["original_filename_text"] = original_filename
    enriched["original_filename_normalized"] = normalize_text(original_filename)
    enriched["canonical_filename_text"] = canonical_filename
    enriched["canonical_filename_normalized"] = normalize_text(canonical_filename)

    # Suggestions
    enriched["title_suggest"] = title_guess or original_filename
    enriched["original_filename_suggest"] = original_filename

    # Topics matching (controlled) - profile-aware topics_path
    area_key = str(enriched.get("area_key", enriched.get("area", "")) or "").strip() or None
    match_input = "\n".join(
        s for s in [
            title_guess,
            original_filename,
            canonical_filename,
            extracted_text,
        ] if s
    )
    topics, topics_source = _match_topics(text=match_input, area_key=area_key, profile=profile)
    enriched["topics"] = topics
    enriched["topics_source"] = topics_source

    return enriched


def backfill_search_fields(client: OpenSearch, *, profile: Any | None = None) -> int:
    """Backfill normalized/suggest fields for old indexed docs. Profile-aware topics/extraction if provided."""
    actions: list[dict[str, Any]] = []
    updated = 0
    for hit in scan(
        client,
        index=settings.opensearch_index,
        query={"query": {"match_all": {}}},
        size=500,
    ):
        doc_id = hit.get("_id")
        src = hit.get("_source") or {}
        enriched = _enrich_search_fields(src, profile=profile)
        actions.append(
            {
                "_op_type": "update",
                "_index": settings.opensearch_index,
                "_id": doc_id,
                "doc": enriched,
            }
        )
        if len(actions) >= 200:
            bulk(client, actions)
            updated += len(actions)
            actions = []
    if actions:
        bulk(client, actions)
        updated += len(actions)
    return updated


def delete_document(client: OpenSearch, doc_id: str, *, refresh: bool = True) -> None:
    client.delete(index=settings.opensearch_index, id=doc_id, refresh=refresh)


def bulk_index_documents(client: OpenSearch, documents: list[dict[str, Any]], *, refresh: bool = True, profile: Any | None = None) -> int:
    """Bulk index. Backward compatible; profile is optional."""
    actions = []
    for doc in documents:
        enriched = _enrich_search_fields(doc, profile=profile)
        actions.append(
            {
                "_op_type": "index",
                "_index": settings.opensearch_index,
                "_id": enriched["doc_id"],
                "_source": enriched,
            }
        )
    success, _ = bulk(client, actions, refresh=refresh)
    return int(success)

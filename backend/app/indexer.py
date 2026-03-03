from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from opensearchpy import OpenSearch
from opensearchpy.helpers import bulk, scan

from .config import settings
from .document_extractor import extract_document_content
from .utils import normalize_text, sha256_file


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
    while _json_size_bytes(base) > limit_bytes and len(base.get("title", "")) > 20:
        base["title"] = str(base.get("title", ""))[: max(20, len(str(base.get("title", ""))) // 2)]
        base["title_normalized"] = normalize_text(base["title"])

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


def index_document(client: OpenSearch, payload: dict[str, Any], *, refresh: bool = True) -> None:
    enriched = _enrich_search_fields(payload)
    limit_bytes = _indexing_pressure_limit_bytes(client)
    if isinstance(limit_bytes, int) and limit_bytes > 0:
        enriched = _trim_payload_to_limit(enriched, limit_bytes)
    client.index(
        index=settings.opensearch_index,
        id=enriched["doc_id"],
        body=enriched,
        refresh=refresh,
    )


def _enrich_search_fields(payload: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(payload)
    extracted_text = str(enriched.get("content", "") or "")
    chunk_text = ""
    chunk_locations: list[str] = []
    content_type = "unknown"
    extraction_status = "not_extracted"
    extraction_metadata: dict[str, Any] = {}

    path_value = str(enriched.get("path", "") or "")
    extraction_metadata = dict(enriched.get("extraction_metadata", {}) or {})
    current_extractor_version = "3"  # 3 = nested content_chunks
    extraction_metadata["extractor_version"] = current_extractor_version
    if path_value and (not enriched.get("sha256") or str(enriched.get("sha256", "")).strip() == ""):
        path_obj_for_sha = Path(path_value)
        if path_obj_for_sha.exists() and path_obj_for_sha.is_file():
            enriched["sha256"] = sha256_file(path_obj_for_sha)
    extracted = None
    if path_value:
        path_obj = Path(path_value)
        if path_obj.exists() and path_obj.is_file():
            max_chars = None if settings.extraction_mode == "all" else settings.extraction_max_chars
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

    title = str(enriched.get("title", ""))
    content = str(enriched.get("content", ""))
    content_chunks_text = str(enriched.get("content_chunks_text", ""))
    original_filename = str(enriched.get("original_filename", ""))
    canonical_filename = str(enriched.get("canonical_filename", ""))

    enriched["title_normalized"] = normalize_text(title)
    enriched["content_normalized"] = normalize_text(content)
    enriched["content_chunks_normalized"] = normalize_text(content_chunks_text)
    enriched["original_filename_text"] = original_filename
    enriched["original_filename_normalized"] = normalize_text(original_filename)
    enriched["canonical_filename_text"] = canonical_filename
    enriched["canonical_filename_normalized"] = normalize_text(canonical_filename)
    enriched["title_suggest"] = title or original_filename
    enriched["original_filename_suggest"] = original_filename
    return enriched


def backfill_search_fields(client: OpenSearch) -> int:
    """Backfill normalized/suggest fields for old indexed docs."""
    actions: list[dict[str, Any]] = []
    updated = 0
    for hit in scan(
        client,
        index=settings.opensearch_index,
        query={"query": {"match_all": {}}},
        _source=True,
    ):
        src = hit.get("_source", {})
        if not src:
            continue
        metadata = src.get("extraction_metadata", {}) if isinstance(src.get("extraction_metadata", {}), dict) else {}
        version_mismatch = metadata.get("extractor_version") != "3"
        needs_backfill = version_mismatch or any(
            field not in src
            for field in (
                "title_normalized",
                "content_normalized",
                "content_chunks_text",
                "content_chunks_normalized",
                "original_filename_text",
                "original_filename_normalized",
                "canonical_filename_text",
                "canonical_filename_normalized",
                "title_suggest",
                "original_filename_suggest",
                "chunk_locations",
                "content_chunks",
                "content_type",
                "extraction_status",
                "extraction_metadata",
            )
        )
        if not needs_backfill:
            continue
        enriched = _enrich_search_fields(src)
        actions.append(
            {
                "_op_type": "update",
                "_index": settings.opensearch_index,
                "_id": hit["_id"],
                "doc": enriched,
            }
        )
        if len(actions) >= 200:
            bulk(client, actions, refresh=False)
            updated += len(actions)
            actions.clear()
    if actions:
        bulk(client, actions, refresh=False)
        updated += len(actions)
    if updated:
        client.indices.refresh(index=settings.opensearch_index)
    return updated

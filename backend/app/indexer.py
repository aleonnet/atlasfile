from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from opensearchpy import OpenSearch
from opensearchpy.helpers import bulk, scan

from .config import settings
from .document_extractor import extract_document_content
from .topics import match_topics
from .utils import fold_ocr_spacing, normalize_text, sha256_file

logger = logging.getLogger(__name__)

# Índices de vetores já garantidos neste processo (evita exists() por documento).
_ENSURED_VECTOR_INDEXES: set[str] = set()


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


def _trim_payload_to_limit(enriched: dict[str, Any], limit_bytes: int) -> dict[str, Any]:
    if _json_size_bytes(enriched) <= limit_bytes:
        return enriched

    trimmed = dict(enriched)
    all_chunks = list(trimmed.get("content_chunks") or [])
    total_chunks = len(all_chunks)

    base = dict(trimmed)
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


def index_document(
    client: OpenSearch,
    payload: dict[str, Any],
    *,
    refresh: bool = True,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
    return enriched


def _derive_doc_kind_from_extension(ext: str) -> str:
    ext = (ext or "").lower()
    if ext in {".html", ".htm"}:
        return "html"
    if ext == ".msg":
        return "msg"
    if ext == ".pdf":
        return "pdf"
    if ext == ".docx":
        return "docx"
    if ext in {".xlsx", ".xlsm", ".xltx", ".xltm"}:
        return "xlsx"
    if ext == ".pptx":
        return "pptx"
    if ext in {".txt", ".md", ".csv", ".json", ".log", ".eml", ".xml", ".yaml", ".yml"}:
        return "plain_text"
    if ext in {".doc", ".xls", ".ppt"}:
        return "legacy_office_binary"
    if ext in {".zip", ".rar"}:
        return "archive_listing"
    return "unsupported"


def _profile_extraction_settings(profile: dict[str, Any] | None) -> tuple[str, int]:
    mode = None
    max_chars = None
    if isinstance(profile, dict):
        idx = profile.get("indexing") or {}
        mode = idx.get("extraction_mode")
        max_chars = idx.get("extraction_max_chars")

    if not isinstance(mode, str) or mode.strip().lower() not in {"all", "excerpt"}:
        mode = str(getattr(settings, "extraction_mode", "excerpt")).strip().lower()
    if mode not in {"all", "excerpt"}:
        mode = "excerpt"

    if not isinstance(max_chars, int) or max_chars <= 0:
        max_chars = int(getattr(settings, "extraction_max_chars", 20000))
    return (mode, max_chars)


def _enrich_search_fields(payload: dict[str, Any], *, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    enriched = dict(payload)
    extracted_text = str(enriched.get("content", "") or "")
    chunk_text = ""
    chunk_locations: list[str] = []
    content_type = "unknown"
    extraction_status = "not_extracted"
    extraction_metadata: dict[str, Any] = {}

    path_value = str(enriched.get("path", "") or "")
    extraction_metadata = dict(enriched.get("extraction_metadata", {}) or {})
    current_extractor_version = "4"  # 4 = nested content_chunks + OCR-folded fields
    extraction_metadata["extractor_version"] = current_extractor_version
    if path_value and (not enriched.get("sha256") or str(enriched.get("sha256", "")).strip() == ""):
        path_obj_for_sha = Path(path_value)
        if path_obj_for_sha.exists() and path_obj_for_sha.is_file():
            enriched["sha256"] = sha256_file(path_obj_for_sha)
    extracted = None
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

    enriched.pop("content", None)
    enriched["chunk_locations"] = chunk_locations
    chunks_raw = getattr(extracted, "chunks", None) if extracted else None
    if chunks_raw:
        enriched["content_chunks"] = [
            {
                "location": c["location"],
                "text": c["text"],
                "text_normalized": normalize_text(c.get("text", "")),
                "text_ocr_folded": fold_ocr_spacing(c.get("text", "")),
            }
            for c in chunks_raw
        ]
    else:
        enriched["content_chunks"] = []
    enriched["content_type"] = content_type
    enriched["extraction_status"] = extraction_status
    enriched["extraction_metadata"] = extraction_metadata
    extension = str(Path(path_value).suffix.lower()) if path_value else ""
    enriched["extension"] = extension
    enriched["doc_kind"] = _derive_doc_kind_from_extension(extension)

    title = str(enriched.get("title", ""))
    original_filename = str(enriched.get("original_filename", ""))
    canonical_filename = str(enriched.get("canonical_filename", ""))

    enriched["title_normalized"] = normalize_text(title)
    enriched["title_ocr_folded"] = fold_ocr_spacing(title)
    enriched["original_filename_text"] = original_filename
    enriched["original_filename_normalized"] = normalize_text(original_filename)
    enriched["original_filename_ocr_folded"] = fold_ocr_spacing(original_filename)
    enriched["canonical_filename_text"] = canonical_filename
    enriched["canonical_filename_normalized"] = normalize_text(canonical_filename)
    enriched["canonical_filename_ocr_folded"] = fold_ocr_spacing(canonical_filename)
    enriched["title_suggest"] = title or original_filename
    enriched["original_filename_suggest"] = original_filename
    pre_topics = enriched.get("topics")
    pre_source = str(enriched.get("topics_source") or "").strip()
    if isinstance(pre_topics, list) and pre_topics and pre_source in {"llm", "llm_policy"}:
        enriched["topics"] = [str(t).strip() for t in pre_topics if str(t).strip()]
        enriched["topics_source"] = pre_source
    else:
        topics_input = "\n".join(
            s
            for s in [title, original_filename, canonical_filename, extracted_text]
            if isinstance(s, str) and s.strip()
        )
        topics, topics_source = match_topics(
            text=topics_input,
            business_domain=str(enriched.get("business_domain", "") or "").strip() or None,
            profile=profile,
        )
        enriched["topics"] = topics
        enriched["topics_source"] = topics_source
    return enriched


# ---------------------------------------------------------------------------
# Embeddings por chunk (índice separado atlasfile_chunk_vectors)
# ---------------------------------------------------------------------------


def _ensure_chunk_vectors_index_cached(client: OpenSearch, provider: Any) -> None:
    from .opensearch_client import ensure_chunk_vectors_index

    index_name = settings.opensearch_chunk_vectors_index
    if index_name in _ENSURED_VECTOR_INDEXES:
        return
    ensure_chunk_vectors_index(client, provider)
    _ENSURED_VECTOR_INDEXES.add(index_name)


def document_embeddings_up_to_date(
    client: OpenSearch,
    doc_id: str,
    sha256: str,
    provider: Any,
) -> bool:
    """True se o índice de vetores já tem chunks deste doc para o mesmo sha256+modelo."""
    if not sha256:
        return False
    try:
        res = client.search(
            index=settings.opensearch_chunk_vectors_index,
            body={
                "query": {"term": {"doc_id": doc_id}},
                "size": 1,
                "_source": ["sha256", "embedding_provider", "embedding_model"],
            },
        )
        hits = res.get("hits", {}).get("hits", [])
        if not hits:
            return False
        src = hits[0].get("_source") or {}
        return (
            src.get("sha256") == sha256
            and src.get("embedding_provider") == provider.provider_name
            and src.get("embedding_model") == provider.model_name
        )
    except Exception:
        return False


def delete_document_chunk_vectors(client: OpenSearch, doc_id: str) -> None:
    """Remove os vetores de um documento. Nunca levanta exceção."""
    try:
        if not client.indices.exists(index=settings.opensearch_chunk_vectors_index):
            return
        client.delete_by_query(
            index=settings.opensearch_chunk_vectors_index,
            body={"query": {"term": {"doc_id": doc_id}}},
            conflicts="proceed",
            refresh=False,
        )
    except Exception:
        logger.exception("Falha ao remover chunk vectors de doc_id=%s", doc_id)


def _set_embedding_status(client: OpenSearch, doc_id: str, status: str) -> None:
    try:
        client.update(
            index=settings.opensearch_index,
            id=doc_id,
            body={"doc": {"embedding_status": status}},
        )
    except Exception:
        pass


def index_document_chunks_embeddings(
    client: OpenSearch,
    payload: dict[str, Any],
    provider: Any | None = None,
    *,
    usage_script_name: str = "embeddings_ingest",
    force: bool = False,
    record_usage: bool = True,
) -> dict[str, Any]:
    """Indexa embeddings dos content_chunks no índice de vetores (1 doc por chunk).

    Idempotente por sha256+provider+modelo (skip incremental, exceto force=True).
    Falha de embedding NUNCA quebra a ingestão: retorna status="failed", loga e
    flaga o doc principal com embedding_status="failed".
    """
    if not getattr(settings, "embedding_enabled", False):
        return {"status": "disabled", "chunks": 0}
    doc_id = str(payload.get("doc_id") or "").strip()
    if not doc_id:
        return {"status": "skipped", "reason": "no_doc_id", "chunks": 0}

    try:
        if provider is None:
            from .embeddings import get_embedding_provider

            provider = get_embedding_provider()
        _ensure_chunk_vectors_index_cached(client, provider)

        sha = str(payload.get("sha256") or "")
        if not force and document_embeddings_up_to_date(client, doc_id, sha, provider):
            return {"status": "skipped", "reason": "up_to_date", "chunks": 0}

        chunks = payload.get("content_chunks") or []
        indexed_chunks = [
            (index, str(chunk.get("text") or ""), str(chunk.get("location") or ""))
            for index, chunk in enumerate(chunks)
            if str(chunk.get("text") or "").strip()
        ]

        delete_document_chunk_vectors(client, doc_id)
        if not indexed_chunks:
            return {"status": "indexed", "chunks": 0}

        tokens_before = int(getattr(provider, "total_tokens_used", 0) or 0)
        embeddings = provider.embed_texts([text for _, text, _ in indexed_chunks])
        tokens_used = int(getattr(provider, "total_tokens_used", 0) or 0) - tokens_before

        actions = [
            {
                "_op_type": "index",
                "_index": settings.opensearch_chunk_vectors_index,
                "_id": f"{doc_id}::{chunk_index:04d}",
                "_source": {
                    "doc_id": doc_id,
                    "project_id": str(payload.get("project_id") or ""),
                    "business_domain": str(payload.get("business_domain") or ""),
                    "document_type": str(payload.get("document_type") or ""),
                    "doc_kind": str(payload.get("doc_kind") or ""),
                    "tags": list(payload.get("tags") or []),
                    "ingested_at": payload.get("ingested_at"),
                    "location": location,
                    "chunk_index": chunk_index,
                    "text": text,
                    "sha256": sha,
                    "embedding_provider": provider.provider_name,
                    "embedding_model": provider.model_name,
                    "embedding": embedding,
                },
            }
            for (chunk_index, text, location), embedding in zip(indexed_chunks, embeddings, strict=True)
        ]
        bulk(client, actions, refresh=False)

        if record_usage and tokens_used > 0:
            from .training_usage import generate_run_id, persist_training_usage

            persist_training_usage(
                script_name=usage_script_name,
                run_id=generate_run_id(),
                provider=provider.provider_name,
                model=provider.model_name,
                usage={"input_tokens": tokens_used},
                records_processed=len(actions),
            )

        _set_embedding_status(client, doc_id, "indexed")
        return {"status": "indexed", "chunks": len(actions), "tokens": tokens_used}
    except Exception:
        logger.exception("Falha ao indexar embeddings de doc_id=%s", doc_id)
        _set_embedding_status(client, doc_id, "failed")
        return {"status": "failed", "chunks": 0}


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
        version_mismatch = metadata.get("extractor_version") != "4"
        needs_backfill = version_mismatch or any(
            field not in src
            for field in (
                "title_normalized",
                "title_ocr_folded",
                "business_domain",
                "original_filename_text",
                "original_filename_normalized",
                "original_filename_ocr_folded",
                "canonical_filename_text",
                "canonical_filename_normalized",
                "canonical_filename_ocr_folded",
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

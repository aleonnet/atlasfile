from __future__ import annotations

from typing import Any

from opensearchpy import OpenSearch

from .config import settings


def get_client() -> OpenSearch:
    """
    OpenSearch client for AtlasFile.

    Notes:
    - We keep verify_certs disabled to match the existing MVP behavior.
    - If you later enable TLS verification, wire cert settings via config/env.
    """
    return OpenSearch(
        hosts=[settings.opensearch_host],
        http_auth=(settings.opensearch_user, settings.opensearch_password),
        use_ssl=settings.opensearch_host.startswith("https://"),
        verify_certs=False,
        ssl_assert_hostname=False,
        ssl_show_warn=False,
        max_retries=5,
        retry_on_status=(429, 502, 503, 504),
        retry_on_timeout=True,
        timeout=60,
    )


def ensure_index(client: OpenSearch) -> None:
    """
    Create or update the documents index.

    This mapping is intentionally "human search" oriented:
    - High-signal fields (title/filenames) are searchable with boosts in queries.
    - Facets use keyword fields: project_id, area_key, doc_kind, topics, decision, tags, etc.
    - Full text lives in content + nested content_chunks with location + inner_hits.
    """
    index_name = settings.opensearch_index

    # Properties are safe to PUT on an existing index (backward-compatible expansion).
    # Avoid renaming existing fields; add new ones.
    properties: dict[str, Any] = {
        # Identity / routing
        "doc_id": {"type": "keyword"},
        "project_id": {"type": "keyword"},
        "area_key": {"type": "keyword"},

        # Title fields (backward compat)
        "title": {"type": "text"},
        "title_normalized": {"type": "text"},
        "title_suggest": {"type": "search_as_you_type"},

        # New: title_guess (preferred by indexer; title is set to title_guess for compat)
        "title_guess": {"type": "text"},
        "title_guess_normalized": {"type": "text"},

        # Content
        "content": {"type": "text"},
        "content_normalized": {"type": "text"},
        "content_chunks_text": {"type": "text"},
        "content_chunks_normalized": {"type": "text"},

        # Location-aware chunks
        "chunk_locations": {"type": "keyword"},
        "content_chunks": {
            "type": "nested",
            "properties": {
                "location": {"type": "keyword"},
                "text": {"type": "text"},
                "text_normalized": {"type": "text"},
            },
        },

        # Extraction diagnostics
        "content_type": {"type": "keyword"},
        "extraction_status": {"type": "keyword"},
        # Keep enabled:false to avoid mapping bloat while still storing the raw dict.
        "extraction_metadata": {"type": "object", "enabled": False},

        # Filenames (keyword for exact match + text for relevance)
        "original_filename": {"type": "keyword"},
        "original_filename_text": {"type": "text"},
        "original_filename_normalized": {"type": "text"},
        "original_filename_suggest": {"type": "search_as_you_type"},
        "canonical_filename": {"type": "keyword"},
        "canonical_filename_text": {"type": "text"},
        "canonical_filename_normalized": {"type": "text"},

        # Path / provenance
        "path": {"type": "keyword"},
        "source_channel": {"type": "keyword"},
        "source_ref": {"type": "keyword"},
        "sender": {"type": "keyword"},
        "received_at": {"type": "date", "ignore_malformed": True},
        "ingested_at": {"type": "date"},
        "processed_at": {"type": "date"},

        # Classification / triage
        "decision": {"type": "keyword"},
        "confidence_score": {"type": "float"},
        "tags": {"type": "keyword"},
        "document_type": {"type": "keyword"},
        "correspondent": {"type": "keyword"},
        "review_status": {"type": "keyword"},

        # Dedupe
        "sha256": {"type": "keyword"},

        # New: explicit facet for type (derived from extension) to support "ppt/pdf" filters
        "extension": {"type": "keyword"},
        "doc_kind": {"type": "keyword"},

        # New: controlled topics (facetable, stable keys)
        "topics": {"type": "keyword"},
        "topics_source": {"type": "keyword"},
    }

    if client.indices.exists(index=index_name):
        # Backward-compatible mapping expansion for existing indexes.
        client.indices.put_mapping(index=index_name, body={"properties": properties})
        return

    mapping: dict[str, Any] = {
        "settings": {
            "index": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                # Keep defaults for analyzers; project language is pt-BR but your normalize_text
                # already handles diacritics. If you later want a Portuguese analyzer, add it here.
            }
        },
        "mappings": {"properties": properties},
    }
    client.indices.create(index=index_name, body=mapping)


def ensure_chat_sessions_index(client: OpenSearch) -> None:
    """Create or update the chat sessions index (separate from documents)."""
    index_name = settings.opensearch_chat_sessions_index
    properties: dict[str, Any] = {
        "title": {"type": "text"},
        "messages": {"type": "object", "enabled": True},
        "model": {"type": "keyword"},
        "createdAt": {"type": "date"},
        "updatedAt": {"type": "date"},
    }
    if client.indices.exists(index=index_name):
        client.indices.put_mapping(index=index_name, body={"properties": properties})
        return
    mapping: dict[str, Any] = {
        "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}},
        "mappings": {"properties": properties},
    }
    client.indices.create(index=index_name, body=mapping)

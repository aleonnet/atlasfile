from __future__ import annotations

from typing import Any

from opensearchpy import OpenSearch

from .config import settings


def get_client() -> OpenSearch:
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


def _document_index_dynamic_settings() -> dict[str, Any]:
    return {
        "number_of_replicas": 0,
        "highlight.max_analyzed_offset": 10_000_000,
        "mapping.nested_objects.limit": int(settings.opensearch_nested_objects_limit),
    }


def ensure_index(client: OpenSearch) -> None:
    index_name = settings.opensearch_index
    properties: dict[str, Any] = {
        "doc_id": {"type": "keyword"},
        "project_id": {"type": "keyword"},
        "business_domain": {"type": "keyword"},
        "title": {"type": "text"},
        "title_normalized": {"type": "text"},
        "title_ocr_folded": {"type": "text"},
        "title_suggest": {"type": "search_as_you_type"},
        "chunk_locations": {"type": "keyword"},
        "content_chunks": {
            "type": "nested",
            "properties": {
                "location": {"type": "keyword"},
                "text": {"type": "text"},
                "text_normalized": {"type": "text"},
                "text_ocr_folded": {"type": "text"},
            },
        },
        "content_type": {"type": "keyword"},
        "extraction_status": {"type": "keyword"},
        "extraction_metadata": {"type": "object", "enabled": False},
        "original_filename": {"type": "keyword"},
        "original_filename_text": {"type": "text"},
        "original_filename_normalized": {"type": "text"},
        "original_filename_ocr_folded": {"type": "text"},
        "original_filename_suggest": {"type": "search_as_you_type"},
        "canonical_filename": {"type": "keyword"},
        "canonical_filename_text": {"type": "text"},
        "canonical_filename_normalized": {"type": "text"},
        "canonical_filename_ocr_folded": {"type": "text"},
        "path": {"type": "keyword"},
        "source_channel": {"type": "keyword"},
        "source_ref": {"type": "keyword"},
        "sender": {"type": "keyword"},
        "received_at": {"type": "date", "ignore_malformed": True},
        "ingested_at": {"type": "date"},
        "processed_at": {"type": "date"},
        "decision": {"type": "keyword"},
        "confidence_score": {"type": "float"},
        "business_domain_confidence": {"type": "float"},
        "document_type_confidence": {"type": "float"},
        "classifier_mode": {"type": "keyword"},
        "classifier_requested_mode": {"type": "keyword"},
        "classifier_fallback_reason": {"type": "keyword"},
        "sha256": {"type": "keyword"},
        "tags": {"type": "keyword"},
        "document_type": {"type": "keyword"},
        "entities": {"type": "object", "enabled": False},
        "correspondent": {"type": "keyword"},
        "review_status": {"type": "keyword"},
        "doc_kind": {"type": "keyword"},
        "extension": {"type": "keyword"},
        "topics": {"type": "keyword"},
        "topics_source": {"type": "keyword"},
    }

    if client.indices.exists(index=index_name):
        # Backward-compatible mapping expansion for existing indexes.
        client.indices.put_settings(index=index_name, body={"index": _document_index_dynamic_settings()})
        client.indices.put_mapping(index=index_name, body={"properties": properties})
        return

    mapping: dict[str, Any] = {
        "settings": {
            "index": {
                "number_of_shards": 1,
                **_document_index_dynamic_settings(),
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
        "project_id": {"type": "keyword"},
        "usage_totals": {"type": "object", "enabled": True},
        "usage_by_model": {"type": "object", "enabled": False},
        "channel": {"type": "keyword"},
        "channel_chat_id": {"type": "keyword"},
    }
    if client.indices.exists(index=index_name):
        client.indices.put_mapping(index=index_name, body={"properties": properties})
        return
    mapping: dict[str, Any] = {
        "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}},
        "mappings": {"properties": properties},
    }
    client.indices.create(index=index_name, body=mapping)


def ensure_classification_usage_index(client: OpenSearch) -> None:
    """Create or update the classification usage index for LLM cost tracking."""
    index_name = settings.opensearch_classification_usage_index
    properties: dict[str, Any] = {
        "doc_id": {"type": "keyword"},
        "filename": {"type": "keyword"},
        "project_id": {"type": "keyword"},
        "provider": {"type": "keyword"},
        "model": {"type": "keyword"},
        "timestamp": {"type": "date"},
        "input_tokens": {"type": "integer"},
        "output_tokens": {"type": "integer"},
        "cache_read_input_tokens": {"type": "integer"},
        "cache_creation_input_tokens": {"type": "integer"},
        "estimated_cost_usd": {"type": "float"},
    }
    if client.indices.exists(index=index_name):
        client.indices.put_mapping(index=index_name, body={"properties": properties})
        return
    mapping: dict[str, Any] = {
        "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}},
        "mappings": {"properties": properties},
    }
    client.indices.create(index=index_name, body=mapping)

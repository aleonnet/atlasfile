from __future__ import annotations

import logging
from typing import Any

from opensearchpy import OpenSearch

from .config import settings

logger = logging.getLogger(__name__)


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
        "embedding_status": {"type": "keyword"},
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


def ensure_chunk_vectors_index(client: OpenSearch, provider: Any | None = None) -> None:
    """Create the per-chunk vector index (separate from the main documents index).

    O índice principal não recebe knn_vector (index.knn é setting estático → exigiria
    reindex). Cada doc aqui é 1 chunk, com metadados duplicados para filtered k-NN
    (engine lucene, suportado no OpenSearch 2.17).
    Se o índice já existe com _meta divergente das settings atuais, apenas loga alerta
    instruindo re-embed — nunca recria automaticamente.
    """
    from .embeddings import get_embedding_provider

    index_name = settings.opensearch_chunk_vectors_index
    if provider is None:
        provider = get_embedding_provider()
    meta = {
        "embedding_provider": provider.provider_name,
        "embedding_model": provider.model_name,
        "embedding_dimension": int(provider.dimension),
    }

    if client.indices.exists(index=index_name):
        try:
            mapping = client.indices.get_mapping(index=index_name)
            existing_meta = (next(iter(mapping.values())).get("mappings") or {}).get("_meta") or {}
        except Exception:
            existing_meta = {}
        if existing_meta and existing_meta != meta:
            logger.warning(
                "Índice %s foi criado com %s mas as settings atuais pedem %s. "
                "Para trocar provider/modelo/dimensão: delete o índice e rode "
                "scripts/backfill_embeddings.py --force.",
                index_name,
                existing_meta,
                meta,
            )
        return

    properties: dict[str, Any] = {
        "doc_id": {"type": "keyword"},
        "project_id": {"type": "keyword"},
        "business_domain": {"type": "keyword"},
        "document_type": {"type": "keyword"},
        "doc_kind": {"type": "keyword"},
        "tags": {"type": "keyword"},
        "ingested_at": {"type": "date", "ignore_malformed": True},
        "location": {"type": "keyword"},
        "chunk_index": {"type": "integer"},
        "text": {"type": "text"},
        "sha256": {"type": "keyword"},
        "embedding_provider": {"type": "keyword"},
        "embedding_model": {"type": "keyword"},
        "embedding": {
            "type": "knn_vector",
            "dimension": int(provider.dimension),
            "method": {
                "name": "hnsw",
                "space_type": "cosinesimil",
                "engine": "lucene",
                "parameters": {"m": 16, "ef_construction": 100},
            },
        },
    }
    body: dict[str, Any] = {
        "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0, "knn": True}},
        "mappings": {"_meta": meta, "properties": properties},
    }
    client.indices.create(index=index_name, body=body)


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


def ensure_chat_usage_index(client: OpenSearch) -> None:
    """Uso LLM do chat ACHATADO (1 doc por chamada): o custo por sessão vive
    aninhado em usage_by_model e não é agregável em visualização — este índice
    é o que permite custo de chat por dia × modelo no dashboard."""
    index_name = settings.opensearch_chat_usage_index
    properties: dict[str, Any] = {
        "session_id": {"type": "keyword"},
        "channel": {"type": "keyword"},
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


def ensure_training_usage_index(client: OpenSearch) -> None:
    """Create or update the training/pipeline usage index for LLM cost tracking."""
    index_name = settings.opensearch_training_usage_index
    properties: dict[str, Any] = {
        "script_name": {"type": "keyword"},
        "run_id": {"type": "keyword"},
        "provider": {"type": "keyword"},
        "model": {"type": "keyword"},
        "timestamp": {"type": "date"},
        "input_tokens": {"type": "integer"},
        "output_tokens": {"type": "integer"},
        "cache_read_input_tokens": {"type": "integer"},
        "cache_creation_input_tokens": {"type": "integer"},
        "estimated_cost_usd": {"type": "float"},
        "records_processed": {"type": "integer"},
        "error_count": {"type": "integer"},
    }
    if client.indices.exists(index=index_name):
        client.indices.put_mapping(index=index_name, body={"properties": properties})
        return
    mapping: dict[str, Any] = {
        "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}},
        "mappings": {"properties": properties},
    }
    client.indices.create(index=index_name, body=mapping)

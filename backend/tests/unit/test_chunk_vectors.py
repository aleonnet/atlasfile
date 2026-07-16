"""Unit tests: índice de vetores (ensure_chunk_vectors_index) e indexação de embeddings por chunk."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

import app.indexer as indexer_module
from app.config import settings
from app.indexer import document_embeddings_up_to_date, index_document_chunks_embeddings
from app.opensearch_client import ensure_chunk_vectors_index


class _StubProvider:
    provider_name = "openai"

    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail
        self.total_tokens_used = 0
        self.embedded: list[list[str]] = []

    @property
    def model_name(self) -> str:
        return "text-embedding-3-small"

    @property
    def dimension(self) -> int:
        return 1536

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if self._fail:
            raise RuntimeError("provider indisponível")
        self.embedded.append(list(texts))
        return [[0.1, 0.2] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]


@pytest.fixture(autouse=True)
def _reset_ensured_indexes(monkeypatch):
    monkeypatch.setattr(indexer_module, "_ENSURED_VECTOR_INDEXES", set())


def test_ensure_chunk_vectors_index_creates_with_knn_mapping() -> None:
    client = MagicMock()
    client.indices.exists.return_value = False

    ensure_chunk_vectors_index(client, _StubProvider())

    client.indices.create.assert_called_once()
    _, kwargs = client.indices.create.call_args
    body = kwargs["body"]
    assert body["settings"]["index"]["knn"] is True
    embedding = body["mappings"]["properties"]["embedding"]
    assert embedding["type"] == "knn_vector"
    assert embedding["dimension"] == 1536
    assert embedding["method"]["engine"] == "lucene"
    assert body["mappings"]["_meta"]["embedding_model"] == "text-embedding-3-small"


def test_ensure_chunk_vectors_index_warns_but_never_recreates_on_meta_divergence(caplog) -> None:
    client = MagicMock()
    client.indices.exists.return_value = True
    client.indices.get_mapping.return_value = {
        settings.opensearch_chunk_vectors_index: {
            "mappings": {
                "_meta": {
                    "embedding_provider": "fastembed",
                    "embedding_model": "intfloat/multilingual-e5-small",
                    "embedding_dimension": 384,
                }
            }
        }
    }

    with caplog.at_level("WARNING"):
        ensure_chunk_vectors_index(client, _StubProvider())

    client.indices.create.assert_not_called()
    assert any("backfill_embeddings" in record.message for record in caplog.records)


class _FakeVectorClient:
    """Cliente fake com respostas controladas para o fluxo de embeddings."""

    def __init__(self, search_hits: list[dict[str, Any]] | None = None) -> None:
        self.indices = MagicMock()
        self.indices.exists.return_value = True
        self._search_hits = search_hits or []
        self.updates: list[tuple[str, str, dict]] = []
        self.deleted: list[dict] = []

    def search(self, index=None, body=None):
        return {"hits": {"hits": self._search_hits}}

    def delete_by_query(self, index=None, body=None, **kwargs):
        self.deleted.append(body)
        return {"deleted": 0}

    def update(self, index=None, id=None, body=None):
        self.updates.append((index, id, body))


def _payload() -> dict[str, Any]:
    return {
        "doc_id": "doc-1",
        "project_id": "proj-1",
        "business_domain": "juridico",
        "document_type": "contrato",
        "doc_kind": "pdf",
        "tags": ["contrato"],
        "ingested_at": "2026-07-16T00:00:00+00:00",
        "sha256": "abc123",
        "content_chunks": [
            {"location": "page_1", "text": "primeiro chunk"},
            {"location": "page_2", "text": "segundo chunk"},
            {"location": "page_3", "text": "   "},  # vazio: não embeda
        ],
    }


def test_index_document_chunks_embeddings_disabled_by_default() -> None:
    # conftest desabilita embedding_enabled por default
    result = index_document_chunks_embeddings(_FakeVectorClient(), _payload())

    assert result == {"status": "disabled", "chunks": 0}


def test_index_document_chunks_embeddings_indexes_chunks(monkeypatch) -> None:
    monkeypatch.setattr(settings, "embedding_enabled", True)
    client = _FakeVectorClient()
    provider = _StubProvider()
    captured: list[list[dict]] = []
    monkeypatch.setattr(indexer_module, "bulk", lambda _client, actions, **kw: captured.append(list(actions)))

    result = index_document_chunks_embeddings(client, _payload(), provider)

    assert result["status"] == "indexed"
    assert result["chunks"] == 2
    actions = captured[0]
    assert [a["_id"] for a in actions] == ["doc-1::0000", "doc-1::0001"]
    first = actions[0]["_source"]
    assert first["project_id"] == "proj-1"
    assert first["sha256"] == "abc123"
    assert first["embedding"] == [0.1, 0.2]
    assert first["embedding_model"] == "text-embedding-3-small"
    # flag no doc principal
    assert client.updates[-1][2] == {"doc": {"embedding_status": "indexed"}}


def test_index_document_chunks_embeddings_failure_never_raises(monkeypatch) -> None:
    monkeypatch.setattr(settings, "embedding_enabled", True)
    client = _FakeVectorClient()

    result = index_document_chunks_embeddings(client, _payload(), _StubProvider(fail=True))

    assert result["status"] == "failed"
    assert client.updates[-1][2] == {"doc": {"embedding_status": "failed"}}


def test_index_document_chunks_embeddings_skips_when_up_to_date(monkeypatch) -> None:
    monkeypatch.setattr(settings, "embedding_enabled", True)
    hits = [
        {
            "_source": {
                "sha256": "abc123",
                "embedding_provider": "openai",
                "embedding_model": "text-embedding-3-small",
            }
        }
    ]
    client = _FakeVectorClient(search_hits=hits)
    provider = _StubProvider()

    result = index_document_chunks_embeddings(client, _payload(), provider)

    assert result == {"status": "skipped", "reason": "up_to_date", "chunks": 0}
    assert provider.embedded == []


def test_document_embeddings_up_to_date_detects_model_change() -> None:
    hits = [
        {
            "_source": {
                "sha256": "abc123",
                "embedding_provider": "openai",
                "embedding_model": "outro-modelo",
            }
        }
    ]
    client = _FakeVectorClient(search_hits=hits)

    assert document_embeddings_up_to_date(client, "doc-1", "abc123", _StubProvider()) is False

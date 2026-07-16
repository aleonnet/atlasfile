"""Unit tests: fusão RRF, braço semântico, rerank e integração do mode=hybrid no /api/search."""
from __future__ import annotations

import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import app.search_hybrid as search_hybrid_module
from app.config import settings
from app.search_hybrid import (
    build_chunk_filters,
    rerank_pairs,
    rrf_fuse,
    semantic_search,
    semantic_search_chunks,
)


# ---------------------------------------------------------------------------
# rrf_fuse
# ---------------------------------------------------------------------------


def test_rrf_fuse_is_deterministic_and_favors_docs_in_both_arms() -> None:
    fused = rrf_fuse([["a", "b", "c"], ["b", "d"]], rank_constant=60)

    ids = [doc_id for doc_id, _ in fused]
    scores = dict(fused)
    # "b" aparece nos dois braços (rank 2 e rank 1) → maior score
    assert ids[0] == "b"
    assert scores["b"] == pytest.approx(1 / 62 + 1 / 61)
    assert scores["a"] == pytest.approx(1 / 61)
    assert set(ids) == {"a", "b", "c", "d"}


def test_rrf_fuse_breaks_score_ties_by_doc_id() -> None:
    # Mesmo rank em braços distintos → mesmo score; desempate lexicográfico estável.
    fused = rrf_fuse([["z"], ["a"]], rank_constant=60)

    assert [doc_id for doc_id, _ in fused] == ["a", "z"]


def test_rrf_fuse_ignores_empty_ids() -> None:
    fused = rrf_fuse([["", "a"], []])

    assert [doc_id for doc_id, _ in fused] == ["a"]


# ---------------------------------------------------------------------------
# build_chunk_filters
# ---------------------------------------------------------------------------


def test_build_chunk_filters_includes_project_aliases_and_all_filters() -> None:
    filters = build_chunk_filters(
        project_id="Kaidô",
        business_domain="juridico",
        tags=["contrato"],
        document_type="contrato",
        doc_kind="pdf",
        date_from="2026-01-01",
        date_to="2026-12-31",
    )

    project_terms = filters[0]["terms"]["project_id"]
    assert "Kaidô" in project_terms
    assert "kaido" in project_terms  # alias normalizado
    assert {"term": {"business_domain": "juridico"}} in filters
    assert {"terms": {"tags": ["contrato"]}} in filters
    assert {"range": {"ingested_at": {"gte": "2026-01-01"}}} in filters
    assert {"range": {"ingested_at": {"lte": "2026-12-31"}}} in filters


# ---------------------------------------------------------------------------
# semantic_search / semantic_search_chunks
# ---------------------------------------------------------------------------


class _StubProvider:
    provider_name = "openai"
    model_name = "text-embedding-3-small"
    dimension = 1536
    total_tokens_used = 0

    def embed_query(self, text: str) -> list[float]:
        return [0.1, 0.2]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2] for _ in texts]


def _knn_response() -> dict[str, Any]:
    return {
        "hits": {
            "hits": [
                {"_score": 0.9, "_source": {"doc_id": "doc-1", "location": "page:1", "text": "trecho um", "chunk_index": 0}},
                {"_score": 0.8, "_source": {"doc_id": "doc-2", "location": "page:3", "text": "trecho dois", "chunk_index": 2}},
                {"_score": 0.7, "_source": {"doc_id": "doc-1", "location": "page:2", "text": "trecho três", "chunk_index": 1}},
            ]
        }
    }


def test_semantic_search_returns_none_when_embeddings_disabled() -> None:
    # conftest desabilita embedding_enabled por default
    assert semantic_search(MagicMock(), "consulta") is None


def test_semantic_search_aggregates_by_doc_with_max_score(monkeypatch) -> None:
    monkeypatch.setattr(settings, "embedding_enabled", True)
    client = MagicMock()
    client.search.return_value = _knn_response()

    docs = semantic_search(client, "consulta", provider=_StubProvider(), filters=[{"term": {"project_id": "p"}}])

    assert docs is not None
    assert [d["doc_id"] for d in docs] == ["doc-1", "doc-2"]
    assert docs[0]["score"] == 0.9
    assert [c["location"] for c in docs[0]["chunks"]] == ["page:1", "page:2"]
    body = client.search.call_args.kwargs["body"]
    assert body["query"]["knn"]["embedding"]["vector"] == [0.1, 0.2]
    assert body["query"]["knn"]["embedding"]["filter"] == {"bool": {"filter": [{"term": {"project_id": "p"}}]}}


def test_semantic_search_returns_none_on_client_failure(monkeypatch) -> None:
    monkeypatch.setattr(settings, "embedding_enabled", True)
    client = MagicMock()
    client.search.side_effect = RuntimeError("índice fora do ar")

    assert semantic_search(client, "consulta", provider=_StubProvider()) is None


def test_semantic_search_chunks_returns_raw_chunks(monkeypatch) -> None:
    monkeypatch.setattr(settings, "embedding_enabled", True)
    client = MagicMock()
    client.search.return_value = _knn_response()

    chunks = semantic_search_chunks(client, "consulta", provider=_StubProvider(), k=3)

    assert chunks is not None
    assert len(chunks) == 3
    assert chunks[0] == {"doc_id": "doc-1", "location": "page:1", "text": "trecho um", "chunk_index": 0, "score": 0.9}


# ---------------------------------------------------------------------------
# rerank_pairs
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_reranker_state(monkeypatch):
    monkeypatch.setattr(search_hybrid_module, "_RERANKER", None)
    monkeypatch.setattr(search_hybrid_module, "_RERANKER_ERROR", None)


def test_rerank_pairs_disabled_returns_none() -> None:
    assert rerank_pairs("consulta", ["texto"]) is None


def test_rerank_pairs_missing_fastembed_disables_and_returns_none(monkeypatch) -> None:
    monkeypatch.setattr(settings, "search_rerank_enabled", True)
    monkeypatch.setitem(sys.modules, "fastembed", None)
    monkeypatch.setitem(sys.modules, "fastembed.rerank.cross_encoder", None)

    assert rerank_pairs("consulta", ["texto"]) is None
    assert search_hybrid_module._RERANKER_ERROR is not None
    # Chamada seguinte não tenta de novo (curto-circuito)
    assert rerank_pairs("consulta", ["texto"]) is None


def test_rerank_pairs_scores_with_stub_model(monkeypatch) -> None:
    monkeypatch.setattr(settings, "search_rerank_enabled", True)
    stub = MagicMock()
    stub.rerank.return_value = [0.2, 0.9]
    monkeypatch.setattr(search_hybrid_module, "_RERANKER", stub)

    scores = rerank_pairs("consulta", ["texto a", "texto b"])

    assert scores == [0.2, 0.9]
    stub.rerank.assert_called_once_with("consulta", ["texto a", "texto b"])


# ---------------------------------------------------------------------------
# GET /api/search — integração do modo híbrido
# ---------------------------------------------------------------------------


def _lexical_os_response() -> dict[str, Any]:
    return {
        "hits": {
            "total": {"value": 1},
            "hits": [
                {
                    "_score": 3.2,
                    "_source": {
                        "doc_id": "doc-lex",
                        "project_id": "proj-1",
                        "business_domain": "juridico",
                        "document_type": "contrato",
                        "original_filename": "Contrato_Locacao.pdf",
                        "canonical_filename": "contrato_locacao.pdf",
                        "path": "/projects/proj-1/02_AREAS/juridico/contrato/Contrato_Locacao.pdf",
                    },
                }
            ],
        }
    }


def test_search_hybrid_degrades_to_lexical_when_semantic_unavailable(client) -> None:
    # embedding_enabled=False (conftest) → braço semântico indisponível → degrade.
    with patch("app.main.os_client") as mock_os:
        mock_os.search.return_value = _lexical_os_response()
        response = client.get("/api/search", params={"q": "contrato", "mode": "hybrid"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["search_mode_effective"] == "lexical"
    assert payload["hits"][0]["doc_id"] == "doc-lex"


def test_search_lexical_mode_reports_effective_mode(client) -> None:
    with patch("app.main.os_client") as mock_os:
        mock_os.search.return_value = _lexical_os_response()
        response = client.get("/api/search", params={"q": "contrato", "mode": "lexical"})

    assert response.status_code == 200
    assert response.json()["search_mode_effective"] == "lexical"


def test_search_hybrid_fuses_and_appends_semantic_only_docs(client) -> None:
    semantic_docs = [
        {
            "doc_id": "doc-sem",
            "score": 0.88,
            "chunks": [{"location": "page:2", "text": "cláusula de locação residencial", "chunk_index": 1, "score": 0.88}],
        },
        {
            "doc_id": "doc-lex",
            "score": 0.75,
            "chunks": [{"location": "page:9", "text": "vigência e renovação", "chunk_index": 8, "score": 0.75}],
        },
    ]
    mget_response = {
        "docs": [
            {
                "found": True,
                "_id": "doc-sem",
                "_source": {
                    "doc_id": "doc-sem",
                    "project_id": "proj-1",
                    "original_filename": "Locacao_Residencial.pdf",
                    "canonical_filename": "locacao_residencial.pdf",
                    "path": "/projects/proj-1/02_AREAS/juridico/contrato/Locacao_Residencial.pdf",
                },
            }
        ]
    }
    with (
        patch("app.main.os_client") as mock_os,
        patch("app.main.semantic_search", return_value=semantic_docs),
    ):
        mock_os.search.return_value = _lexical_os_response()
        mock_os.mget.return_value = mget_response
        response = client.get("/api/search", params={"q": "contrato de aluguel", "mode": "hybrid"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["search_mode_effective"] == "hybrid"
    assert payload["total"] == 2
    ids = [hit["doc_id"] for hit in payload["hits"]]
    # doc-lex aparece nos dois braços → vence na fusão RRF
    assert ids == ["doc-lex", "doc-sem"]
    lex_hit = payload["hits"][0]
    semantic_evidences = [e for e in lex_hit["evidences"] if e.get("match_type") == "semantic"]
    assert semantic_evidences and semantic_evidences[0]["location"] == "page:9"
    sem_hit = payload["hits"][1]
    assert sem_hit["original_filename"] == "Locacao_Residencial.pdf"
    assert sem_hit["evidences"][0]["match_type"] == "semantic"
    assert sem_hit["evidences"][0]["snippet"].startswith("cláusula de locação")


def test_search_semantic_mode_returns_only_semantic_docs(client) -> None:
    semantic_docs = [
        {
            "doc_id": "doc-sem",
            "score": 0.9,
            "chunks": [{"location": "page:1", "text": "texto semântico", "chunk_index": 0, "score": 0.9}],
        }
    ]
    mget_response = {
        "docs": [
            {
                "found": True,
                "_id": "doc-sem",
                "_source": {
                    "doc_id": "doc-sem",
                    "project_id": "proj-1",
                    "original_filename": "Doc_Semantico.pdf",
                    "canonical_filename": "doc_semantico.pdf",
                    "path": "/projects/proj-1/x/Doc_Semantico.pdf",
                },
            }
        ]
    }
    with (
        patch("app.main.os_client") as mock_os,
        patch("app.main.semantic_search", return_value=semantic_docs),
    ):
        mock_os.mget.return_value = mget_response
        response = client.get("/api/search", params={"q": "conceito parafraseado", "mode": "semantic"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["search_mode_effective"] == "semantic"
    assert [hit["doc_id"] for hit in payload["hits"]] == ["doc-sem"]
    # BM25 não deve ser executado no modo semantic
    mock_os.search.assert_not_called()


def test_search_chunks_endpoint_reports_unavailable_without_embeddings(client) -> None:
    with patch("app.main.os_client"):
        response = client.get("/api/search/chunks", params={"q": "contrato"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is False
    assert payload["chunks"] == []

"""Busca híbrida: braço semântico (kNN no índice de chunks) + fusão RRF + rerank opcional.

OpenSearch 2.17 não tem RRF nativo (só ≥2.19) e a hybrid query não convive com a
query BM25 atual (inner_hits/highlights) nem com índices distintos — por isso a
fusão é manual em Python. Este módulo isola o ponto de troca caso a stack suba
para uma versão com RRF nativo.

Rerank: cross-encoder ONNX via fastembed (mesma dependência opcional dos
embeddings locais, sem torch). Decisão registrada no plano rag_hibrido_permissoes_ui_v2
(ajuste aprovado 2026-07-16 após verificação SOTA: cross-encoder > LLM listwise
em custo/latência/qualidade para top-20).
"""

from __future__ import annotations

import logging
from typing import Any

from opensearchpy import OpenSearch

from .config import settings
from .utils import normalize_text

logger = logging.getLogger(__name__)

# Evidências semânticas retornadas por documento na busca agregada.
TOP_CHUNKS_PER_DOC = 3

# Multilíngue (pt-BR incluído), suportado pelo fastembed. Licença CC-BY-NC-4.0 —
# para uso comercial, configurar search_rerank_model com alternativa adequada.
DEFAULT_RERANK_MODEL = "jinaai/jina-reranker-v2-base-multilingual"

_RERANKER: Any | None = None
_RERANKER_ERROR: str | None = None


def build_chunk_filters(
    *,
    project_id: str | None = None,
    business_domain: str | None = None,
    tags: list[str] | None = None,
    document_type: str | None = None,
    doc_kind: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    """Filtros equivalentes aos da busca principal, sobre os campos do índice de chunks."""
    filters: list[dict[str, Any]] = []
    if project_id:
        aliases = {project_id}
        normalized = normalize_text(project_id).replace(" ", "_")
        if normalized:
            aliases.add(normalized)
        filters.append({"terms": {"project_id": sorted(aliases)}})
    if business_domain:
        filters.append({"term": {"business_domain": business_domain}})
    if tags:
        filters.append({"terms": {"tags": tags}})
    if document_type:
        filters.append({"term": {"document_type": document_type}})
    if doc_kind:
        filters.append({"term": {"doc_kind": doc_kind}})
    if date_from:
        filters.append({"range": {"ingested_at": {"gte": date_from}}})
    if date_to:
        filters.append({"range": {"ingested_at": {"lte": date_to}}})
    return filters


def _record_query_usage(provider: Any, tokens_used: int) -> None:
    if tokens_used <= 0:
        return
    try:
        from .training_usage import generate_run_id, persist_training_usage

        persist_training_usage(
            script_name="embeddings_query",
            run_id=generate_run_id(),
            provider=provider.provider_name,
            model=provider.model_name,
            usage={"input_tokens": tokens_used},
            records_processed=1,
        )
    except Exception:
        pass


def _knn_chunk_hits(
    client: OpenSearch,
    query: str,
    *,
    filters: list[dict[str, Any]] | None = None,
    k: int | None = None,
    provider: Any | None = None,
    record_usage: bool = True,
) -> list[dict[str, Any]] | None:
    """Hits crus do kNN no índice de chunks. None = braço semântico indisponível."""
    if not getattr(settings, "embedding_enabled", False):
        return None
    k = int(k or settings.search_knn_k)
    try:
        if provider is None:
            from .embeddings import get_embedding_provider

            provider = get_embedding_provider()
        tokens_before = int(getattr(provider, "total_tokens_used", 0) or 0)
        vector = provider.embed_query(query)
        tokens_used = int(getattr(provider, "total_tokens_used", 0) or 0) - tokens_before
        knn_clause: dict[str, Any] = {"vector": vector, "k": k}
        if filters:
            knn_clause["filter"] = {"bool": {"filter": list(filters)}}
        body = {
            "size": k,
            "query": {"knn": {"embedding": knn_clause}},
            "_source": ["doc_id", "location", "text", "chunk_index"],
        }
        result = client.search(index=settings.opensearch_chunk_vectors_index, body=body)
    except Exception:
        logger.exception("Braço semântico indisponível; busca degrada para lexical")
        return None
    if record_usage:
        _record_query_usage(provider, tokens_used)
    return list(result.get("hits", {}).get("hits", []))


def semantic_search(
    client: OpenSearch,
    query: str,
    *,
    filters: list[dict[str, Any]] | None = None,
    k: int | None = None,
    provider: Any | None = None,
) -> list[dict[str, Any]] | None:
    """Busca semântica agregada por documento (max score; top chunks como evidências).

    Retorna None quando o braço semântico está indisponível (embedding desabilitado
    ou falha de provider/índice) — o chamador degrada para lexical. Lista vazia
    significa "funcionou, sem resultados".
    """
    hits = _knn_chunk_hits(client, query, filters=filters, k=k, provider=provider)
    if hits is None:
        return None
    docs: dict[str, dict[str, Any]] = {}
    for hit in hits:
        src = hit.get("_source") or {}
        doc_id = str(src.get("doc_id") or "").strip()
        if not doc_id:
            continue
        score = float(hit.get("_score") or 0.0)
        entry = docs.setdefault(doc_id, {"doc_id": doc_id, "score": 0.0, "chunks": []})
        entry["score"] = max(entry["score"], score)
        if len(entry["chunks"]) < TOP_CHUNKS_PER_DOC:
            entry["chunks"].append(
                {
                    "location": str(src.get("location") or ""),
                    "text": str(src.get("text") or ""),
                    "chunk_index": int(src.get("chunk_index") or 0),
                    "score": score,
                }
            )
    return sorted(docs.values(), key=lambda d: -float(d["score"]))


def semantic_search_chunks(
    client: OpenSearch,
    query: str,
    *,
    filters: list[dict[str, Any]] | None = None,
    k: int | None = None,
    provider: Any | None = None,
) -> list[dict[str, Any]] | None:
    """Chunks crus (com location) para RAG com citações. None = indisponível."""
    hits = _knn_chunk_hits(client, query, filters=filters, k=k, provider=provider)
    if hits is None:
        return None
    chunks: list[dict[str, Any]] = []
    for hit in hits:
        src = hit.get("_source") or {}
        doc_id = str(src.get("doc_id") or "").strip()
        if not doc_id:
            continue
        chunks.append(
            {
                "doc_id": doc_id,
                "location": str(src.get("location") or ""),
                "text": str(src.get("text") or ""),
                "chunk_index": int(src.get("chunk_index") or 0),
                "score": float(hit.get("_score") or 0.0),
            }
        )
    return chunks


def rrf_fuse(
    rankings: list[list[str]],
    *,
    rank_constant: int | None = None,
) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion: score = Σ 1/(k + rank), rank 1-based.

    Determinístico: empate de score desempata por doc_id.
    """
    k = int(rank_constant or settings.search_rrf_rank_constant)
    scores: dict[str, float] = {}
    for ranking in rankings:
        for position, doc_id in enumerate(ranking, start=1):
            if not doc_id:
                continue
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + position)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def rerank_pairs(query: str, texts: list[str]) -> list[float] | None:
    """Scores do cross-encoder ONNX (fastembed) para pares (query, texto).

    None quando o rerank está desabilitado ou indisponível (fastembed ausente,
    modelo não baixado) — o chamador mantém a ordem da fusão. Erro é logado uma
    única vez e o rerank fica desligado no processo.
    """
    global _RERANKER, _RERANKER_ERROR
    if not getattr(settings, "search_rerank_enabled", False) or not texts:
        return None
    if _RERANKER_ERROR is not None:
        return None
    try:
        if _RERANKER is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            model = (settings.search_rerank_model or "").strip() or DEFAULT_RERANK_MODEL
            _RERANKER = TextCrossEncoder(model_name=model)
        return [float(score) for score in _RERANKER.rerank(query, list(texts))]
    except Exception as exc:
        _RERANKER_ERROR = str(exc)
        logger.exception(
            "Cross-encoder rerank indisponível (search_rerank_enabled=true). "
            "Instale a dependência opcional: pip install -r backend/requirements-local-embeddings.txt"
        )
        return None

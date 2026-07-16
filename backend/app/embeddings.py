"""Camada de embeddings para a busca semântica (RAG).

Providers plugáveis via settings (``embedding_provider``):
- ``openai``   — text-embedding-3-small (default), via API. Custo rastreado em usage_costs.
- ``fastembed`` — intfloat/multilingual-e5-small local (ONNX, sem torch). Requer
  ``pip install -r backend/requirements-local-embeddings.txt``.

Os vetores são indexados por chunk no índice separado ``atlasfile_chunk_vectors``
(ver opensearch_client.ensure_chunk_vectors_index / indexer.index_document_chunks_embeddings).
"""

from __future__ import annotations

import os
from typing import Protocol

from .config import settings

OPENAI_DEFAULT_MODEL = "text-embedding-3-small"
OPENAI_MODEL_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
}

FASTEMBED_DEFAULT_MODEL = "intfloat/multilingual-e5-small"
FASTEMBED_MODEL_DIMENSIONS = {
    "intfloat/multilingual-e5-small": 384,
}
# Modelos da família e5 exigem prefixos assimétricos query/passage.
_E5_QUERY_PREFIX = "query: "
_E5_PASSAGE_PREFIX = "passage: "


class EmbeddingProvider(Protocol):
    provider_name: str

    @property
    def model_name(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class OpenAIEmbeddingProvider:
    provider_name = "openai"

    def __init__(
        self,
        *,
        model: str | None = None,
        dimension: int | None = None,
        batch_size: int | None = None,
    ) -> None:
        self._model = (model or settings.embedding_model or "").strip() or OPENAI_DEFAULT_MODEL
        resolved_dimension = int(dimension or settings.embedding_dimension or 0)
        if resolved_dimension <= 0:
            resolved_dimension = OPENAI_MODEL_DIMENSIONS.get(self._model, 1536)
        self._dimension = resolved_dimension
        self._batch_size = max(1, int(batch_size or settings.embedding_batch_size or 100))
        self._client = None
        # Acumulado de tokens da instância; consumidores calculam deltas para custo.
        self.total_tokens_used = 0

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    def _get_client(self):
        if self._client is None:
            if not os.environ.get("OPENAI_API_KEY"):
                raise RuntimeError(
                    "OPENAI_API_KEY não configurada — necessária para embedding_provider=openai. "
                    "Alternativa local: embedding_provider=fastembed."
                )
            from openai import OpenAI

            self._client = OpenAI()
        return self._client

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._get_client()
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            # A API rejeita strings vazias; preserva o alinhamento por índice.
            batch = [text if text.strip() else " " for text in texts[start : start + self._batch_size]]
            kwargs = {}
            if self._model in OPENAI_MODEL_DIMENSIONS and self._dimension != OPENAI_MODEL_DIMENSIONS[self._model]:
                kwargs["dimensions"] = self._dimension
            response = client.embeddings.create(model=self._model, input=batch, **kwargs)
            vectors.extend([list(item.embedding) for item in response.data])
            usage = getattr(response, "usage", None)
            if usage:
                self.total_tokens_used += int(getattr(usage, "total_tokens", 0) or 0)
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]


class FastEmbedProvider:
    provider_name = "fastembed"

    def __init__(self, *, model: str | None = None, dimension: int | None = None) -> None:
        self._model = (model or settings.embedding_model or "").strip() or FASTEMBED_DEFAULT_MODEL
        resolved_dimension = int(dimension or settings.embedding_dimension or 0)
        if resolved_dimension <= 0:
            resolved_dimension = FASTEMBED_MODEL_DIMENSIONS.get(self._model, 384)
        self._dimension = resolved_dimension
        self._embedder = None
        self.total_tokens_used = 0  # provider local: custo zero, contagem mantida por simetria

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    def _get_embedder(self):
        if self._embedder is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:
                raise RuntimeError(
                    "fastembed não está instalado. Instale com: "
                    "pip install -r backend/requirements-local-embeddings.txt"
                ) from exc
            self._embedder = TextEmbedding(model_name=self._model)
        return self._embedder

    def _is_e5(self) -> bool:
        return "e5" in self._model.lower()

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        embedder = self._get_embedder()
        prefix = _E5_PASSAGE_PREFIX if self._is_e5() else ""
        prepared = [f"{prefix}{text}" for text in texts]
        return [[float(value) for value in vector] for vector in embedder.embed(prepared)]

    def embed_query(self, text: str) -> list[float]:
        embedder = self._get_embedder()
        prefix = _E5_QUERY_PREFIX if self._is_e5() else ""
        vector = next(iter(embedder.embed([f"{prefix}{text}"])))
        return [float(value) for value in vector]


def get_embedding_provider() -> EmbeddingProvider:
    """Factory por settings. Levanta ValueError para provider desconhecido."""
    provider = (settings.embedding_provider or "openai").strip().lower()
    if provider == "openai":
        return OpenAIEmbeddingProvider()
    if provider == "fastembed":
        return FastEmbedProvider()
    raise ValueError(f"embedding_provider desconhecido: {provider!r} (suportados: openai, fastembed)")

"""Unit tests for app.embeddings: providers, factory, defaults e batching."""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from app.config import settings
from app.embeddings import (
    FastEmbedProvider,
    OpenAIEmbeddingProvider,
    get_embedding_provider,
)


def test_factory_defaults_to_openai_provider() -> None:
    provider = get_embedding_provider()

    assert isinstance(provider, OpenAIEmbeddingProvider)
    assert provider.provider_name == "openai"
    assert provider.model_name == "text-embedding-3-small"
    assert provider.dimension == 1536


def test_factory_returns_fastembed_with_local_defaults(monkeypatch) -> None:
    monkeypatch.setattr(settings, "embedding_provider", "fastembed")

    provider = get_embedding_provider()

    assert isinstance(provider, FastEmbedProvider)
    assert provider.model_name == "intfloat/multilingual-e5-small"
    assert provider.dimension == 384


def test_factory_rejects_unknown_provider(monkeypatch) -> None:
    monkeypatch.setattr(settings, "embedding_provider", "banana")

    with pytest.raises(ValueError, match="embedding_provider desconhecido"):
        get_embedding_provider()


class _FakeOpenAIClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.embeddings = SimpleNamespace(create=self._create)

    def _create(self, *, model: str, input: list[str], **kwargs):
        self.calls.append({"model": model, "input": list(input), **kwargs})
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1, 0.2]) for _ in input],
            usage=SimpleNamespace(total_tokens=len(input) * 10),
        )


def test_openai_provider_batches_and_tracks_tokens() -> None:
    provider = OpenAIEmbeddingProvider(batch_size=2)
    fake = _FakeOpenAIClient()
    provider._client = fake

    vectors = provider.embed_texts(["a", "b", "c", "", "e"])

    assert len(vectors) == 5
    assert len(fake.calls) == 3  # 2 + 2 + 1
    # String vazia é substituída por espaço para preservar alinhamento
    assert fake.calls[1]["input"] == ["c", " "]
    assert provider.total_tokens_used == 50


def test_openai_provider_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = OpenAIEmbeddingProvider()

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        provider.embed_texts(["texto"])


def test_fastembed_missing_dependency_raises_clear_error(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "fastembed", None)
    provider = FastEmbedProvider()

    with pytest.raises(RuntimeError, match="requirements-local-embeddings"):
        provider.embed_texts(["texto"])


class _FakeE5Embedder:
    def __init__(self) -> None:
        self.inputs: list[list[str]] = []

    def embed(self, texts: list[str]):
        self.inputs.append(list(texts))
        return [[0.5] * 4 for _ in texts]


def test_fastembed_e5_applies_query_and_passage_prefixes() -> None:
    provider = FastEmbedProvider()
    fake = _FakeE5Embedder()
    provider._embedder = fake

    provider.embed_texts(["doc um", "doc dois"])
    provider.embed_query("pergunta")

    assert fake.inputs[0] == ["passage: doc um", "passage: doc dois"]
    assert fake.inputs[1] == ["query: pergunta"]

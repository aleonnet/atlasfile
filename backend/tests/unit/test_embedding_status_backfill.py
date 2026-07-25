"""embedding_status regravado quando os vetores já estão em dia (v0.50.5).

Bug real: o reconcile deleta e reindexa o doc principal, mas os vetores do
chunk index sobrevivem — `index_document_chunks_embeddings` via
`document_embeddings_up_to_date` retornava "up_to_date" SEM regravar a flag, e o
painel de saúde de embeddings ficava vazio para sempre (medido no stack dev:
0/108 docs com embedding_status e 10k+ vetores presentes).
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app import indexer


class _FakeProvider:
    provider_name = "openai"
    model_name = "text-embedding-3-small"
    total_tokens_used = 0

    def embed_texts(self, texts):  # pragma: no cover - não deve ser chamado aqui
        raise AssertionError("caminho up_to_date não pode gerar embeddings")


def test_up_to_date_regrava_embedding_status(monkeypatch) -> None:
    # settings do ambiente de teste vem com embeddings desligados; este teste
    # exercita justamente o ramo em que estão ligados e já em dia
    monkeypatch.setattr(indexer.settings, "embedding_enabled", True)
    monkeypatch.setattr(indexer, "_ensure_chunk_vectors_index_cached", lambda *a, **k: None)
    monkeypatch.setattr(indexer, "document_embeddings_up_to_date", lambda *a, **k: True)
    client = MagicMock()

    result = indexer.index_document_chunks_embeddings(
        client,
        {"doc_id": "doc-1", "sha256": "abc", "content_chunks": [{"text": "x", "location": "page:1"}]},
        _FakeProvider(),
    )

    assert result["status"] == "skipped"
    assert result["reason"] == "up_to_date"
    client.update.assert_called_once()
    kwargs = client.update.call_args.kwargs
    assert kwargs["id"] == "doc-1"
    assert kwargs["body"] == {"doc": {"embedding_status": "indexed"}}


def test_embeddings_desligados_nao_tocam_o_indice(monkeypatch) -> None:
    monkeypatch.setattr(indexer.settings, "embedding_enabled", False)
    client = MagicMock()

    result = indexer.index_document_chunks_embeddings(client, {"doc_id": "doc-2"}, _FakeProvider())

    assert result["status"] == "disabled"
    client.update.assert_not_called()

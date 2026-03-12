"""Unit tests for _persist_classification_usage in ingestion module."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.ingestion import _persist_classification_usage


def test_persist_writes_to_opensearch() -> None:
    mock_client = MagicMock()
    with patch("app.ingestion._time") as mock_time, \
         patch("app.opensearch_client.get_client", return_value=mock_client):
        mock_time.time.return_value = 1700000000.0
        _persist_classification_usage(
            doc_id="doc-1",
            filename="contrato.pdf",
            project_id="proj-a",
            provider="openai",
            model="gpt-4o-mini",
            usage={
                "input_tokens": 500,
                "output_tokens": 100,
                "cache_read_input_tokens": 10,
                "cache_creation_input_tokens": 5,
                "estimated_cost_usd": 0.0001,
            },
        )
    mock_client.index.assert_called_once()
    call_kw = mock_client.index.call_args[1]
    assert call_kw["body"]["doc_id"] == "doc-1"
    assert call_kw["body"]["filename"] == "contrato.pdf"
    assert call_kw["body"]["project_id"] == "proj-a"
    assert call_kw["body"]["provider"] == "openai"
    assert call_kw["body"]["model"] == "gpt-4o-mini"
    assert call_kw["body"]["input_tokens"] == 500
    assert call_kw["body"]["output_tokens"] == 100
    assert call_kw["body"]["timestamp"] == 1700000000000


def test_persist_handles_empty_usage() -> None:
    mock_client = MagicMock()
    with patch("app.opensearch_client.get_client", return_value=mock_client), \
         patch("app.ingestion._time") as mock_time:
        mock_time.time.return_value = 1700000000.0
        _persist_classification_usage(
            doc_id="doc-2",
            filename="test.pdf",
            project_id="proj-b",
            provider="anthropic",
            model="claude-haiku-4-5",
            usage={},
        )
    call_kw = mock_client.index.call_args[1]
    assert call_kw["body"]["input_tokens"] == 0
    assert call_kw["body"]["output_tokens"] == 0
    assert call_kw["body"]["estimated_cost_usd"] == 0.0


def test_persist_swallows_exceptions() -> None:
    """Should log but not raise if OpenSearch fails."""
    with patch("app.opensearch_client.get_client", side_effect=Exception("connection refused")), \
         patch("app.ingestion._time") as mock_time:
        mock_time.time.return_value = 1700000000.0
        _persist_classification_usage(
            doc_id="doc-3",
            filename="test.pdf",
            project_id="proj-c",
            provider="openai",
            model="gpt-4o-mini",
            usage={"input_tokens": 10, "output_tokens": 5},
        )

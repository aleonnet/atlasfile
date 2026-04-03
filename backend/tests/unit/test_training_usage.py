"""Tests for training_usage module."""
from unittest.mock import MagicMock, patch

from app.training_usage import generate_run_id, persist_training_usage


class TestGenerateRunId:
    def test_returns_string(self):
        rid = generate_run_id()
        assert isinstance(rid, str)
        assert len(rid) == 36  # UUID4 format

    def test_unique_per_call(self):
        ids = {generate_run_id() for _ in range(10)}
        assert len(ids) == 10


class TestPersistTrainingUsage:
    @patch("app.opensearch_client.get_client")
    @patch("app.training_usage.estimate_usage_cost", return_value=0.0042)
    def test_indexes_document(self, mock_cost, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        persist_training_usage(
            script_name="label_corpus_llm",
            run_id="test-run-id",
            provider="openai",
            model="gpt-4o-mini",
            usage={"input_tokens": 1000, "output_tokens": 200},
            records_processed=1,
            error_count=0,
        )

        mock_cost.assert_called_once_with(
            {"input_tokens": 1000, "output_tokens": 200},
            "openai",
            "gpt-4o-mini",
        )
        mock_client.index.assert_called_once()
        call_kwargs = mock_client.index.call_args
        doc = call_kwargs.kwargs["body"] if "body" in call_kwargs.kwargs else call_kwargs[1]["body"]
        assert doc["script_name"] == "label_corpus_llm"
        assert doc["run_id"] == "test-run-id"
        assert doc["provider"] == "openai"
        assert doc["model"] == "gpt-4o-mini"
        assert doc["input_tokens"] == 1000
        assert doc["output_tokens"] == 200
        assert doc["estimated_cost_usd"] == 0.0042
        assert doc["records_processed"] == 1
        assert doc["error_count"] == 0
        assert "timestamp" in doc

    @patch("app.opensearch_client.get_client")
    def test_does_not_raise_on_error(self, mock_get_client):
        mock_get_client.side_effect = ConnectionError("OpenSearch down")
        # Should not raise
        persist_training_usage(
            script_name="test",
            run_id="r",
            provider="openai",
            model="m",
            usage={},
        )

    @patch("app.opensearch_client.get_client")
    @patch("app.training_usage.estimate_usage_cost", return_value=0.0)
    def test_handles_missing_usage_keys(self, mock_cost, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        persist_training_usage(
            script_name="test",
            run_id="r",
            provider="openai",
            model="m",
            usage={},
        )

        mock_client.index.assert_called_once()
        doc = mock_client.index.call_args.kwargs.get("body") or mock_client.index.call_args[1]["body"]
        assert doc["input_tokens"] == 0
        assert doc["output_tokens"] == 0
        assert doc["cache_read_input_tokens"] == 0
        assert doc["cache_creation_input_tokens"] == 0

"""Tests for api_call_count tracking in orchestrator usage accumulation."""
from app.orchestrator import _accumulate_usage, _usage_return


class TestAccumulateUsageApiCallCount:
    def test_increments_api_call_count(self):
        acc: dict = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "estimated_cost_usd": 0.0}
        _accumulate_usage(acc, {"prompt_tokens": 100, "completion_tokens": 10}, "openai", "gpt-4o-mini")
        assert acc["api_call_count"] == 1

    def test_increments_multiple_calls(self):
        acc: dict = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "estimated_cost_usd": 0.0}
        _accumulate_usage(acc, {"prompt_tokens": 100, "completion_tokens": 10}, "openai", "gpt-4o-mini")
        _accumulate_usage(acc, {"prompt_tokens": 200, "completion_tokens": 20}, "openai", "gpt-4o-mini")
        _accumulate_usage(acc, {"prompt_tokens": 300, "completion_tokens": 30}, "openai", "gpt-4o-mini")
        assert acc["api_call_count"] == 3

    def test_does_not_increment_on_none_raw(self):
        acc: dict = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "estimated_cost_usd": 0.0}
        _accumulate_usage(acc, None, "openai", "gpt-4o-mini")
        assert acc.get("api_call_count", 0) == 0

    def test_does_not_increment_on_empty_raw(self):
        acc: dict = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "estimated_cost_usd": 0.0}
        _accumulate_usage(acc, {}, "openai", "gpt-4o-mini")
        assert acc.get("api_call_count", 0) == 0


class TestUsageReturnApiCallCount:
    def test_includes_api_call_count(self):
        acc = {"input_tokens": 500, "output_tokens": 50, "total_tokens": 550, "estimated_cost_usd": 0.01, "api_call_count": 3}
        result = _usage_return(acc)
        assert result["api_call_count"] == 3

    def test_defaults_to_zero(self):
        acc = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "estimated_cost_usd": 0.0}
        result = _usage_return(acc)
        assert result["api_call_count"] == 0

"""Unit tests for usage_costs: config load, get_cost_per_1m, estimate_usage_cost."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.usage_costs import estimate_usage_cost, get_cost_per_1m


def test_get_cost_per_1m_from_config() -> None:
    with patch("app.usage_costs._load_config") as mock_load:
        mock_load.return_value = {
            "openai": {
                "gpt-4o-mini": {"input": 0.15, "output": 0.60, "cache_read": 0, "cache_write": 0},
            },
            "anthropic": {
                "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_write": 3.0},
            },
        }
        assert get_cost_per_1m("openai", "gpt-4o-mini") == (0.15, 0.60, 0.0, 0.0)
        assert get_cost_per_1m("anthropic", "claude-sonnet-4-6") == (3.0, 15.0, 0.30, 3.0)
        # unknown model: config returns {} so we get (0,0,0,0)
        assert get_cost_per_1m("openai", "unknown") == (0.0, 0.0, 0.0, 0.0)
        # empty provider: prov is {} so entry is {} -> (0,0,0,0)
        assert get_cost_per_1m("", "gpt-4o-mini") == (0.0, 0.0, 0.0, 0.0)


def test_estimate_usage_cost_empty() -> None:
    assert estimate_usage_cost(None, "openai", "gpt-4o-mini") == 0.0
    assert estimate_usage_cost({}, "openai", "gpt-4o-mini") == 0.0


def test_estimate_usage_cost_unknown_model() -> None:
    with patch("app.usage_costs.get_cost_per_1m", return_value=None):
        assert estimate_usage_cost({"input_tokens": 1000, "output_tokens": 500}, "x", "y") == 0.0


def test_estimate_usage_cost_from_config() -> None:
    with patch("app.usage_costs.get_cost_per_1m", return_value=(0.15, 0.60, 0.0, 0.0)):
        cost = estimate_usage_cost(
            {"input_tokens": 1_000_000, "output_tokens": 500_000},
            "openai",
            "gpt-4o-mini",
        )
        assert cost == pytest.approx(0.15 + 0.30, rel=1e-5)
        assert cost == 0.45


def test_estimate_usage_cost_embedding_model() -> None:
    with patch("app.usage_costs._load_config") as mock_load:
        mock_load.return_value = {
            "openai": {
                "text-embedding-3-small": {"input": 0.02, "output": 0, "cache_read": 0, "cache_write": 0},
            },
        }
        cost = estimate_usage_cost(
            {"input_tokens": 1_000_000},
            "openai",
            "text-embedding-3-small",
        )
        assert cost == pytest.approx(0.02, rel=1e-6)

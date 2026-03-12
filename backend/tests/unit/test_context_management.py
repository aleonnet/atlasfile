"""Unit tests for context window management: _trim_history_to_context, _estimate_context_pressure."""
from __future__ import annotations

import pytest

from app.orchestrator import _estimate_context_pressure, _trim_history_to_context


# ---------------------------------------------------------------------------
# _estimate_context_pressure
# ---------------------------------------------------------------------------

def test_estimate_pressure_empty_messages():
    result = _estimate_context_pressure([], "openai", "gpt-4.1")
    assert result["context_tokens_estimate"] == 0
    assert result["context_pressure_ratio"] == 0.0
    assert result["context_tokens_limit"] > 0


def test_estimate_pressure_with_content():
    content = "x" * 4000  # ~1000 tokens
    msgs = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": content},
    ]
    result = _estimate_context_pressure(msgs, "openai", "gpt-4.1")
    assert result["context_tokens_estimate"] > 0
    assert 0.0 < result["context_pressure_ratio"] < 0.1
    assert result["context_tokens_limit"] == 1_047_576


def test_estimate_pressure_ratio_capped_at_1():
    huge = "x" * 4_000_000
    msgs = [{"role": "user", "content": huge}]
    result = _estimate_context_pressure(msgs, "anthropic", "claude-haiku-4-5")
    assert result["context_pressure_ratio"] == 1.0


def test_estimate_pressure_uses_correct_model_limit():
    msgs = [{"role": "user", "content": "test"}]
    r_haiku = _estimate_context_pressure(msgs, "anthropic", "claude-haiku-4-5")
    assert r_haiku["context_tokens_limit"] == 200_000
    r_gpt4 = _estimate_context_pressure(msgs, "openai", "gpt-4.1")
    assert r_gpt4["context_tokens_limit"] == 1_047_576


def test_estimate_pressure_proportional():
    """More content -> higher pressure."""
    small = [{"role": "user", "content": "x" * 1000}]
    large = [{"role": "user", "content": "x" * 100_000}]
    r_small = _estimate_context_pressure(small, "openai", "gpt-4o-mini")
    r_large = _estimate_context_pressure(large, "openai", "gpt-4o-mini")
    assert r_large["context_pressure_ratio"] > r_small["context_pressure_ratio"]


# ---------------------------------------------------------------------------
# _trim_history_to_context
# ---------------------------------------------------------------------------

def test_trim_short_history_unchanged():
    msgs = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]
    result = _trim_history_to_context(msgs, "openai", "gpt-4.1")
    assert len(result) == 3
    assert result == msgs


def test_trim_preserves_system_prompt():
    """System prompt (first message) is always kept when truncation occurs."""
    system = {"role": "system", "content": "S" * 400}
    # Each message ~10k tokens. gpt-4o-mini context=128k. 60% = 76.8k tokens.
    # ~8 messages would fill it, so 20 should force truncation.
    old_msgs = [{"role": "user", "content": "M" * 40_000} for _ in range(20)]
    latest = {"role": "user", "content": "Latest question"}
    msgs = [system] + old_msgs + [latest]
    result = _trim_history_to_context(msgs, "openai", "gpt-4o-mini")
    assert result[0]["role"] == "system"
    assert result[0]["content"] == system["content"]
    assert result[-1]["content"] == "Latest question"
    assert len(result) < len(msgs)


def test_trim_keeps_at_least_one_message_after_system():
    system = {"role": "system", "content": "S" * 200_000}
    user = {"role": "user", "content": "U" * 200_000}
    msgs = [system, user]
    result = _trim_history_to_context(msgs, "openai", "gpt-4o-mini")
    assert len(result) >= 2
    assert result[0]["role"] == "system"


def test_trim_no_system_prompt():
    """When there's no system prompt, oldest user/assistant messages are dropped."""
    msgs = [{"role": "user", "content": "M" * 40_000} for _ in range(20)]
    msgs.append({"role": "user", "content": "Latest"})
    result = _trim_history_to_context(msgs, "openai", "gpt-4o-mini")
    assert result[-1]["content"] == "Latest"
    assert len(result) < len(msgs)


def test_trim_empty_messages():
    assert _trim_history_to_context([], "openai", "gpt-4.1") == []


def test_trim_large_model_keeps_more():
    """gpt-4.1 has ~1M context, so moderate history should fit."""
    msgs = [{"role": "user", "content": "M" * 200} for _ in range(100)]
    result = _trim_history_to_context(msgs, "openai", "gpt-4.1")
    assert len(result) == 100  # all fit


def test_trim_fifo_order():
    """Oldest messages should be dropped first (FIFO)."""
    msgs = [
        {"role": "user", "content": f"msg-{i}" + "x" * 40_000}
        for i in range(20)
    ]
    result = _trim_history_to_context(msgs, "openai", "gpt-4o-mini")
    # Last message is always the newest
    assert "msg-19" in result[-1]["content"]
    # First surviving message should have a higher index than 0
    first_idx = int(result[0]["content"].split("-")[1].split("x")[0])
    assert first_idx > 0

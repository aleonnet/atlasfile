"""Unit tests for _maybe_mirror_to_channel in main.py."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def _default_settings():
    """Patch settings to have telegram_mirror_responses enabled."""
    with patch("app.main.settings") as mock_settings:
        mock_settings.telegram_mirror_responses = True
        yield mock_settings


@pytest.fixture
def _disabled_settings():
    """Patch settings to have telegram_mirror_responses disabled."""
    with patch("app.main.settings") as mock_settings:
        mock_settings.telegram_mirror_responses = False
        yield mock_settings


def _make_channel(running: bool = True) -> MagicMock:
    ch = MagicMock()
    ch.is_running.return_value = running
    ch.send_message = AsyncMock()
    return ch


def _make_manager(channel: MagicMock | None = None) -> MagicMock:
    mgr = MagicMock()
    mgr.get_channel.return_value = channel
    return mgr


@pytest.mark.asyncio
async def test_mirror_fires_send(_default_settings) -> None:
    """When mirror enabled + session has channel + appended msgs => send_message called for user + assistant."""
    from app.main import _maybe_mirror_to_channel

    ch = _make_channel()
    mgr = _make_manager(ch)

    session_src = {"channel": "telegram", "channel_chat_id": "12345"}
    appended = [
        MagicMock(**{"model_dump.return_value": {"role": "user", "content": "hi"}}),
        MagicMock(**{"model_dump.return_value": {"role": "assistant", "content": "hello back"}}),
    ]

    with patch("app.main.channel_manager", mgr):
        await _maybe_mirror_to_channel(session_src, appended, "web")

    assert ch.send_message.await_count == 2
    ch.send_message.assert_any_await("12345", "🌐 via web:\nhi")
    ch.send_message.assert_any_await("12345", "hello back")


@pytest.mark.asyncio
async def test_mirror_skip_same_channel(_default_settings) -> None:
    """When source_channel == session.channel, mirror is skipped (avoids loop)."""
    from app.main import _maybe_mirror_to_channel

    ch = _make_channel()
    mgr = _make_manager(ch)

    session_src = {"channel": "telegram", "channel_chat_id": "12345"}
    appended = [
        MagicMock(**{"model_dump.return_value": {"role": "assistant", "content": "reply"}}),
    ]

    with patch("app.main.channel_manager", mgr):
        await _maybe_mirror_to_channel(session_src, appended, "telegram")

    ch.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_mirror_disabled(_disabled_settings) -> None:
    """When mirror is disabled in settings, send_message is not called."""
    from app.main import _maybe_mirror_to_channel

    ch = _make_channel()
    mgr = _make_manager(ch)

    session_src = {"channel": "telegram", "channel_chat_id": "12345"}
    appended = [
        MagicMock(**{"model_dump.return_value": {"role": "assistant", "content": "reply"}}),
    ]

    with patch("app.main.channel_manager", mgr):
        await _maybe_mirror_to_channel(session_src, appended, "web")

    ch.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_mirror_no_channel_in_session(_default_settings) -> None:
    """Sessions without channel (web-originated) don't trigger mirror."""
    from app.main import _maybe_mirror_to_channel

    ch = _make_channel()
    mgr = _make_manager(ch)

    session_src = {"channel": "web", "channel_chat_id": None}
    appended = [
        MagicMock(**{"model_dump.return_value": {"role": "assistant", "content": "reply"}}),
    ]

    with patch("app.main.channel_manager", mgr):
        await _maybe_mirror_to_channel(session_src, appended, "web")

    ch.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_mirror_user_only_message(_default_settings) -> None:
    """If appended messages contain only a user message, it is still mirrored with [via web] prefix."""
    from app.main import _maybe_mirror_to_channel

    ch = _make_channel()
    mgr = _make_manager(ch)

    session_src = {"channel": "telegram", "channel_chat_id": "12345"}
    appended = [
        MagicMock(**{"model_dump.return_value": {"role": "user", "content": "only user msg"}}),
    ]

    with patch("app.main.channel_manager", mgr):
        await _maybe_mirror_to_channel(session_src, appended, "web")

    ch.send_message.assert_awaited_once_with("12345", "🌐 via web:\nonly user msg")


@pytest.mark.asyncio
async def test_mirror_no_content(_default_settings) -> None:
    """If appended messages have no content, mirror doesn't fire."""
    from app.main import _maybe_mirror_to_channel

    ch = _make_channel()
    mgr = _make_manager(ch)

    session_src = {"channel": "telegram", "channel_chat_id": "12345"}
    appended = [
        MagicMock(**{"model_dump.return_value": {"role": "user", "content": ""}}),
    ]

    with patch("app.main.channel_manager", mgr):
        await _maybe_mirror_to_channel(session_src, appended, "web")

    ch.send_message.assert_not_awaited()

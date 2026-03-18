"""Unit tests for the channels module (base, manager, telegram)."""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.base import Channel, ChannelMessage, ChannelStatus
from app.channels.manager import ChannelManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeChannel:
    """Minimal Channel implementation for testing."""

    id = "fake"
    name = "Fake"
    description = "Fake channel for tests"

    def __init__(self) -> None:
        self._running = False
        self._start_cfg: dict[str, Any] = {}
        self.sent: list[tuple[str, str]] = []

    async def start(self, config: dict[str, Any]) -> None:
        self._start_cfg = config
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def send_message(self, chat_id: str, text: str) -> None:
        self.sent.append((chat_id, text))

    def is_running(self) -> bool:
        return self._running

    def get_status(self) -> ChannelStatus:
        return ChannelStatus(
            channel_id=self.id,
            name=self.name,
            running=self._running,
            connected=self._running,
        )


# ---------------------------------------------------------------------------
# Channel Protocol
# ---------------------------------------------------------------------------

def test_fake_channel_satisfies_protocol():
    ch = FakeChannel()
    assert isinstance(ch, Channel)


# ---------------------------------------------------------------------------
# ChannelManager -- register
# ---------------------------------------------------------------------------

def test_manager_register_and_list():
    mgr = ChannelManager(on_message=AsyncMock(return_value="ok"))
    ch = FakeChannel()
    mgr.register(ch)
    assert "fake" in mgr.channel_ids
    assert mgr.get_channel("fake") is ch


def test_manager_get_unknown_channel():
    mgr = ChannelManager(on_message=AsyncMock(return_value="ok"))
    assert mgr.get_channel("nonexistent") is None


# ---------------------------------------------------------------------------
# ChannelManager -- start / stop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_manager_start_stop():
    mgr = ChannelManager(on_message=AsyncMock(return_value="ok"))
    ch = FakeChannel()
    mgr.register(ch)
    await mgr.start_all({"fake": {"enabled": True}})
    assert ch.is_running()
    status = mgr.get_status()
    assert len(status) == 1
    assert status[0].running is True
    await mgr.stop_all()
    assert not ch.is_running()


@pytest.mark.asyncio
async def test_manager_skip_disabled_channel():
    mgr = ChannelManager(on_message=AsyncMock(return_value="ok"))
    ch = FakeChannel()
    mgr.register(ch)
    await mgr.start_all({"fake": {"enabled": False}})
    assert not ch.is_running()


@pytest.mark.asyncio
async def test_manager_start_channel_individually():
    mgr = ChannelManager(on_message=AsyncMock(return_value="ok"))
    ch = FakeChannel()
    mgr.register(ch)
    await mgr.start_channel("fake", {"enabled": True})
    assert ch.is_running()
    await mgr.stop_channel("fake")
    assert not ch.is_running()


@pytest.mark.asyncio
async def test_manager_start_unknown_raises():
    mgr = ChannelManager(on_message=AsyncMock(return_value="ok"))
    with pytest.raises(ValueError, match="Unknown channel"):
        await mgr.start_channel("nope", {})


# ---------------------------------------------------------------------------
# ChannelManager -- dispatch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_manager_dispatch():
    callback = AsyncMock(return_value="resposta do bot")
    mgr = ChannelManager(on_message=callback)
    msg = ChannelMessage(
        channel_id="fake",
        sender_id="123",
        sender_name="Test",
        chat_id="456",
        text="oi",
    )
    reply = await mgr.dispatch(msg)
    assert reply == "resposta do bot"
    callback.assert_awaited_once_with(msg)


@pytest.mark.asyncio
async def test_manager_dispatch_error_returns_fallback():
    callback = AsyncMock(side_effect=RuntimeError("boom"))
    mgr = ChannelManager(on_message=callback)
    msg = ChannelMessage(
        channel_id="fake",
        sender_id="1",
        sender_name="T",
        chat_id="2",
        text="x",
    )
    reply = await mgr.dispatch(msg)
    assert "erro" in reply.lower()


# ---------------------------------------------------------------------------
# TelegramChannel -- requires token
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_telegram_start_requires_token():
    from app.channels.telegram import TelegramChannel

    tg = TelegramChannel(on_message=AsyncMock())
    with pytest.raises(ValueError, match="bot_token"):
        await tg.start({"bot_token": ""})


# ---------------------------------------------------------------------------
# TelegramChannel -- stop when not started is safe
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_telegram_stop_when_not_started():
    from app.channels.telegram import TelegramChannel

    tg = TelegramChannel(on_message=AsyncMock())
    await tg.stop()
    assert not tg.is_running()


# ---------------------------------------------------------------------------
# TelegramChannel -- status
# ---------------------------------------------------------------------------

def test_telegram_status_idle():
    from app.channels.telegram import TelegramChannel

    tg = TelegramChannel(on_message=AsyncMock())
    st = tg.get_status()
    assert st.channel_id == "telegram"
    assert st.running is False
    assert st.connected is False


# ---------------------------------------------------------------------------
# TelegramChannel -- chunk_text
# ---------------------------------------------------------------------------

def test_telegram_chunk_text_short():
    from app.channels.telegram import TelegramChannel

    chunks = TelegramChannel._chunk_text("hello")
    assert chunks == ["hello"]


def test_telegram_chunk_text_long():
    from app.channels.telegram import TelegramChannel

    text = "a" * 5000
    chunks = TelegramChannel._chunk_text(text)
    assert len(chunks) >= 2
    combined = "".join(chunks)
    assert len(combined) == 5000


# ---------------------------------------------------------------------------
# TelegramChannel -- protocol compliance
# ---------------------------------------------------------------------------

def test_telegram_satisfies_protocol():
    from app.channels.telegram import TelegramChannel

    tg = TelegramChannel(on_message=AsyncMock())
    assert isinstance(tg, Channel)


# ---------------------------------------------------------------------------
# Markdown → Telegram HTML conversion
# ---------------------------------------------------------------------------

def test_md_to_tg_html_headings():
    from app.channels.telegram import _md_to_tg_html

    assert "<b>Title</b>" in _md_to_tg_html("## Title")
    assert "<b>Sub</b>" in _md_to_tg_html("### Sub")


def test_md_to_tg_html_bold_italic():
    from app.channels.telegram import _md_to_tg_html

    assert "<b>bold</b>" in _md_to_tg_html("**bold**")
    assert "<i>italic</i>" in _md_to_tg_html("*italic*")


def test_md_to_tg_html_links():
    from app.channels.telegram import _md_to_tg_html

    result = _md_to_tg_html("[click](https://example.com)")
    assert '<a href="https://example.com">click</a>' in result


def test_md_to_tg_html_code_block():
    from app.channels.telegram import _md_to_tg_html

    result = _md_to_tg_html("```python\nprint('hi')\n```")
    assert "<pre>" in result
    assert "print(&#x27;hi&#x27;)" in result
    assert "</pre>" in result


def test_md_to_tg_html_blockquote():
    from app.channels.telegram import _md_to_tg_html

    result = _md_to_tg_html("> quoted text")
    assert "<blockquote>" in result
    assert "quoted text" in result
    assert "</blockquote>" in result


def test_md_to_tg_html_inline_code():
    from app.channels.telegram import _md_to_tg_html

    assert "<code>var</code>" in _md_to_tg_html("`var`")


def test_telegram_command_arg_extracts_value():
    from app.channels.telegram import _command_arg

    assert _command_arg("/projeto taxonomia_e2e_12") == "taxonomia_e2e_12"
    assert _command_arg("/projeto") == ""

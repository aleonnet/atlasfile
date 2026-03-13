"""Integration tests for the session SSE event bus infrastructure."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_notify_triggers_sse_event() -> None:
    """When _notify_session_update is called, the event for that session is set."""
    from app.main import _get_session_event, _notify_session_update, _session_events

    sid = "sess-sse-integ"
    ev = _get_session_event(sid)
    assert not ev.is_set()

    _notify_session_update(sid)
    assert ev.is_set()

    ev.clear()
    assert not ev.is_set()

    _session_events.pop(sid, None)


@pytest.mark.asyncio
async def test_notify_only_affects_target_session() -> None:
    """Notifying session A does not affect session B."""
    from app.main import _get_session_event, _notify_session_update, _session_events

    ev_a = _get_session_event("sess-a")
    ev_b = _get_session_event("sess-b")

    _notify_session_update("sess-a")
    assert ev_a.is_set()
    assert not ev_b.is_set()

    _session_events.pop("sess-a", None)
    _session_events.pop("sess-b", None)


@pytest.mark.asyncio
async def test_stream_generator_emits_on_notify() -> None:
    """The SSE generator yields a session_update event when notified."""
    import asyncio
    from unittest.mock import patch
    from app.main import _stream_session_events, _notify_session_update, _get_session_event, _session_events

    sid = "sess-stream-test"
    _get_session_event(sid)

    mock_session_data = {
        "_source": {
            "title": "Live",
            "messages": [{"role": "user", "content": "hello", "timestamp": 1000}],
            "model": "openai/gpt-4o-mini",
            "createdAt": 1000,
            "updatedAt": 2000,
        }
    }

    async def collect_first_event():
        with patch("app.main.os_client") as mock_os:
            mock_os.get.return_value = mock_session_data
            gen = _stream_session_events(sid)
            # Trigger notification so the generator emits
            _notify_session_update(sid)
            result = await asyncio.wait_for(gen.__anext__(), timeout=5.0)
            await gen.aclose()
            return result

    event_text = await collect_first_event()
    assert "event: session_update" in event_text
    assert "Live" in event_text

    _session_events.pop(sid, None)

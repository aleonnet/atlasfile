"""Unit tests for the session SSE event bus (_notify_session_update, _get_session_event)."""
from __future__ import annotations

import asyncio

import pytest


@pytest.mark.asyncio
async def test_notify_triggers_event() -> None:
    """_notify_session_update sets the asyncio.Event for the given session_id."""
    from app.main import _get_session_event, _notify_session_update, _session_events

    sid = "test-session-1"
    ev = _get_session_event(sid)
    assert not ev.is_set()

    _notify_session_update(sid)
    assert ev.is_set()

    # cleanup
    _session_events.pop(sid, None)


@pytest.mark.asyncio
async def test_notify_no_listener_is_noop() -> None:
    """_notify_session_update on unknown session_id doesn't raise."""
    from app.main import _notify_session_update, _session_events

    _notify_session_update("nonexistent-session")
    assert "nonexistent-session" not in _session_events


@pytest.mark.asyncio
async def test_event_cleared_after_wait() -> None:
    """After waiting and consuming the event, it should be cleared."""
    from app.main import _get_session_event, _notify_session_update, _session_events

    sid = "test-session-2"
    ev = _get_session_event(sid)

    _notify_session_update(sid)
    await asyncio.wait_for(ev.wait(), timeout=1.0)
    ev.clear()
    assert not ev.is_set()

    # cleanup
    _session_events.pop(sid, None)


@pytest.mark.asyncio
async def test_get_session_event_idempotent() -> None:
    """Calling _get_session_event multiple times returns the same Event object."""
    from app.main import _get_session_event, _session_events

    sid = "test-session-3"
    ev1 = _get_session_event(sid)
    ev2 = _get_session_event(sid)
    assert ev1 is ev2

    # cleanup
    _session_events.pop(sid, None)

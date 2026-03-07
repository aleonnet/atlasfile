"""Channel protocol and shared types for the AtlasFile channel layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class ChannelMessage:
    """Inbound message from a messaging channel."""

    channel_id: str
    sender_id: str
    sender_name: str
    chat_id: str
    text: str
    message_id: str = ""
    chat_type: str = "private"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChannelStatus:
    """Runtime status of a channel."""

    channel_id: str
    name: str
    running: bool
    connected: bool
    error: str | None = None
    uptime_seconds: float = 0.0


@runtime_checkable
class Channel(Protocol):
    """Contract that every channel implementation must satisfy."""

    id: str
    name: str
    description: str

    async def start(self, config: dict[str, Any]) -> None: ...
    async def stop(self) -> None: ...
    async def send_message(self, chat_id: str, text: str) -> None: ...
    def is_running(self) -> bool: ...
    def get_status(self) -> ChannelStatus: ...

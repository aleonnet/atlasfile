"""ChannelManager -- registry, lifecycle and inbound dispatch for channels."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from .base import Channel, ChannelMessage, ChannelStatus

logger = logging.getLogger(__name__)


class ChannelManager:
    """Registers channels, manages their lifecycle and dispatches inbound messages."""

    def __init__(self, on_message: Callable[[ChannelMessage], Awaitable[str]]) -> None:
        self._channels: dict[str, Channel] = {}
        self._on_message = on_message

    def register(self, channel: Channel) -> None:
        self._channels[channel.id] = channel
        logger.info("Channel registered: %s (%s)", channel.id, channel.name)

    async def start_all(self, config: dict[str, Any]) -> None:
        for ch_id, channel in self._channels.items():
            ch_cfg = config.get(ch_id, {})
            if not ch_cfg.get("enabled", False):
                logger.info("Channel %s is disabled, skipping", ch_id)
                continue
            try:
                await channel.start(ch_cfg)
                logger.info("Channel %s started", ch_id)
            except Exception:
                logger.exception("Failed to start channel %s (non-fatal)", ch_id)

    async def stop_all(self) -> None:
        for ch_id, channel in self._channels.items():
            if not channel.is_running():
                continue
            try:
                await channel.stop()
                logger.info("Channel %s stopped", ch_id)
            except Exception:
                logger.exception("Error stopping channel %s", ch_id)

    async def start_channel(self, channel_id: str, config: dict[str, Any]) -> None:
        channel = self._channels.get(channel_id)
        if not channel:
            raise ValueError(f"Unknown channel: {channel_id}")
        if channel.is_running():
            await channel.stop()
        await channel.start(config)

    async def stop_channel(self, channel_id: str) -> None:
        channel = self._channels.get(channel_id)
        if not channel:
            raise ValueError(f"Unknown channel: {channel_id}")
        if channel.is_running():
            await channel.stop()

    async def dispatch(self, msg: ChannelMessage) -> str:
        """Route an inbound message to the orchestrator and return the reply text."""
        try:
            return await self._on_message(msg)
        except Exception:
            logger.exception("Error dispatching message from %s/%s", msg.channel_id, msg.sender_id)
            return "Desculpe, ocorreu um erro ao processar sua mensagem."

    def get_status(self) -> list[ChannelStatus]:
        return [ch.get_status() for ch in self._channels.values()]

    def get_channel(self, channel_id: str) -> Channel | None:
        return self._channels.get(channel_id)

    @property
    def channel_ids(self) -> list[str]:
        return list(self._channels.keys())

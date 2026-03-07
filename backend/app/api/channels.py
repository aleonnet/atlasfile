"""API router for channel configuration and status."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from ..config import settings
from ..models import (
    ChannelConfigTelegram,
    ChannelConfigUpdate,
    ChannelStatusItem,
    ChannelStatusResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/channels", tags=["channels"])


def _get_channel_manager():
    from ..main import channel_manager

    return channel_manager


# ---------- GET /api/channels/config ----------


@router.get("/config", response_model=ChannelConfigUpdate)
async def get_channel_config() -> ChannelConfigUpdate:
    return ChannelConfigUpdate(
        channels_enabled=settings.channels_enabled,
        telegram=ChannelConfigTelegram(
            enabled=settings.telegram_enabled,
            bot_token=settings.telegram_bot_token,
        ),
    )


# ---------- PUT /api/channels/config ----------


@router.put("/config", response_model=ChannelConfigUpdate)
async def update_channel_config(body: ChannelConfigUpdate) -> ChannelConfigUpdate:
    settings.channels_enabled = body.channels_enabled
    settings.telegram_enabled = body.telegram.enabled
    settings.telegram_bot_token = body.telegram.bot_token

    cm = _get_channel_manager()

    if body.telegram.enabled and body.telegram.bot_token:
        if cm is None:
            from ..channels import ChannelManager
            from ..channels.telegram import TelegramChannel
            from ..main import _handle_channel_message, channel_manager as _cm

            import app.main as _main_mod

            _main_mod.channel_manager = ChannelManager(on_message=_handle_channel_message)
            _main_mod.channel_manager.register(TelegramChannel(on_message=_main_mod.channel_manager.dispatch))
            cm = _main_mod.channel_manager

        try:
            tg = cm.get_channel("telegram")
            if tg and tg.is_running():
                await cm.stop_channel("telegram")
            await cm.start_channel(
                "telegram",
                {"enabled": True, "bot_token": body.telegram.bot_token},
            )
        except Exception as exc:
            logger.exception("Failed to (re)start telegram channel")
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    elif cm:
        tg = cm.get_channel("telegram")
        if tg and tg.is_running():
            try:
                await cm.stop_channel("telegram")
            except Exception:
                logger.exception("Failed to stop telegram channel")

    return body


# ---------- GET /api/channels/status ----------


@router.get("/status", response_model=ChannelStatusResponse)
async def get_channel_status() -> ChannelStatusResponse:
    cm = _get_channel_manager()
    channels: list[ChannelStatusItem] = []
    if cm:
        for st in cm.get_status():
            channels.append(
                ChannelStatusItem(
                    channel_id=st.channel_id,
                    name=st.name,
                    running=st.running,
                    connected=st.connected,
                    error=st.error,
                    uptime_seconds=st.uptime_seconds,
                )
            )
    else:
        channels.append(
            ChannelStatusItem(
                channel_id="telegram",
                name="Telegram",
                running=False,
                connected=False,
            )
        )
    return ChannelStatusResponse(
        channels_enabled=settings.channels_enabled,
        channels=channels,
    )


# ---------- POST /api/channels/test ----------


@router.post("/test")
async def test_channel(channel_id: str = "telegram") -> dict[str, Any]:
    cm = _get_channel_manager()
    if not cm:
        raise HTTPException(status_code=400, detail="Channel manager not initialized")

    channel = cm.get_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail=f"Unknown channel: {channel_id}")

    if not channel.is_running():
        raise HTTPException(status_code=400, detail=f"Channel {channel_id} is not running")

    return {"ok": True, "channel_id": channel_id, "status": "running"}

"""Telegram channel implementation using aiogram 3.x (long-polling)."""

from __future__ import annotations

import asyncio
import html as html_mod
import logging
import re
import time
from contextlib import suppress
from typing import Any, Awaitable, Callable

from .base import ChannelMessage, ChannelStatus

logger = logging.getLogger(__name__)

_TG_TEXT_LIMIT = 4096


def _md_to_tg_html(text: str) -> str:
    """Convert common Markdown patterns to Telegram-safe HTML.

    Telegram HTML supports: <b>, <i>, <code>, <pre>, <a href="">, <blockquote>.
    Unsupported tags are stripped by Telegram and may cause parse errors.
    """
    lines = text.split("\n")
    out: list[str] = []
    in_code_block = False
    in_blockquote = False

    for line in lines:
        # fenced code blocks
        if line.strip().startswith("```"):
            if in_code_block:
                out.append("</pre>")
                in_code_block = False
            else:
                lang = line.strip().removeprefix("```").strip()
                out.append(f"<pre>{html_mod.escape(lang)}" if lang else "<pre>")
                in_code_block = True
            continue
        if in_code_block:
            out.append(html_mod.escape(line))
            continue

        # blockquote lines (> prefix)
        if line.lstrip().startswith("> "):
            content = line.lstrip().removeprefix("> ").removeprefix(">")
            if not in_blockquote:
                out.append("<blockquote>")
                in_blockquote = True
            out.append(_inline_md_to_html(content))
            continue
        if in_blockquote:
            out.append("</blockquote>")
            in_blockquote = False

        # headings → bold
        heading_m = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_m:
            out.append(f"\n<b>{_inline_md_to_html(heading_m.group(2))}</b>")
            continue

        # horizontal rules
        if re.match(r"^[-*_]{3,}\s*$", line.strip()):
            out.append("—" * 20)
            continue

        out.append(_inline_md_to_html(line))

    if in_blockquote:
        out.append("</blockquote>")
    if in_code_block:
        out.append("</pre>")

    result = "\n".join(out)
    # collapse 3+ consecutive newlines
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def _inline_md_to_html(text: str) -> str:
    """Convert inline Markdown: bold, italic, code, links."""
    # escape HTML entities first (except our own tags added below)
    text = html_mod.escape(text)
    # inline code (`text`)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    # bold+italic (***text***)
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<b><i>\1</i></b>", text)
    # bold (**text**)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # italic (*text*)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    # links [text](url)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


class TelegramChannel:
    """Telegram Bot API channel via aiogram long-polling."""

    id = "telegram"
    name = "Telegram"
    description = "Telegram Bot API via aiogram"

    def __init__(self, on_message: Callable[[ChannelMessage], Awaitable[str]]) -> None:
        self._on_message = on_message
        self._bot: Any = None
        self._dp: Any = None
        self._polling_task: asyncio.Task[None] | None = None
        self._running = False
        self._start_time: float = 0
        self._error: str | None = None

    # -- Channel protocol ------------------------------------------------

    async def start(self, config: dict[str, Any]) -> None:
        token = config.get("bot_token", "")
        if not token:
            raise ValueError("telegram.bot_token is required")

        try:
            from aiogram import Bot, Dispatcher
            from aiogram.client.default import DefaultBotProperties
            from aiogram.enums import ParseMode
        except ImportError as exc:
            raise RuntimeError("aiogram is not installed. Add aiogram>=3.26.0 to requirements.txt") from exc

        self._bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self._dp = Dispatcher()
        self._register_handlers()
        self._error = None

        self._polling_task = asyncio.create_task(
            self._dp.start_polling(self._bot, handle_signals=False),
            name="telegram-polling",
        )
        self._polling_task.add_done_callback(self._on_polling_done)
        self._running = True
        self._start_time = time.monotonic()
        logger.info("Telegram channel started (long-polling)")

    async def stop(self) -> None:
        if self._dp:
            await self._dp.stop_polling()
        if self._polling_task:
            self._polling_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._polling_task
            self._polling_task = None
        if self._bot:
            await self._bot.session.close()
            self._bot = None
        self._dp = None
        self._running = False
        logger.info("Telegram channel stopped")

    async def send_message(self, chat_id: str, text: str) -> None:
        if not self._bot:
            raise RuntimeError("Telegram bot is not running")
        for chunk in self._chunk_text(text):
            await self._bot.send_message(chat_id=int(chat_id), text=chunk)

    def is_running(self) -> bool:
        return self._running

    def get_status(self) -> ChannelStatus:
        uptime = (time.monotonic() - self._start_time) if self._running else 0.0
        return ChannelStatus(
            channel_id=self.id,
            name=self.name,
            running=self._running,
            connected=self._running and self._error is None,
            error=self._error,
            uptime_seconds=round(uptime, 1),
        )

    # -- Internal --------------------------------------------------------

    def _on_polling_done(self, task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            self._error = str(exc)
            self._running = False
            logger.error("Telegram polling stopped with error: %s", exc)

    def _register_handlers(self) -> None:
        from aiogram.filters import Command, CommandStart
        from aiogram.types import Message as AiogramMessage

        @self._dp.message(CommandStart())
        async def _cmd_start(message: AiogramMessage) -> None:
            name = message.from_user.full_name if message.from_user else "there"
            await message.answer(
                f"Olá, {name}! Sou o assistente AtlasFile. "
                "Envie uma pergunta sobre seus documentos.\n"
                "Use /novo para iniciar uma nova sessão."
            )

        @self._dp.message(Command("novo"))
        async def _cmd_novo(message: AiogramMessage) -> None:
            from app.main import _forced_new_sessions
            _forced_new_sessions.add(str(message.chat.id))
            await message.answer("Nova sessão iniciada. Envie sua próxima pergunta.")

        @self._dp.message()
        async def _on_text(message: AiogramMessage) -> None:
            if not message.text:
                await message.answer("Desculpe, por enquanto só processo mensagens de texto.")
                return
            user = message.from_user
            chat_id = message.chat.id
            bot = self._bot
            channel_msg = ChannelMessage(
                channel_id=self.id,
                sender_id=str(user.id) if user else "unknown",
                sender_name=user.full_name if user else "Unknown",
                chat_id=str(chat_id),
                text=message.text,
                message_id=str(message.message_id),
                chat_type=message.chat.type or "private",
                raw=message.model_dump(mode="json") if hasattr(message, "model_dump") else {},
            )

            from aiogram.utils.chat_action import ChatActionSender

            try:
                async with ChatActionSender.typing(bot=bot, chat_id=chat_id):
                    reply = await self._on_message(channel_msg)
            except Exception:
                logger.exception("Error processing channel message")
                await message.answer("Desculpe, ocorreu um erro ao processar sua mensagem.")
                return

            html_reply = _md_to_tg_html(reply)
            for chunk in self._chunk_text(html_reply):
                await message.answer(chunk)

    @staticmethod
    def _chunk_text(text: str) -> list[str]:
        if len(text) <= _TG_TEXT_LIMIT:
            return [text]
        chunks: list[str] = []
        while text:
            if len(text) <= _TG_TEXT_LIMIT:
                chunks.append(text)
                break
            split_at = text.rfind("\n", 0, _TG_TEXT_LIMIT)
            if split_at < 1:
                split_at = _TG_TEXT_LIMIT
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip("\n")
        return chunks

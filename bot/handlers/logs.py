"""
/logs command handler.

Allows admins to view the last N lines of the bot log file directly in Telegram.
"""
from __future__ import annotations

import logging
import os

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config.settings import get_settings
from bot.handlers.filters import IsAdmin

logger = logging.getLogger(__name__)
router = Router(name="logs")

DEFAULT_LINES = 30
MAX_LINES = 100
# Telegram message limit is 4096 chars; we truncate to fit
MAX_MESSAGE_CHARS = 3800


def _tail(filepath: str, n: int) -> str:
    """Read last `n` lines from a file efficiently."""
    if not os.path.exists(filepath):
        return f"(log file not found: {filepath})"

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        tail_lines = lines[-n:] if len(lines) >= n else lines
        return "".join(tail_lines)
    except OSError as exc:
        return f"(error reading log file: {exc})"


@router.message(Command("logs"), IsAdmin())
async def cmd_logs(message: Message) -> None:
    """
    /logs [N]

    Shows the last N lines of the log file (default 30, max 100).
    Example: /logs 50
    """
    cfg = get_settings()

    # Parse optional line count argument
    args = (message.text or "").split(maxsplit=1)
    n = DEFAULT_LINES
    if len(args) == 2:
        try:
            n = min(int(args[1].strip()), MAX_LINES)
        except ValueError:
            await message.answer("⚠️ Использование: /logs [количество строк]\nПример: /logs 50")
            return

    content = _tail(cfg.log_file, n)

    if not content.strip():
        await message.answer("📭 Лог-файл пуст.")
        return

    # Truncate to fit Telegram message limit
    if len(content) > MAX_MESSAGE_CHARS:
        content = "...(обрезано)\n" + content[-MAX_MESSAGE_CHARS:]

    await message.answer(
        f"📋 <b>Последние {n} строк лога:</b>\n\n<pre>{_escape_pre(content)}</pre>",
        parse_mode="HTML",
    )


def _escape_pre(text: str) -> str:
    """Escape HTML inside <pre> block."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

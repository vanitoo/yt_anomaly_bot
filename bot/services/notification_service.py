"""
Notification service.

Formats and sends anomaly alert messages to Telegram.
Handles thumbnail fetching and graceful fallback to text-only messages.
"""
from __future__ import annotations

import logging
from typing import Optional

from aiogram import Bot
from aiogram.types import BufferedInputFile, URLInputFile

from bot.analytics.detector import AnomalyResult

logger = logging.getLogger(__name__)


def _fmt_views(n: int) -> str:
    """Format a view count as human-readable string."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def _fmt_date(dt) -> str:
    return dt.strftime("%d.%m.%Y")


def build_anomaly_caption(channel_title: str, result: AnomalyResult) -> str:
    """Build the formatted Telegram caption for an anomaly alert."""
    v = result.video
    sign = "+" if result.anomaly_percent >= 0 else ""

    lines = [
        "🚨 <b>Аномалия на YouTube</b>",
        "",
        f"📺 <b>Канал:</b> {_escape(channel_title)}",
        f"🎬 <b>Видео:</b> {_escape(v.title)}",
        f"📅 <b>Опубликовано:</b> {_fmt_date(v.published_at)}",
        f"👁 <b>Просмотры:</b> {_fmt_views(v.view_count)}",
        f"📊 <b>Норма канала:</b> {_fmt_views(int(result.baseline))}",
        f"📈 <b>Превышение:</b> {sign}{result.anomaly_percent:.0f}% / {result.anomaly_ratio:.1f}x",
        f"🔗 <b>Ссылка:</b> {v.video_url}",
        "",
        "─────────────────",
        f"📌 Место: <b>{result.rank} из {result.total_analyzed}</b>",
        f"⏱ Возраст: <b>{result.age_days} дн.</b>",
        f"🔬 Метод: <b>{result.baseline_method}</b>",
    ]
    return "\n".join(lines)


def _escape(text: str) -> str:
    """Escape HTML special characters for Telegram HTML parse mode."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


class NotificationService:
    """Sends Telegram messages for detected anomalies."""

    def __init__(self, bot: Bot, chat_id: str) -> None:
        self._bot = bot
        self._chat_id = chat_id

    async def send_anomaly(self, channel_title: str, result: AnomalyResult) -> int:
        """
        Send anomaly notification with thumbnail.

        Returns the Telegram message_id of the sent message.
        """
        caption = build_anomaly_caption(channel_title, result)
        thumbnail_url = result.video.thumbnail_url

        if thumbnail_url:
            try:
                return await self._send_with_photo(caption, thumbnail_url)
            except Exception as exc:
                logger.warning(
                    "Failed to send photo for %r: %s. Falling back to text.",
                    result.video.title,
                    exc,
                )

        # Fallback: text-only message
        return await self._send_text(caption)

    async def _send_with_photo(self, caption: str, photo_url: str) -> int:
        photo = URLInputFile(photo_url)
        msg = await self._bot.send_photo(
            chat_id=self._chat_id,
            photo=photo,
            caption=caption,
            parse_mode="HTML",
        )
        return msg.message_id

    async def _send_text(self, text: str) -> int:
        msg = await self._bot.send_message(
            chat_id=self._chat_id,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=False,
        )
        return msg.message_id

    async def send_plain(self, text: str) -> None:
        """Send a plain text message (for admin notifications, errors, etc.)."""
        await self._bot.send_message(
            chat_id=self._chat_id,
            text=text,
            parse_mode="HTML",
        )

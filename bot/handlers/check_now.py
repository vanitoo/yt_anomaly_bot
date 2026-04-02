"""
/check_now command handler.

Allows admins to trigger an immediate analysis cycle manually.
"""
from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config.settings import get_settings
from bot.handlers.deps import make_analysis_runner
from bot.handlers.filters import IsAdmin
from bot.models.database import get_session

logger = logging.getLogger(__name__)
router = Router(name="check_now")


@router.message(Command("check_now"), IsAdmin())
async def cmd_check_now(message: Message) -> None:
    """
    /check_now

    Immediately triggers the full analysis pipeline for all active channels.
    """
    status_msg = await message.answer("🔄 Запускаю анализ каналов...")

    cfg = get_settings()
    try:
        async with get_session(cfg.database_url) as session:
            runner = make_analysis_runner(session, message.bot)
            summary = await runner.run()

        channels = summary.get("channels_checked", 0)
        sent = summary.get("anomalies_sent", 0)

        if sent > 0:
            result_text = (
                f"✅ Анализ завершён!\n\n"
                f"📺 Каналов проверено: <b>{channels}</b>\n"
                f"🚨 Аномалий отправлено: <b>{sent}</b>"
            )
        else:
            result_text = (
                f"✅ Анализ завершён.\n\n"
                f"📺 Каналов проверено: <b>{channels}</b>\n"
                f"ℹ️ Новых аномалий не найдено."
            )

        await status_msg.edit_text(result_text, parse_mode="HTML")

    except Exception as exc:
        logger.exception("Error during manual check: %s", exc)
        await status_msg.edit_text(
            f"❌ Ошибка во время анализа:\n<code>{exc}</code>", parse_mode="HTML"
        )

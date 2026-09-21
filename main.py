"""Telegram bot entrypoint with shared proxy support."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import get_settings, setup_logging
from bot.handlers import register_all_handlers
from bot.integrations.proxy_runtime import get_proxy_manager
from bot.jobs.scheduler import build_scheduler
from bot.models.migrations import run_migrations

logger = logging.getLogger(__name__)


async def main() -> None:
    cfg = get_settings()
    setup_logging(cfg.log_level, cfg.log_file)

    if not cfg.telegram_bot_token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is empty. For GUI-only mode run: python run_web.py"
        )
    if not cfg.telegram_chat_id:
        raise RuntimeError("TELEGRAM_CHAT_ID is required for Telegram notification mode")

    logger.info("Starting YouTube Anomaly Bot")
    logger.info("Database: %s", cfg.database_url)
    run_migrations(cfg.database_url)

    proxy_manager = get_proxy_manager()
    if proxy_manager.has_proxies:
        await proxy_manager.check_all()
        await proxy_manager.start_healthcheck_loop()
        logger.info("Proxy status: %s", proxy_manager.get_status())

    proxy_session = proxy_manager.get_session() if proxy_manager.has_proxies else None
    if proxy_manager.has_proxies and proxy_session is None:
        raise RuntimeError("Proxies are configured but none is available for Telegram")

    bot_kwargs = {
        "token": cfg.telegram_bot_token,
        "default": DefaultBotProperties(parse_mode=ParseMode.HTML),
    }
    if proxy_session is not None:
        bot_kwargs["session"] = proxy_session

    bot = Bot(**bot_kwargs)
    dp = Dispatcher()
    register_all_handlers(dp)

    scheduler = build_scheduler(bot)
    scheduler.start()
    logger.info("Scheduler started")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await proxy_manager.stop_healthcheck_loop()
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())

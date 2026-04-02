"""
Main entrypoint for the YouTube Anomaly Telegram Bot.

Startup sequence:
1. Load settings from .env
2. Configure logging
3. Create DB tables if not exist
4. Build aiogram Bot + Dispatcher
5. Register all handlers
6. Start APScheduler
7. Start polling (long-polling mode, no webhook)
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import get_settings, setup_logging
from bot.handlers import register_all_handlers
from bot.jobs.scheduler import build_scheduler
from bot.models.database import create_tables

logger = logging.getLogger(__name__)


async def main() -> None:
    cfg = get_settings()
    setup_logging(cfg.log_level, cfg.log_file)

    logger.info("Starting YouTube Anomaly Bot")
    logger.info("Database: %s", cfg.database_url)
    logger.info("Admin IDs: %s", cfg.admin_ids_list)
    logger.info("Schedule: %s", cfg.schedule_interval)

    # Ensure DB schema is up to date
    await create_tables(cfg.database_url)
    logger.info("Database tables ready.")

    # Build aiogram Bot and Dispatcher
    bot = Bot(
        token=cfg.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Register all command handlers
    register_all_handlers(dp)

    # Start the scheduler
    scheduler = build_scheduler(bot)
    scheduler.start()
    logger.info("Scheduler started.")

    try:
        logger.info("Bot is running. Waiting for updates...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())

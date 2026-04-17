"""
Main entrypoint for the YouTube Anomaly Telegram Bot.

Startup sequence:
1. Load settings from .env
2. Configure logging
3. Run Alembic migrations (upgrade to head)
4. Build aiogram Bot + Dispatcher
5. Register all handlers
6. Start APScheduler
7. Start polling (long-polling mode, no webhook)
"""
from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import get_settings, setup_logging
from bot.handlers import register_all_handlers
from bot.jobs.scheduler import build_scheduler

logger = logging.getLogger(__name__)


def run_migrations() -> None:
    """
    Run Alembic migrations synchronously at startup.

    Uses alembic.ini from the project root. DATABASE_URL is read
    from the environment (already loaded by pydantic-settings).
    """
    import subprocess
    import sys

    ini_path = os.path.join(os.path.dirname(__file__), "alembic.ini")
    logger.info("Applying Alembic migrations...")
    
    # Run alembic upgrade via subprocess to avoid event loop conflicts
    result = subprocess.run(
        [sys.executable, "-c", f"""
import asyncio
import os
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig

# Set DATABASE_URL from environment
os.environ['DATABASE_URL'] = '{get_settings().database_url}'

alembic_cfg = AlembicConfig('{ini_path}')
alembic_command.upgrade(alembic_cfg, 'head')
print('Alembic migrations applied successfully.')
        """],
        capture_output=True,
        text=True,
    )
    
    if result.returncode != 0:
        logger.error("Alembic migration failed: %s", result.stderr)
        raise RuntimeError(f"Alembic migration failed: {result.stderr}")
    
    logger.info("Alembic migrations applied successfully.")


async def main() -> None:
    cfg = get_settings()
    setup_logging(cfg.log_level, cfg.log_file)

    logger.info("Starting YouTube Anomaly Bot")
    logger.info("Database: %s", cfg.database_url)
    logger.info("Admin IDs: %s", cfg.admin_ids_list)
    logger.info("Schedule: %s", cfg.schedule_interval)

    # Apply DB migrations on every startup (idempotent)
    run_migrations()

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

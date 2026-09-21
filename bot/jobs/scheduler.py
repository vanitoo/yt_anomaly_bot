"""Scheduled jobs using APScheduler."""
from __future__ import annotations

import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from bot.config.settings import get_settings
from bot.handlers.deps import make_youtube_client
from bot.models.database import get_session
from bot.services.analysis_runner import AnalysisRunner

logger = logging.getLogger(__name__)


async def _run_analysis_job(bot: Bot) -> None:
    cfg = get_settings()
    logger.info("Scheduled analysis job triggered")
    try:
        async with get_session(cfg.database_url) as session:
            runner = AnalysisRunner(
                session=session,
                youtube_client=make_youtube_client(),
                bot=bot,
                chat_id=cfg.telegram_chat_id,
                notify_telegram=True,
            )
            summary = await runner.run()
        logger.info("Scheduled analysis finished: %s", summary)
    except Exception as exc:
        logger.exception("Scheduled analysis job failed: %s", exc)


def build_scheduler(bot: Bot) -> AsyncIOScheduler:
    cfg = get_settings()
    scheduler = AsyncIOScheduler(timezone="UTC")
    schedule = cfg.schedule_interval.lower()

    if schedule == "weekly":
        trigger = CronTrigger(day_of_week="mon", hour=9, minute=0)
    elif schedule == "daily":
        trigger = CronTrigger(hour=9, minute=0)
    elif schedule == "hourly":
        trigger = IntervalTrigger(hours=1)
    else:
        logger.warning("Unknown schedule_interval %r, defaulting to weekly", schedule)
        trigger = CronTrigger(day_of_week="mon", hour=9, minute=0)

    scheduler.add_job(
        _run_analysis_job,
        trigger=trigger,
        kwargs={"bot": bot},
        id="analysis_job",
        replace_existing=True,
        misfire_grace_time=3600,
        max_instances=1,
    )
    return scheduler

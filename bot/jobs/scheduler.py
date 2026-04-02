"""
Scheduled jobs using APScheduler.

Runs the analysis pipeline automatically based on the configured schedule.
"""
from __future__ import annotations

import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from bot.config.settings import get_settings
from bot.models.database import get_session
from bot.services.analysis_runner import AnalysisRunner
from bot.integrations.youtube.client import YouTubeClient

logger = logging.getLogger(__name__)


async def _run_analysis_job(bot: Bot) -> None:
    """
    The actual job function called by APScheduler.

    Creates a fresh session and runner for each execution to avoid
    stale connections and ensure clean transaction scope.
    """
    cfg = get_settings()
    logger.info("Scheduled analysis job triggered.")
    try:
        async with get_session(cfg.database_url) as session:
            runner = AnalysisRunner(
                session=session,
                youtube_client=YouTubeClient(api_key=cfg.youtube_api_key),
                bot=bot,
                chat_id=cfg.telegram_chat_id,
            )
            summary = await runner.run()
        logger.info("Scheduled analysis finished: %s", summary)
    except Exception as exc:
        logger.exception("Scheduled analysis job failed: %s", exc)


def build_scheduler(bot: Bot) -> AsyncIOScheduler:
    """
    Build and configure the APScheduler instance.

    Schedule is determined by the SCHEDULE_INTERVAL config value:
      - weekly  → every Monday at 09:00
      - daily   → every day at 09:00
      - hourly  → every hour at :00
    """
    cfg = get_settings()
    scheduler = AsyncIOScheduler(timezone="UTC")

    schedule = cfg.schedule_interval.lower()

    if schedule == "weekly":
        trigger = CronTrigger(day_of_week="mon", hour=9, minute=0)
        logger.info("Scheduler: weekly (Monday 09:00 UTC)")
    elif schedule == "daily":
        trigger = CronTrigger(hour=9, minute=0)
        logger.info("Scheduler: daily (09:00 UTC)")
    elif schedule == "hourly":
        trigger = IntervalTrigger(hours=1)
        logger.info("Scheduler: hourly")
    else:
        logger.warning(
            "Unknown schedule_interval %r, defaulting to weekly.", schedule
        )
        trigger = CronTrigger(day_of_week="mon", hour=9, minute=0)

    scheduler.add_job(
        _run_analysis_job,
        trigger=trigger,
        kwargs={"bot": bot},
        id="analysis_job",
        replace_existing=True,
        misfire_grace_time=3600,  # allow up to 1h late start
    )

    return scheduler

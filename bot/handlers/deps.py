"""
Dependency factory helpers for handlers.

Provides a consistent way to build service instances inside handlers
without coupling handlers to the DI wiring details.
"""
from __future__ import annotations

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config.settings import get_settings
from bot.integrations.youtube.client import YouTubeClient
from bot.services.analysis_runner import AnalysisRunner
from bot.services.channel_service import ChannelService
from bot.services.settings_service import SettingsService


def make_youtube_client() -> YouTubeClient:
    return YouTubeClient(api_key=get_settings().youtube_api_key)


def make_channel_service(session: AsyncSession) -> ChannelService:
    return ChannelService(session=session, youtube_client=make_youtube_client())


def make_settings_service(session: AsyncSession) -> SettingsService:
    return SettingsService(session=session)


def make_analysis_runner(session: AsyncSession, bot: Bot) -> AnalysisRunner:
    cfg = get_settings()
    return AnalysisRunner(
        session=session,
        youtube_client=make_youtube_client(),
        bot=bot,
        chat_id=cfg.telegram_chat_id,
    )

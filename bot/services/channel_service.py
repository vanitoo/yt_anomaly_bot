"""
Channel management service.

Handles adding, removing, and listing tracked YouTube channels.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from bot.integrations.youtube.client import (
    ChannelInfo,
    ChannelNotFoundError,
    YouTubeAPIError,
    YouTubeClient,
)
from bot.models.orm import Channel
from bot.repositories.channel_repo import ChannelRepository

logger = logging.getLogger(__name__)


class ChannelService:
    def __init__(self, session: AsyncSession, youtube_client: YouTubeClient) -> None:
        self._repo = ChannelRepository(session)
        self._yt = youtube_client

    async def add_channel(self, url: str) -> Tuple[Channel, bool]:
        """
        Add a channel by URL.

        Returns (channel, created) where `created` is False if it already existed.
        Raises ChannelNotFoundError or YouTubeAPIError on failure.
        """
        info: ChannelInfo = await self._yt.resolve_channel(url)
        existing = await self._repo.get_by_youtube_id(info.youtube_channel_id)
        if existing:
            if not existing.is_active:
                await self._repo.set_active(info.youtube_channel_id, True)
                logger.info("Re-activated channel: %s", info.title)
            return existing, False

        channel = await self._repo.create(
            youtube_channel_id=info.youtube_channel_id,
            channel_title=info.title,
            input_url=url,
        )
        return channel, True

    async def remove_channel(self, url_or_id: str) -> bool:
        """
        Remove a channel by URL or YouTube channel ID.

        Returns True if deleted, False if not found.
        """
        # Try to extract channel ID from URL first
        try:
            info = await self._yt.resolve_channel(url_or_id)
            return await self._repo.delete(info.youtube_channel_id)
        except (ChannelNotFoundError, YouTubeAPIError):
            # Maybe user passed a bare youtube_channel_id
            return await self._repo.delete(url_or_id)

    async def toggle_channel(self, url_or_id: str, active: bool) -> bool:
        try:
            info = await self._yt.resolve_channel(url_or_id)
            return await self._repo.set_active(info.youtube_channel_id, active)
        except (ChannelNotFoundError, YouTubeAPIError):
            return await self._repo.set_active(url_or_id, active)

    async def list_channels(self) -> List[Channel]:
        return await self._repo.get_all()

    async def get_active_channels(self) -> List[Channel]:
        return await self._repo.get_active()

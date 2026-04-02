"""
Repository for Channel CRUD operations.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.orm import Channel

logger = logging.getLogger(__name__)


class ChannelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_all(self) -> List[Channel]:
        result = await self._session.execute(select(Channel).order_by(Channel.created_at))
        return list(result.scalars().all())

    async def get_active(self) -> List[Channel]:
        result = await self._session.execute(
            select(Channel).where(Channel.is_active.is_(True)).order_by(Channel.created_at)
        )
        return list(result.scalars().all())

    async def get_by_id(self, channel_id: int) -> Optional[Channel]:
        return await self._session.get(Channel, channel_id)

    async def get_by_youtube_id(self, youtube_channel_id: str) -> Optional[Channel]:
        result = await self._session.execute(
            select(Channel).where(Channel.youtube_channel_id == youtube_channel_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        youtube_channel_id: str,
        channel_title: str,
        input_url: str,
    ) -> Channel:
        channel = Channel(
            youtube_channel_id=youtube_channel_id,
            channel_title=channel_title,
            input_url=input_url,
            is_active=True,
        )
        self._session.add(channel)
        await self._session.flush()
        logger.info("Created channel: %s (%s)", channel_title, youtube_channel_id)
        return channel

    async def set_active(self, youtube_channel_id: str, is_active: bool) -> bool:
        result = await self._session.execute(
            update(Channel)
            .where(Channel.youtube_channel_id == youtube_channel_id)
            .values(is_active=is_active)
        )
        return result.rowcount > 0

    async def delete(self, youtube_channel_id: str) -> bool:
        channel = await self.get_by_youtube_id(youtube_channel_id)
        if channel is None:
            return False
        await self._session.delete(channel)
        logger.info("Deleted channel: %s", youtube_channel_id)
        return True

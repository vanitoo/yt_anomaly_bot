"""
Repository for Video CRUD operations.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.orm import Video

logger = logging.getLogger(__name__)


class VideoRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_youtube_id(self, youtube_video_id: str) -> Optional[Video]:
        result = await self._session.execute(
            select(Video).where(Video.youtube_video_id == youtube_video_id)
        )
        return result.scalar_one_or_none()

    async def get_channel_videos_since(
        self,
        channel_id: int,
        since: datetime,
        include_shorts: bool = False,
    ) -> List[Video]:
        """Return videos for a channel published after `since`, optionally excluding shorts."""
        query = (
            select(Video)
            .where(Video.channel_id == channel_id)
            .where(Video.published_at >= since)
        )
        if not include_shorts:
            query = query.where(Video.is_short.is_(False))
        query = query.order_by(Video.published_at.desc())
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def upsert(
        self,
        *,
        youtube_video_id: str,
        channel_id: int,
        title: str,
        published_at: datetime,
        view_count: int,
        like_count: Optional[int],
        duration_seconds: Optional[int],
        is_short: bool,
        thumbnail_url: Optional[str],
        video_url: str,
    ) -> Video:
        """Insert or update a video by its YouTube ID."""
        existing = await self.get_by_youtube_id(youtube_video_id)
        if existing:
            existing.title = title
            existing.view_count = view_count
            existing.like_count = like_count
            existing.thumbnail_url = thumbnail_url
            existing.fetched_at = datetime.now(timezone.utc)
            await self._session.flush()
            return existing

        video = Video(
            youtube_video_id=youtube_video_id,
            channel_id=channel_id,
            title=title,
            published_at=published_at,
            view_count=view_count,
            like_count=like_count,
            duration_seconds=duration_seconds,
            is_short=is_short,
            thumbnail_url=thumbnail_url,
            video_url=video_url,
        )
        self._session.add(video)
        await self._session.flush()
        return video

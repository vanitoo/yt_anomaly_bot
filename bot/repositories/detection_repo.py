"""
Repositories for Detection and Setting models.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.orm import Detection, Setting

logger = logging.getLogger(__name__)


class DetectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def was_video_sent(self, video_id: int) -> bool:
        """Return True if this video was already sent as an anomaly signal."""
        result = await self._session.execute(
            select(Detection)
            .where(Detection.video_id == video_id)
            .where(Detection.sent_to_chat.is_(True))
        )
        return result.scalar_one_or_none() is not None

    async def get_max_ratio_for_video(self, video_id: int) -> Optional[float]:
        """Return the highest anomaly_ratio previously recorded for this video."""
        result = await self._session.execute(
            select(Detection.anomaly_ratio)
            .where(Detection.video_id == video_id)
            .order_by(Detection.anomaly_ratio.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        video_id: int,
        channel_id: int,
        baseline_value: float,
        anomaly_ratio: float,
        anomaly_percent: float,
        baseline_method: str,
        view_count_at_detection: int,
    ) -> Detection:
        detection = Detection(
            video_id=video_id,
            channel_id=channel_id,
            baseline_value=baseline_value,
            anomaly_ratio=anomaly_ratio,
            anomaly_percent=anomaly_percent,
            baseline_method=baseline_method,
            view_count_at_detection=view_count_at_detection,
            sent_to_chat=False,
            status="detected",
        )
        self._session.add(detection)
        await self._session.flush()
        return detection

    async def mark_sent(self, detection_id: int, telegram_message_id: int) -> None:
        detection = await self._session.get(Detection, detection_id)
        if detection:
            detection.sent_to_chat = True
            detection.telegram_message_id = telegram_message_id
            detection.status = "sent"
            await self._session.flush()

    async def mark_failed(self, detection_id: int) -> None:
        detection = await self._session.get(Detection, detection_id)
        if detection:
            detection.status = "failed"
            await self._session.flush()


class SettingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, key: str) -> Optional[str]:
        setting = await self._session.get(Setting, key)
        return setting.value if setting else None

    async def set(self, key: str, value: str) -> None:
        setting = await self._session.get(Setting, key)
        if setting:
            setting.value = value
        else:
            self._session.add(Setting(key=key, value=value))
        await self._session.flush()

    async def get_all(self) -> dict[str, str]:
        result = await self._session.execute(select(Setting))
        return {s.key: s.value for s in result.scalars().all()}

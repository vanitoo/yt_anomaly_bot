"""
Analysis runner service.

Orchestrates the full pipeline:
  fetch videos → upsert DB → detect anomalies → deduplicate → notify Telegram.

Deduplication logic:
  - First signal: video has never been sent → always send.
  - Repeat signal: video was already sent, but ratio grew significantly
    (by REPEAT_SIGNAL_MULTIPLIER or more) → send again with [🔁 UPDATE] label.
  - By default repeat signals are disabled; enable via setting repeat_signals=true.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.analytics.detector import AnalysisConfig, AnomalyResult, VideoMetric, detect_anomalies
from bot.integrations.youtube.client import YouTubeAPIError, YouTubeClient
from bot.models.orm import Channel, Video
from bot.repositories.channel_repo import ChannelRepository
from bot.repositories.detection_repo import DetectionRepository
from bot.repositories.video_repo import VideoRepository
from bot.services.metrics import (
    metrics,
    METRIC_CHANNELS_TOTAL,
    track_notification,
)
from bot.services.notification_service import NotificationService
from bot.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

# A repeat signal is sent when the new ratio is at least this much higher
# than the previously recorded maximum ratio. E.g. 2.0 means ratio must
# double compared to last recorded value (e.g. 2x → 4x, or 3x → 6x).
REPEAT_SIGNAL_MULTIPLIER = 2.0


class AnalysisRunner:
    """
    Runs the full anomaly detection pipeline for all active channels.
    """

    def __init__(
        self,
        session: AsyncSession,
        youtube_client: YouTubeClient,
        bot: Bot,
        chat_id: str,
    ) -> None:
        self._session = session
        self._yt = youtube_client
        self._bot = bot
        self._chat_id = chat_id

        self._channel_repo = ChannelRepository(session)
        self._video_repo = VideoRepository(session)
        self._detection_repo = DetectionRepository(session)
        self._settings_svc = SettingsService(session)
        self._notifier = NotificationService(bot, chat_id)

    async def run(self) -> dict:
        """
        Execute a full analysis cycle.

        Returns a summary dict with stats for logging/reporting.
        """
        logger.info("=== Starting analysis cycle ===")
        config = await self._settings_svc.get_analysis_config()
        repeat_signals_enabled = await self._settings_svc.get_bool(
            "repeat_signals", default=False
        )
        channels = await self._channel_repo.get_active()
        
        # Update channels gauge
        metrics.set_gauge(METRIC_CHANNELS_TOTAL, len(channels))
        
        logger.info("Active channels: %d", len(channels))

        total_sent = 0

        for channel in channels:
            try:
                sent = await self._process_channel(
                    channel, config, repeat_signals_enabled
                )
                total_sent += sent
            except YouTubeAPIError as exc:
                logger.error("YouTube API error for channel %r: %s", channel.channel_title, exc)
            except Exception as exc:
                logger.exception(
                    "Unexpected error processing channel %r: %s", channel.channel_title, exc
                )

        logger.info(
            "=== Analysis cycle complete | channels=%d | anomalies_sent=%d ===",
            len(channels),
            total_sent,
        )
        return {"channels_checked": len(channels), "anomalies_sent": total_sent}

    async def _process_channel(
        self,
        channel: Channel,
        config: AnalysisConfig,
        repeat_signals_enabled: bool,
    ) -> int:
        """Process one channel. Returns count of anomalies sent."""
        logger.info("Checking channel: %s (%s)", channel.channel_title, channel.youtube_channel_id)

        # Resolve channel info to get uploads playlist
        try:
            channel_info = await self._yt.resolve_channel(channel.youtube_channel_id)
        except Exception as exc:
            logger.error("Cannot resolve channel %r: %s", channel.channel_title, exc)
            return 0

        # Fetch videos from YouTube
        raw_videos = await self._yt.get_channel_videos(channel_info, max_results=200)
        logger.info("Fetched %d videos from YouTube for %r", len(raw_videos), channel.channel_title)

        # Upsert all fetched videos into DB
        cutoff = datetime.now(timezone.utc) - timedelta(days=config.period_days)
        for rv in raw_videos:
            if rv.published_at < cutoff:
                continue
            await self._video_repo.upsert(
                youtube_video_id=rv.youtube_video_id,
                channel_id=channel.id,
                title=rv.title,
                published_at=rv.published_at,
                view_count=rv.view_count,
                like_count=rv.like_count,
                duration_seconds=rv.duration_seconds,
                is_short=rv.is_short,
                thumbnail_url=rv.thumbnail_url,
                video_url=rv.video_url,
            )

        # Load videos from DB for analysis
        db_videos = await self._video_repo.get_channel_videos_since(
            channel.id,
            since=cutoff,
            include_shorts=config.include_shorts,
        )
        logger.info(
            "Videos in DB for analysis: %d (channel %r)", len(db_videos), channel.channel_title
        )

        # Convert to VideoMetric objects
        metrics = [self._to_metric(v) for v in db_videos]

        # Run anomaly detection
        anomalies, baseline = detect_anomalies(
            metrics, config, channel_label=channel.channel_title
        )

        if not anomalies:
            return 0

        # Deduplicate and send
        sent_count = 0
        for result in anomalies:
            video_db = await self._video_repo.get_by_youtube_id(result.video.youtube_video_id)
            if video_db is None:
                continue

            already_sent = await self._detection_repo.was_video_sent(video_db.id)

            if already_sent:
                # Check if we should send a repeat signal
                if not repeat_signals_enabled:
                    logger.debug("Skipping already-sent video (repeat disabled): %s", result.video.title)
                    continue

                prev_max_ratio = await self._detection_repo.get_max_ratio_for_video(video_db.id)
                if prev_max_ratio is None or result.anomaly_ratio < prev_max_ratio * REPEAT_SIGNAL_MULTIPLIER:
                    logger.debug(
                        "Skipping repeat signal for %r: ratio=%.2fx prev_max=%.2fx (need %.2fx)",
                        result.video.title,
                        result.anomaly_ratio,
                        prev_max_ratio or 0,
                        (prev_max_ratio or 0) * REPEAT_SIGNAL_MULTIPLIER,
                    )
                    continue

                logger.info(
                    "Repeat signal for %r: ratio grew %.2fx → %.2fx",
                    result.video.title,
                    prev_max_ratio,
                    result.anomaly_ratio,
                )
                is_repeat = True
            else:
                is_repeat = False

            # Create detection record
            detection = await self._detection_repo.create(
                video_id=video_db.id,
                channel_id=channel.id,
                baseline_value=result.baseline,
                anomaly_ratio=result.anomaly_ratio,
                anomaly_percent=result.anomaly_percent,
                baseline_method=result.baseline_method,
                view_count_at_detection=result.video.view_count,
            )

            # Send Telegram notification
            try:
                msg_id = await self._notifier.send_anomaly(
                    channel_title=channel.channel_title,
                    result=result,
                    is_repeat=is_repeat,
                )
                await self._detection_repo.mark_sent(detection.id, msg_id)
                sent_count += 1
                track_notification()
                logger.info(
                    "Sent %snotification for %r (ratio=%.2fx)",
                    "repeat " if is_repeat else "",
                    result.video.title,
                    result.anomaly_ratio,
                )
            except Exception as exc:
                logger.error("Failed to send notification for %r: %s", result.video.title, exc)
                await self._detection_repo.mark_failed(detection.id)

        return sent_count

    @staticmethod
    def _to_metric(video: Video) -> VideoMetric:
        return VideoMetric(
            video_id=video.id,
            youtube_video_id=video.youtube_video_id,
            title=video.title,
            published_at=video.published_at,
            view_count=video.view_count,
            thumbnail_url=video.thumbnail_url,
            video_url=video.video_url,
            is_short=video.is_short,
        )


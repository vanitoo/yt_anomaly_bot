"""Analysis runner: fetch -> persist -> detect -> deduplicate -> optional Telegram notify."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.analytics.detector import AnalysisConfig, VideoMetric, detect_anomalies
from bot.integrations.youtube.client import YouTubeAPIError, YouTubeClient
from bot.models.orm import Channel, Video
from bot.repositories.channel_repo import ChannelRepository
from bot.repositories.detection_repo import DetectionRepository
from bot.repositories.video_repo import VideoRepository
from bot.services.metrics import metrics, METRIC_CHANNELS_TOTAL, track_notification
from bot.services.notification_service import NotificationService
from bot.services.settings_service import SettingsService

logger = logging.getLogger(__name__)
REPEAT_SIGNAL_MULTIPLIER = 2.0


class AnalysisRunner:
    """Run analysis either in Telegram delivery mode or standalone GUI mode."""

    def __init__(
        self,
        session: AsyncSession,
        youtube_client: YouTubeClient,
        bot: Bot | None = None,
        chat_id: str | None = None,
        *,
        notify_telegram: bool = True,
    ) -> None:
        self._session = session
        self._yt = youtube_client
        self._channel_repo = ChannelRepository(session)
        self._video_repo = VideoRepository(session)
        self._detection_repo = DetectionRepository(session)
        self._settings_svc = SettingsService(session)
        self._notifier = (
            NotificationService(bot, chat_id)
            if notify_telegram and bot is not None and chat_id
            else None
        )

    @property
    def gui_mode(self) -> bool:
        return self._notifier is None

    async def run(self) -> dict:
        logger.info("=== Starting analysis cycle (mode=%s) ===", "gui" if self.gui_mode else "telegram")
        config = await self._settings_svc.get_analysis_config()
        repeat_signals_enabled = await self._settings_svc.get_bool("repeat_signals", default=False)
        channels = await self._channel_repo.get_active()
        metrics.set_gauge(METRIC_CHANNELS_TOTAL, len(channels))

        total_detected = 0
        total_sent = 0
        errors: list[str] = []

        for channel in channels:
            try:
                detected, sent = await self._process_channel(
                    channel, config, repeat_signals_enabled
                )
                total_detected += detected
                total_sent += sent
            except YouTubeAPIError as exc:
                message = f"{channel.channel_title}: {exc}"
                errors.append(message)
                logger.error("YouTube API error for %r: %s", channel.channel_title, exc)
            except Exception as exc:
                message = f"{channel.channel_title}: {exc}"
                errors.append(message)
                logger.exception("Unexpected error processing %r", channel.channel_title)

        summary = {
            "channels_checked": len(channels),
            "anomalies_detected": total_detected,
            "anomalies_sent": total_sent,
            "errors": errors,
        }
        logger.info("=== Analysis complete: %s ===", summary)
        return summary

    async def _process_channel(
        self,
        channel: Channel,
        config: AnalysisConfig,
        repeat_signals_enabled: bool,
    ) -> tuple[int, int]:
        logger.info("Checking channel: %s (%s)", channel.channel_title, channel.youtube_channel_id)
        channel_info = await self._yt.resolve_channel(channel.youtube_channel_id)
        raw_videos = await self._yt.get_channel_videos(channel_info, max_results=200)

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

        db_videos = await self._video_repo.get_channel_videos_since(
            channel.id, since=cutoff, include_shorts=config.include_shorts
        )
        anomalies, _ = detect_anomalies(
            [self._to_metric(v) for v in db_videos],
            config,
            channel_label=channel.channel_title,
        )

        detected_count = 0
        sent_count = 0
        for result in anomalies:
            video_db = await self._video_repo.get_by_youtube_id(result.video.youtube_video_id)
            if video_db is None:
                continue

            already_seen = (
                await self._detection_repo.was_video_detected(video_db.id)
                if self.gui_mode
                else await self._detection_repo.was_video_sent(video_db.id)
            )
            is_repeat = False
            if already_seen:
                if not repeat_signals_enabled:
                    continue
                prev_max = await self._detection_repo.get_max_ratio_for_video(video_db.id)
                if prev_max is None or result.anomaly_ratio < prev_max * REPEAT_SIGNAL_MULTIPLIER:
                    continue
                is_repeat = True

            detection = await self._detection_repo.create(
                video_id=video_db.id,
                channel_id=channel.id,
                baseline_value=result.baseline,
                anomaly_ratio=result.anomaly_ratio,
                anomaly_percent=result.anomaly_percent,
                baseline_method=result.baseline_method,
                view_count_at_detection=result.video.view_count,
            )
            detected_count += 1

            if self._notifier is None:
                continue

            try:
                msg_id = await self._notifier.send_anomaly(
                    channel_title=channel.channel_title,
                    result=result,
                    is_repeat=is_repeat,
                )
                await self._detection_repo.mark_sent(detection.id, msg_id)
                sent_count += 1
                track_notification()
            except Exception as exc:
                logger.error("Failed to send Telegram notification for %r: %s", result.video.title, exc)
                await self._detection_repo.mark_failed(detection.id)

        return detected_count, sent_count

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

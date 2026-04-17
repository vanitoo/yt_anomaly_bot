"""
Anomaly detection analytics.

Implements statistical baseline calculation and anomaly scoring
for YouTube channel videos. Designed for easy strategy swapping.
"""
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from bot.services.metrics import (
    metrics,
    METRIC_CHANNELS_TOTAL,
    METRIC_VIDEOS_ANALYZED_TOTAL,
    track_detection,
)

logger = logging.getLogger(__name__)

MIN_VIDEOS_FOR_ANALYSIS = 5


@dataclass
class VideoMetric:
    """Minimal video data needed for anomaly analysis."""
    video_id: int
    youtube_video_id: str
    title: str
    published_at: datetime
    view_count: int
    thumbnail_url: Optional[str]
    video_url: str
    is_short: bool


@dataclass
class AnomalyResult:
    """Result of anomaly analysis for a single video."""
    video: VideoMetric
    baseline: float
    baseline_method: str
    anomaly_ratio: float
    anomaly_percent: float
    rank: int              # 1-based rank by views (1 = highest)
    total_analyzed: int    # total videos in the analysis window
    age_days: int


@dataclass
class AnalysisConfig:
    """
    Runtime-configurable analysis parameters.

    All fields have sensible defaults matching the spec.
    """
    threshold: float = 1.8          # anomaly_ratio must exceed this
    min_views: int = 5000           # minimum views to be considered
    min_age_days: int = 7           # video must be at least this old
    period_days: int = 90           # look-back window in days
    baseline_method: str = "median" # "median" | "trimmed_mean"
    include_shorts: bool = False
    include_fresh_in_baseline: bool = False  # include <min_age_days videos in baseline calc


def _calculate_baseline(views_list: List[int], method: str) -> Optional[float]:
    """
    Calculate the baseline view count for a list of view counts.

    Returns None if the list is empty.
    """
    if not views_list:
        return None

    if method == "trimmed_mean":
        n = len(views_list)
        if n < 5:
            # Fall back to median for small samples
            return float(statistics.median(views_list))
        cut = max(1, int(n * 0.10))
        trimmed = sorted(views_list)[cut:-cut]
        return statistics.mean(trimmed) if trimmed else float(statistics.median(views_list))

    # Default: median
    return float(statistics.median(views_list))


def detect_anomalies(
    videos: List[VideoMetric],
    config: AnalysisConfig,
    channel_label: str = "",
) -> Tuple[List[AnomalyResult], Optional[float]]:
    """
    Analyse a list of videos and return anomalous ones along with the baseline value.

    Args:
        videos: All videos fetched for the channel.
        config: Analysis configuration.
        channel_label: Used only for log messages.

    Returns:
        (anomalies sorted by ratio desc, baseline value or None)
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=config.period_days)
    min_age_cutoff = now - timedelta(days=config.min_age_days)

    # Filter to analysis window
    window_videos = [
        v for v in videos
        if v.published_at >= cutoff
        and (config.include_shorts or not v.is_short)
    ]

    # Split into mature (old enough) and fresh
    mature_videos = [v for v in window_videos if v.published_at <= min_age_cutoff]
    fresh_videos = [v for v in window_videos if v.published_at > min_age_cutoff]

    # Decide which set to use for baseline calculation
    baseline_source = (
        window_videos if config.include_fresh_in_baseline else mature_videos
    )

    if len(baseline_source) < MIN_VIDEOS_FOR_ANALYSIS:
        logger.warning(
            "Channel %r has too few videos for analysis (%d < %d). Skipping.",
            channel_label,
            len(baseline_source),
            MIN_VIDEOS_FOR_ANALYSIS,
        )
        return [], None

    # Track videos analyzed
    metrics.inc_counter(METRIC_VIDEOS_ANALYZED_TOTAL, value=len(mature_videos))

    view_counts = [v.view_count for v in baseline_source]
    baseline = _calculate_baseline(view_counts, config.baseline_method)

    if baseline is None or baseline == 0:
        logger.warning("Baseline is zero or None for channel %r. Skipping.", channel_label)
        return [], baseline

    logger.info(
        "Channel %r | method=%s | baseline=%.0f | mature_videos=%d | fresh=%d",
        channel_label,
        config.baseline_method,
        baseline,
        len(mature_videos),
        len(fresh_videos),
    )

    # Sort mature videos by views descending for ranking
    ranked = sorted(mature_videos, key=lambda v: v.view_count, reverse=True)

    anomalies: List[AnomalyResult] = []
    for rank, video in enumerate(ranked, start=1):
        ratio = video.view_count / baseline
        percent = ((video.view_count - baseline) / baseline) * 100
        age_days = (now - video.published_at).days

        if (
            ratio >= config.threshold
            and video.view_count >= config.min_views
        ):
            # Track detection
            track_detection(channel_label)
            anomalies.append(
                AnomalyResult(
                    video=video,
                    baseline=baseline,
                    baseline_method=config.baseline_method,
                    anomaly_ratio=ratio,
                    anomaly_percent=percent,
                    rank=rank,
                    total_analyzed=len(mature_videos),
                    age_days=age_days,
                )
            )

    anomalies.sort(key=lambda a: a.anomaly_ratio, reverse=True)
    logger.info(
        "Channel %r | anomalies found: %d", channel_label, len(anomalies)
    )
    return anomalies, baseline

"""
Tests for the anomaly detection analytics module.

Tests cover:
- Baseline calculation (median, trimmed_mean)
- Anomaly detection logic
- Edge cases: empty input, too few videos, zero baseline, shorts filtering
"""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from typing import List

from bot.analytics.detector import (
    AnalysisConfig,
    AnomalyResult,
    VideoMetric,
    _calculate_baseline,
    detect_anomalies,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_video(
    video_id: int,
    views: int,
    age_days: int,
    is_short: bool = False,
    title: str = "Test Video",
) -> VideoMetric:
    """Factory for VideoMetric with sensible defaults."""
    now = datetime.now(timezone.utc)
    return VideoMetric(
        video_id=video_id,
        youtube_video_id=f"yt_{video_id}",
        title=title,
        published_at=now - timedelta(days=age_days),
        view_count=views,
        thumbnail_url=None,
        video_url=f"https://youtube.com/watch?v=yt_{video_id}",
        is_short=is_short,
    )


def _default_config(**kwargs) -> AnalysisConfig:
    defaults = dict(
        threshold=1.8,
        min_views=1000,
        min_age_days=7,
        period_days=90,
        baseline_method="median",
        include_shorts=False,
        include_fresh_in_baseline=False,
    )
    defaults.update(kwargs)
    return AnalysisConfig(**defaults)


# ---------------------------------------------------------------------------
# _calculate_baseline
# ---------------------------------------------------------------------------

class TestCalculateBaseline:
    def test_median_odd_count(self):
        assert _calculate_baseline([10, 20, 30, 40, 50], "median") == 30.0

    def test_median_even_count(self):
        assert _calculate_baseline([10, 20, 30, 40], "median") == 25.0

    def test_trimmed_mean_basic(self):
        # 10 values: cut top and bottom 1 each → mean of [20,30,40,50,60,70,80,90]
        values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        result = _calculate_baseline(values, "trimmed_mean")
        assert result == pytest.approx(55.0)

    def test_trimmed_mean_small_sample_falls_back_to_median(self):
        # < 5 values → median fallback
        result = _calculate_baseline([10, 20, 30], "trimmed_mean")
        assert result == 20.0

    def test_empty_returns_none(self):
        assert _calculate_baseline([], "median") is None
        assert _calculate_baseline([], "trimmed_mean") is None

    def test_single_value_median(self):
        assert _calculate_baseline([42], "median") == 42.0

    def test_unknown_method_falls_back_to_median(self):
        # Unknown method should default to median behaviour through the else branch
        result = _calculate_baseline([10, 20, 30], "unknown_method")
        assert result == 20.0


# ---------------------------------------------------------------------------
# detect_anomalies
# ---------------------------------------------------------------------------

class TestDetectAnomalies:
    def _normal_channel(self) -> List[VideoMetric]:
        """10 mature videos with ~20k views each, one obvious outlier."""
        videos = [_make_video(i, 20_000, age_days=10 + i) for i in range(1, 10)]
        videos.append(_make_video(99, 100_000, age_days=15))  # outlier
        return videos

    def test_detects_obvious_outlier(self):
        videos = self._normal_channel()
        config = _default_config(threshold=1.8, min_views=1000)
        anomalies, baseline = detect_anomalies(videos, config, "TestChannel")
        assert baseline is not None
        assert len(anomalies) == 1
        assert anomalies[0].video.video_id == 99
        assert anomalies[0].anomaly_ratio > 1.8

    def test_anomaly_ratio_calculation(self):
        videos = self._normal_channel()
        config = _default_config()
        anomalies, baseline = detect_anomalies(videos, config)
        assert anomalies
        top = anomalies[0]
        expected_ratio = top.video.view_count / baseline
        assert top.anomaly_ratio == pytest.approx(expected_ratio)

    def test_anomaly_percent_calculation(self):
        videos = self._normal_channel()
        config = _default_config()
        anomalies, _ = detect_anomalies(videos, config)
        top = anomalies[0]
        expected_pct = ((top.video.view_count - top.baseline) / top.baseline) * 100
        assert top.anomaly_percent == pytest.approx(expected_pct)

    def test_fresh_videos_excluded_from_anomaly_candidates(self):
        """Videos newer than min_age_days should never appear as anomalies."""
        videos = [_make_video(i, 20_000, age_days=10) for i in range(1, 10)]
        # This super-viral video is only 3 days old → should be excluded
        videos.append(_make_video(99, 999_999, age_days=2))
        config = _default_config(min_age_days=7)
        anomalies, _ = detect_anomalies(videos, config)
        ids = [a.video.video_id for a in anomalies]
        assert 99 not in ids

    def test_too_few_videos_returns_empty(self):
        """Fewer than MIN_VIDEOS_FOR_ANALYSIS → no anomalies, no crash."""
        videos = [_make_video(i, 10_000, age_days=15) for i in range(3)]
        config = _default_config()
        anomalies, baseline = detect_anomalies(videos, config)
        assert anomalies == []
        assert baseline is None

    def test_min_views_filter(self):
        """Videos below min_views should not be flagged, even with high ratio."""
        videos = [_make_video(i, 5_000, age_days=10) for i in range(1, 9)]
        # High ratio but tiny absolute views
        videos.append(_make_video(99, 50_000, age_days=20))
        config = _default_config(min_views=60_000)
        anomalies, _ = detect_anomalies(videos, config)
        assert len(anomalies) == 0

    def test_shorts_excluded_by_default(self):
        videos = [_make_video(i, 20_000, age_days=10) for i in range(1, 9)]
        # Short with massive views
        videos.append(_make_video(99, 500_000, age_days=20, is_short=True))
        config = _default_config(include_shorts=False)
        anomalies, _ = detect_anomalies(videos, config)
        ids = [a.video.video_id for a in anomalies]
        assert 99 not in ids

    def test_shorts_included_when_configured(self):
        videos = [_make_video(i, 20_000, age_days=10) for i in range(1, 9)]
        videos.append(_make_video(99, 500_000, age_days=20, is_short=True))
        config = _default_config(include_shorts=True)
        anomalies, _ = detect_anomalies(videos, config)
        ids = [a.video.video_id for a in anomalies]
        assert 99 in ids

    def test_anomalies_sorted_by_ratio_desc(self):
        """Multiple anomalies should be sorted highest ratio first."""
        videos = [_make_video(i, 10_000, age_days=10 + i) for i in range(1, 9)]
        videos.append(_make_video(101, 50_000, age_days=15))
        videos.append(_make_video(102, 80_000, age_days=20))
        config = _default_config(threshold=1.5)
        anomalies, _ = detect_anomalies(videos, config)
        ratios = [a.anomaly_ratio for a in anomalies]
        assert ratios == sorted(ratios, reverse=True)

    def test_rank_reflects_view_position(self):
        """The #1 ranked video should have the most views."""
        videos = [_make_video(i, 20_000, age_days=10 + i) for i in range(1, 9)]
        videos.append(_make_video(99, 100_000, age_days=20))  # outlier, most views
        config = _default_config(threshold=1.5)
        anomalies, _ = detect_anomalies(videos, config)
        assert anomalies[0].rank == 1

    def test_videos_outside_period_excluded(self):
        """Videos older than period_days should not be analysed."""
        videos = [_make_video(i, 20_000, age_days=10) for i in range(1, 9)]
        videos.append(_make_video(99, 500_000, age_days=120))  # older than 90-day window
        config = _default_config(period_days=90)
        anomalies, _ = detect_anomalies(videos, config)
        ids = [a.video.video_id for a in anomalies]
        assert 99 not in ids

    def test_trimmed_mean_baseline_method(self):
        """Smoke-test with trimmed_mean method."""
        videos = [_make_video(i, 20_000 + i * 100, age_days=10 + i) for i in range(12)]
        videos.append(_make_video(99, 200_000, age_days=20))
        config = _default_config(baseline_method="trimmed_mean", threshold=1.5)
        anomalies, baseline = detect_anomalies(videos, config)
        assert baseline is not None
        assert len(anomalies) >= 1
        assert anomalies[0].baseline_method == "trimmed_mean"

    def test_age_days_field_is_correct(self):
        videos = [_make_video(i, 20_000, age_days=10) for i in range(1, 9)]
        videos.append(_make_video(99, 100_000, age_days=14))
        config = _default_config(threshold=1.5)
        anomalies, _ = detect_anomalies(videos, config)
        matching = [a for a in anomalies if a.video.video_id == 99]
        assert matching
        assert matching[0].age_days == 14

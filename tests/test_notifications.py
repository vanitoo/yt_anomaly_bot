"""
Tests for notification message formatting.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from bot.analytics.detector import AnomalyResult, VideoMetric
from bot.services.notification_service import build_anomaly_caption, _fmt_views, _escape


class TestFmtViews:
    def test_millions(self):
        assert _fmt_views(1_500_000) == "1.5M"

    def test_thousands(self):
        assert _fmt_views(84_000) == "84K"

    def test_small(self):
        assert _fmt_views(999) == "999"

    def test_exactly_one_million(self):
        assert _fmt_views(1_000_000) == "1.0M"

    def test_exactly_one_thousand(self):
        assert _fmt_views(1_000) == "1K"


class TestEscape:
    def test_ampersand(self):
        assert _escape("AT&T") == "AT&amp;T"

    def test_lt_gt(self):
        assert _escape("<b>bold</b>") == "&lt;b&gt;bold&lt;/b&gt;"

    def test_quotes(self):
        assert _escape('say "hello"') == "say &quot;hello&quot;"

    def test_clean_string(self):
        assert _escape("Hello World") == "Hello World"


class TestBuildAnomalyCaption:
    def _make_result(self) -> AnomalyResult:
        video = VideoMetric(
            video_id=1,
            youtube_video_id="abc123",
            title="Why All Investors Make This Mistake",
            published_at=datetime(2026, 3, 12, tzinfo=timezone.utc),
            view_count=84_000,
            thumbnail_url="https://img.youtube.com/vi/abc123/maxresdefault.jpg",
            video_url="https://www.youtube.com/watch?v=abc123",
            is_short=False,
        )
        return AnomalyResult(
            video=video,
            baseline=21_000.0,
            baseline_method="median",
            anomaly_ratio=4.0,
            anomaly_percent=300.0,
            rank=1,
            total_analyzed=18,
            age_days=11,
        )

    def test_contains_channel_name(self):
        result = self._make_result()
        caption = build_anomaly_caption("Ivan Ivanov", result)
        assert "Ivan Ivanov" in caption

    def test_contains_video_title(self):
        result = self._make_result()
        caption = build_anomaly_caption("Channel", result)
        assert "Why All Investors Make This Mistake" in caption

    def test_contains_views(self):
        result = self._make_result()
        caption = build_anomaly_caption("Channel", result)
        assert "84K" in caption

    def test_contains_baseline(self):
        result = self._make_result()
        caption = build_anomaly_caption("Channel", result)
        assert "21K" in caption

    def test_contains_ratio(self):
        result = self._make_result()
        caption = build_anomaly_caption("Channel", result)
        assert "4.0x" in caption

    def test_contains_percent(self):
        result = self._make_result()
        caption = build_anomaly_caption("Channel", result)
        assert "+300%" in caption

    def test_contains_rank(self):
        result = self._make_result()
        caption = build_anomaly_caption("Channel", result)
        assert "1 из 18" in caption

    def test_contains_age(self):
        result = self._make_result()
        caption = build_anomaly_caption("Channel", result)
        assert "11 дн." in caption

    def test_contains_baseline_method(self):
        result = self._make_result()
        caption = build_anomaly_caption("Channel", result)
        assert "median" in caption

    def test_contains_video_url(self):
        result = self._make_result()
        caption = build_anomaly_caption("Channel", result)
        assert "https://www.youtube.com/watch?v=abc123" in caption

    def test_html_special_chars_in_title_escaped(self):
        result = self._make_result()
        result.video.title = "AT&T <Special> \"Quoted\""
        caption = build_anomaly_caption("Channel", result)
        assert "&amp;" in caption
        assert "&lt;" in caption

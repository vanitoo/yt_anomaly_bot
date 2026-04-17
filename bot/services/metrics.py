"""
Metrics and monitoring module.

Provides Prometheus-compatible metrics for monitoring bot performance.
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Generator

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    Simple metrics collector for monitoring.
    
    Supports:
    - Counters (monotonically increasing)
    - Gauges (current value)
    - Histograms (distribution of values)
    """

    def __init__(self):
        self._counters: dict[str, int] = {}
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = {}
        self._timers: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Counters
    # ------------------------------------------------------------------

    def inc_counter(self, name: str, value: int = 1, labels: dict | None = None) -> None:
        """Increment a counter."""
        key = self._make_key(name, labels)
        self._counters[key] = self._counters.get(key, 0) + value

    def get_counter(self, name: str, labels: dict | None = None) -> int:
        """Get current counter value."""
        key = self._make_key(name, labels)
        return self._counters.get(key, 0)

    # ------------------------------------------------------------------
    # Gauges
    # ------------------------------------------------------------------

    def set_gauge(self, name: str, value: float, labels: dict | None = None) -> None:
        """Set a gauge value."""
        key = self._make_key(name, labels)
        self._gauges[key] = value

    def get_gauge(self, name: str, labels: dict | None = None) -> float:
        """Get current gauge value."""
        key = self._make_key(name, labels)
        return self._gauges.get(key, 0.0)

    # ------------------------------------------------------------------
    # Histograms
    # ------------------------------------------------------------------

    def observe(self, name: str, value: float, labels: dict | None = None) -> None:
        """Record a value in a histogram."""
        key = self._make_key(name, labels)
        if key not in self._histograms:
            self._histograms[key] = []
        self._histograms[key].append(value)

    def get_histogram_stats(self, name: str, labels: dict | None = None) -> dict:
        """Get histogram statistics."""
        key = self._make_key(name, labels)
        values = self._histograms.get(key, [])
        if not values:
            return {"count": 0, "sum": 0, "avg": 0, "min": 0, "max": 0}
        return {
            "count": len(values),
            "sum": sum(values),
            "avg": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
        }

    # ------------------------------------------------------------------
    # Timers
    # ------------------------------------------------------------------

    @contextmanager
    def timer(self, name: str, labels: dict | None = None) -> Generator[None, None, None]:
        """Context manager to time a block of code."""
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            self.observe(f"{name}_duration_seconds", elapsed, labels)
            self.inc_counter(f"{name}_total", 1, labels)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _make_key(self, name: str, labels: dict | None = None) -> str:
        """Create a unique key from name and labels."""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def reset(self) -> None:
        """Reset all metrics."""
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()
        self._timers.clear()

    def get_all_metrics(self) -> dict:
        """Get all metrics as a dictionary."""
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {k: self.get_histogram_stats(k) for k in self._histograms},
        }

    def render_prometheus_format(self) -> str:
        """Render metrics in Prometheus exposition format."""
        lines = []

        for name, value in sorted(self._counters.items()):
            metric_name = self._normalize_name(name)
            lines.append(f"# TYPE {metric_name} counter")
            lines.append(f"{metric_name} {value}")

        for name, value in sorted(self._gauges.items()):
            metric_name = self._normalize_name(name)
            lines.append(f"# TYPE {metric_name} gauge")
            lines.append(f"{metric_name} {value}")

        for name in sorted(self._histograms.keys()):
            stats = self.get_histogram_stats(name)
            metric_name = self._normalize_name(name)
            lines.append(f"# TYPE {metric_name} histogram")
            lines.append(f"{metric_name}_count {stats['count']}")
            lines.append(f"{metric_name}_sum {stats['sum']}")

        return "\n".join(lines)

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize metric name for Prometheus format."""
        return name.replace("{", "_").replace("}", "").replace(",", "_")


# Global metrics instance
metrics = MetricsCollector()

# Pre-defined metric names
METRIC_API_REQUESTS_TOTAL = "youtube_api_requests_total"
METRIC_API_ERRORS_TOTAL = "youtube_api_errors_total"
METRIC_API_DURATION_SECONDS = "youtube_api_duration_seconds"
METRIC_CACHE_HITS_TOTAL = "youtube_cache_hits_total"
METRIC_CACHE_MISSES_TOTAL = "youtube_cache_misses_total"
METRIC_DETECTIONS_TOTAL = "anomaly_detections_total"
METRIC_CHANNELS_TOTAL = "channels_total"
METRIC_VIDEOS_ANALYZED_TOTAL = "videos_analyzed_total"
METRIC_NOTIFICATIONS_SENT_TOTAL = "notifications_sent_total"
METRIC_DB_QUERIES_TOTAL = "db_queries_total"
METRIC_DB_QUERY_DURATION_SECONDS = "db_query_duration_seconds"


def track_api_request(endpoint: str, success: bool = True) -> None:
    """Track an API request."""
    labels = {"endpoint": endpoint}
    if success:
        metrics.inc_counter(METRIC_API_REQUESTS_TOTAL, labels=labels)
    else:
        metrics.inc_counter(METRIC_API_ERRORS_TOTAL, labels=labels)


def track_cache_hit() -> None:
    """Track a cache hit."""
    metrics.inc_counter(METRIC_CACHE_HITS_TOTAL)


def track_cache_miss() -> None:
    """Track a cache miss."""
    metrics.inc_counter(METRIC_CACHE_MISSES_TOTAL)


def track_detection(channel_id: str) -> None:
    """Track an anomaly detection."""
    metrics.inc_counter(METRIC_DETECTIONS_TOTAL, labels={"channel": channel_id})


def track_notification() -> None:
    """Track a sent notification."""
    metrics.inc_counter(METRIC_NOTIFICATIONS_SENT_TOTAL)


def track_video_analyzed() -> None:
    """Track an analyzed video."""
    metrics.inc_counter(METRIC_VIDEOS_ANALYZED_TOTAL)


def track_db_query(query_type: str) -> None:
    """Track a database query."""
    labels = {"query_type": query_type}
    metrics.inc_counter(METRIC_DB_QUERIES_TOTAL, labels=labels)


@contextmanager
def track_db_query_time(query_type: str) -> Generator[None, None, None]:
    """Context manager to track database query duration."""
    labels = {"query_type": query_type}
    with metrics.timer(METRIC_DB_QUERY_DURATION_SECONDS, labels=labels):
        yield

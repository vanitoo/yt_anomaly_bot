"""
Settings service.

Provides a typed interface over the raw key-value settings table.
Falls back to values from the application config if a key is not set in DB.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from bot.analytics.detector import AnalysisConfig
from bot.config.settings import get_settings
from bot.repositories.detection_repo import SettingRepository

logger = logging.getLogger(__name__)


class SettingsService:
    """Typed read/write access to runtime settings."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = SettingRepository(session)
        self._cfg = get_settings()

    async def get_analysis_config(self) -> AnalysisConfig:
        repo = self._repo
        threshold = float(
            (await repo.get("threshold")) or self._cfg.default_threshold
        )
        min_views = int(
            (await repo.get("min_views")) or self._cfg.default_min_views
        )
        min_age_days = int(
            (await repo.get("min_age_days")) or self._cfg.default_min_age_days
        )
        period_days = int(
            (await repo.get("period_days")) or self._cfg.default_period_days
        )
        baseline_method = (
            (await repo.get("baseline_method")) or self._cfg.default_baseline_method
        )
        include_shorts = (
            (await repo.get("include_shorts")) or str(self._cfg.default_include_shorts)
        ).lower() in ("true", "1", "yes")
        include_fresh_in_baseline = (
            (await repo.get("include_fresh_in_baseline"))
            or str(self._cfg.default_include_fresh_in_baseline)
        ).lower() in ("true", "1", "yes")

        return AnalysisConfig(
            threshold=threshold,
            min_views=min_views,
            min_age_days=min_age_days,
            period_days=period_days,
            baseline_method=baseline_method,
            include_shorts=include_shorts,
            include_fresh_in_baseline=include_fresh_in_baseline,
        )

    async def set(self, key: str, value: str) -> None:
        await self._repo.set(key, value)

    async def get_all_display(self) -> dict[str, str]:
        cfg = get_settings()
        defaults = {
            "threshold": str(cfg.default_threshold),
            "min_views": str(cfg.default_min_views),
            "min_age_days": str(cfg.default_min_age_days),
            "period_days": str(cfg.default_period_days),
            "baseline_method": cfg.default_baseline_method,
            "include_shorts": str(cfg.default_include_shorts),
            "include_fresh_in_baseline": str(cfg.default_include_fresh_in_baseline),
            "schedule": cfg.schedule_interval,
        }
        overrides = await self._repo.get_all()
        defaults.update(overrides)
        return defaults

"""
Application settings loaded from environment variables.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Telegram ---
    telegram_bot_token: str
    telegram_chat_id: str
    admin_user_ids: str = ""  # comma-separated list of Telegram user IDs

    # --- YouTube ---
    youtube_api_key: str

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///./data/bot.db"

    # --- Analysis defaults ---
    default_threshold: float = 1.8
    default_min_views: int = 5000
    default_min_age_days: int = 7
    default_period_days: int = 90
    default_baseline_method: str = "median"  # median | trimmed_mean
    default_include_shorts: bool = False
    default_include_fresh_in_baseline: bool = False  # include <7d videos in baseline

    # --- Scheduler ---
    schedule_interval: str = "weekly"  # weekly | daily | hourly

    # --- Logging ---
    log_level: str = "INFO"
    log_file: str = "logs/bot.log"

    @field_validator("admin_user_ids", mode="before")
    @classmethod
    def strip_admin_ids(cls, v: str) -> str:
        return v.strip()

    @property
    def admin_ids_list(self) -> List[int]:
        if not self.admin_user_ids:
            return []
        return [int(x.strip()) for x in self.admin_user_ids.split(",") if x.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

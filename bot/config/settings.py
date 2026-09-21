"""Application settings loaded from environment variables."""
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
    # Optional so the standalone web GUI can run without Telegram configured.
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    admin_user_ids: str = ""

    # --- YouTube ---
    youtube_api_key: str
    youtube_cache_ttl_minutes: int = 15

    # --- Proxy ---
    # PROXY accepts comma/semicolon/newline separated proxy URLs.
    proxy: str = ""
    proxy_mode: str = "failover"
    proxy_healthcheck_url: str = "https://www.youtube.com/generate_204"
    proxy_healthcheck_timeout: float = 8.0
    proxy_healthcheck_interval: float = 60.0

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///./data/bot.db"

    # --- Analysis defaults ---
    default_threshold: float = 1.8
    default_min_views: int = 5000
    default_min_age_days: int = 7
    default_period_days: int = 90
    default_baseline_method: str = "median"
    default_include_shorts: bool = False
    default_include_fresh_in_baseline: bool = False

    # --- Scheduler ---
    schedule_interval: str = "weekly"

    # --- Standalone web GUI ---
    web_auto_scan: bool = True
    web_poll_interval_minutes: int = 60
    web_scan_on_start: bool = True

    # --- Logging ---
    log_level: str = "INFO"
    log_file: str = "logs/bot.log"

    @field_validator("admin_user_ids", mode="before")
    @classmethod
    def strip_admin_ids(cls, v: str) -> str:
        return (v or "").strip()

    @property
    def admin_ids_list(self) -> List[int]:
        if not self.admin_user_ids:
            return []
        return [int(x.strip()) for x in self.admin_user_ids.split(",") if x.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

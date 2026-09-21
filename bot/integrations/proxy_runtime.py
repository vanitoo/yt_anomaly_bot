"""Shared ProxyManager instance used by Telegram, YouTube and the web UI."""
from __future__ import annotations

from functools import lru_cache

from bot.config.settings import get_settings
from bot.integrations.proxy_manager import ProxyManager


@lru_cache(maxsize=1)
def get_proxy_manager() -> ProxyManager:
    cfg = get_settings()
    return ProxyManager.from_env_string(
        cfg.proxy,
        mode=cfg.proxy_mode,
        healthcheck_url=cfg.proxy_healthcheck_url,
        healthcheck_timeout=cfg.proxy_healthcheck_timeout,
        healthcheck_interval=cfg.proxy_healthcheck_interval,
    )


def reset_proxy_manager() -> None:
    """Clear the singleton cache (mainly useful in tests)."""
    get_proxy_manager.cache_clear()

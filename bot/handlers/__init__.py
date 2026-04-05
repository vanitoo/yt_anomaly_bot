"""
Handler registry.

Import all routers here so main.py only needs to import this module.
"""
from aiogram import Dispatcher

from .start import router as start_router
from .channels import router as channels_router
from .settings_handlers import router as settings_router
from .check_now import router as check_now_router
from .logs import router as logs_router


def register_all_handlers(dp: Dispatcher) -> None:
    """Register all handler routers with the dispatcher."""
    dp.include_router(start_router)
    dp.include_router(channels_router)
    dp.include_router(settings_router)
    dp.include_router(check_now_router)
    dp.include_router(logs_router)


__all__ = ["register_all_handlers"]

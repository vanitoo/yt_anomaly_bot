"""
Admin authorization filter for aiogram handlers.

Checks if the Telegram user_id is in the admin list (env config or DB admins table).
"""
from __future__ import annotations

import logging
from typing import Union

from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery

from bot.config.settings import get_settings

logger = logging.getLogger(__name__)


class IsAdmin(BaseFilter):
    """Filter that passes only for admin user IDs."""

    async def __call__(self, event: Union[Message, CallbackQuery]) -> bool:
        settings = get_settings()
        user = event.from_user
        if user is None:
            return False
        allowed = settings.admin_ids_list
        is_admin = user.id in allowed
        if not is_admin:
            logger.warning("Unauthorized access attempt by user_id=%s", user.id)
        return is_admin

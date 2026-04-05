"""
Handlers for channel management commands:
/add_channel, /remove_channel, /list_channels
"""
from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config.settings import get_settings
from bot.handlers.deps import make_channel_service
from bot.handlers.filters import IsAdmin
from bot.integrations.youtube.client import ChannelNotFoundError, YouTubeAPIError
from bot.models.database import get_session

logger = logging.getLogger(__name__)
router = Router(name="channels")


@router.message(Command("add_channel"), IsAdmin())
async def cmd_add_channel(message: Message) -> None:
    """
    /add_channel <url>

    Resolves and adds a YouTube channel to the watchlist.
    """
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer(
            "⚠️ Укажи ссылку на канал.\n"
            "Пример: <code>/add_channel https://youtube.com/@MrBeast</code>",
            parse_mode="HTML",
        )
        return

    url = args[1].strip()
    await message.answer(f"🔍 Ищу канал по ссылке: <code>{url}</code>...", parse_mode="HTML")

    cfg = get_settings()
    try:
        async with get_session(cfg.database_url) as session:
            svc = make_channel_service(session)
            channel, created = await svc.add_channel(url)

        if created:
            await message.answer(
                f"✅ Канал добавлен!\n\n"
                f"📺 <b>{channel.channel_title}</b>\n"
                f"🆔 ID: <code>{channel.youtube_channel_id}</code>",
                parse_mode="HTML",
            )
        else:
            await message.answer(
                f"ℹ️ Канал уже отслеживается.\n\n"
                f"📺 <b>{channel.channel_title}</b>",
                parse_mode="HTML",
            )
    except ChannelNotFoundError as exc:
        await message.answer(f"❌ Канал не найден: {exc}", parse_mode="HTML")
    except YouTubeAPIError as exc:
        logger.error("YouTube API error in add_channel: %s", exc)
        await message.answer(f"❌ Ошибка YouTube API: {exc}")
    except Exception as exc:
        logger.exception("Unexpected error in add_channel: %s", exc)
        await message.answer("❌ Произошла неожиданная ошибка. Смотри логи.")


@router.message(Command("remove_channel"), IsAdmin())
async def cmd_remove_channel(message: Message) -> None:
    """
    /remove_channel <url_or_id>

    Removes a channel from the watchlist.
    """
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer(
            "⚠️ Укажи ссылку или ID канала.\n"
            "Пример: <code>/remove_channel https://youtube.com/@MrBeast</code>",
            parse_mode="HTML",
        )
        return

    url_or_id = args[1].strip()
    cfg = get_settings()
    try:
        async with get_session(cfg.database_url) as session:
            svc = make_channel_service(session)
            deleted = await svc.remove_channel(url_or_id)

        if deleted:
            await message.answer("✅ Канал удалён из списка отслеживания.")
        else:
            await message.answer("⚠️ Канал не найден в базе.")
    except YouTubeAPIError as exc:
        await message.answer(f"❌ Ошибка YouTube API: {exc}")
    except Exception as exc:
        logger.exception("Unexpected error in remove_channel: %s", exc)
        await message.answer("❌ Произошла неожиданная ошибка.")


@router.message(Command("list_channels"))
async def cmd_list_channels(message: Message) -> None:
    """
    /list_channels

    Shows all tracked channels with their status.
    """
    cfg = get_settings()
    async with get_session(cfg.database_url) as session:
        svc = make_channel_service(session)
        channels = await svc.list_channels()

    if not channels:
        await message.answer("📭 Список каналов пуст. Добавь первый: /add_channel <url>")
        return

    lines = ["📋 <b>Отслеживаемые каналы:</b>\n"]
    for ch in channels:
        status = "✅" if ch.is_active else "⏸"
        lines.append(
            f"{status} <b>{ch.channel_title}</b>\n"
            f"   🆔 <code>{ch.youtube_channel_id}</code>"
        )
    lines.append(
        "\n<i>Управление: /enable_channel &lt;url&gt; | /disable_channel &lt;url&gt;</i>"
    )
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("enable_channel"), IsAdmin())
async def cmd_enable_channel(message: Message) -> None:
    """
    /enable_channel <url_or_id>

    Re-enables a previously disabled channel.
    """
    await _toggle_channel(message, active=True)


@router.message(Command("disable_channel"), IsAdmin())
async def cmd_disable_channel(message: Message) -> None:
    """
    /disable_channel <url_or_id>

    Pauses tracking for a channel without deleting it.
    """
    await _toggle_channel(message, active=False)


async def _toggle_channel(message: Message, active: bool) -> None:
    """Shared logic for enable/disable channel commands."""
    action = "включить" if active else "выключить"
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        cmd = "enable_channel" if active else "disable_channel"
        await message.answer(
            f"⚠️ Укажи ссылку или ID канала.\n"
            f"Пример: <code>/{cmd} https://youtube.com/@MrBeast</code>",
            parse_mode="HTML",
        )
        return

    url_or_id = args[1].strip()
    cfg = get_settings()
    try:
        async with get_session(cfg.database_url) as session:
            svc = make_channel_service(session)
            ok = await svc.toggle_channel(url_or_id, active=active)

        if ok:
            icon = "▶️" if active else "⏸"
            status_text = "включён" if active else "приостановлен"
            await message.answer(
                f"{icon} Канал <b>{status_text}</b>.", parse_mode="HTML"
            )
        else:
            await message.answer(
                f"⚠️ Канал не найден в базе. Сначала добавь его через /add_channel."
            )
    except YouTubeAPIError as exc:
        await message.answer(f"❌ Ошибка YouTube API: {exc}")
    except Exception as exc:
        logger.exception("Unexpected error in toggle_channel (active=%s): %s", active, exc)
        await message.answer(f"❌ Не удалось {action} канал. Смотри логи.")

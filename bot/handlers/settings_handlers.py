"""
Handlers for settings commands:
/settings, /set_threshold, /set_min_views, /set_min_age_days,
/set_period_days, /set_baseline, /set_schedule
"""
from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config.settings import get_settings
from bot.handlers.filters import IsAdmin
from bot.models.database import get_session
from bot.services.metrics import metrics
from bot.services.settings_service import SettingsService

logger = logging.getLogger(__name__)
router = Router(name="settings")

VALID_BASELINE_METHODS = ("median", "trimmed_mean")
VALID_SCHEDULES = ("weekly", "daily", "hourly")


@router.message(Command("settings"))
async def cmd_settings(message: Message) -> None:
    """Show current analysis settings."""
    cfg = get_settings()
    async with get_session(cfg.database_url) as session:
        svc = SettingsService(session)
        all_settings = await svc.get_all_display()

    lines = [
        "⚙️ <b>Текущие настройки анализа</b>\n",
        f"📊 Порог аномалии: <b>{all_settings.get('threshold')}</b>x",
        f"👁 Мин. просмотры: <b>{all_settings.get('min_views')}</b>",
        f"📅 Мин. возраст видео: <b>{all_settings.get('min_age_days')}</b> дн.",
        f"📆 Окно анализа: <b>{all_settings.get('period_days')}</b> дн.",
        f"🔬 Метод baseline: <b>{all_settings.get('baseline_method')}</b>",
        f"🩳 Shorts: <b>{all_settings.get('include_shorts')}</b>",
        f"🔁 Повторные сигналы: <b>{all_settings.get('repeat_signals', 'false')}</b>",
        f"🆕 Свежие в baseline: <b>{all_settings.get('include_fresh_in_baseline')}</b>",
        f"⏰ Расписание: <b>{all_settings.get('schedule')}</b>",
    ]
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("set_threshold"), IsAdmin())
async def cmd_set_threshold(message: Message) -> None:
    """
    /set_threshold 1.8
    Set anomaly detection threshold (minimum ratio above baseline).
    """
    val = _get_single_arg(message.text)
    if val is None:
        await message.answer("⚠️ Использование: /set_threshold 1.8")
        return
    try:
        v = float(val)
        if v <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Значение должно быть положительным числом, например 1.8")
        return

    await _save_setting(message, "threshold", str(v))
    await message.answer(f"✅ Порог аномалии установлен: <b>{v}x</b>", parse_mode="HTML")


@router.message(Command("set_min_views"), IsAdmin())
async def cmd_set_min_views(message: Message) -> None:
    """
    /set_min_views 5000
    Set minimum view count for a video to be considered an anomaly.
    """
    val = _get_single_arg(message.text)
    if val is None:
        await message.answer("⚠️ Использование: /set_min_views 5000")
        return
    try:
        v = int(val)
        if v < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Значение должно быть целым неотрицательным числом.")
        return

    await _save_setting(message, "min_views", str(v))
    await message.answer(f"✅ Мин. просмотры установлены: <b>{v}</b>", parse_mode="HTML")


@router.message(Command("set_min_age_days"), IsAdmin())
async def cmd_set_min_age_days(message: Message) -> None:
    """
    /set_min_age_days 7
    Set minimum age (in days) a video must have before being analyzed.
    """
    val = _get_single_arg(message.text)
    if val is None:
        await message.answer("⚠️ Использование: /set_min_age_days 7")
        return
    try:
        v = int(val)
        if v < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Значение должно быть целым неотрицательным числом.")
        return

    await _save_setting(message, "min_age_days", str(v))
    await message.answer(f"✅ Мин. возраст видео: <b>{v} дн.</b>", parse_mode="HTML")


@router.message(Command("set_period_days"), IsAdmin())
async def cmd_set_period_days(message: Message) -> None:
    """
    /set_period_days 90
    Set the look-back window for analysis (in days).
    """
    val = _get_single_arg(message.text)
    if val is None:
        await message.answer("⚠️ Использование: /set_period_days 90")
        return
    try:
        v = int(val)
        if v < 7:
            raise ValueError("too small")
    except ValueError:
        await message.answer("❌ Значение должно быть целым числом >= 7.")
        return

    await _save_setting(message, "period_days", str(v))
    await message.answer(f"✅ Окно анализа: <b>{v} дн.</b>", parse_mode="HTML")


@router.message(Command("set_baseline"), IsAdmin())
async def cmd_set_baseline(message: Message) -> None:
    """
    /set_baseline median|trimmed_mean
    Set the baseline calculation method.
    """
    val = _get_single_arg(message.text)
    if val is None or val not in VALID_BASELINE_METHODS:
        await message.answer(
            f"⚠️ Допустимые значения: {', '.join(VALID_BASELINE_METHODS)}\n"
            "Пример: /set_baseline median"
        )
        return

    await _save_setting(message, "baseline_method", val)
    await message.answer(f"✅ Метод baseline: <b>{val}</b>", parse_mode="HTML")


@router.message(Command("set_schedule"), IsAdmin())
async def cmd_set_schedule(message: Message) -> None:
    """
    /set_schedule weekly|daily|hourly
    Set how often the bot automatically runs analysis.
    Note: requires bot restart to take effect.
    """
    val = _get_single_arg(message.text)
    if val is None or val not in VALID_SCHEDULES:
        await message.answer(
            f"⚠️ Допустимые значения: {', '.join(VALID_SCHEDULES)}\n"
            "Пример: /set_schedule daily"
        )
        return

    await _save_setting(message, "schedule", val)
    await message.answer(
        f"✅ Расписание изменено: <b>{val}</b>\n"
        "⚠️ Перезапусти бота, чтобы новое расписание вступило в силу.",
        parse_mode="HTML",
    )


@router.message(Command("set_include_shorts"), IsAdmin())
async def cmd_set_include_shorts(message: Message) -> None:
    """
    /set_include_shorts true|false
    Toggle whether YouTube Shorts are included in analysis.
    """
    val = _get_single_arg(message.text)
    if val is None or val.lower() not in ("true", "false", "1", "0", "yes", "no"):
        await message.answer(
            "⚠️ Допустимые значения: true / false\n"
            "Пример: /set_include_shorts true"
        )
        return

    normalized = "true" if val.lower() in ("true", "1", "yes") else "false"
    await _save_setting(message, "include_shorts", normalized)
    label = "включены ✅" if normalized == "true" else "выключены ⏸"
    await message.answer(f"🩳 Shorts теперь <b>{label}</b>", parse_mode="HTML")


@router.message(Command("set_repeat_signals"), IsAdmin())
async def cmd_set_repeat_signals(message: Message) -> None:
    """
    /set_repeat_signals true|false
    Toggle whether already-sent anomalies can be re-sent if their ratio grows
    significantly (by 2x compared to the previously recorded value).
    """
    val = _get_single_arg(message.text)
    if val is None or val.lower() not in ("true", "false", "1", "0", "yes", "no"):
        await message.answer(
            "⚠️ Допустимые значения: true / false\n"
            "Пример: /set_repeat_signals true"
        )
        return

    normalized = "true" if val.lower() in ("true", "1", "yes") else "false"
    await _save_setting(message, "repeat_signals", normalized)
    label = "включены ✅" if normalized == "true" else "выключены ⏸"
    await message.answer(f"🔁 Повторные сигналы <b>{label}</b>", parse_mode="HTML")


@router.message(Command("metrics"), IsAdmin())
async def cmd_metrics(message: Message) -> None:
    """Show current metrics and statistics."""
    all_metrics = metrics.get_all_metrics()
    
    lines = ["📊 <b>Метрики бота</b>\n"]
    
    # Counters
    if all_metrics["counters"]:
        lines.append("📈 <b>Счётчики:</b>")
        for name, value in sorted(all_metrics["counters"].items()):
            short_name = name.split("_total")[0].replace("youtube_", "").replace("anomaly_", "").replace("db_", "")
            lines.append(f"  • {short_name}: <b>{value}</b>")
        lines.append("")
    
    # Gauges
    if all_metrics["gauges"]:
        lines.append("📊 <b>Гейджи:</b>")
        for name, value in sorted(all_metrics["gauges"].items()):
            short_name = name.replace("_total", "").replace("_channels", "")
            lines.append(f"  • {short_name}: <b>{value}</b>")
        lines.append("")
    
    # Histograms
    if all_metrics["histograms"]:
        lines.append("⏱ <b>Время операций:</b>")
        for name, stats in sorted(all_metrics["histograms"].items()):
            if stats["count"] > 0:
                short_name = name.replace("_duration_seconds", "").replace("youtube_", "").replace("db_", "")
                lines.append(f"  • {short_name}:")
                lines.append(f"      средний: <b>{stats['avg']:.3f}s</b>")
                lines.append(f"      макс: <b>{stats['max']:.3f}s</b>")
                lines.append(f"      запросов: <b>{stats['count']}</b>")
        lines.append("")
    
    if not any([all_metrics["counters"], all_metrics["gauges"], all_metrics["histograms"]]):
        lines.append("Нет данных о метриках. Запустите анализ для сбора статистики.")
    
    await message.answer("\n".join(lines), parse_mode="HTML")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_single_arg(text: str | None) -> str | None:
    """Extract the single argument after the command."""
    parts = (text or "").strip().split(maxsplit=1)
    return parts[1].strip() if len(parts) == 2 else None


async def _save_setting(message: Message, key: str, value: str) -> None:
    cfg = get_settings()
    async with get_session(cfg.database_url) as session:
        svc = SettingsService(session)
        await svc.set(key, value)

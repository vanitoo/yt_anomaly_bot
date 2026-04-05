"""
/start and /help command handlers.
"""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router(name="start")

WELCOME_TEXT = """
👋 <b>YouTube Anomaly Bot</b>

Я отслеживаю YouTube-каналы и нахожу ролики с аномально высоким числом просмотров.

<b>Как это работает:</b>
• Вы добавляете каналы через /add_channel
• Бот по расписанию анализирует ролики за 90 дней
• Находит видео, которые сильно выбиваются из нормы
• Отправляет уведомление с деталями

Введи /help для полного списка команд.
""".strip()

HELP_TEXT = """
📋 <b>Список команд</b>

<b>Каналы:</b>
/add_channel &lt;url&gt; — добавить канал
/remove_channel &lt;url&gt; — удалить канал
/list_channels — список отслеживаемых каналов
/enable_channel &lt;url&gt; — включить канал
/disable_channel &lt;url&gt; — приостановить канал

<b>Анализ:</b>
/check_now — запустить проверку вручную

<b>Настройки (только админы):</b>
/settings — текущие параметры анализа
/set_threshold &lt;число&gt; — порог аномалии (по умолч. 1.8)
/set_min_views &lt;число&gt; — мин. просмотры (по умолч. 5000)
/set_min_age_days &lt;число&gt; — мин. возраст видео в днях (по умолч. 7)
/set_period_days &lt;число&gt; — окно анализа в днях (по умолч. 90)
/set_baseline &lt;median|trimmed_mean&gt; — метод расчёта нормы
/set_schedule &lt;weekly|daily|hourly&gt; — расписание проверок
/set_include_shorts &lt;true|false&gt; — учитывать Shorts
/set_repeat_signals &lt;true|false&gt; — повторные сигналы при росте

<b>Администрирование:</b>
/logs [N] — последние N строк лога (по умолч. 30)

<b>Прочее:</b>
/start — приветствие
/help — этот список
""".strip()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(WELCOME_TEXT, parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, parse_mode="HTML")

# YouTube Anomaly Bot

Telegram-бот для поиска аномально успешных YouTube-видео.

Бот отслеживает заданные каналы, анализирует ролики за последние 90 дней
и находит видео, которые статистически выбиваются по просмотрам — затем
отправляет уведомление с превью и деталями прямо в Telegram.

---

## Возможности

- Добавление/удаление/включение/выключение YouTube-каналов через Telegram
- Поддержка любых форматов ссылок: `@handle`, `/channel/UC...`, `/user/`, `/c/`, `/watch?v=`, `/playlist?list=`
- Два метода расчёта нормы: **median** и **trimmed_mean**
- Фильтрация Shorts по длительности (< 61 сек)
- Дедупликация: один ролик — один раз. Опционально — повторный сигнал при кратном росте
- Расписание: weekly / daily / hourly (APScheduler)
- Ручной запуск через `/check_now`
- Все параметры меняются через Telegram без перезапуска
- Просмотр логов прямо в Telegram (`/logs`)
- Миграции через **Alembic** (SQLite по умолчанию, легко → PostgreSQL)

---

## Быстрый старт

### 1. Распакуй проект и создай окружение

```bash
cd yt_anomaly_bot
python -m venv .venv
source .venv/bin/activate      # Linux / macOS
# .venv\Scripts\activate       # Windows
pip install -r requirements.txt
```

### 2. Настрой переменные окружения

```bash
cp .env.example .env
```

Заполни `.env`:

| Переменная | Описание |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен от [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | ID чата для уведомлений |
| `ADMIN_USER_IDS` | Твой Telegram user_id (узнай через [@userinfobot](https://t.me/userinfobot)) |
| `YOUTUBE_API_KEY` | API-ключ из [Google Cloud Console](https://console.cloud.google.com) |

#### Получение YouTube API Key

1. [console.cloud.google.com](https://console.cloud.google.com) → создай проект
2. APIs & Services → Enable APIs → **YouTube Data API v3**
3. Credentials → Create Credentials → **API Key**

> Дневная квота: ~10 000 units. Один цикл анализа 10 каналов ≈ 200–500 units.

### 3. Примени миграции

```bash
alembic upgrade head
```

База данных `data/bot.db` создаётся автоматически.
При следующих запусках `main.py` применяет миграции сам.

### 4. Запусти бота

```bash
python main.py
```

---

## Alembic — управление миграциями

```bash
# Применить все миграции до последней
alembic upgrade head

# Откатить последнюю миграцию
alembic downgrade -1

# Показать текущую версию
alembic current

# Показать историю миграций
alembic history

# Создать новую миграцию (автогенерация из моделей)
alembic revision --autogenerate -m "add new column"
```

При изменении ORM-моделей в `bot/models/orm.py`:
1. Запусти `alembic revision --autogenerate -m "описание"`
2. Проверь сгенерированный файл в `migrations/versions/`
3. Примени: `alembic upgrade head`

> **SQLite + ALTER TABLE**: Alembic использует `render_as_batch=True`, что позволяет
> корректно применять миграции к SQLite (который не поддерживает ALTER TABLE нативно).

---

## Команды бота

### Каналы
| Команда | Описание |
|---|---|
| `/add_channel <url>` | Добавить канал (поддерживает все форматы URL) |
| `/remove_channel <url>` | Удалить канал |
| `/list_channels` | Список каналов со статусом |
| `/enable_channel <url>` | Включить приостановленный канал |
| `/disable_channel <url>` | Приостановить канал (без удаления) |

### Анализ
| Команда | Описание |
|---|---|
| `/check_now` | Запустить проверку вручную |

### Настройки (только для админов)
| Команда | Описание |
|---|---|
| `/settings` | Показать все текущие параметры |
| `/set_threshold 1.8` | Порог аномалии (ratio >= threshold) |
| `/set_min_views 5000` | Мин. просмотры для сигнала |
| `/set_min_age_days 7` | Мин. возраст видео в днях |
| `/set_period_days 90` | Окно анализа в днях |
| `/set_baseline median` | Метод: `median` или `trimmed_mean` |
| `/set_schedule weekly` | Расписание: `weekly`, `daily`, `hourly` |
| `/set_include_shorts true` | Включать Shorts в анализ |
| `/set_repeat_signals true` | Повторные сигналы при 2x-росте ratio |

### Администрирование
| Команда | Описание |
|---|---|
| `/logs [N]` | Последние N строк лога (по умолч. 30) |

---

## Алгоритм обнаружения аномалий

```
Для каждого активного канала:
  1. Скачать до 200 видео из uploads-плейлиста (YouTube API)
  2. Уложить в базу (upsert по youtube_video_id)
  3. Отфильтровать ролики младше min_age_days и старше period_days
  4. Если < 5 роликов → пропустить с предупреждением в лог
  5. Рассчитать baseline (median или trimmed_mean)
  6. Для каждого ролика: ratio = views / baseline
  7. Если ratio >= threshold И views >= min_views → аномалия
  8. Проверить дедупликацию по таблице detections
  9. Если repeat_signals=true и ratio вырос в 2x+ → повторный сигнал
 10. Отправить в Telegram с thumbnail и аналитикой
```

---

## Поддерживаемые форматы URL каналов

```
https://youtube.com/channel/UCxxxxxxxxxxxxxxxxxxxxxxxx
https://youtube.com/@MrBeast
https://youtube.com/user/LinusTechTips
https://youtube.com/c/TED
https://youtube.com/watch?v=dQw4w9WgXcQ    ← определит канал по видео
https://youtube.com/playlist?list=PLxxxx   ← определит канал по плейлисту
UCxxxxxxxxxxxxxxxxxxxxxxxx                 ← голый channel ID
@MrBeast                                   ← голый handle
```

---

## Структура проекта

```
yt_anomaly_bot/
├── main.py                            ← точка входа
├── alembic.ini                        ← конфиг Alembic
├── .env.example
├── requirements.txt
├── pytest.ini
├── README.md
├── data/                              ← SQLite база (авто)
├── logs/                              ← логи (авто)
├── migrations/
│   ├── env.py                         ← async Alembic env
│   ├── script.py.mako                 ← шаблон миграций
│   └── versions/
│       └── 0001_initial.py            ← начальная схема
└── bot/
    ├── config/     settings.py, logging_setup.py
    ├── models/     orm.py (5 таблиц), database.py
    ├── repositories/  channel, video, detection, settings
    ├── integrations/youtube/client.py
    ├── analytics/detector.py
    ├── services/   analysis_runner, channel, notification, settings
    ├── handlers/   start, channels, settings, check_now, logs, filters
    └── jobs/scheduler.py
```

---

## Тесты

```bash
pytest -v
```

Покрывают:
- Алгоритм детекции аномалий (14 тестов)
- URL-парсинг YouTube клиента (11 тестов)
- Форматирование Telegram-сообщений (13 тестов)

---

## Переход на PostgreSQL

```bash
pip install asyncpg
```

В `.env`:
```
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/yt_anomaly_bot
```

Затем:
```bash
alembic upgrade head
python main.py
```

---

## Пример уведомления

```
🚨 Аномалия на YouTube

📺 Канал: Иван Иванов
🎬 Видео: «Почему все инвесторы делают эту ошибку»
📅 Опубликовано: 12.03.2026
👁 Просмотры: 84K
📊 Норма канала: 21K
📈 Превышение: +300% / 4.0x
🔗 Ссылка: https://youtube.com/watch?v=...

─────────────────
📌 Место: 1 из 18
⏱ Возраст: 11 дн.
🔬 Метод: median
```

Повторный сигнал отличается заголовком: `🔁 Повторный сигнал — YouTube аномалия`

---

## Веб-панель

Отдельный FastAPI-сервер с дашбордом. Работает независимо от бота, читает ту же базу данных.

### Запуск

```bash
python run_web.py
# или
python run_web.py --host 0.0.0.0 --port 8000
# или с авто-перезагрузкой (dev-mode)
python run_web.py --reload
```

Открой браузер: **http://localhost:8000**

### Что есть в панели

**Раздел «Обзор»**
- 6 ключевых метрик: каналы, видео, аномалии, лучший ratio, время последней проверки
- Timeline-график — аномалии по дням + avg ratio (bar + line)
- Histogram — распределение аномалий по диапазонам ratio (1.8–2x, 2–3x, …, 10x+)
- Топ каналов с progress bar по количеству аномалий
- Таблица последних 8 аномалий с превью

**Раздел «Аномалии»**
- Полная таблица всех детекций с thumbnail
- Фильтры по периоду: 30 / 90 / 180 / 365 дней
- Фильтры по ratio: все / 2x+ / 3x+ / 5x+
- Пагинация (25 записей на страницу)
- Фильтр по каналу через боковую панель

**Раздел «Каналы»**
- Таблица всех каналов с кол-вом видео, аномалий, лучшим ratio и датой последней детекции
- Статус active / paused

### REST API

Документация: **http://localhost:8000/api/docs**

| Endpoint | Описание |
|---|---|
| `GET /api/stats/overview` | Общая статистика |
| `GET /api/detections` | Список аномалий (пагинация, фильтры) |
| `GET /api/channels` | Список каналов со статистикой |
| `GET /api/charts/anomalies_over_time` | Данные для timeline-графика |
| `GET /api/charts/ratio_distribution` | Данные для histogram |
| `GET /api/charts/top_channels` | Топ каналов |

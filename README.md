# YouTube Anomaly Bot

Telegram-бот для поиска аномально успешных YouTube-видео.

Бот отслеживает заданные каналы, анализирует ролики за последние 90 дней
и находит видео, которые статистически выбиваются по просмотрам — затем
отправляет уведомление с превью и деталями прямо в Telegram.

---

## Возможности

- Добавление/удаление YouTube-каналов через Telegram-команды
- Поддержка любых форматов ссылок: `@handle`, `/channel/UC...`, `/user/`, `/c/`
- Два метода расчёта нормы: **median** и **trimmed_mean**
- Фильтрация Shorts по длительности
- Дедупликация: один ролик отправляется только один раз
- Расписание: weekly / daily / hourly (через APScheduler)
- Ручной запуск через `/check_now`
- Все параметры анализа меняются через Telegram без перезапуска
- SQLite для MVP, легко переключается на PostgreSQL

---

## Быстрый старт

### 1. Клонируй / распакуй проект

```bash
cd yt_anomaly_bot
```

### 2. Создай виртуальное окружение и установи зависимости

```bash
python -m venv .venv
source .venv/bin/activate      # Linux / macOS
# .venv\Scripts\activate       # Windows

pip install -r requirements.txt
```

### 3. Настрой переменные окружения

```bash
cp .env.example .env
```

Открой `.env` и заполни:

| Переменная | Описание |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен от [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | ID чата куда слать уведомления |
| `ADMIN_USER_IDS` | Твой Telegram user_id (через [@userinfobot](https://t.me/userinfobot)) |
| `YOUTUBE_API_KEY` | API-ключ из [Google Cloud Console](https://console.cloud.google.com) |

#### Как получить YouTube API Key

1. Перейди на [console.cloud.google.com](https://console.cloud.google.com)
2. Создай проект → **APIs & Services** → **Enable APIs**
3. Найди и включи **YouTube Data API v3**
4. **Credentials** → **Create Credentials** → **API Key**

> Дневная квота: ~10 000 units. Один цикл анализа 10 каналов ≈ 200–500 units.

### 4. Запусти бота

```bash
python main.py
```

При первом запуске автоматически создаётся база данных `data/bot.db`.

---

## Команды бота

### Каналы
| Команда | Описание |
|---|---|
| `/add_channel <url>` | Добавить канал |
| `/remove_channel <url>` | Удалить канал |
| `/list_channels` | Список каналов |

### Анализ
| Команда | Описание |
|---|---|
| `/check_now` | Запустить проверку вручную |

### Настройки (только для админов)
| Команда | Описание |
|---|---|
| `/settings` | Показать текущие параметры |
| `/set_threshold 1.8` | Порог аномалии (ratio >= threshold) |
| `/set_min_views 5000` | Мин. просмотры |
| `/set_min_age_days 7` | Мин. возраст видео |
| `/set_period_days 90` | Окно анализа в днях |
| `/set_baseline median` | Метод: `median` или `trimmed_mean` |
| `/set_schedule weekly` | Расписание: `weekly`, `daily`, `hourly` |

---

## Как работает алгоритм

```
Для каждого активного канала:
  1. Скачать видео за последние period_days дней (YouTube API)
  2. Уложить в базу (upsert по youtube_video_id)
  3. Отфильтровать ролики младше min_age_days
  4. Если < 5 роликов → пропустить с предупреждением
  5. Рассчитать baseline (median или trimmed_mean)
  6. Для каждого ролика: ratio = views / baseline
  7. Если ratio >= threshold И views >= min_views → аномалия
  8. Проверить дедупликацию (таблица detections)
  9. Отправить в Telegram с thumbnail
```

---

## Структура проекта

```
yt_anomaly_bot/
├── main.py                        # Точка входа
├── .env.example                   # Пример конфига
├── requirements.txt
├── pytest.ini
├── data/                          # SQLite база (создаётся автоматически)
├── logs/                          # Логи (создаётся автоматически)
└── bot/
    ├── config/
    │   ├── settings.py            # Pydantic Settings
    │   └── logging_setup.py
    ├── models/
    │   ├── orm.py                 # SQLAlchemy модели
    │   └── database.py            # Engine, session factory
    ├── repositories/
    │   ├── channel_repo.py
    │   ├── video_repo.py
    │   └── detection_repo.py
    ├── integrations/
    │   └── youtube/
    │       └── client.py          # YouTube Data API v3
    ├── analytics/
    │   └── detector.py            # Алгоритм аномалий
    ├── services/
    │   ├── analysis_runner.py     # Оркестратор пайплайна
    │   ├── channel_service.py
    │   ├── notification_service.py
    │   └── settings_service.py
    ├── handlers/
    │   ├── start.py               # /start, /help
    │   ├── channels.py            # /add_channel, /remove_channel, /list_channels
    │   ├── settings_handlers.py   # /settings, /set_*
    │   ├── check_now.py           # /check_now
    │   ├── filters.py             # IsAdmin filter
    │   └── deps.py                # Dependency factories
    └── jobs/
        └── scheduler.py           # APScheduler
```

---

## Тесты

```bash
pytest -v
```

Тесты покрывают:
- Алгоритм детекции аномалий (`test_detector.py`)
- URL-парсинг YouTube клиента (`test_youtube_client.py`)
- Форматирование Telegram-сообщений (`test_notifications.py`)

---

## Переход на PostgreSQL

1. Установи драйвер: `pip install asyncpg`
2. В `.env` замени:
   ```
   DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/yt_anomaly_bot
   ```
3. Перезапусти — таблицы создадутся автоматически.

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

Сообщение отправляется с обложкой видео как photo + caption.

# KODA.md — Инструкции для работы с проектом

## Обзор проекта

**YouTube Anomaly Bot** — Telegram-бот для обнаружения аномально успешных видео на YouTube-каналах.

Бот отслеживает заданные каналы, анализирует видео за последние 90 дней и находит ролики, которые статистически выбиваются по просмотрам, затем отправляет уведомление с превью и деталями в Telegram.

### Основные технологии

| Компонент | Технология |
|-----------|------------|
| Telegram-фреймворк | aiogram 3.10.0 |
| HTTP-клиент | httpx 0.27.2 |
| База данных | SQLAlchemy 2.0.35 + aiosqlite 0.20.0 |
| Конфигурация | Pydantic 2.9.2 + pydantic-settings 2.5.2 |
| Планировщик | APScheduler 3.10.4 |
| Тестирование | pytest 8.3.3 + pytest-asyncio 0.24.0 |

### Архитектура

Проект построен по принципам Clean Architecture с чётким разделением слоёв:

```
bot/
├── config/           # Конфигурация и логирование
├── models/           # ORM-модели SQLAlchemy
├── repositories/     # Слой доступа к данным
├── services/         # Бизнес-логика
├── handlers/         # Обработчики Telegram-команд
├── analytics/        # Алгоритм детекции аномалий
├── integrations/     # Интеграции (YouTube API)
└── jobs/             # Планировщик задач
```

---

## Сборка и запуск

### Предварительные требования

- Python 3.10+
- Токен Telegram-бота (от @BotFather)
- API-ключ YouTube Data API v3 (из Google Cloud Console)

### Установка

```bash
# Создание виртуального окружения
python -m venv .venv
source .venv/bin/activate      # Linux/macOS
# .venv\Scripts\activate       # Windows

# Установка зависимостей
pip install -r requirements.txt
```

### Настройка окружения

```bash
cp .env.example .env
```

Заполните переменные в `.env`:

| Переменная | Описание |
|------------|----------|
| `TELEGRAM_BOT_TOKEN` | Токен Telegram-бота от @BotFather |
| `TELEGRAM_CHAT_ID` | ID чата для уведомлений |
| `ADMIN_USER_IDS` | Список Telegram user ID через запятую |
| `YOUTUBE_API_KEY` | API-ключ из Google Cloud Console |

### Запуск

```bash
python main.py
```

При первом запуске автоматически создаётся база данных SQLite по пути `data/bot.db`.

---

## Тестирование

```bash
pytest -v
```

Тесты находятся в директории `tests/` и покрывают:

- `test_detector.py` — алгоритм детекции аномалий
- `test_youtube_client.py` — парсинг URL YouTube
- `test_notifications.py` — форматирование Telegram-сообщений

Конфигурация pytest находится в `pytest.ini`:

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

---

## Команды Telegram-бота

### Управление каналами

| Команда | Описание |
|---------|----------|
| `/add_channel <url>` | Добавить YouTube-канал |
| `/remove_channel <url>` | Удалить канал |
| `/list_channels` | Показать список каналов |

### Запуск анализа

| Команда | Описание |
|---------|----------|
| `/check_now` | Запустить проверку вручную |

### Настройки (только для админов)

| Команда | Описание |
|---------|----------|
| `/settings` | Показать текущие параметры |
| `/set_threshold 1.8` | Установить порог аномалии |
| `/set_min_views 5000` | Минимальное количество просмотров |
| `/set_min_age_days 7` | Минимальный возраст видео в днях |
| `/set_period_days 90` | Окно анализа в днях |
| `/set_baseline median` | Метод расчёта: `median` или `trimmed_mean` |
| `/set_schedule weekly` | Расписание: `weekly`, `daily`, `hourly` |

---

## Структура базы данных

Проект использует SQLAlchemy ORM с асинхронными моделями:

### Основные таблицы

- **channels** — отслеживаемые YouTube-каналы
- **videos** — видео, полученные через YouTube API
- **detections** — записи об обнаруженных аномалиях
- **settings** — ключ-значение для runtime-настроек
- **admins** — Telegram-администраторы бота

---

## Алгоритм детекции аномалий

Реализован в `bot/analytics/detector.py`:

1. Загрузить видео канала за последние N дней (по умолчанию 90)
2. Отфильтровать видео младше минимального возраста (по умолчанию 7 дней)
3. Если видео меньше 5 — пропустить канал
4. Рассчитать baseline (median или trimmed_mean) по просмотрам
5. Для каждого видео: вычислить ratio = просмотры / baseline
6. Если ratio >= threshold И просмотры >= min_views — это аномалия
7. Проверить дедупликацию (одно видео — одно уведомление)
8. Отправить уведомление в Telegram

---

## Переход на PostgreSQL

Для масштабирования проекта можно переключиться на PostgreSQL:

1. Установить драйвер: `pip install asyncpg`
2. В `.env` изменить:
   ```
   DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/yt_anomaly_bot
   ```
3. Перезапустить бота — таблицы создадутся автоматически

---

## Важные файлы проекта

| Файл | Назначение |
|------|------------|
| `main.py` | Точка входа, инициализация бота и планировщика |
| `bot/config/settings.py` | Загрузка конфигурации через Pydantic |
| `bot/models/orm.py` | SQLAlchemy-модели |
| `bot/analytics/detector.py` | Алгоритм обнаружения аномалий |
| `bot/integrations/youtube/client.py` | YouTube Data API v3 клиент |
| `bot/services/analysis_runner.py` | Оркестратор анализа |
| `bot/handlers/` | Обработчики Telegram-команд |
| `bot/jobs/scheduler.py` | APScheduler для периодических задач |
| `requirements.txt` | Зависимости проекта |
| `.env.example` | Шаблон конфигурации |

---

## Рекомендации по разработке

- При добавлении новых зависимостей обновлять `requirements.txt`
- Все новые функции покрывать тестами в `tests/`
- Использовать async/await для работы с БД и HTTP
- Придерживаться структуры: handlers → services → repositories → models
- Конфиденциальные данные хранить только в `.env`, не коммитить в репозиторий

---

## CI/CD

Проект использует GitHub Actions для автоматического тестирования и сборки:

### Конфигурация

Файл `.github/workflows/ci.yml` содержит pipeline с тремя этапами:

1. **Тестирование** — запуск pytest на Python 3.10, 3.11, 3.12 (Ubuntu, Windows)
2. **Linting** — проверка кода через flake8 и black
3. **Docker Build** — сборка и публикация образа на Docker Hub (только при push в main)

### Локальный запуск тестов

```bash
pytest -v --cov=bot --cov-report=html
```

### Просмотр статусов CI

Статусы pull request'ов и коммитов отображаются на вкладке **Actions** в GitHub.

---

## Кэширование YouTube API

Для экономии квоты YouTube API реализовано двухуровневое кэширование:

### LRU-кэш настроек

Конфигурация загружается один раз и кэшируется через `lru_cache`.

### SQLite-кэш ответов API

- **Расположение**: `data/youtube_cache.db`
- **TTL**: 12 часов
- **Ключ**: SHA-256 хэш от endpoint + параметры запроса

Кэш автоматически очищается от устаревших записей.

### Отключение кэша

```python
client = YouTubeClient(api_key="...", cache_enabled=False)
```

---

## Метрики и мониторинг

В проекте реализована система сбора метрик в `bot/services/metrics.py`:

### Типы метрик

| Метрика | Тип | Описание |
|---------|-----|----------|
| `youtube_api_requests_total` | Counter | Количество запросов к YouTube API |
| `youtube_api_errors_total` | Counter | Количество ошибок API |
| `youtube_cache_hits_total` | Counter | Попадания в кэш |
| `youtube_cache_misses_total` | Counter | Промахи кэша |
| `anomaly_detections_total` | Counter | Обнаруженные аномалии |
| `channels_total` | Gauge | Количество активных каналов |
| `videos_analyzed_total` | Counter | Проанализированные видео |
| `notifications_sent_total` | Counter | Отправленные уведомления |
| `db_queries_total` | Counter | Выполненные DB-запросы |
| `*_duration_seconds` | Histogram | Время выполнения операций |

### Команда просмотра метрик

```
/metics
```

Доступна только администраторам. Показывает текущую статистику в удобном формате.

### Экспорт в Prometheus

Метрики можно получить в формате Prometheus через:

```python
from bot.services.metrics import metrics
print(metrics.render_prometheus_format())
```

---

## Миграции базы данных (Alembic)

Проект использует Alembic для управления миграциями БД:

### Команды

```bash
# Создать новую миграцию
alembic revision --autogenerate -m "Описание изменений"

# Применить миграции
alembic upgrade head

# Откатить одну миграцию
alembic downgrade -1

# Показать текущее состояние
alembic current
```

### Конфигурация

- `alembic.ini` — основной конфиг
- `migrations/env.py` — настройка окружения
- `migrations/versions/` — версияльные миграции

Поддерживает async SQLAlchemy (aiosqlite / asyncpg).

---

## TODO

- Добавить CI/CD для автоматического тестирования ✅
- Рассмотреть использование Alembic для миграций БД ✅
- Добавить метрики и мониторинг ✅
- Реализовать кэширование ответов YouTube API ✅

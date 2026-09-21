# Standalone GUI + proxy

Этот режим позволяет тестировать мониторинг YouTube **без Telegram**. Приложение само
опросит активные каналы, сохранит видео и аномалии в общей БД и покажет результат в
браузере.

## 1. Настройка

Скопируйте пример окружения:

```bash
cp .env.example .env
```

Минимум для GUI:

```env
YOUTUBE_API_KEY=...
DATABASE_URL=sqlite+aiosqlite:///./data/bot.db

PROXY=http://user:pass@host:3128;socks5://user:pass@host:1080
PROXY_MODE=failover

WEB_AUTO_SCAN=true
WEB_SCAN_ON_START=true
WEB_POLL_INTERVAL_MINUTES=60
```

`TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID` можно оставить пустыми.

Поддерживаемые режимы прокси: `off`, `single`, `sticky`, `failover`,
`random`, `rotate`. В режиме `failover` используется первый живой прокси, при
сетевой ошибке запрос переключается на следующий, а health-check позволяет вернуться
на primary после его восстановления.

> Если прокси настроены, но все недоступны, YouTube-запрос **не уходит напрямую**.
> Это сделано намеренно, чтобы приложение не обходило заданную proxy policy.

## 2. Запуск без Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run_web.py
```

Откройте: http://127.0.0.1:8000

API docs: http://127.0.0.1:8000/api/docs

## 3. Docker

Standalone GUI — сервис по умолчанию:

```bash
docker compose up -d web
```

Откройте: http://localhost:8000

Telegram-режим запускается отдельно:

```bash
docker compose --profile telegram up -d bot
```

PostgreSQL также вынесен в отдельный profile:

```bash
docker compose --profile postgres up -d postgres
```

## 4. Что видно в GUI

- состояние фонового опроса;
- состояние ProxyManager и каждого прокси;
- добавление, пауза и удаление YouTube-каналов;
- кнопка ручного опроса;
- автоматический опрос по `WEB_POLL_INTERVAL_MINUTES`;
- таблица последних видео;
- таблица найденных аномалий;
- график просмотров последних видео;
- график количества аномалий по дням.

## 5. Проверка прокси

В интерфейсе есть кнопка **«Проверить прокси»**. Также доступны:

- `GET /api/proxy/status`
- `POST /api/proxy/check`
- `POST /api/scan/run`

Proxy credentials в статусе маскируются.

## 6. Telegram + YouTube через один ProxyManager

При запуске `main.py` aiogram использует управляемую proxy-сессию. YouTube API
использует тот же singleton ProxyManager, поэтому оба направления видят одинаковый
failover/status и общий health-check.

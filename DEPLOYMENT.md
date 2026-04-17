# Инструкция по развертыванию YouTube Anomaly Bot на сервере

## Варианты развертывания

1. **Docker Compose** (рекомендуется) — проще всего, все зависимости в контейнерах
2. **Прямой запуск** — без Docker, требует установки Python и зависимостей

---

## Вариант 1: Развертывание через Docker Compose (рекомендуется)

### Предварительные требования

- Ubuntu 20.04+ / Debian 11+ / CentOS 8+
- 2 GB RAM минимум
- 10 GB свободного места на диске
- Доступ в интернет (для Telegram API и YouTube API)

### Шаг 1: Установка Docker и Docker Compose

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка зависимостей
sudo apt install -y apt-transport-https ca-certificates curl gnupg lsb-release

# Добавление GPG-ключа Docker
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Добавление репозитория Docker
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Установка Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io

# Установка Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Проверка установки
docker --version
docker-compose --version

# Добавление пользователя в группу docker (чтобы не использовать sudo)
sudo usermod -aG docker $USER
newgrp docker
```

### Шаг 2: Клонирование проекта

```bash
# Переход в директорию /opt
cd /opt

# Клонирование репозитория (если у вас есть доступ)
git clone <ваш-репозиторий>.git youtube-anomaly-bot
cd youtube-anomaly-bot

# ИЛИ загрузка файлов вручную через scp/sftp
# scp -r ./bot ./tests *.py *.ini .env.example docker-compose.yml Dockerfile user@server:/opt/youtube-anomaly-bot/
```

### Шаг 3: Настройка окружения

```bash
# Создание файла .env
cp .env.example .env

# Редактирование .env
nano .env
```

Заполните переменные:

```env
# === Telegram ===
TELEGRAM_BOT_TOKEN=ваш_токен_от_BotFather
TELEGRAM_CHAT_ID=ваш_ID_чата_для_уведомлений
ADMIN_USER_IDS=ваш_Telegram_user_id

# === YouTube API ===
YOUTUBE_API_KEY=ваш_API_ключ_из_Google_Cloud_Console

# === База данных (оставьте SQLite для простоты) ===
DATABASE_URL=sqlite+aiosqlite:///./data/bot.db

# === Настройки анализа ===
DEFAULT_THRESHOLD=1.8
DEFAULT_MIN_VIEWS=5000
DEFAULT_MIN_AGE_DAYS=7
DEFAULT_PERIOD_DAYS=90
DEFAULT_BASELINE_METHOD=median

# === Логирование ===
LOG_LEVEL=INFO
LOG_FILE=logs/bot.log
```

**Как узнать Telegram Chat ID и User ID:**

- Отправьте любое сообщение боту, затем перейдите по ссылке: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
- Найдите `"chat":{"id":123456789}` или `"from":{"id":123456789}`

### Шаг 4: Запуск контейнеров

```bash
# Переход в директорию проекта
cd /opt/youtube-anomaly-bot

# Запуск в фоновом режиме
docker-compose up -d

# Проверка статуса
docker-compose ps

# Просмотр логов
docker-compose logs -f bot
```

### Шаг 5: Проверка работы

```bash
# Проверка, что бот запущен
docker-compose logs bot | grep "Bot is running"

# Проверка сети (должно вернуть 200 OK)
docker exec yt-anomaly-bot python -c "import urllib.request; print(urllib.request.urlopen('https://api.telegram.org', timeout=5).status)"
```

### Шаг 6: Автоматический запуск при старте сервера

```bash
# Docker Compose уже настроен на автоматический запуск через restart: unless-stopped
# Если нужно перезапустить:
docker-compose restart
```

### Управление контейнерами

```bash
# Остановка
docker-compose down

# Перезапуск
docker-compose restart

# Просмотр логов
docker-compose logs -f bot
docker-compose logs -f postgres  # если используете PostgreSQL

# Обновление кода
git pull
docker-compose build --no-cache
docker-compose up -d

# Полная очистка (удалит все данные!)
docker-compose down -v
```

---

## Вариант 2: Прямой запуск на сервере (без Docker)

### Шаг 1: Установка Python и зависимостей

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка Python 3.11 и зависимостей
sudo apt install -y python3.11 python3.11-venv python3-pip git

# Проверка версии
python3.11 --version
```

### Шаг 2: Клонирование проекта

```bash
cd /opt
git clone <ваш-репозиторий>.git youtube-anomaly-bot
cd youtube-anomaly-bot
```

### Шаг 3: Создание виртуального окружения

```bash
# Создание виртуального окружения
python3.11 -m venv .venv

# Активация
source .venv/bin/activate

# Установка зависимостей
pip install --upgrade pip
pip install -r requirements.txt
```

### Шаг 4: Настройка окружения

```bash
# Создание .env
cp .env.example .env
nano .env

# Заполните те же переменные, что и в Варианте 1
```

### Шаг 5: Применение миграций

```bash
# Активация виртуального окружения
source .venv/bin/activate

# Применение миграций Alembic
alembic upgrade head
```

### Шаг 6: Запуск бота

```bash
# Запуск в фоне через nohup
nohup python main.py > logs/bot.log 2>&1 &

# Или через screen/tmux
screen -S bot
python main.py
# Ctrl+A, затем D для отсоединения
```

### Настройка systemd сервиса (рекомендуется)

Создайте файл `/etc/systemd/system/youtube-anomaly-bot.service`:

```ini
[Unit]
Description=YouTube Anomaly Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/youtube-anomaly-bot
Environment="PATH=/opt/youtube-anomaly-bot/.venv/bin"
ExecStart=/opt/youtube-anomaly-bot/.venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Активация сервиса:

```bash
# Перезагрузка systemd
sudo systemctl daemon-reload

# Включение автозапуска
sudo systemctl enable youtube-anomaly-bot

# Запуск
sudo systemctl start youtube-anomaly-bot

# Статус
sudo systemctl status youtube-anomaly-bot

# Лог
sudo journalctl -u youtube-anomaly-bot -f
```

---

## Настройка PostgreSQL (опционально)

### Через Docker Compose

```yaml
# В docker-compose.yml postgres уже настроен
# Просто измените .env:
DATABASE_URL=postgresql+asyncpg://ytbot:changeme@postgres:5432/yt_anomaly_bot
```

### На отдельном сервере

```bash
# Установка PostgreSQL
sudo apt install -y postgresql postgresql-contrib

# Создание базы и пользователя
sudo -u postgres psql
CREATE DATABASE yt_anomaly_bot;
CREATE USER ytbot WITH PASSWORD 'changeme';
GRANT ALL PRIVILEGES ON DATABASE yt_anomaly_bot TO ytbot;
\q

# В .env:
DATABASE_URL=postgresql+asyncpg://ytbot:changeme@ваш-сервер:5432/yt_anomaly_bot
```

---

## Мониторинг и логирование

### Просмотр логов

```bash
# Docker
docker-compose logs -f bot
docker-compose logs --tail=100 bot

# Без Docker
tail -f /opt/youtube-anomaly-bot/logs/bot.log
sudo journalctl -u youtube-anomaly-bot -f
```

### Проверка здоровья

```bash
# Проверка процесса
docker ps | grep yt-anomaly-bot

# Без Docker
pgrep -f "python main.py"

# Проверка сети
curl -I https://api.telegram.org
```

### Ротация логов

Добавьте в `/etc/logrotate.d/youtube-anomaly-bot`:

```
/opt/youtube-anomaly-bot/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    notifempty
    create 0644 ubuntu ubuntu
}
```

---

## Резервное копирование

### SQLite база

```bash
# Остановить бота
docker-compose stop bot

# Резервная копия
cp /opt/youtube-anomaly-bot/data/bot.db /backup/bot.db.$(date +%Y%m%d)

# Запуск обратно
docker-compose start bot
```

### PostgreSQL база

```bash
docker exec yt-anomaly-postgres pg_dump -U ytbot yt_anomaly_bot > backup.sql
```

### Восстановление

```bash
# SQLite
cp /backup/bot.db.20240101 /opt/youtube-anomaly-bot/data/bot.db

# PostgreSQL
cat backup.sql | docker exec -i yt-anomaly-postgres psql -U ytbot yt_anomaly_bot
```

---

## Решение проблем

### Бот не подключается к Telegram

```bash
# Проверка сети
docker exec yt-anomaly-bot python -c "import urllib.request; print(urllib.request.urlopen('https://api.telegram.org', timeout=5).status)"

# Проверка DNS
docker exec yt-anomaly-bot cat /etc/resolv.conf

# Решение: добавить DNS в docker-compose.yml
dns:
  - 8.8.8.8
  - 8.8.4.4
```

### Ошибка миграций

```bash
# Очистка базы и перезапуск
docker-compose down -v
docker-compose up -d
```

### Высокое потребление памяти

```bash
# Перезапуск контейнера
docker-compose restart bot

# Ограничение памяти в docker-compose.yml
mem_limit: 512m
```

---

## Безопасность

### Файлы .env

```bash
# Не коммитьте .env в Git
echo ".env" >> .gitignore

# Ограничьте доступ
chmod 600 /opt/youtube-anomaly-bot/.env
```

### Firewall

```bash
# Разрешите только необходимый трафик
sudo ufw allow 22/tcp   # SSH
sudo ufw enable
```

### Обновления

```bash
# Регулярное обновление системы
sudo apt update && sudo apt upgrade -y

# Обновление Docker
sudo apt install --upgrade docker-ce docker-compose
```

---

## Проверка после развертывания

```bash
# 1. Контейнеры работают
docker-compose ps

# 2. Логи без ошибок
docker-compose logs bot | grep -i error

# 3. Бот отвечает в Telegram (отправьте команду /start)

# 4. База данных создана
ls -la /opt/youtube-anomaly-bot/data/

# 5. Логи пишутся
ls -la /opt/youtube-anomaly-bot/logs/
```

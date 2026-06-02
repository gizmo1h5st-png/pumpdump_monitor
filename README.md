# 🚀 Pump & Dump Monitor — Telegram Mini App

Мониторит все бессрочные фьючерсы Bybit (≥$100k объём), ищет пампы/дампы ≥5%/10%, строит скриншоты графиков с FVG/OB/зонами и шлёт алерты в Telegram.

## ⚡ Быстрый старт

```bash
# 1. Клонирование
# 2. Создать .env из .env.example и вписать BOT_TOKEN
# 3. Запуск локально
pip install -r requirements.txt
python main.py
```

## 🐳 Docker / Railway

```bash
docker build -t pumpdump .
docker run -p 8000:8000 --env-file .env pumpdump
```

Railway: подключить GitHub-репозиторий, переменные взять из `.env.example`.

## 🎛 Telegram Mini App

В боте нажмите **«Открыть монитор»** — откроется WebApp с дашбордом, настройками и историей алертов.

## 🔧 Переменные окружения

| Переменная | Описание |
|---|---|
| `BOT_TOKEN` | Токен Telegram-бота (@BotFather) |
| `DATABASE_URL` | `sqlite:///data/bot.db` по умолчанию |
| `TZ` | `Europe/Moscow` |
| `PAIRS_UPDATE_MIN` | Как часто обновлять список пар (5) |
| `SNAP_INTERVAL_SEC` | Период снапшотов (60) |
| `MAX_CONCURRENT_SNAPS` | Параллельных скриншотов (10) |

## 📁 Структура

- `main.py` — точка входа
- `bybit_client.py` — REST Bybit (aiohttp)
- `monitor.py` — движок сбора + памп/дамп детектор
- `chart_builder.py` — matplotlib/mplfinance скриншоты
- `db.py` — SQLite (aiosqlite)
- `bot_handlers.py` — команды TG
- `web_app.py` — FastAPI + Mini App
- `templates/index.html` — UI Mini App
- `static/style.css` / `app.js` — стили и логика фронта

## ⚠️ Лимиты

Bybit public API: ~50 req/s. Мы делаем 1 bulk-запрос тикеров каждые 1.5 сек — влезаем с запасом.

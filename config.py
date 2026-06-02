"""
Конфигурация через переменные окружения (.env)
"""
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/bot.db")
TZ = os.getenv("TZ", "Europe/Moscow")

# Интервалы (сек / мин)
PAIRS_UPDATE_MIN = int(os.getenv("PAIRS_UPDATE_MIN", "5"))
SNAP_INTERVAL_SEC = int(os.getenv("SNAP_INTERVAL_SEC", "60"))
MAX_CONCURRENT_SNAPS = int(os.getenv("MAX_CONCURRENT_SNAPS", "10"))

# Bybit public
BYBIT_REST = "https://api.bybit.com"
BYBIT_WS = "wss://stream.bybit.com/v5/public/linear"

# Дефолтные настройки пользователя
DEFAULTS = {
    "timeframe": "5",
    "pump_threshold": 5.0,   # %
    "volume_min_usd": 100_000,
    "zone_pct": 2.0,         # зона интереса ±%
    "ob_mult": 1.5,          # body >= ATR * N
    "volume_delta_mult": 1.5,
    "fvg_enabled": 1,
    "lot_threshold": 10.0,   # мин кол-во лотов для разметки (в единицах base coin)
    "paused": 0,
}

assert BOT_TOKEN, "BOT_TOKEN обязателен! Заполните .env"

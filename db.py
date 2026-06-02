"""
Async SQLite через aiosqlite
"""
import aiosqlite
import os
from datetime import datetime
from config import DATABASE_URL

# Преобразуем sqlite:///data/bot.db → data/bot.db
DB_PATH = DATABASE_URL.replace("sqlite:///", "")
os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                chat_id INTEGER PRIMARY KEY,
                timeframe TEXT DEFAULT '5',
                pump_threshold REAL DEFAULT 5.0,
                volume_min_usd REAL DEFAULT 100000,
                zone_pct REAL DEFAULT 2.0,
                ob_mult REAL DEFAULT 1.5,
                volume_delta_mult REAL DEFAULT 1.5,
                fvg_enabled INTEGER DEFAULT 1,
                lot_threshold REAL DEFAULT 10.0,
                paused INTEGER DEFAULT 0,
                updated_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                symbol TEXT,
                direction TEXT,
                change_percent REAL,
                price REAL,
                screenshot_path TEXT,
                timestamp TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS snapshots_journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                timeframe TEXT,
                screenshot_path TEXT,
                created_at TEXT
            )
        """)
        await db.commit()

async def get_settings(chat_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM user_settings WHERE chat_id=?", (chat_id,)) as cur:
            row = await cur.fetchone()
            if row:
                return dict(row)
            # создать дефолт
            d = {
                "chat_id": chat_id,
                "timeframe": "5",
                "pump_threshold": 5.0,
                "volume_min_usd": 100000.0,
                "zone_pct": 2.0,
                "ob_mult": 1.5,
                "volume_delta_mult": 1.5,
                "fvg_enabled": 1,
                "lot_threshold": 10.0,
                "paused": 0,
                "updated_at": datetime.utcnow().isoformat(),
            }
            await db.execute("""
                INSERT INTO user_settings (chat_id, timeframe, pump_threshold, volume_min_usd,
                    zone_pct, ob_mult, volume_delta_mult, fvg_enabled, lot_threshold, paused, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, tuple(d.values()))
            await db.commit()
            return d

async def save_settings(chat_id: int, fields: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        sets = ", ".join(f"{k}=?" for k in fields)
        vals = list(fields.values()) + [chat_id]
        await db.execute(f"UPDATE user_settings SET {sets} WHERE chat_id=?", vals)
        await db.commit()

async def add_alert(chat_id, symbol, direction, change_percent, price, screenshot_path):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO alerts (chat_id, symbol, direction, change_percent, price, screenshot_path, timestamp)
            VALUES (?,?,?,?,?,?,?)
        """, (chat_id, symbol, direction, change_percent, price, screenshot_path, datetime.utcnow().isoformat()))
        await db.commit()

async def get_alerts(chat_id, limit=5):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM alerts WHERE chat_id=? ORDER BY id DESC LIMIT ?", (chat_id, limit)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

async def add_snapshot(symbol, timeframe, screenshot_path):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO snapshots_journal (symbol, timeframe, screenshot_path, created_at)
            VALUES (?,?,?,?)
        """, (symbol, timeframe, screenshot_path, datetime.utcnow().isoformat()))
        await db.commit()

async def cleanup_old_snapshots(days=1):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            DELETE FROM snapshots_journal WHERE created_at < datetime('now', '-{} days')
        """.format(days))
        await db.commit()

import asyncio
import os
from collections import defaultdict, deque
from datetime import datetime, timedelta
from config import PAIRS_UPDATE_MIN, SNAP_INTERVAL_SEC, MAX_CONCURRENT_SNAPS
from bybit_client import BybitClient
from chart_builder import build_snapshot
from db import add_alert, add_snapshot, get_settings, cleanup_old_snapshots
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

class Monitor:
    def __init__(self, bot_app):
        self.client = BybitClient()
        self.bot = bot_app
        self.symbols: list[str] = []
        self.price_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=300))
        self.snap_sem = asyncio.Semaphore(MAX_CONCURRENT_SNAPS)
        self.running = True
        self._last_alert: dict[str, datetime] = {}
        
        # Статистика для вывода в боте
        self.start_time = datetime.utcnow()
        self.last_update_time = None
        self.cycles_count = 0
        self.last_error = "Нет"
        self.recent_activity = deque(maxlen=5) # Последние 5 значимых движений

    async def start(self):
        await self.client.start()
        await self._update_symbols()
        asyncio.create_task(self._loop_update_symbols())
        asyncio.create_task(self._loop_pumpdump())
        asyncio.create_task(self._cleanup_loop())

    async def stop(self):
        self.running = False
        await self.client.close()

    async def _update_symbols(self):
        try:
            instruments = await self.client.get_linear_symbols()
            tickers = await self.client.get_tickers()
            vol_map = {t["symbol"]: float(t.get("turnover24h", 0)) for t in tickers}
            
            # Берем минимальный порог из всех пользователей (для оптимизации мониторинга)
            # Но для простоты мониторим топ 500 по ликвидности
            new_symbols = []
            for inst in instruments:
                sym = inst["symbol"]
                if inst.get("status") != "Trading": continue
                if vol_map.get(sym, 0) >= 100_000:
                    new_symbols.append(sym)
            new_symbols.sort(key=lambda s: vol_map.get(s, 0), reverse=True)
            self.symbols = new_symbols[:500]
            self.last_update_time = datetime.utcnow()
            print(f"[Monitor] Список обновлён: {len(self.symbols)} пар")
        except Exception as e:
            self.last_error = str(e)[:50]
            print(f"[Monitor] Ошибка обновления списка: {e}")

    async def _loop_update_symbols(self):
        while self.running:
            await asyncio.sleep(PAIRS_UPDATE_MIN * 60)
            await self._update_symbols()

    async def _loop_pumpdump(self):
        while self.running:
            await asyncio.sleep(1.5)
            self.cycles_count += 1
            if not self.symbols: continue
            try:
                tickers = await self.client.get_tickers()
                now = datetime.utcnow()
                for t in tickers:
                    sym = t["symbol"]
                    if sym not in self.symbols: continue
                    price = float(t.get("lastPrice", 0))
                    if price <= 0: continue
                    hist = self.price_history[sym]
                    hist.append((now, price))
                    await self._check_pumpdump(sym, price, hist, now)
            except Exception as e:
                self.last_error = str(e)[:50]

    async def _check_pumpdump(self, sym: str, price: float, hist: deque, now: datetime):
        window = timedelta(minutes=5)
        old_price = None
        for ts, p in reversed(hist):
            if now - ts <= window: old_price = p
            else: break
        if old_price is None or old_price == 0: return
        change = (price - old_price) / old_price * 100.0
        
        if abs(change) >= 1.5:
            self.recent_activity.append(f"{now.strftime('%H:%M:%S')} | {sym} | {change:+.2f}%")

        if abs(change) >= 5.0:
            direction = "PUMP" if change > 0 else "DUMP"
            last = self._last_alert.get(sym)
            if last and (now - last) < timedelta(minutes=10): return
            self._last_alert[sym] = now
            await self._fire_alert(sym, direction, change, price)

    async def _fire_alert(self, sym: str, direction: str, change: float, price: float):
        from db import DB_PATH, add_alert
        import aiosqlite
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT * FROM user_settings WHERE paused=0") as cur:
                    rows = await cur.fetchall()
            
            for row in rows:
                chat_id = row["chat_id"]
                if abs(change) < row["pump_threshold"]: continue
                
                # Фильтр по объему из настроек пользователя
                # (Для этого нужно было бы хранить vol_map, но пока используем общий фильтр монитора)
                
                tf = row["timeframe"]
                klines = await self.client.get_klines(sym, tf, limit=50)
                trades = await self.client.get_recent_trade(sym, limit=60)
                
                path = build_snapshot(sym, klines, trades, dict(row), {
                    "direction": direction, "change_percent": round(change, 2), "score": 7,
                })
                
                await add_alert(chat_id, sym, direction, round(change, 2), price, path)
                
                emoji = "🟢" if direction == "PUMP" else "🔴"
                caption = (
                    f"{emoji} <b>{direction} DETECTED!</b>\n\n"
                    f"Пара: <code>{sym}</code>\n"
                    f"Изменение: <b>{change:+.2f}%</b> (5m)\n"
                    f"Цена: <code>{price:,.2f}</code>\n"
                    f"Тема: <code>{row['theme'].upper()}</code>"
                )
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("📊 TV", url=f"https://www.tradingview.com/chart/?symbol=BYBIT%3A{sym}.P"),
                    InlineKeyboardButton("⚡ Bybit", url=f"https://www.bybit.com/trade/usdt/{sym}")
                ]])
                await self.bot.bot.send_photo(chat_id, open(path, "rb"), caption=caption, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            print(f"[Alert Error] {e}")

    async def _cleanup_loop(self):
        while self.running:
            await asyncio.sleep(3600)
            await cleanup_old_snapshots(days=1)

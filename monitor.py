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
        self.price_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=400))
        self.snap_sem = asyncio.Semaphore(MAX_CONCURRENT_SNAPS)
        self.running = True
        self._last_alert: dict[str, datetime] = {}
        self.alert_counts: dict[str, int] = {}
        
        # Статистика
        self.start_time = datetime.utcnow()
        self.last_update_time = None
        self.last_poll_time = None
        self.cycles_count = 0
        self.last_error = "Нет"
        self.recent_activity = deque(maxlen=8) 

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
            if not tickers: return
            
            vol_map = {t["symbol"]: float(t.get("turnover24h", 0)) for t in tickers}
            new_symbols = []
            for inst in instruments:
                sym = inst["symbol"]
                if inst.get("status") != "Trading": continue
                # Берем все ликвидные пары
                if vol_map.get(sym, 0) >= 50_000:
                    new_symbols.append(sym)
            
            new_symbols.sort(key=lambda s: vol_map.get(s, 0), reverse=True)
            self.symbols = new_symbols[:500]
            self.last_update_time = datetime.utcnow()
            print(f"[Monitor] Реестр обновлен: {len(self.symbols)} пар")
        except Exception as e:
            self.last_error = f"Update error: {str(e)[:30]}"

    async def _loop_update_symbols(self):
        while self.running:
            await asyncio.sleep(PAIRS_UPDATE_MIN * 60)
            await self._update_symbols()

    async def _loop_pumpdump(self):
        while self.running:
            await asyncio.sleep(2.0)
            if not self.symbols: continue
            try:
                tickers = await self.client.get_tickers()
                if not tickers: continue
                
                self.last_poll_time = datetime.utcnow()
                self.cycles_count += 1
                now = datetime.utcnow()
                
                for t in tickers:
                    sym = t["symbol"]
                    if sym not in self.symbols: continue
                    price = float(t.get("lastPrice", 0))
                    if price <= 0: continue
                    
                    hist = self.price_history[sym]
                    hist.append((now, price))
                    
                    # Проверяем изменение только если есть хотя бы 2 точки
                    if len(hist) > 1:
                        await self._check_pumpdump(sym, price, hist, now)
            except Exception as e:
                self.last_error = f"Poll error: {str(e)[:30]}"

    async def _check_pumpdump(self, sym: str, price: float, hist: deque, now: datetime):
        # Окно анализа - 5 минут
        window = timedelta(minutes=5)
        old_price = None
        
        for ts, p in reversed(hist):
            if now - ts >= timedelta(seconds=30): # Минимум 30 сек разницы для расчета
                old_price = p
                if now - ts >= window: break # Нашли край 5-минутного окна
        
        if old_price is None or old_price == 0: return
        
        change = (price - old_price) / old_price * 100.0
        
        # Консоль последних движений (>1.0%)
        if abs(change) >= 1.0:
            entry = f"🕒 {now.strftime('%H:%M')} | {sym} | {change:+.2f}%"
            if entry not in self.recent_activity:
                self.recent_activity.append(entry)

        # Порог алерта (Только PUMP)
        if change >= 5.0:
            last = self._last_alert.get(sym)
            if last and (now - last) < timedelta(minutes=10): return
            
            # Номер сигнала
            if last and (now - last) < timedelta(hours=1):
                self.alert_counts[sym] = self.alert_counts.get(sym, 0) + 1
            else:
                self.alert_counts[sym] = 1
            
            self._last_alert[sym] = now
            asyncio.create_task(self._fire_alert(sym, change, price, self.alert_counts[sym]))

    async def _fire_alert(self, sym: str, change: float, price: float, signal_num: int):
        from db import DB_PATH, add_alert, get_settings
        import aiosqlite
        try:
            direction = "PUMP"
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT * FROM user_settings WHERE paused=0") as cur:
                    rows = await cur.fetchall()
            
            for row in rows:
                if change < row["pump_threshold"]: continue
                
                settings = dict(row)
                klines = await self.client.get_klines(sym, settings["timeframe"], limit=60)
                path = build_snapshot(sym, klines, [], settings, {"change_percent": change})
                
                if not path: continue
                
                await add_alert(row["chat_id"], sym, direction, round(change, 2), price, path)
                
                emoji = "🟢"
                caption = (
                    f"{emoji} <b>{sym} {change:+.2f}% (№{signal_num})</b>\n\n"
                    f"💰 Цена: <code>{price:g}</code>\n"
                    f"🕒 ТФ: <code>{settings['timeframe']}m</code>"
                )
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("📊 TV", url=f"https://www.tradingview.com/chart/?symbol=BYBIT%3A{sym}.P"),
                    InlineKeyboardButton("⚡ Bybit", url=f"https://www.bybit.com/trade/usdt/{sym}")
                ]])
                await self.bot.bot.send_photo(row["chat_id"], open(path, "rb"), caption=caption, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            print(f"Fire alert error: {e}")

    async def _cleanup_loop(self):
        while self.running:
            await asyncio.sleep(3600)
            await cleanup_old_snapshots(days=1)

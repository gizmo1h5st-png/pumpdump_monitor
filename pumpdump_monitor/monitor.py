"""
Фоновый движок мониторинга:
1. Обновление списка пар каждые N мин (volume >= $100k)
2. Снапшоты раз в SNAP_INTERVAL_SEC (ограничение concurrency)
3. Poll тикеров каждые 1.5 сек — детект пампов/дампов
"""
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
        self._last_alert: dict[str, datetime] = {}  # дедупликация алертов по паре

    async def start(self):
        await self.client.start()
        await self._update_symbols()
        asyncio.create_task(self._loop_update_symbols())
        asyncio.create_task(self._loop_snapshots())
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
            new_symbols = []
            for inst in instruments:
                sym = inst["symbol"]
                if inst.get("status") != "Trading":
                    continue
                if vol_map.get(sym, 0) >= 100_000:
                    new_symbols.append(sym)
            new_symbols.sort(key=lambda s: vol_map.get(s, 0), reverse=True)
            self.symbols = new_symbols[:100]
            print(f"[Monitor] Список обновлён: {len(self.symbols)} пар")
        except Exception as e:
            print(f"[Monitor] Ошибка обновления списка: {e}")

    async def _loop_update_symbols(self):
        while self.running:
            await asyncio.sleep(PAIRS_UPDATE_MIN * 60)
            await self._update_symbols()

    async def _loop_snapshots(self):
        while self.running:
            await asyncio.sleep(SNAP_INTERVAL_SEC)
            if not self.symbols:
                continue
            targets = self.symbols[:30]
            tasks = [self._make_snapshot(sym) for sym in targets]
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _make_snapshot(self, symbol: str):
        async with self.snap_sem:
            try:
                settings = {
                    "timeframe": "5",
                    "zone_pct": 2.0,
                    "ob_mult": 1.5,
                    "fvg_enabled": 1,
                    "lot_threshold": 10.0,
                }
                klines = await self.client.get_klines(symbol, settings["timeframe"], limit=50)
                trades = await self.client.get_recent_trade(symbol, limit=60)
                path = build_snapshot(symbol, klines, trades, settings)
                if path:
                    await add_snapshot(symbol, settings["timeframe"], path)
            except Exception as e:
                print(f"[Snapshot] {symbol}: {e}")

    async def _loop_pumpdump(self):
        while self.running:
            await asyncio.sleep(1.5)
            if not self.symbols:
                continue
            try:
                tickers = await self.client.get_tickers()
                now = datetime.utcnow()
                for t in tickers:
                    sym = t["symbol"]
                    if sym not in self.symbols:
                        continue
                    price = float(t.get("lastPrice", 0))
                    if price <= 0:
                        continue
                    hist = self.price_history[sym]
                    hist.append((now, price))
                    await self._check_pumpdump(sym, price, hist, now)
            except Exception as e:
                print(f"[PumpDump] poll error: {e}")

    async def _check_pumpdump(self, sym: str, price: float, hist: deque, now: datetime):
        window = timedelta(minutes=5)
        old_price = None
        for ts, p in reversed(hist):
            if now - ts <= window:
                old_price = p
            else:
                break
        if old_price is None or old_price == 0:
            return
        change = (price - old_price) / old_price * 100.0
        if abs(change) >= 5.0:
            direction = "PUMP" if change > 0 else "DUMP"
            last = self._last_alert.get(sym)
            if last and (now - last) < timedelta(minutes=10):
                return  # дедупликация: не чаще раза в 10 мин
            self._last_alert[sym] = now
            await self._fire_alert(sym, direction, change, price)

    async def _fire_alert(self, sym: str, direction: str, change: float, price: float):
        from db import DB_PATH
        import aiosqlite
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT * FROM user_settings WHERE paused=0") as cur:
                    rows = await cur.fetchall()
        except Exception as e:
            print(f"[Alert] DB error: {e}")
            return

        for row in rows:
            chat_id = row["chat_id"]
            thr = float(row["pump_threshold"])
            if abs(change) < thr:
                continue
            tf = row["timeframe"]
            try:
                klines = await self.client.get_klines(sym, tf, limit=50)
                trades = await self.client.get_recent_trade(sym, limit=60)
                settings = dict(row)

                # Расчёт score и метрик для отображения
                fvg_zones = []  # упрощённо
                ob_zones = []
                vol_mult = 1.0
                score = min(abs(change) * 2, 10)  # базовый score до 10
                if abs(change) >= 10:
                    score = 10
                elif abs(change) >= 7:
                    score = 8
                elif abs(change) >= 5:
                    score = 6

                pumpdump_info = {
                    "direction": direction,
                    "change_percent": round(change, 2),
                    "score": int(score),
                    "fvg_count": len(fvg_zones),
                    "ob_count": len(ob_zones),
                    "vol_mult": round(vol_mult, 1),
                }

                path = build_snapshot(sym, klines, trades, settings, pumpdump_info)
                await add_alert(chat_id, sym, direction, round(change, 2), price, path)

                # Формируем красивое сообщение с HTML
                emoji = "🟢" if direction == "PUMP" else "🔴"
                trend_emoji = "📈" if direction == "PUMP" else "📉"

                caption = (
                    f"{emoji} <b>{direction}</b> <code>{sym}</code>\n\n"
                    f"{trend_emoji} Изменение: <b>{change:+.2f}%</b>\n"
                    f"💰 Цена: <code>{price:,.2f}</code>\n"
                    f"⏰ Время: <code>{datetime.utcnow().strftime('%H:%M:%S UTC')}</code>\n\n"
                    f"🎯 Score: <b>{int(score)}/10</b>\n"
                    f"📊 FVG: {len(fvg_zones)} | OB: {len(ob_zones)} | VOL: {vol_mult:.1f}x\n"
                    f"⚡ Таймфрейм: {tf}m"
                )

                # Кнопки
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("📊 TradingView", url=f"https://www.tradingview.com/chart/?symbol=BYBIT%3A{sym}.P"),
                        InlineKeyboardButton("⚡ Bybit", url=f"https://www.bybit.com/trade/usdt/{sym}")
                    ]
                ])

                await self.bot.bot.send_photo(
                    chat_id=chat_id,
                    photo=open(path, "rb"),
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
            except Exception as e:
                print(f"[Alert] {sym} -> {chat_id}: {e}")

    async def _cleanup_loop(self):
        while self.running:
            await asyncio.sleep(3600)
            try:
                await cleanup_old_snapshots(days=1)
            except Exception as e:
                print(f"[Cleanup] {e}")

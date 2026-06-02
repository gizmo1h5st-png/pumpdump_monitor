"""
Telegram handlers (python-telegram-bot v20+)
"""
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes
from db import get_settings, get_alerts
from monitor import Monitor
from chart_builder import build_snapshot
from bybit_client import BybitClient

MONITOR: Monitor | None = None

def set_monitor(m: Monitor):
    global MONITOR
    MONITOR = m

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await get_settings(chat_id)  # создаст дефолт если нет
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Открыть монитор", url=f"https://t.me/{context.bot.username}/pumpdump")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton("📊 Алерты", callback_data="alerts")],
    ])
    await update.message.reply_text(
        "Привет! <b>Pump & Dump Monitor</b> следит за Bybit perpetuals.\n"
        "Нажми кнопку ниже, чтобы открыть Mini App.",
        reply_markup=kb, parse_mode="HTML"
    )

async def alerts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    rows = await get_alerts(chat_id, limit=5)
    if not rows:
        await update.message.reply_text("Алертов пока нет.")
        return
    for r in rows:
        emoji = "🟢" if r['direction'] == "PUMP" else "🔴"
        caption = (
            f"{emoji} <b>{r['direction']}</b> <code>{r['symbol']}</code>\n"
            f"📈 {r['change_percent']:+.2f}% @ <code>{r['price']:,.2f}</code>\n"
            f"⏰ {r['timestamp'][:16]}"
        )
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📊 TradingView", url=f"https://www.tradingview.com/chart/?symbol=BYBIT%3A{r['symbol']}.P"),
                InlineKeyboardButton("⚡ Bybit", url=f"https://www.bybit.com/trade/usdt/{r['symbol']}")
            ]
        ])
        if r["screenshot_path"] and os.path.exists(r["screenshot_path"]):
            await context.bot.send_photo(chat_id, photo=open(r["screenshot_path"], "rb"), caption=caption, parse_mode="HTML", reply_markup=keyboard)
        else:
            await update.message.reply_text(caption, parse_mode="HTML", reply_markup=keyboard)

async def snapshot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args
    if not args:
        await update.message.reply_text("Укажи символ: /snapshot BTCUSDT")
        return
    sym = args[0].upper()
    settings = await get_settings(chat_id)
    client = BybitClient()
    await client.start()
    try:
        klines = await client.get_klines(sym, settings["timeframe"], limit=50)
        trades = await client.get_recent_trade(sym, limit=60)
        path = build_snapshot(sym, klines, trades, settings)
        if path:
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📊 TradingView", url=f"https://www.tradingview.com/chart/?symbol=BYBIT%3A{sym}.P"),
                    InlineKeyboardButton("⚡ Bybit", url=f"https://www.bybit.com/trade/usdt/{sym}")
                ]
            ])
            await context.bot.send_photo(chat_id, photo=open(path, "rb"), caption=f"📸 Снапшот <code>{sym}</code>", parse_mode="HTML", reply_markup=keyboard)
        else:
            await update.message.reply_text("Недостаточно данных для графика.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")
    finally:
        await client.close()

async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Порог 5%", callback_data="set_thr_5"), InlineKeyboardButton("Порог 10%", callback_data="set_thr_10")],
        [InlineKeyboardButton("Таймфрейм 1m", callback_data="tf_1"), InlineKeyboardButton("5m", callback_data="tf_5"), InlineKeyboardButton("15m", callback_data="tf_15")],
        [InlineKeyboardButton("⏸ Пауза/Старт", callback_data="toggle_pause")],
    ])
    await query.edit_message_text("⚙️ Настройки:", reply_markup=kb)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from db import save_settings
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    data = query.data
    if data == "settings":
        return await settings_callback(update, context)
    if data == "alerts":
        return await alerts_cmd(update, context)
    if data.startswith("set_thr_"):
        thr = float(data.split("_")[-1])
        await save_settings(chat_id, {"pump_threshold": thr})
        await query.edit_message_text(f"Порог установлен: {thr}%")
    elif data.startswith("tf_"):
        tf = data.split("_")[-1]
        await save_settings(chat_id, {"timeframe": tf})
        await query.edit_message_text(f"Таймфрейм: {tf}m")
    elif data == "toggle_pause":
        s = await get_settings(chat_id)
        new_paused = 0 if s["paused"] else 1
        await save_settings(chat_id, {"paused": new_paused})
        status = "⏸ Пауза" if new_paused else "▶️ Работа"
        await query.edit_message_text(status)

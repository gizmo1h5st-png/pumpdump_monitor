"""
Telegram handlers (python-telegram-bot v20+)
"""
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from db import get_settings, get_alerts
from monitor import Monitor
from chart_builder import build_snapshot
from bybit_client import BybitClient

MONITOR: Monitor | None = None

def set_monitor(m: Monitor):
    global MONITOR
    MONITOR = m

def get_main_menu_keyboard():
    """Главное меню без Mini App"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton("📊 Последние алерты", callback_data="alerts")],
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await get_settings(chat_id)
    
    text = (
        "🤖 <b>Pump & Dump Monitor запущен.</b>\n"
        "Я слежу за рынком Bybit 24/7 и пришлю сигнал, как только замечу памп или дамп."
    )
    
    if update.message:
        await update.message.reply_text(text, reply_markup=get_main_menu_keyboard(), parse_mode="HTML")
    else:
        await update.callback_query.edit_message_text(text, reply_markup=get_main_menu_keyboard(), parse_mode="HTML")

async def alerts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    query = update.callback_query
    
    rows = await get_alerts(chat_id, limit=5)
    back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]])
    
    if not rows:
        if query:
            await query.edit_message_text("Алертов пока нет.", reply_markup=back_kb)
        else:
            await update.message.reply_text("Алертов пока нет.", reply_markup=back_kb)
        return

    if query:
        await query.message.delete()

    for r in rows:
        emoji = "🟢" if r['direction'] == "PUMP" else "🔴"
        caption = (
            f"{emoji} <b>{r['direction']}</b> <code>{r['symbol']}</code>\n"
            f"📈 {r['change_percent']:+.2f}% @ <code>{r['price']:,.2f}</code>\n"
            f"⏰ {r['timestamp'][:16]}"
        )
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📊 TV", url=f"https://www.tradingview.com/chart/?symbol=BYBIT%3A{r['symbol']}.P"),
                InlineKeyboardButton("⚡ Bybit", url=f"https://www.bybit.com/trade/usdt/{r['symbol']}")
            ]
        ])
        
        if r["screenshot_path"] and os.path.exists(r["screenshot_path"]):
            await context.bot.send_photo(chat_id, photo=open(r["screenshot_path"], "rb"), caption=caption, parse_mode="HTML", reply_markup=keyboard)
        else:
            await context.bot.send_message(chat_id, text=caption, parse_mode="HTML", reply_markup=keyboard)
    
    await context.bot.send_message(chat_id, "Выше последние 5 алертов.", reply_markup=back_kb)

async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Порог 5%", callback_data="set_thr_5"), InlineKeyboardButton("Порог 10%", callback_data="set_thr_10")],
        [InlineKeyboardButton("Таймфрейм 1m", callback_data="tf_1"), InlineKeyboardButton("5m", callback_data="tf_5"), InlineKeyboardButton("15m", callback_data="tf_15")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")],
    ])
    await query.edit_message_text("⚙️ Настройки мониторинга:", reply_markup=kb)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from db import save_settings
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    data = query.data

    if data == "main_menu":
        return await start(update, context)
    if data == "settings":
        return await settings_callback(update, context)
    if data == "alerts":
        return await alerts_cmd(update, context)

    if data.startswith("set_thr_"):
        thr = float(data.split("_")[-1])
        await save_settings(chat_id, {"pump_threshold": thr})
        await query.edit_message_text(f"✅ Порог установлен: {thr}%", reply_markup=get_main_menu_keyboard())
    elif data.startswith("tf_"):
        tf = data.split("_")[-1]
        await save_settings(chat_id, {"timeframe": tf})
        await query.edit_message_text(f"✅ Таймфрейм: {tf}m", reply_markup=get_main_menu_keyboard())

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
                    InlineKeyboardButton("📊 TV", url=f"https://www.tradingview.com/chart/?symbol=BYBIT%3A{sym}.P"),
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

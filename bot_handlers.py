import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from db import get_settings, get_alerts, save_settings
from monitor import Monitor

MONITOR: Monitor | None = None

def set_monitor(m: Monitor):
    global MONITOR
    MONITOR = m

def get_main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ Статус и Настройки", callback_data="settings")],
        [InlineKeyboardButton("📊 Последние алерты", callback_data="alerts")],
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await get_settings(chat_id)
    text = "🤖 <b>Pump & Dump Monitor</b>\nСистема активна. Слежу за рынком..."
    if update.message:
        await update.message.reply_text(text, reply_markup=get_main_menu_keyboard(), parse_mode="HTML")
    else:
        await update.callback_query.edit_message_text(text, reply_markup=get_main_menu_keyboard(), parse_mode="HTML")

async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    s = await get_settings(chat_id)
    
    uptime = str(datetime.utcnow() - MONITOR.start_time).split(".")[0]
    last_upd = MONITOR.last_update_time.strftime("%H:%M:%S") if MONITOR.last_update_time else "Н/Д"
    activity_log = "\n".join(MONITOR.recent_activity) if MONITOR.recent_activity else "Активности пока нет"
    
    status_text = (
        f"🖥 <b>СТАТУС:</b> 🟢 OK | <b>Uptime:</b> <code>{uptime}</code>\n"
        f"┣ Пар: <b>{len(MONITOR.symbols)}</b> | ТФ: <b>{s['timeframe']}m</b>\n"
        f"┗ Обновление: <code>{last_upd} UTC</code>\n\n"
        f"📝 <b>ПОСЛЕДНИЕ ДВИЖЕНИЯ (>1.5%):</b>\n"
        f"<code>{activity_log}</code>\n\n"
        f"⚙️ <b>ПАРАМЕТРЫ:</b>\n"
        f"┣ Порог: <b>{s['pump_threshold']}%</b> | Увед: <b>{'⏸ OFF' if s['paused'] else '🔔 ON'}</b>\n"
        f"┣ Тема: <b>{s['theme'].upper()}</b>\n"
        f"┗ Индикаторы: <b>{'📈' if s['show_delta'] else '⬜'}Delta {'📈' if s['show_oi'] else '⬜'}OI {'📈' if s['show_liq'] else '⬜'}Liq</b>\n"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📈 Порог: 5%", callback_data="set_thr_5"), InlineKeyboardButton("📈 Порог: 10%", callback_data="set_thr_10")],
        [InlineKeyboardButton("🕒 1m", callback_data="tf_1"), InlineKeyboardButton("🕒 5m", callback_data="tf_5"), InlineKeyboardButton("🕒 15m", callback_data="tf_15")],
        [InlineKeyboardButton("🎨 Тема: DARK", callback_data="set_theme_dark"), InlineKeyboardButton("🎨 Тема: LIGHT", callback_data="set_theme_light")],
        [InlineKeyboardButton("📊 Настройка панелей", callback_data="indicator_settings")],
        [InlineKeyboardButton("🛠 Фильтры объема", callback_data="expert_settings")],
        [InlineKeyboardButton("⏸ Пауза / Старт", callback_data="toggle_pause")],
        [InlineKeyboardButton("🔄 Обновить статус", callback_data="settings")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")],
    ])
    await query.edit_message_text(status_text, reply_markup=kb, parse_mode="HTML")

async def indicator_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    s = await get_settings(chat_id)
    text = "📊 <b>НАСТРОЙКА ПАНЕЛЕЙ:</b>"
    def btn_txt(label, val): return f"{'✅' if val else '❌'} {label}"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(btn_txt("Delta Volume", s['show_delta']), callback_data="toggle_ind_delta")],
        [InlineKeyboardButton(btn_txt("Open Interest", s['show_oi']), callback_data="toggle_ind_oi")],
        [InlineKeyboardButton(btn_txt("Liquidations", s['show_liq']), callback_data="toggle_ind_liq")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="settings")],
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")

async def expert_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    s = await get_settings(chat_id)
    text = (
        f"🛠 <b>ФИЛЬТРЫ ОБЪЕМА:</b>\n\n"
        f"┣ Мин. объем (24ч): <b>${s['volume_min_usd']:,.0f}</b>\n"
        f"┗ <i>Бот игнорирует монеты с объемом ниже этого порога.</i>"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 100k", callback_data="set_vol_100000"), InlineKeyboardButton("💰 1M", callback_data="set_vol_1000000")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="settings")],
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")

async def alerts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    query = update.callback_query
    rows = await get_alerts(chat_id, limit=5)
    back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]])
    if not rows:
        text = "Алертов пока нет."
        if query: await query.edit_message_text(text, reply_markup=back_kb)
        else: await update.message.reply_text(text, reply_markup=back_kb)
        return
    if query: await query.message.delete()
    for r in rows:
        emoji = "🟢" if r['direction'] == "PUMP" else "🔴"
        caption = f"{emoji} <b>{r['direction']}</b> <code>{r['symbol']}</code>\n📈 {r['change_percent']:+.2f}% @ <code>{r['price']:,.2f}</code>"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📊 TV", url=f"https://www.tradingview.com/chart/?symbol=BYBIT%3A{r['symbol']}.P")]])
        if r["screenshot_path"] and os.path.exists(r["screenshot_path"]):
            await context.bot.send_photo(chat_id, photo=open(r["screenshot_path"], "rb"), caption=caption, parse_mode="HTML", reply_markup=kb)
    await context.bot.send_message(chat_id, "Выше последние 5 алертов.", reply_markup=back_kb)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = update.effective_chat.id

    if data == "main_menu": return await start(update, context)
    if data == "settings": return await settings_callback(update, context)
    if data == "expert_settings": return await expert_settings_callback(update, context)
    if data == "indicator_settings": return await indicator_settings_callback(update, context)
    if data == "alerts": return await alerts_cmd(update, context)
    
    if data.startswith("set_thr_"):
        await save_settings(chat_id, {"pump_threshold": float(data.split("_")[-1])})
        return await settings_callback(update, context)
    elif data.startswith("tf_"):
        await save_settings(chat_id, {"timeframe": data.split("_")[-1]})
        return await settings_callback(update, context)
    elif data.startswith("set_theme_"):
        await save_settings(chat_id, {"theme": data.split("_")[-1]})
        return await settings_callback(update, context)
    elif data.startswith("toggle_ind_"):
        ind = data.split("_")[-1]
        s = await get_settings(chat_id)
        field = f"show_{ind}"
        await save_settings(chat_id, {field: 0 if s[field] else 1})
        return await indicator_settings_callback(update, context)
    elif data.startswith("set_vol_"):
        await save_settings(chat_id, {"volume_min_usd": float(data.split("_")[-1])})
        return await expert_settings_callback(update, context)
    elif data == "toggle_pause":
        s = await get_settings(chat_id)
        await save_settings(chat_id, {"paused": 0 if s["paused"] else 1})
        return await settings_callback(update, context)

async def test_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text("⏳ Генерирую тестовый алерт...")
    from bybit_client import BybitClient
    from chart_builder import build_snapshot
    client = BybitClient()
    await client.start()
    try:
        sym = "BTCUSDT"
        settings = await get_settings(chat_id)
        klines = await client.get_klines(sym, settings["timeframe"], limit=50)
        trades = await client.get_recent_trade(sym, limit=60)
        pump_info = {"direction": "PUMP", "change_percent": 2.50, "score": 8}
        path = build_snapshot(sym, klines, trades, settings, pump_info)
        if path:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("📊 TV", url=f"https://www.tradingview.com/chart/?symbol=BYBIT%3A{sym}.P")]])
            await context.bot.send_photo(chat_id, open(path, "rb"), caption=f"🧪 <b>ТЕСТОВЫЙ АЛЕРТ</b>", parse_mode="HTML", reply_markup=kb)
    except Exception as e: await update.message.reply_text(f"❌ Ошибка: {e}")
    finally: await client.close()

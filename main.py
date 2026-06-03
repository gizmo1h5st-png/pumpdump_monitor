"""
Точка входа:
- Инициализация БД
- Запуск Monitor (asyncio background tasks)
- Запуск python-telegram-bot polling
"""
import asyncio
import logging

from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from config import BOT_TOKEN
from db import init_db
from monitor import Monitor
from bot_handlers import start, alerts_cmd, button_callback, set_monitor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("main")

async def main():
    logger.info("Инициализация БД...")
    await init_db()

    logger.info("Запуск Telegram бота...")
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрация команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("alerts", alerts_cmd))
    application.add_handler(CallbackQueryHandler(button_callback))

    # Монитор
    monitor = Monitor(application)
    set_monitor(monitor)
    await monitor.start()

    # PTB polling
    await application.initialize()
    await application.start()
    logger.info("Бот работает. Нажмите Ctrl+C для остановки.")
    await application.updater.start_polling(drop_pending_updates=True)

    # Бесконечный sleep пока не придёт сигнал
    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    finally:
        await monitor.stop()
        await application.stop()
        await application.shutdown()

if __name__ == "__main__":
    asyncio.run(main())

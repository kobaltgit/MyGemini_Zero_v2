"""
MyGemini Zero v2 - Application Main Entry Point.
Initializes structured logging, async SQLite database, registers aiogram 3.x routers and middlewares,
and launches long-polling with graceful shutdown.
"""

import asyncio
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from core.config import settings
from core.logger import setup_logging, get_logger
from core.database import init_db, engine
from handlers import register_all_routers
from middlewares.auth import AuthMiddleware
from middlewares.antispam import KeyLeakAndAntispamMiddleware

logger = get_logger("bot_general")


async def main() -> None:
    """Configures and runs the Telegram bot."""
    setup_logging()
    logger.info("Starting MyGemini Zero v2...")

    if not settings.BOT_TOKEN:
        logger.error("BOT_TOKEN is not configured! Please provide it in .env file.")
        print("ОШИБКА: BOT_TOKEN не установлен в файле .env!")
        return

    # Initialize database and tables
    logger.info("Initializing database...")
    await init_db()

    # Initialize bot and dispatcher
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=None),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Register Middlewares
    dp.message.middleware(KeyLeakAndAntispamMiddleware())
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    # Register all Routers
    register_all_routers(dp)
    logger.info("All handlers and middlewares registered successfully.")

    # Drop any pending updates and start polling
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        bot_info = await bot.get_me()
        logger.info(f"Bot @{bot_info.username} (ID: {bot_info.id}) started polling.")
        print(f"=== MyGemini Zero v2 запущен (@{bot_info.username}) ===")
        await dp.start_polling(bot)
    except Exception as e:
        logger.critical(f"Fatal error during bot execution: {e}", exc_info=True)
    finally:
        await bot.session.close()
        await engine.dispose()
        logger.info("MyGemini Zero v2 stopped cleanly.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Application interrupted by user.")
        sys.exit(0)

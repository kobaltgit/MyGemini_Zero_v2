"""
MyGemini Zero v2 - Application Main Entry Point.
Initializes structured logging, async SQLite database, registers aiogram 3.x routers and middlewares,
sets up Russian bot command menu in Telegram, and launches long-polling with graceful shutdown.
"""

import asyncio
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeDefault

from core.config import settings
from core.logger import setup_logging, get_logger
from core.database import init_db, engine
from handlers import register_all_routers
from middlewares.auth import AuthMiddleware
from middlewares.antispam import KeyLeakAndAntispamMiddleware
from middlewares.logging import CallbackLoggingMiddleware

logger = get_logger("bot_general")


async def setup_bot_commands(bot: Bot) -> None:
    """Registers Russian command descriptions in Telegram's blue [Menu] button."""
    commands = [
        BotCommand(command="start", description="Перезапустить бота и показать меню"),
        BotCommand(command="profile", description="👤 Личный кабинет (звание, анкета, подписка)"),
        BotCommand(command="dialogs", description="🗂️ Список диалогов"),
        BotCommand(command="new_dialog", description="➕ Создать новый диалог"),
        BotCommand(command="rename", description="✏️ Переименовать текущий диалог"),
        BotCommand(command="settings", description="⚙️ Настройки моделей, персон и ключа"),
        BotCommand(command="documents", description="📄 Документы в памяти диалога (RAG)"),
        BotCommand(command="history", description="📅 История сообщений по датам"),
        BotCommand(command="guide", description="📚 Интерактивное руководство пользователя"),
        BotCommand(command="translate", description="🌐 Быстрый переводчик"),
        BotCommand(command="feedback", description="✉️ Обратная связь / поддержка"),
        BotCommand(command="memorize", description="📎 Инструкция по отправке документов"),
        BotCommand(command="reset", description="🔄 Сброс контекста диалога"),
        BotCommand(command="help", description="❓ Справка по всем возможностям"),
        BotCommand(command="logout", description="🔒 Заблокировать сейф в памяти"),
        BotCommand(command="cancel", description="❌ Отменить текущее действие"),
        BotCommand(command="panic", description="🚨 Информация о паник-пароле"),
    ]
    try:
        await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
        logger.info("Bot commands successfully registered with Telegram.")
    except Exception as e:
        logger.warning(f"Could not register bot commands: {e}")


async def main() -> None:
    """Configures and runs the Telegram bot."""
    setup_logging()
    logger.info("Starting MyGemini Zero v2...")

    # Preload user guide markdown files
    try:
        from services.guide_manager import load_guides
        load_guides()
    except Exception as e:
        logger.warning(f"Could not preload guides: {e}")

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
    dp.callback_query.outer_middleware(CallbackLoggingMiddleware())
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

        # Register Telegram Commands
        await setup_bot_commands(bot)

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

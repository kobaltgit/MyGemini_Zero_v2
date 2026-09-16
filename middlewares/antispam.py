"""
Antispam and Key Leak Prevention Middleware for MyGemini Zero v2.
Immediately deletes messages containing plain-text Google API keys to prevent leaks.
"""

import re
import asyncio
from typing import Dict, Any, Callable, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
from core.logger import get_logger

logger = get_logger("user_messages")

# Pattern detecting typical Google AI Studio API keys: AIzaSy...
API_KEY_PATTERN = re.compile(r"\bAIzaSy[A-Za-z0-9_-]{33,}\b")


class KeyLeakAndAntispamMiddleware(BaseMiddleware):
    """
    Scans incoming text for plain Google API keys.
    If detected, instantly purges the message within 0.25s and alerts the user.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.text:
            text = event.text.strip()
            # Fast check: does it look like a raw Google API key?
            if text.startswith("AIzaSy") and len(text) >= 35 or API_KEY_PATTERN.search(text):
                try:
                    await asyncio.sleep(0.25)
                    await event.delete()
                except Exception as e:
                    logger.warning(f"Failed to delete leaked key message: {e}")

                await event.answer(
                    "⚠️ <b>Внимание! Безопасность превыше всего.</b>\n\n"
                    "Обнаружена попытка отправки открытого API-ключа Google в текст чата. "
                    "Сообщение было немедленно удалено, чтобы ключ не остался в истории переписки.\n\n"
                    "Пожалуйста, вводите ключ через защищённое всплывающее окно в разделе <b>⚙️ Настройки -> 🔑 Установить API-ключ</b>.",
                    parse_mode="HTML",
                )
                return

        return await handler(event, data)

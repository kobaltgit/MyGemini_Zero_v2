"""
Button and Callback Logging Middleware for MyGemini Zero v2.
Logs every inline button click with user context, execution time, and error details.
Ensures button spinners on mobile devices are safely dismissed even on handler exceptions.
"""

import time
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, CallbackQuery
from core.logger import get_logger

logger = get_logger("user_messages")


class CallbackLoggingMiddleware(BaseMiddleware):
    """
    Middleware that captures and logs all Telegram inline button callbacks.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, CallbackQuery):
            return await handler(event, data)

        user = event.from_user
        user_info = f"{user.id} (@{user.username})" if user.username else str(user.id)
        callback_data = event.data or "<empty>"
        msg_id = event.message.message_id if event.message else "unknown"

        logger.info(f"🔘 [Button Click] User: {user_info} | Data: '{callback_data}' | MsgID: {msg_id}")
        start_time = time.monotonic()

        try:
            result = await handler(event, data)
            duration_ms = round((time.monotonic() - start_time) * 1000, 1)
            logger.info(f"✅ [Button Done] User: {user_info} | Data: '{callback_data}' | Duration: {duration_ms}ms")
            # Dismiss spinner if handler didn't call answer()
            try:
                await event.answer()
            except Exception:
                pass
            return result
        except Exception as e:
            duration_ms = round((time.monotonic() - start_time) * 1000, 1)
            logger.error(
                f"❌ [Button Error] User: {user_info} | Data: '{callback_data}' | Duration: {duration_ms}ms | Error: {e}",
                exc_info=True,
            )
            # Quietly dismiss spinner on mobile without sending any message or modal popup
            try:
                await event.answer()
            except Exception:
                pass
            raise e

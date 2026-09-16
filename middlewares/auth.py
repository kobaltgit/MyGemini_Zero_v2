"""
Authentication and Session Lifetime Middleware for MyGemini Zero v2.
Enforces Zero-Knowledge memory lifecycle:
- In-memory Fernet session keys with automatic 1-hour inactivity timeout lock
- User blocking checks
- Maintenance mode gates
"""

import time
from typing import Dict, Any, Callable, Awaitable, Optional
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from cryptography.fernet import Fernet

from core.config import settings
from core.database import async_session_maker
from database.repositories import UserRepository, SettingsRepository
from core.logger import get_logger

logger = get_logger("user_messages")


class SessionManager:
    """Manages active ephemeral Zero-Knowledge decryption keys in RAM."""

    def __init__(self):
        # user_id -> Fernet instance
        self._active_sessions: Dict[int, Fernet] = {}
        # user_id -> last activity epoch seconds
        self._last_activity: Dict[int, float] = {}

    def unlock_session(self, user_id: int, fernet: Fernet) -> None:
        """Stores cipher instance in memory and updates activity timestamp."""
        self._active_sessions[user_id] = fernet
        self._last_activity[user_id] = time.monotonic()
        logger.info(f"Session unlocked for user {user_id}", extra={"user_id": user_id})

    def lock_session(self, user_id: int) -> None:
        """Purges active cipher from RAM."""
        self._active_sessions.pop(user_id, None)
        self._last_activity.pop(user_id, None)
        logger.info(f"Session locked for user {user_id}", extra={"user_id": user_id})

    def touch_session(self, user_id: int) -> None:
        """Refreshes inactivity timer."""
        if user_id in self._active_sessions:
            self._last_activity[user_id] = time.monotonic()

    def get_fernet(self, user_id: int) -> Optional[Fernet]:
        """
        Retrieves active cipher if within timeout window; otherwise locks and returns None.
        """
        if user_id not in self._active_sessions:
            return None

        last_active = self._last_activity.get(user_id, 0)
        elapsed = time.monotonic() - last_active

        if elapsed > settings.SESSION_TIMEOUT_SECONDS:
            logger.info(f"Session timed out for user {user_id} ({elapsed:.0f}s). Locking vault.", extra={"user_id": user_id})
            self.lock_session(user_id)
            return None

        self.touch_session(user_id)
        return self._active_sessions.get(user_id)

    def is_unlocked(self, user_id: int) -> bool:
        return self.get_fernet(user_id) is not None


# Global session manager instance
session_manager = SessionManager()


class AuthMiddleware(BaseMiddleware):
    """
    Validates user blocking, checks maintenance mode, and injects session data.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user_id = None
        if isinstance(event, (Message, CallbackQuery)) and event.from_user:
            user_id = event.from_user.id

        if not user_id:
            return await handler(event, data)

        async with async_session_maker() as session:
            user_repo = UserRepository(session)
            settings_repo = SettingsRepository(session)
            user = await user_repo.get_by_id(user_id)

            lang_code = "ru"
            if user and user.language_code:
                lang_code = user.language_code
            elif event.from_user and event.from_user.language_code:
                lang_code = "ru" if event.from_user.language_code.startswith("ru") else "en"

            # Check maintenance mode
            is_maintenance = await settings_repo.is_maintenance_mode()
            is_admin = user_id == settings.ADMIN_USER_ID

            if is_maintenance and not is_admin:
                maintenance_text = (
                    "🛠 Бот временно находится на техническом обслуживании. Пожалуйста, попробуйте позже."
                    if lang_code == "ru"
                    else "🛠 The bot is temporarily under maintenance. Please try again later."
                )
                if isinstance(event, Message):
                    await event.answer(maintenance_text)
                elif isinstance(event, CallbackQuery):
                    await event.answer(maintenance_text, show_alert=True)
                return

            # Check user blocked
            if user and user.is_blocked:
                blocked_text = (
                    "⛔️ Ваш аккаунт заблокирован администратором."
                    if lang_code == "ru"
                    else "⛔️ Your account has been blocked by an administrator."
                )
                if isinstance(event, Message):
                    await event.answer(blocked_text)
                elif isinstance(event, CallbackQuery):
                    await event.answer(blocked_text, show_alert=True)
                return

            # Inject session & repositories into handler data
            fernet = session_manager.get_fernet(user_id)
            data["fernet"] = fernet
            data["session_manager"] = session_manager
            data["db_user"] = user
            data["lang_code"] = lang_code

        return await handler(event, data)


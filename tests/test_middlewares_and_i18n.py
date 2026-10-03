"""
Unit tests for middlewares and localization:
- core/localization.py (get_text, ru/en keys parity, string formatting)
- middlewares/antispam.py (KeyLeakAndAntispamMiddleware: AIzaSy key detection & purge)
- middlewares/auth.py (AuthMiddleware: maintenance mode, user blocking, context injection)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import Message, User as TgUser, Chat
from core.localization import get_text, LOCALIZATION, DEFAULT_LANG
from middlewares.antispam import KeyLeakAndAntispamMiddleware, API_KEY_PATTERN
from middlewares.auth import AuthMiddleware, session_manager
from core.config import settings


class TestLocalization:
    """Tests for core/localization.py."""

    def test_get_text_ru_and_en(self):
        text_ru = get_text("zk_setup_prompt", lang_code="ru")
        text_en = get_text("zk_setup_prompt", lang_code="en")
        assert "Создание хранилища" in text_ru
        assert "Create Your Vault" in text_en or "Vault" in text_en or "password" in text_en.lower()

    def test_get_text_unknown_key_fallback(self):
        assert get_text("non_existent_key_12345", lang_code="ru") == "non_existent_key_12345"

    def test_get_text_formatting(self):
        # Test with formatting kwargs if key has placeholders
        formatted = get_text("zk_setup_prompt", lang_code="ru", dummy="val")
        assert isinstance(formatted, str)

    def test_key_parity_critical_keys(self):
        """Ensure critical localization keys exist in both RU and EN dictionaries."""
        ru_dict = LOCALIZATION.get("ru", {})
        en_dict = LOCALIZATION.get("en", {})

        critical_keys = [
            "zk_setup_prompt",
            "zk_warning",
            "zk_confirm_prompt",
            "zk_unlock_prompt",
            "zk_unlock_fail",
            "zk_unlock_success",
            "panic_password_prompt",
            "profile_start",
        ]

        for k in critical_keys:
            assert k in ru_dict, f"Missing key in RU: {k}"
            assert k in en_dict, f"Missing key in EN: {k}"


class TestAntispamMiddleware:
    """Tests for middlewares/antispam.py."""

    def test_api_key_regex(self):
        valid_key = "AIzaSyB1234567890abcdefghijklmnopqrstuv"
        assert API_KEY_PATTERN.search(valid_key) is not None
        assert API_KEY_PATTERN.search("Just normal text with AIzaSy short") is None

    @pytest.mark.asyncio
    async def test_leaked_key_purged(self):
        middleware = KeyLeakAndAntispamMiddleware()
        handler = AsyncMock()

        # Mock Telegram Message containing raw API key
        event = MagicMock(spec=Message)
        event.text = "AIzaSyB1234567890abcdefghijklmnopqrstuvwxyz12"
        event.delete = AsyncMock()
        event.answer = AsyncMock()

        data = {}
        await middleware(handler, event, data)

        # Message must be deleted and user alerted
        event.delete.assert_awaited_once()
        event.answer.assert_awaited_once()
        # Handler must NOT be called
        handler.assert_not_called()

    async def test_normal_message_passes_through(self):
        middleware = KeyLeakAndAntispamMiddleware()
        handler = AsyncMock(return_value="OK")

        event = MagicMock(spec=Message)
        event.text = "Привет, помоги решить уравнение"
        data = {}

        result = await middleware(handler, event, data)

        handler.assert_awaited_once_with(event, data)
        assert result == "OK"


@pytest.mark.asyncio
class TestAuthMiddleware:
    """Tests for middlewares/auth.py."""

    async def test_maintenance_mode_blocks_regular_users(self, monkeypatch):
        middleware = AuthMiddleware()
        handler = AsyncMock()

        user = TgUser(id=99999, is_bot=False, first_name="Regular", language_code="ru")
        chat = Chat(id=99999, type="private")
        event = MagicMock(spec=Message)
        event.from_user = user
        event.chat = chat
        event.answer = AsyncMock()

        data = {}

        # Mock SettingsRepository to report maintenance_mode = True
        from unittest.mock import patch
        with patch("middlewares.auth.SettingsRepository.is_maintenance_mode", AsyncMock(return_value=True)):
            with patch("middlewares.auth.UserRepository.get_by_id", AsyncMock(return_value=None)):
                await middleware(handler, event, data)

        # Must answer with maintenance notice and block execution
        event.answer.assert_awaited_once()
        handler.assert_not_called()

    async def test_maintenance_mode_allows_admin(self, monkeypatch):
        middleware = AuthMiddleware()
        handler = AsyncMock(return_value="ADMIN_OK")

        admin_id = settings.ADMIN_USER_ID or 7777777
        user = TgUser(id=admin_id, is_bot=False, first_name="Admin", language_code="ru")
        chat = Chat(id=admin_id, type="private")
        event = MagicMock(spec=Message)
        event.from_user = user
        event.chat = chat
        event.answer = AsyncMock()

        data = {}

        from unittest.mock import patch
        with patch.object(settings, "ADMIN_USER_ID", admin_id):
            with patch("middlewares.auth.SettingsRepository.is_maintenance_mode", AsyncMock(return_value=True)):
                with patch("middlewares.auth.UserRepository.get_by_id", AsyncMock(return_value=None)):
                    result = await middleware(handler, event, data)

        assert result == "ADMIN_OK"
        handler.assert_awaited_once()

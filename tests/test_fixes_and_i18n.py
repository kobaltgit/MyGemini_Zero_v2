"""
Verification test suite for bilingualism (i18n), UI helpers, calendar, guide,
error parser, and navigation fixes in MyGemini Zero v2.
"""

import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from aiogram.exceptions import TelegramBadRequest

from core.localization import get_text, LOCALIZATION
from core.ui_helpers import safe_edit_message_text, safe_answer_callback
from keyboards.inline import (
    get_main_menu_keyboard,
    get_settings_keyboard,
    get_language_keyboard,
    get_admin_keyboard,
    get_admin_user_actions_keyboard,
    get_admin_extend_sub_keyboard,
    get_cancel_keyboard,
    get_close_button,
)
from keyboards.reply import get_main_reply_keyboard, get_locked_reply_keyboard
from services.error_parser import get_user_friendly_error_key
from services.guide_manager import load_guides, get_full_guide, get_guide_section
from services.calendar_helper import create_calendar_keyboard


class TestLocalization(unittest.TestCase):
    def test_ru_and_en_keys_exist(self):
        self.assertIn("ru", LOCALIZATION)
        self.assertIn("en", LOCALIZATION)
        self.assertTrue(len(LOCALIZATION["ru"]) > 50)
        self.assertTrue(len(LOCALIZATION["en"]) > 50)

    def test_get_text_formatting(self):
        ru_text = get_text("zk_unlock_success", "ru")
        en_text = get_text("zk_unlock_success", "en")
        self.assertIn("разблокирована", ru_text)
        self.assertIn("unlocked", en_text)

    def test_get_text_with_kwargs(self):
        text = get_text("welcome", "ru", name="Алексей")
        self.assertIn("Алексей", text)

    def test_fallback_to_default(self):
        # Non-existent language falls back to ru
        text = get_text("zk_setup_success", "es")
        self.assertIn("успешно", text)


class TestUiHelpers(unittest.IsolatedAsyncioTestCase):
    async def test_safe_edit_message_not_modified(self):
        mock_msg = MagicMock()
        mock_msg.edit_text = AsyncMock(
            side_effect=TelegramBadRequest(
                method="editMessageText",
                message="Bad Request: message is not modified: specified new message content and reply markup are exactly the same as a current content and reply markup of the message"
            )
        )
        res = await safe_edit_message_text(mock_msg, "Same text")
        # Should return True without raising exception
        self.assertTrue(res)

    async def test_safe_edit_message_not_found(self):
        mock_msg = MagicMock()
        mock_msg.message_id = 123
        mock_msg.edit_text = AsyncMock(
            side_effect=TelegramBadRequest(
                method="editMessageText",
                message="Bad Request: message to edit not found"
            )
        )
        res = await safe_edit_message_text(mock_msg, "Text")
        self.assertFalse(res)

    async def test_safe_answer_callback(self):
        mock_cb = MagicMock()
        mock_cb.answer = AsyncMock()
        await safe_answer_callback(mock_cb, "Done")
        mock_cb.answer.assert_awaited_once_with(text="Done", show_alert=False)


class TestKeyboardsBilingual(unittest.TestCase):
    def test_inline_main_menu_bilingual(self):
        kb_ru = get_main_menu_keyboard(is_unlocked=True, is_admin=True, lang_code="ru")
        kb_en = get_main_menu_keyboard(is_unlocked=True, is_admin=True, lang_code="en")

        ru_texts = [btn.text for row in kb_ru.inline_keyboard for btn in row]
        en_texts = [btn.text for row in kb_en.inline_keyboard for btn in row]

        self.assertIn("💬 Новый диалог", ru_texts)
        self.assertIn("💬 New Dialog", en_texts)
        self.assertIn("❌ Закрыть", ru_texts)
        self.assertIn("❌ Close", en_texts)

    def test_settings_keyboard_language_switcher(self):
        kb_ru = get_settings_keyboard("gemini-2.5-flash", "default", "default", True, "ru")
        ru_texts = [btn.text for row in kb_ru.inline_keyboard for btn in row]
        self.assertTrue(any("Язык:" in t for t in ru_texts))
        self.assertTrue(any("паник-пароль" in t for t in ru_texts))

        kb_en = get_settings_keyboard("gemini-2.5-flash", "default", "default", True, "en")
        en_texts = [btn.text for row in kb_en.inline_keyboard for btn in row]
        self.assertTrue(any("Language:" in t for t in en_texts))
        self.assertTrue(any("Panic Password" in t for t in en_texts))

    def test_language_keyboard(self):
        kb = get_language_keyboard(current_lang="ru", lang_code="ru")
        cb_datas = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        self.assertIn("set_lang:ru", cb_datas)
        self.assertIn("set_lang:en", cb_datas)

    def test_cancel_keyboard(self):
        kb = get_cancel_keyboard(callback_data="menu_settings", lang_code="ru")
        cb_datas = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        self.assertIn("menu_settings", cb_datas)
        self.assertIn("close_menu", cb_datas)

    def test_reply_keyboards_bilingual(self):
        r_ru = get_main_reply_keyboard(is_admin=True, lang_code="ru")
        r_en = get_main_reply_keyboard(is_admin=True, lang_code="en")

        ru_texts = [btn.text for row in r_ru.keyboard for btn in row]
        en_texts = [btn.text for row in r_en.keyboard for btn in row]

        self.assertIn("🗂️ Диалоги", ru_texts)
        self.assertIn("🗂️ Dialogs", en_texts)


class TestServices(unittest.TestCase):
    def test_error_parser(self):
        err_429 = {"error": "RESOURCE_EXHAUSTED: quota exceeded 429"}
        err_503 = {"error": "service_unavailable: model is overloaded"}
        err_safety = {"error": "finish_reason: SAFETY block"}

        self.assertEqual(get_user_friendly_error_key(err_429), "gemini_error_quota_exceeded")
        self.assertEqual(get_user_friendly_error_key(err_503), "gemini_error_unavailable")
        self.assertEqual(get_user_friendly_error_key(err_safety), "gemini_error_safety")

    def test_guide_manager(self):
        load_guides()
        full_ru = get_full_guide("ru")
        full_en = get_full_guide("en")
        self.assertTrue(len(full_ru) > 100)
        self.assertTrue(len(full_en) > 100)

        sec_api = get_guide_section("API_KEY", "ru")
        self.assertNotIn("не найден", sec_api)

    def test_calendar_helper(self):
        kb = create_calendar_keyboard(year=2026, month=9, lang_code="ru")
        self.assertIsNotNone(kb)
        all_cb = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        self.assertTrue(any("calendar_date:2026-09" in cb for cb in all_cb))
        self.assertTrue(any("calendar_month:" in cb for cb in all_cb))


class TestCommandFilters(unittest.TestCase):
    def test_multi_command_filter(self):
        from aiogram.filters import Command
        cmd_guide = Command("guide", "help_guide")
        self.assertEqual(cmd_guide.commands, ("guide", "help_guide"))

        cmd_feedback = Command("feedback", "support")
        self.assertEqual(cmd_feedback.commands, ("feedback", "support"))

        cmd_profile = Command("profile", "account")
        self.assertEqual(cmd_profile.commands, ("profile", "account"))


if __name__ == "__main__":
    unittest.main()

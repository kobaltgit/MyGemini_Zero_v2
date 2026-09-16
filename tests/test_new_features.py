"""
Unit tests for new features in MyGemini Zero v2:
- User rank calculation and account card rendering
- Dialog auto-naming title generation
- Subscribers list sorting with green marker (🟢)
- Persistent Reply keyboard and Close buttons
- Throttler with context header
"""

import unittest
from unittest.mock import AsyncMock, MagicMock

from database.models.user import User
from services.account import get_user_rank, format_account_card
from services.dialog_namer import fallback_title_from_text
from keyboards.reply import get_main_reply_keyboard, get_locked_reply_keyboard
from keyboards.inline import (
    get_main_menu_keyboard,
    get_settings_keyboard,
    get_documents_list_keyboard,
    get_profile_keyboard,
)


class TestNewFeatures(unittest.TestCase):

    def test_user_rank_progression(self):
        """Verifies user rank calculation based on sent messages count."""
        self.assertEqual(get_user_rank(0), "🥉 Новичок")
        self.assertEqual(get_user_rank(10), "🥉 Новичок")
        self.assertEqual(get_user_rank(49), "🥉 Новичок")
        self.assertEqual(get_user_rank(50), "🥈 Ветеран чата")
        self.assertEqual(get_user_rank(249), "🥈 Ветеран чата")
        self.assertEqual(get_user_rank(250), "🥇 Мастер общения")
        self.assertEqual(get_user_rank(999), "🥇 Мастер общения")
        self.assertEqual(get_user_rank(1000), "👑 Легенда")
        self.assertEqual(get_user_rank(5000), "👑 Легенда")

    def test_format_account_card(self):
        """Verifies account card text rendering with ranks and details."""
        u = User(
            user_id=12345,
            username="testuser",
            first_name="Алексей",
            subscription_status="active",
            subscription_end_date="2026-12-31",
            gemini_model="gemini-2.5-pro",
            first_interaction_date="2026-01-01 10:00:00",
        )
        profile_data = {
            "role": "Инженер",
            "field": "ИТ",
            "stack": "Python, Docker",
            "projects": "Telegram Bot",
            "goals": "Автоматизация",
        }
        card = format_account_card(u, message_count=150, profile_data=profile_data, is_vault_unlocked=True)
        self.assertIn("Алексей", card)
        self.assertIn("🥈 Ветеран чата", card)
        self.assertIn("150", card)
        self.assertIn("gemini-2.5-pro", card)
        self.assertIn("Инженер", card)
        self.assertIn("Python, Docker", card)

    def test_dialog_title_fallback(self):
        """Verifies fallback auto-title logic from raw user text."""
        title1 = fallback_title_from_text("Напиши подробный скрипт парсинга HTML на Python")
        self.assertIn("Напиши", title1)
        self.assertLessEqual(len(title1), 35)

        title2 = fallback_title_from_text("### *Привет!* Как дела?")
        self.assertNotIn("#", title2)
        self.assertNotIn("*", title2)
        self.assertIn("Привет", title2)

        title_empty = fallback_title_from_text("   ")
        self.assertEqual(title_empty, "Новый диалог")

    def test_subscribers_sorting_logic(self):
        """Verifies that paid active subscribers are sorted to top with green marker 🟢, while expired ones get ⚪."""
        from database.repositories.user_repository import UserRepository
        user_repo = UserRepository(None)

        user_paid_future = User(user_id=1, username="paid1", first_name="Пётр", subscription_status="active", subscription_end_date="2026-10-01")
        user_expired = User(user_id=2, username="free2", first_name="Иван", subscription_status="active", subscription_end_date="2025-01-01")
        user_paid_long = User(user_id=3, username="paid3", first_name="Ольга", subscription_status="active", subscription_end_date="2026-11-01")

        self.assertTrue(user_repo.is_subscription_active(user_paid_future))
        self.assertFalse(user_repo.is_subscription_active(user_expired))
        self.assertTrue(user_repo.is_subscription_active(user_paid_long))

        subscribers = [user_expired, user_paid_future, user_paid_long]
        user_payments_map = {1: [object()], 2: [object()], 3: [object()]}

        def subscriber_sort_key(s):
            payments = user_payments_map.get(s.user_id, [])
            total_paid = len(payments)
            is_active = 1 if user_repo.is_subscription_active(s) else 0
            end_d = s.subscription_end_date or ""
            return (is_active, end_d, total_paid)

        sorted_subs = sorted(subscribers, key=subscriber_sort_key, reverse=True)

        self.assertEqual(sorted_subs[0].user_id, 3)
        self.assertEqual(sorted_subs[1].user_id, 1)
        self.assertEqual(sorted_subs[2].user_id, 2)

        marker_top = "🟢" if user_repo.is_subscription_active(sorted_subs[0]) else "⚪"
        marker_mid = "🟢" if user_repo.is_subscription_active(sorted_subs[1]) else "⚪"
        marker_last = "🟢" if user_repo.is_subscription_active(sorted_subs[2]) else "⚪"
        self.assertEqual(marker_top, "🟢")
        self.assertEqual(marker_mid, "🟢")
        self.assertEqual(marker_last, "⚪")

    def test_reply_keyboard_structure(self):
        """Verifies that ReplyKeyboardMarkup has required buttons and persistence."""
        kb = get_main_reply_keyboard(is_admin=True)
        self.assertTrue(kb.is_persistent)
        self.assertTrue(kb.resize_keyboard)

        button_texts = [btn.text for row in kb.keyboard for btn in row]
        self.assertIn("🗂️ Диалоги", button_texts)
        self.assertIn("➕ Новый диалог", button_texts)
        self.assertIn("⚙️ Настройки", button_texts)
        self.assertIn("👤 Личный кабинет", button_texts)
        self.assertIn("📄 Документы", button_texts)
        self.assertIn("🔄 Сброс контекста", button_texts)
        self.assertIn("❓ Помощь", button_texts)
        self.assertIn("👑 Админка", button_texts)

    def test_inline_keyboards_have_close_button(self):
        """Verifies that all interactive inline menus contain a close button (close_menu)."""
        kb_main = get_main_menu_keyboard()
        all_callbacks_main = [btn.callback_data for row in kb_main.inline_keyboard for btn in row if btn.callback_data]
        self.assertIn("close_menu", all_callbacks_main)

        kb_settings = get_settings_keyboard("gemini-2.5-flash", "balanced", "default", True)
        all_callbacks_settings = [btn.callback_data for row in kb_settings.inline_keyboard for btn in row if btn.callback_data]
        self.assertIn("close_menu", all_callbacks_settings)

        kb_profile = get_profile_keyboard(True)
        all_callbacks_profile = [btn.callback_data for row in kb_profile.inline_keyboard for btn in row if btn.callback_data]
        self.assertIn("close_menu", all_callbacks_profile)

        sample_docs = [{"file_name": "test.pdf", "file_hash": "abc", "chunks_count": 5}]
        kb_docs = get_documents_list_keyboard(sample_docs)
        all_callbacks_docs = [btn.callback_data for row in kb_docs.inline_keyboard for btn in row if btn.callback_data]
        self.assertIn("close_menu", all_callbacks_docs)
        self.assertIn("doc_del:abc", all_callbacks_docs)


class TestAsyncFeatures(unittest.IsolatedAsyncioTestCase):

    async def test_render_settings_view(self):
        """Verifies that render_settings_view executes cleanly without any attribute errors."""
        from handlers.settings import render_settings_view
        from core.database import init_db, async_session_maker
        from database.repositories import UserRepository

        await init_db()
        async with async_session_maker() as session:
            repo = UserRepository(session)
            await repo.add_or_update_user(user_id=999999, username="settingstest", first_name="Test", last_name="User")

        text, kb = await render_settings_view(999999)
        self.assertIn("Настройки AI-ассистента", text)
        self.assertGreater(len(kb.inline_keyboard), 0)

    async def test_throttler_with_context_header(self):
        """Verifies that MessageStreamThrottler prepends header to Telegram display and keeps finalize clean."""
        from services.throttler import MessageStreamThrottler

        mock_bot = AsyncMock()
        mock_msg = MagicMock()
        mock_msg.message_id = 12345

        header = "• **Диалог:** `Тест`\n• **Персона:** `Обычный`\n• **Модель:** `gemini-2.5-flash`\n---\n\n"
        throttler = MessageStreamThrottler(
            bot=mock_bot,
            chat_id=10001,
            initial_message=mock_msg,
            header_text=header,
        )

        await throttler.handle_chunk("Привет, ")
        await throttler.handle_chunk("мир!")

        raw_response = await throttler.finalize()
        self.assertEqual(raw_response, "Привет, мир!")
        self.assertTrue(mock_bot.edit_message_text.called)
        last_call_kwargs = mock_bot.edit_message_text.call_args.kwargs
        self.assertIn("text", last_call_kwargs)
        self.assertIn("Тест", last_call_kwargs["text"])
        self.assertIn("Привет", last_call_kwargs["text"])


if __name__ == "__main__":
    unittest.main()

"""
Unit tests for UI, Keyboards, and Handler Phase 2 components:
- get_session_ttl_keyboard (15, 60, 480, 1440 minutes, checkmarks, RU/EN)
- get_settings_keyboard (session TTL & Python sandbox toggles, RU/EN)
- Settings handlers (settings_ttl, set_ttl:<val>, settings_toggle_code_exec)
- Chat handler code_execution parameter pass-through and token usage metadata extraction
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import CallbackQuery, Message, User as TgUser, Chat

from core.database import init_db, async_session_maker
from core.crypto import generate_salt, get_fernet_instance
from database.repositories import UserRepository, DialogRepository, ConversationRepository
from keyboards.inline import (
    get_session_ttl_keyboard,
    get_settings_keyboard,
)
from handlers.settings import (
    render_settings_view,
    handle_settings_ttl,
    handle_set_ttl,
    handle_toggle_code_exec,
)
from handlers.chat import (
    handle_user_message,
    handle_chat_action_regen,
    active_streams,
)
from middlewares.auth import session_manager


class TestKeyboardsPhase2(unittest.TestCase):
    """Tests for Phase 2 inline keyboards."""

    def test_get_session_ttl_keyboard_ru(self):
        """Verifies session TTL selector keyboard in Russian with correct checkmarks and callbacks."""
        for ttl in (15, 60, 480, 1440):
            kb = get_session_ttl_keyboard(current_ttl=ttl, lang_code="ru")
            all_btns = [btn for row in kb.inline_keyboard for btn in row]
            cb_map = {b.callback_data: b.text for b in all_btns if b.callback_data}

            self.assertIn("set_ttl:15", cb_map)
            self.assertIn("set_ttl:60", cb_map)
            self.assertIn("set_ttl:480", cb_map)
            self.assertIn("set_ttl:1440", cb_map)
            self.assertIn("menu_settings", cb_map)
            self.assertIn("close_menu", cb_map)

            active_btn_text = cb_map[f"set_ttl:{ttl}"]
            self.assertTrue(active_btn_text.startswith("✅"))

        # Verify exact RU labels
        kb_default = get_session_ttl_keyboard(current_ttl=60, lang_code="ru")
        cb_map = {b.callback_data: b.text for row in kb_default.inline_keyboard for b in row}
        self.assertEqual(cb_map["set_ttl:15"], "⏱️ 15 минут")
        self.assertEqual(cb_map["set_ttl:60"], "✅ 🕐 1 час")
        self.assertEqual(cb_map["set_ttl:480"], "💼 8 часов")
        self.assertEqual(cb_map["set_ttl:1440"], "🌙 24 часа")
        self.assertEqual(cb_map["menu_settings"], "⬅️ Назад в настройки")
        self.assertEqual(cb_map["close_menu"], "❌ Закрыть")

    def test_get_session_ttl_keyboard_en(self):
        """Verifies session TTL selector keyboard in English."""
        kb = get_session_ttl_keyboard(current_ttl=15, lang_code="en")
        cb_map = {b.callback_data: b.text for row in kb.inline_keyboard for b in row}

        self.assertEqual(cb_map["set_ttl:15"], "✅ ⏱️ 15 mins")
        self.assertEqual(cb_map["set_ttl:60"], "🕐 1 hour")
        self.assertEqual(cb_map["set_ttl:480"], "💼 8 hours")
        self.assertEqual(cb_map["set_ttl:1440"], "🌙 24 hours")
        self.assertEqual(cb_map["menu_settings"], "⬅️ Back to Settings")
        self.assertEqual(cb_map["close_menu"], "❌ Close")

    def test_get_settings_keyboard_ttl_and_code_exec_ru(self):
        """Verifies session TTL and Python sandbox toggle buttons in get_settings_keyboard (RU)."""
        # Disabled sandbox & 60 min TTL
        kb_off = get_settings_keyboard(
            current_model="gemini-2.5-flash",
            current_style="default",
            current_persona="default",
            has_api_key=True,
            lang_code="ru",
            current_session_ttl=60,
            code_execution_enabled=False,
        )
        cb_map = {b.callback_data: b.text for row in kb_off.inline_keyboard for b in row if b.callback_data}
        self.assertIn("settings_ttl", cb_map)
        self.assertIn("settings_toggle_code_exec", cb_map)
        self.assertEqual(cb_map["settings_ttl"], "⏱️ Сессия: 1 час")
        self.assertEqual(cb_map["settings_toggle_code_exec"], "🐍 Песочница Python: 🔴 Выкл")

        # Enabled sandbox & 15 min TTL
        kb_on = get_settings_keyboard(
            current_model="gemini-2.5-flash",
            current_style="default",
            current_persona="default",
            has_api_key=True,
            lang_code="ru",
            current_session_ttl=15,
            code_execution_enabled=True,
        )
        cb_map_on = {b.callback_data: b.text for row in kb_on.inline_keyboard for b in row if b.callback_data}
        self.assertEqual(cb_map_on["settings_ttl"], "⏱️ Сессия: 15 мин")
        self.assertEqual(cb_map_on["settings_toggle_code_exec"], "🐍 Песочница Python: 🟢 Вкл")

        # 8 hours and 24 hours TTL labels
        kb_8h = get_settings_keyboard(
            current_model="gemini-2.5-flash",
            current_style="default",
            current_persona="default",
            has_api_key=True,
            lang_code="ru",
            current_session_ttl=480,
        )
        cb_map_8h = {b.callback_data: b.text for row in kb_8h.inline_keyboard for b in row if b.callback_data}
        self.assertEqual(cb_map_8h["settings_ttl"], "⏱️ Сессия: 8 ч")

        kb_24h = get_settings_keyboard(
            current_model="gemini-2.5-flash",
            current_style="default",
            current_persona="default",
            has_api_key=True,
            lang_code="ru",
            current_session_ttl=1440,
        )
        cb_map_24h = {b.callback_data: b.text for row in kb_24h.inline_keyboard for b in row if b.callback_data}
        self.assertEqual(cb_map_24h["settings_ttl"], "⏱️ Сессия: 24 ч")

    def test_get_settings_keyboard_ttl_and_code_exec_en(self):
        """Verifies session TTL and Python sandbox toggle buttons in get_settings_keyboard (EN)."""
        kb_en = get_settings_keyboard(
            current_model="gemini-2.5-flash",
            current_style="default",
            current_persona="default",
            has_api_key=True,
            lang_code="en",
            current_session_ttl=480,
            code_execution_enabled=True,
        )
        cb_map = {b.callback_data: b.text for row in kb_en.inline_keyboard for b in row if b.callback_data}
        self.assertIn("settings_ttl", cb_map)
        self.assertIn("settings_toggle_code_exec", cb_map)
        self.assertEqual(cb_map["settings_ttl"], "⏱️ Session: 8 hours")
        self.assertEqual(cb_map["settings_toggle_code_exec"], "🐍 Python Sandbox: 🟢 On")


class TestSettingsHandlersPhase2(unittest.IsolatedAsyncioTestCase):
    """Tests for settings TTL and Python sandbox handlers."""

    async def asyncSetUp(self):
        await init_db()
        self.user_id = 992233
        self.password = "StrongMasterP@ssPhase2"

        async with async_session_maker() as session:
            repo = UserRepository(session)
            await repo.add_or_update_user(
                user_id=self.user_id,
                username="test_phase2_user",
                first_name="Phase2",
                last_name="Tester",
            )
            await repo.set_master_password(self.user_id, self.password)
            self.salt = await repo.get_salt(self.user_id)
            self.fernet = get_fernet_instance(self.password, self.salt)
            await repo.set_api_key(self.user_id, "AIzaSyFakeKeyForPhase2_1234567890", self.fernet)

        session_manager.unlock_session(self.user_id, self.fernet)

    async def asyncTearDown(self):
        session_manager.lock_session(self.user_id)
        active_streams.clear()

    async def test_render_settings_view_shows_ttl_and_code_exec(self):
        """Verifies render_settings_view includes session TTL and sandbox lines."""
        text, kb = await render_settings_view(self.user_id)
        self.assertIn("Песочница Python:", text)
        self.assertIn("Таймаут сессии:", text)

        cb_list = [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data]
        self.assertIn("settings_ttl", cb_list)
        self.assertIn("settings_toggle_code_exec", cb_list)

    async def test_handle_settings_ttl(self):
        """Verifies opening session TTL configuration keyboard."""
        cb_msg = MagicMock(spec=Message)
        cb_msg.edit_text = AsyncMock()
        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = TgUser(id=self.user_id, is_bot=False, first_name="Phase2")
        cb.message = cb_msg
        cb.answer = AsyncMock()
        cb.data = "settings_ttl"

        await handle_settings_ttl(cb)
        cb_msg.edit_text.assert_called_once()
        sent_kb = cb_msg.edit_text.call_args[1].get("reply_markup")
        cb_names = [b.callback_data for r in sent_kb.inline_keyboard for b in r if b.callback_data]
        self.assertIn("set_ttl:15", cb_names)
        self.assertIn("set_ttl:60", cb_names)
        self.assertIn("set_ttl:480", cb_names)
        self.assertIn("set_ttl:1440", cb_names)

    async def test_handle_set_ttl(self):
        """Verifies updating session TTL in DB and refreshing view."""
        cb_msg = MagicMock(spec=Message)
        cb_msg.edit_text = AsyncMock()
        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = TgUser(id=self.user_id, is_bot=False, first_name="Phase2", language_code="ru")
        cb.message = cb_msg
        cb.answer = AsyncMock()
        cb.data = "set_ttl:480"

        await handle_set_ttl(cb)

        # Check DB update
        async with async_session_maker() as session:
            repo = UserRepository(session)
            user = await repo.get_by_id(self.user_id)
            self.assertEqual(user.session_ttl_minutes, 480)

        cb_msg.edit_text.assert_called_once()
        rendered_text = cb_msg.edit_text.call_args.kwargs.get("text", "")
        self.assertIn("💼 8 часов", rendered_text)

    async def test_handle_toggle_code_exec(self):
        """Verifies toggling Python sandbox on and off."""
        cb_msg = MagicMock(spec=Message)
        cb_msg.edit_text = AsyncMock()
        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = TgUser(id=self.user_id, is_bot=False, first_name="Phase2", language_code="ru")
        cb.message = cb_msg
        cb.answer = AsyncMock()
        cb.data = "settings_toggle_code_exec"

        # Initial state is False, toggling turns it True
        await handle_toggle_code_exec(cb)
        async with async_session_maker() as session:
            repo = UserRepository(session)
            user = await repo.get_by_id(self.user_id)
            self.assertTrue(user.enable_code_execution)

        cb_msg.edit_text.assert_called_once()
        rendered_text = cb_msg.edit_text.call_args.kwargs.get("text", "")
        self.assertIn("🟢 Включена", rendered_text)

        # Toggle second time -> turns False
        cb_msg.edit_text.reset_mock()
        await handle_toggle_code_exec(cb)
        async with async_session_maker() as session:
            repo = UserRepository(session)
            user = await repo.get_by_id(self.user_id)
            self.assertFalse(user.enable_code_execution)

        cb_msg.edit_text.assert_called_once()
        rendered_text2 = cb_msg.edit_text.call_args.kwargs.get("text", "")
        self.assertIn("🔴 Выключена", rendered_text2)


class TestChatCodeExecutionPhase2(unittest.IsolatedAsyncioTestCase):
    """Tests for chat handler code_execution parameter pass-through and token usage metadata."""

    async def asyncSetUp(self):
        await init_db()
        self.user_id = 993344
        self.password = "StrongMasterP@ssPhase2Chat"

        async with async_session_maker() as session:
            repo = UserRepository(session)
            await repo.add_or_update_user(
                user_id=self.user_id,
                username="test_phase2_chat",
                first_name="Phase2Chat",
                last_name="Tester",
            )
            await repo.set_master_password(self.user_id, self.password)
            self.salt = await repo.get_salt(self.user_id)
            self.fernet = get_fernet_instance(self.password, self.salt)
            await repo.set_api_key(self.user_id, "AIzaSyFakeKeyForPhase2Chat_1234567890", self.fernet)
            await repo.update_subscription(self.user_id, "active", "2099-12-31")

        session_manager.unlock_session(self.user_id, self.fernet)

    async def asyncTearDown(self):
        session_manager.lock_session(self.user_id)
        active_streams.clear()

    @patch("handlers.chat.GeminiService")
    async def test_handle_user_message_passes_enable_code_execution_true(self, mock_gemini_class):
        """Verifies enable_code_execution=True is passed to generate_stream when user enabled sandbox."""
        async with async_session_maker() as session:
            repo = UserRepository(session)
            await repo.update_settings(self.user_id, enable_code_execution=True)

        captured_kwargs = {}
        mock_gemini_inst = MagicMock()

        class MockChunk(str):
            pass

        chunk = MockChunk("Hello with code")
        meta = MagicMock()
        meta.prompt_token_count = 15
        meta.candidates_token_count = 25
        meta.total_token_count = 40
        chunk.usage_metadata = meta

        async def fake_stream(*args, **kwargs):
            nonlocal captured_kwargs
            captured_kwargs = kwargs
            yield chunk

        mock_gemini_inst.generate_stream = fake_stream
        mock_gemini_class.return_value = mock_gemini_inst

        chat_id = 112233
        msg = MagicMock(spec=Message)
        msg.chat = Chat(id=chat_id, type="private")
        msg.from_user = TgUser(id=self.user_id, is_bot=False, first_name="Phase2Chat", language_code="ru")
        msg.text = "Write a python script"
        msg.caption = None
        msg.photo = None
        msg.voice = None
        msg.document = None

        placeholder_msg = MagicMock(spec=Message)
        placeholder_msg.message_id = 999
        placeholder_msg.chat = msg.chat
        msg.answer = AsyncMock(return_value=placeholder_msg)

        bot_mock = MagicMock()
        bot_mock.edit_message_text = AsyncMock()

        await handle_user_message(msg, bot=bot_mock)

        self.assertIn("enable_code_execution", captured_kwargs)
        self.assertTrue(captured_kwargs["enable_code_execution"])

    @patch("handlers.chat.GeminiService")
    async def test_handle_user_message_passes_enable_code_execution_false(self, mock_gemini_class):
        """Verifies enable_code_execution=False is passed when user disabled sandbox."""
        async with async_session_maker() as session:
            repo = UserRepository(session)
            await repo.update_settings(self.user_id, enable_code_execution=False)

        captured_kwargs = {}
        mock_gemini_inst = MagicMock()

        async def fake_stream(*args, **kwargs):
            nonlocal captured_kwargs
            captured_kwargs = kwargs
            yield "Hello without code"

        mock_gemini_inst.generate_stream = fake_stream
        mock_gemini_class.return_value = mock_gemini_inst

        chat_id = 112234
        msg = MagicMock(spec=Message)
        msg.chat = Chat(id=chat_id, type="private")
        msg.from_user = TgUser(id=self.user_id, is_bot=False, first_name="Phase2Chat", language_code="ru")
        msg.text = "Just chat"
        msg.caption = None
        msg.photo = None
        msg.voice = None
        msg.document = None

        placeholder_msg = MagicMock(spec=Message)
        placeholder_msg.message_id = 1000
        placeholder_msg.chat = msg.chat
        msg.answer = AsyncMock(return_value=placeholder_msg)

        bot_mock = MagicMock()
        bot_mock.edit_message_text = AsyncMock()

        await handle_user_message(msg, bot=bot_mock)

        self.assertIn("enable_code_execution", captured_kwargs)
        self.assertFalse(captured_kwargs["enable_code_execution"])

    @patch("handlers.chat.GeminiService")
    async def test_handle_chat_action_regen_passes_enable_code_execution(self, mock_gemini_class):
        """Verifies enable_code_execution pass-through on response regeneration."""
        async with async_session_maker() as session:
            repo = UserRepository(session)
            await repo.update_settings(self.user_id, enable_code_execution=True)

            dlg_repo = DialogRepository(session)
            dlg = await dlg_repo.create_dialog(self.user_id, "Code Execution Topic", set_active=True)
            conv_repo = ConversationRepository(session)
            await conv_repo.add_message(
                user_id=self.user_id,
                dialog_id=dlg.dialog_id,
                role="user",
                message_text="Calculate fibonacci(10)",
                fernet_instance=self.fernet,
            )
            await conv_repo.add_message(
                user_id=self.user_id,
                dialog_id=dlg.dialog_id,
                role="bot",
                message_text="Old answer",
                fernet_instance=self.fernet,
            )

        captured_kwargs = {}
        mock_gemini_inst = MagicMock()

        class MockChunk(str):
            pass

        chunk = MockChunk("55")
        meta = MagicMock()
        meta.prompt_token_count = 12
        meta.candidates_token_count = 5
        meta.total_token_count = 17
        chunk.usage_metadata = meta

        async def fake_stream(*args, **kwargs):
            nonlocal captured_kwargs
            captured_kwargs = kwargs
            yield chunk

        mock_gemini_inst.generate_stream = fake_stream
        mock_gemini_class.return_value = mock_gemini_inst

        chat_id = 998811
        cb_msg = MagicMock(spec=Message)
        cb_msg.chat = Chat(id=chat_id, type="private")
        cb_msg.message_id = 789
        cb_msg.edit_text = AsyncMock()
        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = TgUser(id=self.user_id, is_bot=False, first_name="Phase2Chat", language_code="ru")
        cb.message = cb_msg
        cb.answer = AsyncMock()
        cb.data = "chat_action:regen"

        bot_mock = MagicMock()
        bot_mock.edit_message_text = AsyncMock()

        await handle_chat_action_regen(cb, bot=bot_mock)

        self.assertIn("enable_code_execution", captured_kwargs)
        self.assertTrue(captured_kwargs["enable_code_execution"])

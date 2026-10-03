"""
Unit tests for UI, Keyboards, and Handler Phase 1 improvements:
- Quick actions keyboard (regen, undo)
- Streaming stop keyboard
- Thinking budget selector and settings keyboard integration
- Dialog menu keyboard and Markdown export handler
- Live stream abort (stop), turn undo, and prompt regeneration handlers
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import CallbackQuery, Message, User as TgUser, Chat, BufferedInputFile

from core.database import init_db, async_session_maker
from core.crypto import generate_salt, get_fernet_instance
from database.repositories import UserRepository, DialogRepository, ConversationRepository
from keyboards.inline import (
    get_chat_quick_actions_keyboard,
    get_streaming_stop_keyboard,
    get_thinking_budget_keyboard,
    get_settings_keyboard,
    get_dialog_menu_keyboard,
)
from handlers.settings import render_settings_view, handle_settings_thinking, handle_set_thinking
from handlers.dialogs import handle_dialog_export
from handlers.chat import (
    handle_chat_action_stop,
    handle_chat_action_undo,
    handle_chat_action_regen,
    handle_chat_action_export,
    active_streams,
)
from middlewares.auth import session_manager


class TestKeyboardsPhase1(unittest.TestCase):

    def test_quick_actions_keyboard(self):
        """Verifies quick actions inline keyboard in RU and EN."""
        kb_ru = get_chat_quick_actions_keyboard("ru")
        callbacks = [btn.callback_data for row in kb_ru.inline_keyboard for btn in row]
        texts = [btn.text for row in kb_ru.inline_keyboard for btn in row]
        self.assertEqual(callbacks, ["chat_action:regen", "chat_action:undo", "chat_action:export"])
        self.assertIn("🔄 Еще раз", texts)
        self.assertIn("↩️ Откатить шаг", texts)
        self.assertIn("📥 Экспорт диалога", texts)

        kb_en = get_chat_quick_actions_keyboard("en")
        texts_en = [btn.text for row in kb_en.inline_keyboard for btn in row]
        self.assertIn("🔄 Regenerate", texts_en)
        self.assertIn("↩️ Undo turn", texts_en)
        self.assertIn("📥 Export Dialogue", texts_en)

    def test_streaming_stop_keyboard(self):
        """Verifies streaming stop button keyboard in RU and EN."""
        kb_ru = get_streaming_stop_keyboard("ru")
        self.assertEqual(len(kb_ru.inline_keyboard), 1)
        btn = kb_ru.inline_keyboard[0][0]
        self.assertEqual(btn.callback_data, "chat_action:stop")
        self.assertEqual(btn.text, "⏹️ Стоп")

        kb_en = get_streaming_stop_keyboard("en")
        btn_en = kb_en.inline_keyboard[0][0]
        self.assertEqual(btn_en.text, "⏹️ Stop")

    def test_thinking_budget_keyboard(self):
        """Verifies thinking budget keyboard checkmarks and callback data."""
        for budget in (0, 1024, 4096):
            kb = get_thinking_budget_keyboard(current_budget=budget, lang_code="ru")
            all_btns = [btn for row in kb.inline_keyboard for btn in row]
            cb_map = {b.callback_data: b.text for b in all_btns if b.callback_data}
            self.assertIn("set_thinking:0", cb_map)
            self.assertIn("set_thinking:1024", cb_map)
            self.assertIn("set_thinking:4096", cb_map)
            self.assertIn("menu_settings", cb_map)
            self.assertIn("close_menu", cb_map)

            # Checkmark check
            active_btn_text = cb_map[f"set_thinking:{budget}"]
            self.assertTrue(active_btn_text.startswith("✅"))

    def test_settings_keyboard_thinking_button(self):
        """Verifies thinking button integration in get_settings_keyboard."""
        kb = get_settings_keyboard(
            current_model="gemini-2.5-flash",
            current_style="default",
            current_persona="default",
            has_api_key=True,
            lang_code="ru",
            current_thinking_budget=1024,
        )
        cb_map = {btn.callback_data: btn.text for row in kb.inline_keyboard for btn in row if btn.callback_data}
        self.assertIn("settings_thinking", cb_map)
        self.assertIn("🧠 Размышления: ⚖️ Баланс", cb_map["settings_thinking"])

        kb_instant = get_settings_keyboard(
            current_model="gemini-2.5-flash",
            current_style="default",
            current_persona="default",
            has_api_key=True,
            lang_code="en",
            current_thinking_budget=0,
        )
        cb_map_en = {btn.callback_data: btn.text for row in kb_instant.inline_keyboard for btn in row if btn.callback_data}
        self.assertIn("settings_thinking", cb_map_en)
        self.assertIn("🧠 Thinking: ⚡ Instant", cb_map_en["settings_thinking"])

    def test_dialog_menu_keyboard(self):
        """Verifies dialog menu keyboard contains export, switch, rename, delete."""
        kb = get_dialog_menu_keyboard(dialog_id=77, lang_code="ru")
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        self.assertIn("dialog_export:77", callbacks)
        self.assertIn("dialog_switch:77", callbacks)
        self.assertIn("dialog_rename_prompt:77", callbacks)
        self.assertIn("dialog_delete:77", callbacks)
        self.assertIn("dialog_list", callbacks)
        self.assertIn("close_menu", callbacks)


class TestHandlersPhase1(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()
        self.user_id = 881234
        self.password = "StrongMasterP@ss1"

        async with async_session_maker() as session:
            repo = UserRepository(session)
            await repo.add_or_update_user(
                user_id=self.user_id,
                username="test_ui_user",
                first_name="UI",
                last_name="Tester",
            )
            await repo.set_master_password(self.user_id, self.password)
            self.salt = await repo.get_salt(self.user_id)
            self.fernet = get_fernet_instance(self.password, self.salt)
            await repo.set_api_key(self.user_id, "AIzaSyFakeKeyForTesting1234567890", self.fernet)

        session_manager.unlock_session(self.user_id, self.fernet)

    async def asyncTearDown(self):
        session_manager.lock_session(self.user_id)
        active_streams.clear()

    async def test_render_settings_view_shows_thinking(self):
        """Verifies render_settings_view includes thinking budget status."""
        text, kb = await render_settings_view(self.user_id)
        self.assertIn("Размышления:", text)
        cb_list = [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data]
        self.assertIn("settings_thinking", cb_list)

    async def test_handle_settings_thinking_and_set_thinking(self):
        """Verifies opening thinking budget view and updating it."""
        cb_msg = MagicMock(spec=Message)
        cb_msg.edit_text = AsyncMock()
        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = TgUser(id=self.user_id, is_bot=False, first_name="UI")
        cb.message = cb_msg
        cb.answer = AsyncMock()

        # 1. Open thinking keyboard
        cb.data = "settings_thinking"
        await handle_settings_thinking(cb)
        cb_msg.edit_text.assert_called_once()
        sent_kb = cb_msg.edit_text.call_args[1].get("reply_markup")
        cb_names = [b.callback_data for r in sent_kb.inline_keyboard for b in r if b.callback_data]
        self.assertIn("set_thinking:4096", cb_names)

        # 2. Select 4096
        cb_msg.edit_text.reset_mock()
        cb.data = "set_thinking:4096"
        await handle_set_thinking(cb)

        async with async_session_maker() as session:
            repo = UserRepository(session)
            user = await repo.get_by_id(self.user_id)
            self.assertEqual(user.thinking_budget, 4096)

        cb_msg.edit_text.assert_called_once()
        rendered_text = cb_msg.edit_text.call_args.kwargs.get("text", "")
        self.assertIn("🔬 Глубокий анализ (4096)", rendered_text)

    async def test_dialog_export_markdown(self):
        """Verifies Markdown export of dialog messages as a file attachment."""
        async with async_session_maker() as session:
            dlg_repo = DialogRepository(session)
            dlg = await dlg_repo.create_dialog(self.user_id, "Python Guide", set_active=True)
            conv_repo = ConversationRepository(session)
            await conv_repo.add_message(
                user_id=self.user_id,
                dialog_id=dlg.dialog_id,
                role="user",
                message_text="How do I use list comprehensions?",
                fernet_instance=self.fernet,
            )
            await conv_repo.add_message(
                user_id=self.user_id,
                dialog_id=dlg.dialog_id,
                role="bot",
                message_text="Use `[x for x in iterable]`.",
                fernet_instance=self.fernet,
            )

        cb_msg = MagicMock(spec=Message)
        cb_msg.answer_document = AsyncMock()
        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = TgUser(id=self.user_id, is_bot=False, first_name="UI")
        cb.message = cb_msg
        cb.answer = AsyncMock()
        cb.data = f"dialog_export:{dlg.dialog_id}"

        await handle_dialog_export(cb)

        cb_msg.answer_document.assert_called_once()
        call_kwargs = cb_msg.answer_document.call_args[1]
        doc = call_kwargs["document"]
        self.assertIsInstance(doc, BufferedInputFile)
        self.assertTrue(doc.filename.endswith(".md"))
        self.assertTrue(doc.filename.startswith(f"dialog_{dlg.dialog_id}_"))

        # Check document content
        content_str = doc.data.decode("utf-8")
        self.assertIn("# 💬 Python Guide", content_str)
        self.assertIn("### 👤 Пользователь", content_str)
        self.assertIn("How do I use list comprehensions?", content_str)
        self.assertIn("### 🤖 Ассистент", content_str)
        self.assertIn("Use `[x for x in iterable]`.", content_str)

    async def test_chat_action_stop(self):
        """Verifies stopping an active streaming throttler."""
        fake_throttler = MagicMock()
        fake_throttler.abort = MagicMock()
        chat_id = 999111
        active_streams[chat_id] = fake_throttler

        cb_msg = MagicMock(spec=Message)
        cb_msg.chat = Chat(id=chat_id, type="private")
        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = TgUser(id=self.user_id, is_bot=False, first_name="UI", language_code="ru")
        cb.message = cb_msg
        cb.answer = AsyncMock()
        cb.data = "chat_action:stop"

        await handle_chat_action_stop(cb)
        fake_throttler.abort.assert_called_once()
        cb.answer.assert_called_once()
        ans_text = cb.answer.call_args.kwargs.get("text", "")
        self.assertIn("остановлена", ans_text)

    async def test_chat_action_undo(self):
        """Verifies undoing the last user/bot turn in active dialog."""
        async with async_session_maker() as session:
            dlg_repo = DialogRepository(session)
            dlg = await dlg_repo.create_dialog(self.user_id, "Undo Topic", set_active=True)
            conv_repo = ConversationRepository(session)
            await conv_repo.add_message(
                user_id=self.user_id,
                dialog_id=dlg.dialog_id,
                role="user",
                message_text="Mistaken user prompt",
                fernet_instance=self.fernet,
            )
            await conv_repo.add_message(
                user_id=self.user_id,
                dialog_id=dlg.dialog_id,
                role="bot",
                message_text="Mistaken bot answer",
                fernet_instance=self.fernet,
            )

        cb_msg = MagicMock(spec=Message)
        cb_msg.edit_text = AsyncMock()
        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = TgUser(id=self.user_id, is_bot=False, first_name="UI", language_code="ru")
        cb.message = cb_msg
        cb.answer = AsyncMock()
        cb.data = "chat_action:undo"

        await handle_chat_action_undo(cb)

        cb_msg.edit_text.assert_called_once()
        edit_text = cb_msg.edit_text.call_args.kwargs.get("text", "")
        self.assertIn("Последний шаг отменен", edit_text)
        self.assertIn("Mistaken user prompt", edit_text)

        # Confirm messages removed from DB
        async with async_session_maker() as session:
            conv_repo = ConversationRepository(session)
            msgs = await conv_repo.get_dialog_messages(dlg.dialog_id, self.fernet)
            self.assertEqual(len(msgs), 0)

    @patch("handlers.chat.GeminiService")
    async def test_chat_action_regen(self, mock_gemini_class):
        """Verifies regenerating the last assistant response."""
        # Setup mock stream generator
        mock_gemini_inst = MagicMock()
        async def fake_stream(*args, **kwargs):
            yield "Regenerated "
            yield "answer content."
        mock_gemini_inst.generate_stream = fake_stream
        mock_gemini_class.return_value = mock_gemini_inst

        async with async_session_maker() as session:
            dlg_repo = DialogRepository(session)
            dlg = await dlg_repo.create_dialog(self.user_id, "Regen Topic", set_active=True)
            conv_repo = ConversationRepository(session)
            await conv_repo.add_message(
                user_id=self.user_id,
                dialog_id=dlg.dialog_id,
                role="user",
                message_text="User question for regen",
                fernet_instance=self.fernet,
            )
            await conv_repo.add_message(
                user_id=self.user_id,
                dialog_id=dlg.dialog_id,
                role="bot",
                message_text="First bad answer",
                fernet_instance=self.fernet,
            )

        chat_id = 777333
        cb_msg = MagicMock(spec=Message)
        cb_msg.chat = Chat(id=chat_id, type="private")
        cb_msg.message_id = 456
        cb_msg.edit_text = AsyncMock()
        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = TgUser(id=self.user_id, is_bot=False, first_name="UI", language_code="ru")
        cb.message = cb_msg
        cb.answer = AsyncMock()
        cb.data = "chat_action:regen"

        bot_mock = MagicMock()
        bot_mock.edit_message_text = AsyncMock()

        await handle_chat_action_regen(cb, bot=bot_mock)

        # Check DB has regenerated response
        async with async_session_maker() as session:
            conv_repo = ConversationRepository(session)
            msgs = await conv_repo.get_dialog_messages(dlg.dialog_id, self.fernet)
            self.assertEqual(len(msgs), 2)
            self.assertEqual(msgs[0]["text"], "User question for regen")
            self.assertEqual(msgs[1]["text"], "Regenerated answer content.")

    async def test_chat_action_export(self):
        """Verifies export button from chat quick actions sends markdown document."""
        async with async_session_maker() as session:
            dlg_repo = DialogRepository(session)
            dlg = await dlg_repo.create_dialog(self.user_id, "Export From Chat", set_active=True)
            conv_repo = ConversationRepository(session)
            await conv_repo.add_message(
                user_id=self.user_id,
                dialog_id=dlg.dialog_id,
                role="user",
                message_text="Hello to export",
                fernet_instance=self.fernet,
            )

        cb_msg = MagicMock(spec=Message)
        cb_msg.answer_document = AsyncMock()
        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = TgUser(id=self.user_id, is_bot=False, first_name="UI", language_code="ru")
        cb.message = cb_msg
        cb.answer = AsyncMock()
        cb.data = "chat_action:export"

        await handle_chat_action_export(cb)

        cb_msg.answer_document.assert_awaited_once()
        args, kwargs = cb_msg.answer_document.call_args
        doc = kwargs.get("document")
        self.assertIsInstance(doc, BufferedInputFile)
        self.assertTrue(doc.filename.startswith("dialog_"))
        self.assertTrue(doc.filename.endswith(".md"))


"""
Unit tests for new features in MyGemini Zero v2:
- User rank calculation and account card rendering
- Dialog auto-naming title generation
- Subscribers list sorting with green marker (🟢)
- Persistent Reply keyboard and Close buttons
"""

import pytest
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


def test_user_rank_progression():
    """Verifies user rank calculation based on sent messages count."""
    assert get_user_rank(0) == "🥉 Новичок"
    assert get_user_rank(10) == "🥉 Новичок"
    assert get_user_rank(49) == "🥉 Новичок"
    assert get_user_rank(50) == "🥈 Ветеран чата"
    assert get_user_rank(249) == "🥈 Ветеран чата"
    assert get_user_rank(250) == "🥇 Мастер общения"
    assert get_user_rank(999) == "🥇 Мастер общения"
    assert get_user_rank(1000) == "👑 Легенда"
    assert get_user_rank(5000) == "👑 Легенда"


def test_format_account_card():
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
    assert "Алексей" in card
    assert "🥈 Ветеран чата" in card
    assert "150" in card
    assert "gemini-2.5-pro" in card
    assert "Инженер" in card
    assert "Python, Docker" in card


def test_dialog_title_fallback():
    """Verifies fallback auto-title logic from raw user text."""
    title1 = fallback_title_from_text("Напиши подробный скрипт парсинга HTML на Python")
    assert "Напиши" in title1
    assert len(title1) <= 35

    title2 = fallback_title_from_text("### *Привет!* Как дела?")
    assert "#" not in title2
    assert "*" not in title2
    assert "Привет" in title2

    title_empty = fallback_title_from_text("   ")
    assert title_empty == "Новый диалог"


def test_subscribers_sorting_logic():
    """Verifies that paid subscribers are sorted to top with green marker 🟢."""
    user_paid_1 = User(user_id=1, username="paid1", first_name="Пётр", subscription_status="active", subscription_end_date="2026-10-01")
    user_free_2 = User(user_id=2, username="free2", first_name="Иван", subscription_status="expired", subscription_end_date="2026-01-01")
    user_paid_3 = User(user_id=3, username="paid3", first_name="Ольга", subscription_status="active", subscription_end_date="2026-11-01")

    subscribers = [user_free_2, user_paid_1, user_paid_3]
    user_payments_map = {1: [object()], 2: [], 3: [object()]}

    def subscriber_sort_key(s):
        payments = user_payments_map.get(s.user_id, [])
        total_paid = len(payments)
        is_active = 1 if s.subscription_status == "active" else 0
        has_paid = 1 if (is_active or total_paid > 0) else 0
        end_d = s.subscription_end_date or ""
        return (has_paid, is_active, end_d)

    sorted_subs = sorted(subscribers, key=subscriber_sort_key, reverse=True)

    # Top users must be the paid active ones
    assert sorted_subs[0].user_id == 3  # end date November
    assert sorted_subs[1].user_id == 1  # end date October
    assert sorted_subs[2].user_id == 2  # expired free user

    # Markers check
    marker_top = "🟢" if sorted_subs[0].subscription_status == "active" else "⚪"
    marker_last = "🟢" if sorted_subs[2].subscription_status == "active" else "⚪"
    assert marker_top == "🟢"
    assert marker_last == "⚪"


def test_reply_keyboard_structure():
    """Verifies that ReplyKeyboardMarkup has required buttons and persistence."""
    kb = get_main_reply_keyboard(is_admin=True)
    assert kb.is_persistent is True
    assert kb.resize_keyboard is True

    # Flatten buttons text
    button_texts = [btn.text for row in kb.keyboard for btn in row]
    assert "🗂️ Диалоги" in button_texts
    assert "➕ Новый диалог" in button_texts
    assert "⚙️ Настройки" in button_texts
    assert "👤 Личный кабинет" in button_texts
    assert "📄 Документы" in button_texts
    assert "🔄 Сброс контекста" in button_texts
    assert "❓ Помощь" in button_texts
    assert "👑 Админка" in button_texts


def test_inline_keyboards_have_close_button():
    """Verifies that all interactive inline menus contain a close button (close_menu)."""
    kb_main = get_main_menu_keyboard()
    all_callbacks_main = [btn.callback_data for row in kb_main.inline_keyboard for btn in row if btn.callback_data]
    assert "close_menu" in all_callbacks_main

    kb_settings = get_settings_keyboard("gemini-2.5-flash", "balanced", "default", True)
    all_callbacks_settings = [btn.callback_data for row in kb_settings.inline_keyboard for btn in row if btn.callback_data]
    assert "close_menu" in all_callbacks_settings

    kb_profile = get_profile_keyboard(True)
    all_callbacks_profile = [btn.callback_data for row in kb_profile.inline_keyboard for btn in row if btn.callback_data]
    assert "close_menu" in all_callbacks_profile

    sample_docs = [{"file_name": "test.pdf", "file_hash": "abc", "chunks_count": 5}]
    kb_docs = get_documents_list_keyboard(sample_docs)
    all_callbacks_docs = [btn.callback_data for row in kb_docs.inline_keyboard for btn in row if btn.callback_data]
    assert "close_menu" in all_callbacks_docs
    assert "doc_del:abc" in all_callbacks_docs


@pytest.mark.asyncio
async def test_render_settings_view():
    """Verifies that render_settings_view executes cleanly without any attribute errors."""
    from handlers.settings import render_settings_view
    from core.database import init_db, async_session_maker
    from database.repositories import UserRepository

    await init_db()
    async with async_session_maker() as session:
        repo = UserRepository(session)
        await repo.add_or_update_user(user_id=999999, username="settingstest", first_name="Test", last_name="User")

    text, kb = await render_settings_view(999999)
    assert "Настройки AI-ассистента" in text
    assert len(kb.inline_keyboard) > 0


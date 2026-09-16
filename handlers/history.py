"""
History by Date & Interactive Calendar Handler for MyGemini Zero v2.
Allows users to browse message history by calendar date.
"""

from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from core.database import async_session_maker
from database.repositories import UserRepository, ConversationRepository
from middlewares.auth import session_manager
from keyboards.inline import get_unlock_keyboard, get_close_button
from services.calendar_helper import (
    create_calendar_keyboard,
    CALLBACK_CALENDAR_DATE_PREFIX,
    CALLBACK_CALENDAR_MONTH_PREFIX,
    CALLBACK_IGNORE,
)
from core.ui_helpers import safe_edit_message_text, safe_answer_callback
from core.logger import get_logger

logger = get_logger("user_messages")
router = Router(name="history")


@router.message(Command("history"))
async def handle_history_command(message: Message):
    """Entry point for /history command. Opens interactive calendar."""
    try:
        await message.delete()
    except Exception:
        pass

    user_id = message.from_user.id
    fernet = session_manager.get_fernet(user_id)

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    if not fernet:
        prompt_text = (
            "🔒 <b>Сейф заблокирован.</b>\n"
            "Для просмотра истории переписки сначала разблокируйте память мастер-паролем."
            if lang_code == "ru"
            else "🔒 <b>Vault is locked.</b>\n"
            "To view conversation history, please unlock memory with your master password first."
        )
        await message.answer(prompt_text, reply_markup=get_unlock_keyboard(lang_code), parse_mode="HTML")
        return

    intro_text = (
        "📅 <b>История сообщений по датам:</b>\n\n"
        "Выберите интересующий день в календаре ниже, чтобы просмотреть переписку за эту дату:"
        if lang_code == "ru"
        else "📅 <b>Message History by Date:</b>\n\n"
        "Select a date in the calendar below to view conversation history for that day:"
    )

    await message.answer(
        intro_text,
        reply_markup=create_calendar_keyboard(lang_code=lang_code),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith(CALLBACK_CALENDAR_MONTH_PREFIX))
async def handle_calendar_month_navigation(callback: CallbackQuery):
    """Navigates previous/next month in calendar."""
    await safe_answer_callback(callback)
    user_id = callback.from_user.id
    data_part = callback.data[len(CALLBACK_CALENDAR_MONTH_PREFIX):]

    try:
        year_str, month_str = data_part.split("-")
        year, month = int(year_str), int(month_str)
    except Exception:
        return

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    intro_text = (
        "📅 <b>История сообщений по датам:</b>\n\n"
        "Выберите интересующий день в календаре ниже, чтобы просмотреть переписку за эту дату:"
        if lang_code == "ru"
        else "📅 <b>Message History by Date:</b>\n\n"
        "Select a date in the calendar below to view conversation history for that day:"
    )

    await safe_edit_message_text(
        message=callback.message,
        text=intro_text,
        reply_markup=create_calendar_keyboard(year=year, month=month, lang_code=lang_code),
        parse_mode="HTML",
    )


@router.callback_query(F.data == CALLBACK_IGNORE)
async def handle_calendar_ignore(callback: CallbackQuery):
    """Silently ignores clicks on calendar labels or empty cells."""
    await safe_answer_callback(callback)


@router.callback_query(F.data.startswith(CALLBACK_CALENDAR_DATE_PREFIX))
async def handle_calendar_date_selection(callback: CallbackQuery):
    """Renders messages for the selected date."""
    user_id = callback.from_user.id
    fernet = session_manager.get_fernet(user_id)
    date_str = callback.data[len(CALLBACK_CALENDAR_DATE_PREFIX):]

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    if not fernet:
        await safe_answer_callback(
            callback,
            text="Сейф заблокирован. Разблокируйте мастер-паролем." if lang_code == "ru" else "Vault is locked.",
            show_alert=True,
        )
        return

    await safe_answer_callback(callback)

    async with async_session_maker() as session:
        conv_repo = ConversationRepository(session)
        messages = await conv_repo.get_messages_by_date(user_id, date_str, fernet)

    if not messages:
        no_msg = (
            f"ℹ️ За дату <b>{date_str}</b> сообщений не найдено."
            if lang_code == "ru"
            else f"ℹ️ No messages found for <b>{date_str}</b>."
        )
        await callback.message.answer(no_msg, parse_mode="HTML")
        return

    lines = [
        f"📜 <b>История переписки за {date_str}:</b>\n"
        if lang_code == "ru"
        else f"📜 <b>Conversation history for {date_str}:</b>\n"
    ]

    for m in messages:
        role_label = (
            ("👤 Вы:" if m["role"] == "user" else "🤖 AI:")
            if lang_code == "ru"
            else ("👤 You:" if m["role"] == "user" else "🤖 AI:")
        )
        ts = m["timestamp"][11:16] if len(m["timestamp"]) >= 16 else ""
        time_str = f" <i>({ts})</i>" if ts else ""
        lines.append(f"<b>{role_label}</b>{time_str}\n{m['text']}\n")

    full_text = "\n".join(lines)
    # Split text if exceeds 4000 characters
    chunk_size = 3800
    for i in range(0, len(full_text), chunk_size):
        part = full_text[i:i + chunk_size]
        await callback.message.answer(part, parse_mode="HTML")

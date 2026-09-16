"""
Feedback & Support Handler for MyGemini Zero v2.
Allows users to submit feedback or bug reports, forwarding them directly to the admin in Telegram PM.
"""

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from core.database import async_session_maker
from database.repositories import UserRepository
from keyboards.inline import get_cancel_keyboard, get_close_button
from core.config import settings
from core.logger import get_logger

logger = get_logger("user_messages")
router = Router(name="feedback")


class FeedbackStates(StatesGroup):
    waiting_for_feedback = State()


@router.message(Command("feedback", "support"))
async def handle_feedback_command(message: Message, state: FSMContext):
    """Entry point for /feedback command."""
    try:
        await message.delete()
    except Exception:
        pass

    user_id = message.from_user.id
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    await state.set_state(FeedbackStates.waiting_for_feedback)

    prompt = (
        "✉️ <b>Обратная связь и поддержка:</b>\n\n"
        "Напишите ваше сообщение, вопрос или пожелание разработчикам. "
        "Оно будет передано администратору бота:"
        if lang_code == "ru"
        else "✉️ <b>Feedback & Support:</b>\n\n"
        "Send your message, question, or suggestion. "
        "It will be forwarded directly to the administrator:"
    )

    await message.answer(
        prompt,
        reply_markup=get_cancel_keyboard(callback_data="close_menu", lang_code=lang_code),
        parse_mode="HTML",
    )


@router.message(FeedbackStates.waiting_for_feedback)
async def process_feedback_message(message: Message, state: FSMContext, bot: Bot):
    """Forwards feedback to admin and notifies user."""
    user_id = message.from_user.id
    feedback_text = message.text.strip() if message.text else ""
    await state.clear()

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    if not feedback_text:
        await message.answer("⚠️ Пустое сообщение.")
        return

    # Notify admin
    uname = f"@{message.from_user.username}" if message.from_user.username else "без username"
    full_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip() or "Пользователь"

    admin_msg = (
        f"✉️ <b>Новое сообщение обратной связи!</b>\n\n"
        f"• <b>От:</b> {full_name} ({uname})\n"
        f"• <b>ID:</b> <code>{user_id}</code>\n\n"
        f"<b>Текст сообщения:</b>\n{feedback_text}"
    )

    # Reply button for admin
    reply_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✉️ Ответить", callback_data=f"admin_reply_user:{user_id}")],
    ])

    try:
        await bot.send_message(
            chat_id=settings.ADMIN_USER_ID,
            text=admin_msg,
            reply_markup=reply_kb,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Failed to forward feedback to admin: {e}")

    confirm_text = (
        "✅ <b>Спасибо за обратную связь!</b> Ваше сообщение передано администратору."
        if lang_code == "ru"
        else "✅ <b>Thank you for your feedback!</b> Your message has been sent to the administrator."
    )
    await message.answer(
        confirm_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[get_close_button(lang_code)]]),
        parse_mode="HTML",
    )

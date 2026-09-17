"""
Start and Onboarding Handler for MyGemini Zero v2.
Handles /start, user registration, first interaction setup, and main navigation.
Supports bilingual onboarding (RU / EN), safe editing, and FSM state clearing.
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from core.config import settings
from core.database import async_session_maker
from database.repositories import UserRepository
from keyboards.inline import (
    get_main_menu_keyboard,
    get_set_password_keyboard,
    get_unlock_keyboard,
)
from keyboards.reply import get_main_reply_keyboard, get_locked_reply_keyboard
from middlewares.auth import session_manager
from core.ui_helpers import safe_edit_message_text, safe_answer_callback
from core.localization import get_text
from core.logger import get_logger

logger = get_logger("user_messages")
router = Router(name="start")


@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext):
    """Entry point for /start command."""
    await state.clear()
    user = message.from_user
    if not user:
        return

    lang_code = "ru" if not user.language_code or user.language_code.startswith("ru") else "en"

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        db_user, is_new = await user_repo.add_or_update_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            lang_code=lang_code,
        )
        if db_user and db_user.language_code:
            lang_code = db_user.language_code

        has_password = await user_repo.is_master_password_set(user.id)

    # 1. New user onboarding: prompt to set master password
    if not has_password:
        if lang_code == "ru":
            welcome_text = (
                f"👋 Здравствуйте, <b>{user.first_name}</b>!\n\n"
                "Добро пожаловать в <b>MyGemini Zero v2</b> — приватного AI-ассистента с архитектурой <b>Zero-Knowledge</b>.\n\n"
                "🔒 <b>Как это устроено:</b>\n"
                "• Вся ваша переписка и Google API-ключ шифруются вашим мастер-паролем.\n"
                "• Пароль никогда не отправляется на сервер и не хранится в открытом виде.\n"
                "• Без вашего мастер-пароля прочитать сообщения невозможно даже разработчикам бота.\n\n"
                "Для начала работы установите ваш <b>мастер-пароль</b>. "
                "Нажмите кнопку ниже, чтобы ввести его в чате (он будет мгновенно удален):"
            )
        else:
            welcome_text = (
                f"👋 Hello, <b>{user.first_name}</b>!\n\n"
                "Welcome to <b>MyGemini Zero v2</b> — a private AI assistant with <b>Zero-Knowledge</b> architecture.\n\n"
                "🔒 <b>How it works:</b>\n"
                "• All your conversations and Google API key are encrypted with your master password.\n"
                "• The password is never stored on the server in plain text.\n"
                "• Without your master password, no one (not even the bot developers) can access your data.\n\n"
                "To get started, set your <b>master password</b>. "
                "Click the button below to enter it safely in chat (it will be instantly deleted):"
            )

        await message.answer(
            welcome_text,
            reply_markup=get_set_password_keyboard(lang_code),
            parse_mode="HTML",
        )
        return

    # 2. Existing user check session state
    is_unlocked = session_manager.is_unlocked(user.id)
    is_admin = (user.id == settings.ADMIN_USER_ID)

    if not is_unlocked:
        if lang_code == "ru":
            locked_text = (
                f"👋 С возвращением, <b>{user.first_name}</b>!\n\n"
                "🔐 Ваше хранилище заблокировано для обеспечения конфиденциальности.\n"
                "Введите мастер-пароль, чтобы расшифровать диалоги и продолжить общение с AI:"
            )
        else:
            locked_text = (
                f"👋 Welcome back, <b>{user.first_name}</b>!\n\n"
                "🔐 Your vault is locked to protect your privacy.\n"
                "Enter your master password to decrypt dialogues and continue chatting with AI:"
            )

        await message.answer(
            locked_text,
            reply_markup=get_unlock_keyboard(lang_code),
            parse_mode="HTML",
        )
        return

    # 3. Session is unlocked: show main menu
    if lang_code == "ru":
        ready_text = (
            f"🤖 <b>MyGemini Zero v2</b> готов к работе!\n\n"
            "Сейф разблокирован. Задайте любой вопрос, отправьте голосовое сообщение, фото или документ."
        )
    else:
        ready_text = (
            f"🤖 <b>MyGemini Zero v2</b> is ready!\n\n"
            "Vault is unlocked. Ask any question, send voice message, photo, or document."
        )

    await message.answer(
        ready_text,
        reply_markup=get_main_menu_keyboard(is_unlocked=True, is_admin=is_admin, lang_code=lang_code),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "back_to_main")
async def handle_back_to_main(callback: CallbackQuery, state: FSMContext):
    """Returns to the primary main menu safely, clearing any lingering FSM states."""
    await safe_answer_callback(callback)
    await state.clear()
    await state.update_data(_active_menu_msg_id=callback.message.message_id)
    user_id = callback.from_user.id
    is_unlocked = session_manager.is_unlocked(user_id)
    is_admin = (user_id == settings.ADMIN_USER_ID)

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    menu_title = (
        "Главное меню управления <b>MyGemini Zero v2</b>:"
        if lang_code == "ru"
        else "Main Menu of <b>MyGemini Zero v2</b>:"
    )

    await safe_edit_message_text(
        message=callback.message,
        text=menu_title,
        reply_markup=get_main_menu_keyboard(is_unlocked=is_unlocked, is_admin=is_admin, lang_code=lang_code),
        parse_mode="HTML",
    )

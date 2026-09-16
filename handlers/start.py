"""
Start and Onboarding Handler for MyGemini Zero v2.
Handles /start, user registration, first interaction setup, and main navigation.
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart

from core.config import settings
from core.database import async_session_maker
from database.repositories import UserRepository
from keyboards.inline import (
    get_main_menu_keyboard,
    get_set_password_keyboard,
    get_unlock_keyboard,
)
from middlewares.auth import session_manager
from core.logger import get_logger

logger = get_logger("user_messages")
router = Router(name="start")


@router.message(CommandStart())
async def handle_start(message: Message):
    """Entry point for /start command."""
    user = message.from_user
    if not user:
        return

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        db_user, is_new = await user_repo.add_or_update_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            lang_code=user.language_code,
        )

        has_password = await user_repo.is_master_password_set(user.id)

    # 1. New user onboarding: prompt to set master password
    if not has_password:
        await message.answer(
            f"👋 Здравствуйте, <b>{user.first_name}</b>!\n\n"
            "Добро пожаловать в <b>MyGemini Zero v2</b> — приватного AI-ассистента с архитектурой <b>Zero-Knowledge</b>.\n\n"
            "🔒 <b>Как это устроено:</b>\n"
            "• Вся ваша переписка и Google API-ключ шифруются вашим мастер-паролем.\n"
            "• Пароль никогда не отправляется на сервер и не хранится в открытом виде.\n"
            "• Без вашего мастер-пароля прочитать сообщения невозможно даже разработчикам бота.\n\n"
            "Для начала работы установите ваш <b>мастер-пароль</b>. "
            "Нажмите кнопку ниже, чтобы ввести его безопасно во всплывающем окне:",
            reply_markup=get_set_password_keyboard(),
            parse_mode="HTML",
        )
        return

    # 2. Existing user check session state
    is_unlocked = session_manager.is_unlocked(user.id)
    is_admin = user.id == settings.ADMIN_USER_ID

    if not is_unlocked:
        await message.answer(
            f"👋 С возвращением, <b>{user.first_name}</b>!\n\n"
            "🔐 Ваше хранилище заблокировано для обеспечения конфиденциальности.\n"
            "Введите мастер-пароль, чтобы расшифровать диалоги и продолжить общение с AI:",
            reply_markup=get_unlock_keyboard(),
            parse_mode="HTML",
        )
        return

    # 3. Session is unlocked: show main menu
    await message.answer(
        f"🤖 <b>MyGemini Zero v2</b> готов к работе!\n\n"
        "Сейф разблокирован. Задайте любой вопрос, отправьте голосовое сообщение, фото или документ.",
        reply_markup=get_main_menu_keyboard(is_unlocked=True, is_admin=is_admin),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "back_to_main")
async def handle_back_to_main(callback: CallbackQuery):
    """Returns to the primary main menu."""
    await callback.answer()
    user_id = callback.from_user.id
    is_unlocked = session_manager.is_unlocked(user_id)
    is_admin = user_id == settings.ADMIN_USER_ID

    await callback.message.edit_text(
        "Главное меню управления <b>MyGemini Zero v2</b>:",
        reply_markup=get_main_menu_keyboard(is_unlocked=is_unlocked, is_admin=is_admin),
        parse_mode="HTML",
    )

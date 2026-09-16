"""
Authentication & Zero-Knowledge Vault Handler for MyGemini Zero v2.
Processes WebApp modal inputs (masked with dots) and secure chat fallbacks.
Handles master password setup, vault unlock, panic wipe, and session lock.
"""

import json
import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from core.database import async_session_maker
from database.repositories import UserRepository, ConversationRepository
from core.crypto import get_fernet_instance
from middlewares.auth import session_manager
from keyboards.inline import (
    get_main_menu_keyboard,
    get_unlock_keyboard,
    get_set_password_keyboard,
    get_api_key_input_keyboard,
)
from core.config import settings
from core.logger import get_logger

logger = get_logger("user_messages")
router = Router(name="auth")


class AuthStates(StatesGroup):
    waiting_for_password_setup = State()
    waiting_for_password_unlock = State()
    waiting_for_api_key = State()
    waiting_for_panic_setup = State()


@router.message(F.web_app_data)
async def handle_webapp_data(message: Message, state: FSMContext):
    """
    Receives data securely submitted from the Telegram WebApp modal popup.
    Input in the popup is masked with dots (••••••) and never appears in chat history.
    """
    user_id = message.from_user.id
    raw_data = message.web_app_data.data

    try:
        payload = json.loads(raw_data)
    except Exception as e:
        logger.error(f"Invalid JSON from WebApp: {e}")
        await message.answer("❌ Ошибка обработки данных из веб-окна.")
        return

    action = payload.get("action")
    value = payload.get("value", "").strip()

    if not value:
        await message.answer("⚠️ Введено пустое значение.")
        return

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        conv_repo = ConversationRepository(session)

        # 1. Action: Password (Setup or Unlock)
        if action == "password":
            has_password = await user_repo.is_master_password_set(user_id)

            if not has_password:
                # Setting password for the first time
                await user_repo.set_master_password(user_id, value)
                salt = await user_repo.get_salt(user_id)
                fernet = get_fernet_instance(value, salt)
                session_manager.unlock_session(user_id, fernet)

                await message.answer(
                    "✅ <b>Мастер-пароль успешно установлен!</b>\n\n"
                    "Ваше хранилище активировано и разблокировано. Теперь все сообщения и ключи шифруются на лету.\n\n"
                    "⚠️ <i>Обязательно запомните или сохраните мастер-пароль. Если вы его забудете, "
                    "восстановить доступ к сохранённым диалогам будет невозможно!</i>",
                    reply_markup=get_main_menu_keyboard(is_unlocked=True, is_admin=(user_id == settings.ADMIN_USER_ID)),
                    parse_mode="HTML",
                )
                return

            # Check if panic password was entered
            if await user_repo.verify_panic_password(user_id, value):
                # Panic wipe triggered!
                await conv_repo.clear_user_data(user_id)
                session_manager.lock_session(user_id)
                await message.answer(
                    "🚨 <b>Аварийный сброс выполнен.</b>\n"
                    "Все диалоги, сообщения, профиль и ключи были безвозвратно удалены из базы данных.",
                    parse_mode="HTML",
                )
                return

            # Normal unlock
            if await user_repo.verify_master_password(user_id, value):
                salt = await user_repo.get_salt(user_id)
                fernet = get_fernet_instance(value, salt)
                session_manager.unlock_session(user_id, fernet)

                await message.answer(
                    "🔓 <b>Сейф успешно разблокирован!</b>\n"
                    "Сессия активна. Диалоги расшифрованы и готовы к продолжению.",
                    reply_markup=get_main_menu_keyboard(is_unlocked=True, is_admin=(user_id == settings.ADMIN_USER_ID)),
                    parse_mode="HTML",
                )
            else:
                await message.answer(
                    "❌ <b>Неверный мастер-пароль!</b>\nПопробуйте ещё раз:",
                    reply_markup=get_unlock_keyboard(),
                    parse_mode="HTML",
                )

        # 2. Action: Set API Key
        elif action == "apikey":
            fernet = session_manager.get_fernet(user_id)
            if not fernet:
                await message.answer(
                    "🔒 Сначала разблокируйте сейф мастер-паролем, чтобы зашифровать ключ.",
                    reply_markup=get_unlock_keyboard(),
                )
                return

            await user_repo.set_api_key(user_id, value, fernet)
            await message.answer(
                "🔑 <b>API-ключ Google Gemini успешно сохранён!</b>\n\n"
                "Ключ зашифрован вашим мастер-паролем (Zero-Knowledge) и надёжно сохранён.",
                reply_markup=get_main_menu_keyboard(is_unlocked=True, is_admin=(user_id == settings.ADMIN_USER_ID)),
                parse_mode="HTML",
            )

        # 3. Action: Panic Password Setup
        elif action == "panic":
            await user_repo.set_panic_password(user_id, value)
            await message.answer(
                "🚨 <b>Паник-пароль успешно установлен!</b>\n\n"
                "Если в окне ввода мастер-пароля ввести этот паник-пароль, бот моментально и безвозвратно сотрёт "
                "всю историю сообщений, файлы памяти и ключи.",
                reply_markup=get_main_menu_keyboard(is_unlocked=True, is_admin=(user_id == settings.ADMIN_USER_ID)),
                parse_mode="HTML",
            )


@router.callback_query(F.data == "vault_lock")
async def handle_vault_lock(callback: CallbackQuery):
    """Locks the vault immediately and purges keys from memory."""
    user_id = callback.from_user.id
    session_manager.lock_session(user_id)

    await callback.message.edit_text(
        "🔒 <b>Сейф заблокирован.</b>\n"
        "Ключи дешифрования удалены из оперативной памяти. Для продолжения введите мастер-пароль:",
        reply_markup=get_unlock_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer("Сейф заблокирован")


@router.callback_query(F.data == "vault_unlock_chat")
async def handle_vault_unlock_chat_prompt(callback: CallbackQuery, state: FSMContext):
    """Fallback prompt for unlocking via chat."""
    await state.set_state(AuthStates.waiting_for_password_unlock)
    await callback.message.edit_text(
        "⌨️ Введите ваш мастер-пароль в чат.\n\n"
        "ℹ️ <i>Ваше сообщение с паролем будет автоматически удалено ботом через долю секунды, "
        "чтобы не оставаться в истории переписки.</i>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AuthStates.waiting_for_password_unlock)
async def process_chat_password_unlock(message: Message, state: FSMContext):
    """Processes chat fallback password entry and deletes the message immediately."""
    user_id = message.from_user.id
    password = message.text.strip() if message.text else ""

    # Instant deletion of password message
    try:
        await asyncio.sleep(0.25)
        await message.delete()
    except Exception:
        pass

    await state.clear()

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        conv_repo = ConversationRepository(session)

        # Check panic password first
        if await user_repo.verify_panic_password(user_id, password):
            await conv_repo.clear_user_data(user_id)
            session_manager.lock_session(user_id)
            await message.answer("🚨 <b>Аварийный сброс выполнен.</b> Все данные удалены.")
            return

        if await user_repo.verify_master_password(user_id, password):
            salt = await user_repo.get_salt(user_id)
            fernet = get_fernet_instance(password, salt)
            session_manager.unlock_session(user_id, fernet)

            await message.answer(
                "🔓 <b>Сейф успешно разблокирован!</b>",
                reply_markup=get_main_menu_keyboard(is_unlocked=True, is_admin=(user_id == settings.ADMIN_USER_ID)),
                parse_mode="HTML",
            )
        else:
            await message.answer(
                "❌ <b>Неверный мастер-пароль.</b> Попробуйте ещё раз:",
                reply_markup=get_unlock_keyboard(),
                parse_mode="HTML",
            )


@router.callback_query(F.data == "vault_setup_chat")
async def handle_vault_setup_chat_prompt(callback: CallbackQuery, state: FSMContext):
    """Fallback prompt for setting password via chat."""
    await state.set_state(AuthStates.waiting_for_password_setup)
    await callback.message.edit_text(
        "⌨️ Введите новый мастер-пароль в чат.\n\n"
        "ℹ️ <i>Сообщение будет мгновенно удалено сразу после прочтения.</i>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AuthStates.waiting_for_password_setup)
async def process_chat_password_setup(message: Message, state: FSMContext):
    """Sets master password from chat input."""
    user_id = message.from_user.id
    password = message.text.strip() if message.text else ""

    try:
        await asyncio.sleep(0.25)
        await message.delete()
    except Exception:
        pass

    await state.clear()

    if len(password) < 4:
        await message.answer("⚠️ Пароль слишком короткий (минимум 4 символа).", reply_markup=get_set_password_keyboard())
        return

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        await user_repo.set_master_password(user_id, password)
        salt = await user_repo.get_salt(user_id)
        fernet = get_fernet_instance(password, salt)
        session_manager.unlock_session(user_id, fernet)

    await message.answer(
        "✅ <b>Мастер-пароль установлен!</b>\n\nСейф активирован и разблокирован.",
        reply_markup=get_main_menu_keyboard(is_unlocked=True, is_admin=(user_id == settings.ADMIN_USER_ID)),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "api_key_chat_input")
async def handle_api_key_chat_prompt(callback: CallbackQuery, state: FSMContext):
    """Fallback chat input for API key."""
    await state.set_state(AuthStates.waiting_for_api_key)
    await callback.message.edit_text(
        "⌨️ Отправьте ваш Google Gemini API-ключ ответным сообщением.\n\n"
        "ℹ️ <i>Ключ будет удален из чата сразу после сохранения.</i>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AuthStates.waiting_for_api_key)
async def process_chat_api_key(message: Message, state: FSMContext):
    """Saves API key from chat."""
    user_id = message.from_user.id
    api_key = message.text.strip() if message.text else ""

    try:
        await asyncio.sleep(0.25)
        await message.delete()
    except Exception:
        pass

    await state.clear()

    fernet = session_manager.get_fernet(user_id)
    if not fernet:
        await message.answer("🔒 Сейф заблокирован. Разблокируйте его для сохранения ключа.", reply_markup=get_unlock_keyboard())
        return

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        await user_repo.set_api_key(user_id, api_key, fernet)

    await message.answer(
        "🔑 <b>API-ключ сохранён и зашифрован!</b>",
        reply_markup=get_main_menu_keyboard(is_unlocked=True, is_admin=(user_id == settings.ADMIN_USER_ID)),
        parse_mode="HTML",
    )

"""
Authentication & Zero-Knowledge Vault Handler for MyGemini Zero v2.
Processes secure chat inputs and WebApp modal data.
Handles two-step master password setup, two-step panic password setup,
vault unlock, panic wipe, and session lock.
Provides instant deletion of secret messages and Cancel buttons on all prompts.
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
    get_cancel_keyboard,
    get_close_button,
)
from keyboards.reply import get_main_reply_keyboard, get_locked_reply_keyboard, get_setup_reply_keyboard
from core.ui_helpers import safe_edit_message_text, safe_answer_callback
from core.localization import get_text
from core.config import settings
from core.logger import get_logger

logger = get_logger("user_messages")
router = Router(name="auth")


class AuthStates(StatesGroup):
    waiting_for_password_setup = State()
    waiting_for_password_confirm = State()
    waiting_for_password_unlock = State()
    waiting_for_api_key = State()
    waiting_for_panic_setup = State()
    waiting_for_panic_confirm = State()


async def safe_instant_delete(message: Message):
    """Deletes sensitive message after a fraction of a second."""
    try:
        await asyncio.sleep(0.25)
        await message.delete()
    except Exception:
        pass


@router.message(F.web_app_data)
async def handle_webapp_data(message: Message, state: FSMContext):
    """
    Receives data securely submitted from the Telegram WebApp modal popup.
    Input in the popup is masked with dots (••••••) and never appears in chat history.
    """
    user_id = message.from_user.id
    raw_data = message.web_app_data.data if message.web_app_data else "{}"

    # Instantly delete the service message
    await safe_instant_delete(message)
    await state.clear()

    try:
        payload = json.loads(raw_data)
    except Exception as e:
        logger.error(f"Invalid JSON from WebApp: {e}")
        await message.answer("❌ Ошибка обработки данных из веб-окна.")
        return

    action = (payload.get("action") or "").strip().lower()
    value = (payload.get("value") or "").strip()

    if not value:
        await message.answer("⚠️ Введено пустое значение.")
        return

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        conv_repo = ConversationRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"
        is_admin = (user_id == settings.ADMIN_USER_ID)
        has_password = await user_repo.is_master_password_set(user_id)

        # 1. Action: Setup (Initial Master Password)
        if action in ("setup", "register") or (action == "password" and not has_password):
            if len(value) < 4:
                err_msg = (
                    "⚠️ Пароль слишком короткий (минимум 4 символа)."
                    if lang_code == "ru"
                    else "⚠️ Password too short (minimum 4 characters)."
                )
                await message.answer(err_msg, reply_markup=get_setup_reply_keyboard(lang_code))
                return

            await user_repo.set_master_password(user_id, value)
            salt = await user_repo.get_salt(user_id)
            fernet = get_fernet_instance(value, salt)
            session_manager.unlock_session(user_id, fernet)

            success_text = (
                "✅ <b>Мастер-пароль успешно установлен!</b>\n\n"
                "Ваше зашифрованное хранилище активировано и разблокировано. "
                "Теперь все сообщения и ключи шифруются на лету симметричным шифром Fernet.\n\n"
                "Задайте любой вопрос или отправьте файл для начала работы!"
                if lang_code == "ru"
                else "✅ <b>Master password set successfully!</b>\n\n"
                "Your encrypted vault is activated and unlocked. "
                "All messages and keys are encrypted on-the-fly using Fernet cipher.\n\n"
                "Ask any question or send a file to get started!"
            )
            await message.answer(
                success_text,
                reply_markup=get_main_reply_keyboard(is_admin=is_admin, lang_code=lang_code),
                parse_mode="HTML",
            )
            return

        # 2. Action: Unlock
        if action in ("unlock", "password"):
            # Check panic password first
            if await user_repo.verify_panic_password(user_id, value):
                await conv_repo.clear_user_data(user_id)
                session_manager.lock_session(user_id)
                panic_text = (
                    "🚨 <b>Аварийный сброс выполнен.</b>\n"
                    "Все диалоги, сообщения, профиль и ключи были безвозвратно удалены из базы данных."
                    if lang_code == "ru"
                    else "🚨 <b>Emergency wipe executed.</b>\n"
                    "All dialogues, messages, profile, and keys have been permanently wiped."
                )
                await message.answer(panic_text, reply_markup=get_locked_reply_keyboard(lang_code), parse_mode="HTML")
                return

            if await user_repo.verify_master_password(user_id, value):
                salt = await user_repo.get_salt(user_id)
                fernet = get_fernet_instance(value, salt)
                session_manager.unlock_session(user_id, fernet)

                unlock_text = (
                    "🔓 <b>Сейф успешно разблокирован!</b>\n\n"
                    "Ключи расшифровки загружены в память. Диалоги готовы к продолжению."
                    if lang_code == "ru"
                    else "🔓 <b>Vault unlocked successfully!</b>\n\n"
                    "Decryption keys loaded into memory. Dialogues are ready."
                )
                await message.answer(
                    unlock_text,
                    reply_markup=get_main_reply_keyboard(is_admin=is_admin, lang_code=lang_code),
                    parse_mode="HTML",
                )
            else:
                wrong_text = (
                    "❌ <b>Неверный мастер-пароль.</b> Попробуйте ещё раз:"
                    if lang_code == "ru"
                    else "❌ <b>Incorrect master password.</b> Please try again:"
                )
                await message.answer(
                    wrong_text,
                    reply_markup=get_locked_reply_keyboard(lang_code),
                    parse_mode="HTML",
                )
            return

        # 3. Action: API Key
        if action == "apikey":
            fernet = session_manager.get_fernet(user_id)
            if not fernet:
                locked_prompt = (
                    "🔒 Сейф заблокирован. Разблокируйте его для сохранения ключа."
                    if lang_code == "ru"
                    else "🔒 Vault is locked. Unlock it to save your key."
                )
                await message.answer(locked_prompt, reply_markup=get_locked_reply_keyboard(lang_code))
                return

            await user_repo.set_api_key(user_id, value, fernet)
            done_key = (
                "🔑 <b>API-ключ Google Gemini успешно сохранён!</b>\n\n"
                "Ключ зашифрован вашим мастер-паролем (Zero-Knowledge) и надёжно сохранён."
                if lang_code == "ru"
                else "🔑 <b>Google Gemini API key saved!</b>\n\n"
                "Key is encrypted with your master password (Zero-Knowledge) and securely saved."
            )
            await message.answer(
                done_key,
                reply_markup=get_main_reply_keyboard(is_admin=is_admin, lang_code=lang_code),
                parse_mode="HTML",
            )
            return

        # 4. Action: Panic Password Setup
        if action == "panic":
            await user_repo.set_panic_password(user_id, value)
            done_panic = (
                "🚨 <b>Паник-пароль успешно установлен!</b>\n\n"
                "Если в окне ввода мастер-пароля ввести этот паник-пароль, бот моментально и безвозвратно сотрёт "
                "всю историю сообщений, файлы памяти и ключи."
                if lang_code == "ru"
                else "🚨 <b>Panic password set successfully!</b>\n\n"
                "If entered during unlock, the bot will immediately and permanently erase all chat history and keys."
            )
            await message.answer(
                done_panic,
                reply_markup=get_main_reply_keyboard(is_admin=is_admin, lang_code=lang_code),
                parse_mode="HTML",
            )
            return


@router.callback_query(F.data == "vault_lock")
async def handle_vault_lock(callback: CallbackQuery):
    """Locks the vault immediately and purges keys from memory."""
    await safe_answer_callback(callback)
    user_id = callback.from_user.id
    session_manager.lock_session(user_id)

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    text = (
        "🔒 <b>Сейф заблокирован.</b>\n"
        "Ключи дешифрования удалены из оперативной памяти сервера.\n"
        "Для разблокировки введите ваш мастер-пароль:"
        if lang_code == "ru"
        else "🔒 <b>Vault locked.</b>\n"
        "Decryption keys have been purged from memory.\n"
        "Enter your master password to unlock:"
    )

    await safe_edit_message_text(
        callback.message,
        text,
        reply_markup=get_unlock_keyboard(lang_code),
        parse_mode="HTML",
    )
    try:
        await callback.message.answer(
            "🔐 Введите мастер-пароль:" if lang_code == "ru" else "🔐 Enter master password:",
            reply_markup=get_locked_reply_keyboard(lang_code),
        )
    except Exception:
        pass


@router.callback_query(F.data == "vault_unlock_chat")
async def handle_vault_unlock_chat_prompt(callback: CallbackQuery, state: FSMContext):
    """Prompt for unlocking via chat."""
    await safe_answer_callback(callback)
    await state.set_state(AuthStates.waiting_for_password_unlock)
    user_id = callback.from_user.id

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    prompt = (
        "⌨️ <b>Введите ваш мастер-пароль в чат:</b>\n\n"
        "ℹ️ <i>Ваше сообщение с паролем будет автоматически удалено ботом через долю секунды, "
        "чтобы не оставаться в истории переписки.</i>"
        if lang_code == "ru"
        else "⌨️ <b>Enter your master password in chat:</b>\n\n"
        "ℹ️ <i>Your password message will be automatically deleted in a fraction of a second.</i>"
    )

    await safe_edit_message_text(
        callback.message,
        prompt,
        reply_markup=get_cancel_keyboard(callback_data="back_to_main", lang_code=lang_code),
        parse_mode="HTML",
    )


@router.message(AuthStates.waiting_for_password_unlock)
async def process_chat_password_unlock(message: Message, state: FSMContext):
    """Processes chat fallback password entry and deletes the message immediately."""
    user_id = message.from_user.id
    password = message.text.strip() if message.text else ""
    await safe_instant_delete(message)
    await state.clear()

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"
        conv_repo = ConversationRepository(session)

        # 1. Check panic password first
        if await user_repo.verify_panic_password(user_id, password):
            await conv_repo.clear_user_data(user_id)
            session_manager.lock_session(user_id)
            msg = (
                "🚨 <b>Аварийный сброс выполнен.</b>\n"
                "Все диалоги, сообщения, профиль и ключи были безвозвратно удалены из базы данных."
                if lang_code == "ru"
                else "🚨 <b>Emergency wipe executed.</b>\n"
                "All dialogues, messages, profile, and keys have been permanently wiped."
            )
            await message.answer(msg, parse_mode="HTML")
            return

        # 2. Check master password
        if await user_repo.verify_master_password(user_id, password):
            salt = await user_repo.get_salt(user_id)
            fernet = get_fernet_instance(password, salt)
            session_manager.unlock_session(user_id, fernet)

            success_text = (
                "🔓 <b>Сейф успешно разблокирован!</b>\n"
                "Сессия активна. Диалоги расшифрованы и готовы к продолжению."
                if lang_code == "ru"
                else "🔓 <b>Vault successfully unlocked!</b>\n"
                "Session active. Dialogues decrypted and ready."
            )
            await message.answer(
                success_text,
                reply_markup=get_main_reply_keyboard(is_admin=(user_id == settings.ADMIN_USER_ID), lang_code=lang_code),
                parse_mode="HTML",
            )
        else:
            fail_text = (
                "❌ <b>Неверный мастер-пароль!</b>\nПопробуйте ещё раз:"
                if lang_code == "ru"
                else "❌ <b>Incorrect master password!</b>\nPlease try again:"
            )
            await message.answer(
                fail_text,
                reply_markup=get_unlock_keyboard(lang_code),
                parse_mode="HTML",
            )
            try:
                await message.answer(
                    "🔐 Введите мастер-пароль в окне или в чате:" if lang_code == "ru" else "🔐 Enter master password in window or chat:",
                    reply_markup=get_locked_reply_keyboard(lang_code),
                )
            except Exception:
                pass


@router.callback_query(F.data == "vault_setup_chat")
async def handle_vault_setup_chat_prompt(callback: CallbackQuery, state: FSMContext):
    """Step 1 prompt for setting master password via chat."""
    await safe_answer_callback(callback)
    await state.set_state(AuthStates.waiting_for_password_setup)
    user_id = callback.from_user.id

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    prompt = (
        "🔐 <b>Создание мастер-пароля (Шаг 1 из 2):</b>\n\n"
        "Придумайте и введите ваш <b>мастер-пароль</b> в чат.\n\n"
        "⚠️ <i>Минимум 4 символа. Сообщение будет мгновенно удалено сразу после прочтения.</i>"
        if lang_code == "ru"
        else "🔐 <b>Create Master Password (Step 1 of 2):</b>\n\n"
        "Enter your new <b>master password</b> in chat.\n\n"
        "⚠️ <i>Minimum 4 characters. The message will be instantly deleted.</i>"
    )

    await safe_edit_message_text(
        callback.message,
        prompt,
        reply_markup=get_cancel_keyboard(callback_data="close_menu", lang_code=lang_code),
        parse_mode="HTML",
    )


@router.message(AuthStates.waiting_for_password_setup)
async def process_chat_password_setup(message: Message, state: FSMContext):
    """Step 1: receives candidate password, prompts for confirmation."""
    user_id = message.from_user.id
    password = message.text.strip() if message.text else ""
    await safe_instant_delete(message)

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    if len(password) < 4:
        too_short = (
            "⚠️ Пароль слишком короткий (минимум 4 символа). Попробуйте снова:"
            if lang_code == "ru"
            else "⚠️ Password too short (minimum 4 characters). Try again:"
        )
        await message.answer(too_short, reply_markup=get_cancel_keyboard(callback_data="close_menu", lang_code=lang_code))
        return

    await state.update_data(candidate_master_password=password)
    await state.set_state(AuthStates.waiting_for_password_confirm)

    confirm_prompt = (
        "🔐 <b>Подтверждение пароля (Шаг 2 из 2):</b>\n\n"
        "Отлично! А теперь, для подтверждения, <b>введите этот же пароль ещё раз</b>.\n\n"
        "❗️ <i>ВАЖНО: Если вы забудете этот пароль, восстановить доступ к диалогам будет НЕВОЗМОЖНО. "
        "У нас нет функции сброса пароля!</i>"
        if lang_code == "ru"
        else "🔐 <b>Confirm Password (Step 2 of 2):</b>\n\n"
        "Great! Now, for confirmation, <b>enter this same password once more</b>.\n\n"
        "❗️ <i>IMPORTANT: If you forget this password, recovering your data is IMPOSSIBLE. "
        "There is no password reset feature!</i>"
    )

    await message.answer(
        confirm_prompt,
        reply_markup=get_cancel_keyboard(callback_data="close_menu", lang_code=lang_code),
        parse_mode="HTML",
    )


@router.message(AuthStates.waiting_for_password_confirm)
async def process_chat_password_confirm(message: Message, state: FSMContext):
    """Step 2: verifies password confirmation and saves it."""
    user_id = message.from_user.id
    confirm_password = message.text.strip() if message.text else ""
    await safe_instant_delete(message)

    data = await state.get_data()
    candidate = data.get("candidate_master_password", "")
    await state.clear()

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    if confirm_password != candidate:
        mismatch_text = (
            "❌ <b>Пароли не совпадают!</b>\nПожалуйста, начните установку пароля заново."
            if lang_code == "ru"
            else "❌ <b>Passwords do not match!</b>\nPlease start password setup again."
        )
        await message.answer(
            mismatch_text,
            reply_markup=get_set_password_keyboard(lang_code),
            parse_mode="HTML",
        )
        return

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        await user_repo.set_master_password(user_id, confirm_password)
        salt = await user_repo.get_salt(user_id)
        fernet = get_fernet_instance(confirm_password, salt)
        session_manager.unlock_session(user_id, fernet)

    success_text = (
        "✅ <b>Мастер-пароль успешно установлен!</b>\n\n"
        "Ваше зашифрованное хранилище активировано и разблокировано. "
        "Теперь все сообщения и ключи шифруются на лету симметричным шифром Fernet.\n\n"
        "Задайте любой вопрос или отправьте файл для начала работы!"
        if lang_code == "ru"
        else "✅ <b>Master password successfully set!</b>\n\n"
        "Your encrypted vault is activated and unlocked. "
        "All conversations and keys are now encrypted on the fly.\n\n"
        "Ask any question or send a file to begin!"
    )

    await message.answer(
        success_text,
        reply_markup=get_main_menu_keyboard(is_unlocked=True, is_admin=(user_id == settings.ADMIN_USER_ID), lang_code=lang_code),
        parse_mode="HTML",
    )
    try:
        await message.answer(
            "⌨️ Главное меню:" if lang_code == "ru" else "⌨️ Main Menu:",
            reply_markup=get_main_reply_keyboard(is_admin=(user_id == settings.ADMIN_USER_ID), lang_code=lang_code),
        )
    except Exception:
        pass


@router.callback_query(F.data == "panic_setup_start")
async def handle_panic_setup_start(callback: CallbackQuery, state: FSMContext):
    """Step 1 prompt for panic password setup."""
    await safe_answer_callback(callback)
    await state.set_state(AuthStates.waiting_for_panic_setup)
    user_id = callback.from_user.id

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    prompt = (
        "🚨 <b>Установка паник-пароля (Шаг 1 из 2):</b>\n\n"
        "Придумайте и введите ваш <b>пароль паники</b> в чат.\n\n"
        "⚠️ <b>Важно:</b> он <i>не должен</i> совпадать с вашим основным мастер-паролем."
        if lang_code == "ru"
        else "🚨 <b>Set Panic Password (Step 1 of 2):</b>\n\n"
        "Enter your <b>panic password</b> in chat.\n\n"
        "⚠️ <b>Important:</b> it <i>must not</i> match your master password."
    )

    await safe_edit_message_text(
        callback.message,
        prompt,
        reply_markup=get_cancel_keyboard(callback_data="menu_settings", lang_code=lang_code),
        parse_mode="HTML",
    )


@router.message(AuthStates.waiting_for_panic_setup)
async def process_chat_panic_setup(message: Message, state: FSMContext):
    """Step 1 of panic setup: checks candidate, requests confirmation."""
    user_id = message.from_user.id
    panic_pwd = message.text.strip() if message.text else ""
    await safe_instant_delete(message)

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

        if await user_repo.verify_master_password(user_id, panic_pwd):
            same_err = (
                "❌ Пароль паники не может совпадать с вашим основным мастер-паролем. Придумайте другой:"
                if lang_code == "ru"
                else "❌ Panic password cannot match your main master password. Try another one:"
            )
            await message.answer(same_err, reply_markup=get_cancel_keyboard(callback_data="menu_settings", lang_code=lang_code))
            return

    if len(panic_pwd) < 4:
        too_short = "⚠️ Пароль паники слишком короткий (минимум 4 символа)." if lang_code == "ru" else "⚠️ Panic password too short (minimum 4 characters)."
        await message.answer(too_short, reply_markup=get_cancel_keyboard(callback_data="menu_settings", lang_code=lang_code))
        return

    await state.update_data(candidate_panic=panic_pwd)
    await state.set_state(AuthStates.waiting_for_panic_confirm)

    confirm_prompt = (
        "🚨 <b>Подтверждение паник-пароля (Шаг 2 из 2):</b>\n\n"
        "Пожалуйста, введите пароль паники ещё раз для подтверждения:"
        if lang_code == "ru"
        else "🚨 <b>Confirm Panic Password (Step 2 of 2):</b>\n\n"
        "Please enter your panic password once more for confirmation:"
    )

    await message.answer(
        confirm_prompt,
        reply_markup=get_cancel_keyboard(callback_data="menu_settings", lang_code=lang_code),
        parse_mode="HTML",
    )


@router.message(AuthStates.waiting_for_panic_confirm)
async def process_chat_panic_confirm(message: Message, state: FSMContext):
    """Step 2 of panic setup: verifies confirmation and saves panic password."""
    user_id = message.from_user.id
    confirm_pwd = message.text.strip() if message.text else ""
    await safe_instant_delete(message)

    data = await state.get_data()
    candidate = data.get("candidate_panic", "")
    await state.clear()

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    if confirm_pwd != candidate:
        mismatch = (
            "❌ Пароли паники не совпадают. Начните настройку заново."
            if lang_code == "ru"
            else "❌ Panic passwords do not match. Please restart setup."
        )
        await message.answer(mismatch, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[get_close_button(lang_code)]]))
        return

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        await user_repo.set_panic_password(user_id, confirm_pwd)

    success_msg = (
        "✅ <b>Пароль паники успешно установлен!</b>\n\n"
        "Если в окне ввода пароля ввести этот паник-пароль, бот моментально "
        "сотрёт всю историю переписки, файлы векторной памяти и ваш API-ключ."
        if lang_code == "ru"
        else "✅ <b>Panic password successfully set!</b>\n\n"
        "If entered upon unlock, the bot will immediately wipe all dialogues, vector memory, and your API key."
    )

    await message.answer(
        success_msg,
        reply_markup=get_main_menu_keyboard(is_unlocked=True, is_admin=(user_id == settings.ADMIN_USER_ID), lang_code=lang_code),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "api_key_chat_input")
async def handle_api_key_chat_prompt(callback: CallbackQuery, state: FSMContext):
    """Fallback chat input for API key."""
    await safe_answer_callback(callback)
    await state.set_state(AuthStates.waiting_for_api_key)
    user_id = callback.from_user.id

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    prompt = (
        "⌨️ <b>Отправьте ваш Google Gemini API-ключ:</b>\n\n"
        "Ключ начинается на <code>AIzaSy...</code>.\n\n"
        "ℹ️ <i>Сообщение будет мгновенно удалено сразу после сохранения.</i>"
        if lang_code == "ru"
        else "⌨️ <b>Send your Google Gemini API key:</b>\n\n"
        "The key starts with <code>AIzaSy...</code>.\n\n"
        "ℹ️ <i>The message will be deleted instantly after saving.</i>"
    )

    await safe_edit_message_text(
        callback.message,
        prompt,
        reply_markup=get_cancel_keyboard(callback_data="menu_settings", lang_code=lang_code),
        parse_mode="HTML",
    )


@router.message(AuthStates.waiting_for_api_key)
async def process_chat_api_key(message: Message, state: FSMContext):
    """Saves API key from chat."""
    user_id = message.from_user.id
    api_key = message.text.strip() if message.text else ""
    await safe_instant_delete(message)
    await state.clear()

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    fernet = session_manager.get_fernet(user_id)
    if not fernet:
        err = "🔒 Сейф заблокирован. Разблокируйте его для сохранения ключа." if lang_code == "ru" else "🔒 Vault is locked."
        await message.answer(err, reply_markup=get_unlock_keyboard(lang_code))
        return

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        await user_repo.set_api_key(user_id, api_key, fernet)

    done = (
        "🔑 <b>API-ключ Google Gemini успешно сохранён и зашифрован!</b>"
        if lang_code == "ru"
        else "🔑 <b>Google Gemini API key saved and encrypted!</b>"
    )
    await message.answer(
        done,
        reply_markup=get_main_menu_keyboard(is_unlocked=True, is_admin=(user_id == settings.ADMIN_USER_ID), lang_code=lang_code),
        parse_mode="HTML",
    )

"""
Settings Handler for MyGemini Zero v2.
Manages AI model selection with Google Search badges (🌐),
persona switching, communication styles, language (RU/EN), and API key configuration.
Includes panic password configuration and safe message editing.
"""

from typing import Tuple
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from core.database import async_session_maker
from database.repositories import UserRepository
from services.gemini import GeminiService
from keyboards.inline import (
    get_settings_keyboard,
    get_models_keyboard,
    get_styles_keyboard,
    get_personas_keyboard,
    get_api_key_input_keyboard,
    get_language_keyboard,
    get_unlock_keyboard,
    get_close_button,
)
from keyboards.reply import get_main_reply_keyboard
from core.config import settings, BOT_STYLES, BOT_PERSONAS
from middlewares.auth import session_manager
from core.ui_helpers import safe_edit_message_text, safe_answer_callback
from core.localization import get_text
from core.logger import get_logger

logger = get_logger("user_messages")
router = Router(name="settings")


async def render_settings_view(user_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    """Generates text and inline keyboard for the settings menu."""
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        has_api_key = await user_repo.is_api_key_set(user_id)

    lang_code = user.language_code if user and user.language_code else "ru"
    cur_model = (user.gemini_model if user and user.gemini_model else settings.DEFAULT_MODEL_ID)
    cur_style = BOT_STYLES.get(user.bot_style if user else "default", "🤖 По умолчанию")
    persona_dict = BOT_PERSONAS.get(user.active_persona if user else "default", {})
    cur_persona = persona_dict.get("name_ru", "🤖 Обычный") if lang_code == "ru" else persona_dict.get("name_en", "🤖 Normal")

    if lang_code == "ru":
        key_status = "✅ Установлен" if has_api_key else "❌ Не установлен"
        lang_str = "🇷🇺 Русский"
        text = (
            "⚙️ <b>Настройки AI-ассистента:</b>\n\n"
            f"• <b>Модель:</b> <code>{cur_model}</code>\n"
            f"• <b>Персона:</b> {cur_persona}\n"
            f"• <b>Стиль:</b> {cur_style}\n"
            f"• <b>Язык:</b> {lang_str}\n"
            f"• <b>API-ключ:</b> {key_status}\n\n"
            "Выберите параметр для изменения:"
        )
    else:
        key_status = "✅ Set" if has_api_key else "❌ Not set"
        lang_str = "🇬🇧 English"
        text = (
            "⚙️ <b>AI Assistant Settings:</b>\n\n"
            f"• <b>Model:</b> <code>{cur_model}</code>\n"
            f"• <b>Persona:</b> {cur_persona}\n"
            f"• <b>Style:</b> {cur_style}\n"
            f"• <b>Language:</b> {lang_str}\n"
            f"• <b>API Key:</b> {key_status}\n\n"
            "Select setting to configure:"
        )

    keyboard = get_settings_keyboard(
        current_model=cur_model,
        current_style=cur_style,
        current_persona=cur_persona,
        has_api_key=has_api_key,
        lang_code=lang_code,
    )
    return text, keyboard


@router.callback_query(F.data == "menu_settings")
async def handle_settings_menu(callback: CallbackQuery, state: FSMContext | None = None):
    """Renders the settings menu with user preferences."""
    await safe_answer_callback(callback)
    if state:
        await state.clear()
    user_id = callback.from_user.id
    text, keyboard = await render_settings_view(user_id)
    await safe_edit_message_text(callback.message, text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "settings_language")
async def handle_settings_language(callback: CallbackQuery):
    """Renders language switcher."""
    await safe_answer_callback(callback)
    user_id = callback.from_user.id

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        current_lang = user.language_code if user and user.language_code else "ru"

    title = "🌐 <b>Выберите язык интерфейса / Select Language:</b>"
    await safe_edit_message_text(
        callback.message,
        title,
        reply_markup=get_language_keyboard(current_lang=current_lang, lang_code=current_lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("set_lang:"))
async def handle_set_language(callback: CallbackQuery):
    """Updates language in DB and refreshes settings and persistent keyboard."""
    user_id = callback.from_user.id
    new_lang = callback.data.split("set_lang:")[1]

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        await user_repo.update_settings(user_id=user_id, language_code=new_lang)

    is_admin = (user_id == settings.ADMIN_USER_ID)
    ans_text = "Язык изменён на Русский" if new_lang == "ru" else "Language changed to English"
    await safe_answer_callback(callback, text=ans_text)

    # Issue updated persistent Reply keyboard in new language
    try:
        await callback.message.answer(
            "⌨️ Клавиатура обновлена" if new_lang == "ru" else "⌨️ Keyboard updated",
            reply_markup=get_main_reply_keyboard(is_admin=is_admin, lang_code=new_lang),
        )
    except Exception:
        pass

    text, keyboard = await render_settings_view(user_id)
    await safe_edit_message_text(callback.message, text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "settings_panic")
async def handle_settings_panic(callback: CallbackQuery):
    """Shows panic password configuration menu."""
    await safe_answer_callback(callback)
    user_id = callback.from_user.id
    fernet = session_manager.get_fernet(user_id)

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    if not fernet:
        prompt_text = (
            "🔒 <b>Сейф заблокирован.</b>\n"
            "Для настройки паник-пароля сначала разблокируйте память мастер-паролем."
            if lang_code == "ru"
            else "🔒 <b>Vault is locked.</b>\n"
            "To configure panic password, please unlock memory with your master password first."
        )
        await safe_edit_message_text(
            callback.message,
            prompt_text,
            reply_markup=get_unlock_keyboard(lang_code),
            parse_mode="HTML",
        )
        return

    if lang_code == "ru":
        panic_text = (
            "🚨 <b>Настройка аварийного паник-пароля (Panic Wipe):</b>\n\n"
            "Паник-пароль используется в экстренных ситуациях.\n"
            "Если при разблокировке бота вы введёте этот пароль вместо основного мастер-пароля, "
            "бот моментально и безвозвратно <b>сотрёт всю историю диалогов, векторную память и ключи</b>, "
            "но сделает вид, что произошла обычная разблокировка.\n\n"
            "⚠️ <i>Паник-пароль не должен совпадать с вашим мастер-паролем.</i>"
        )
        btn_set = "⌨️ Установить новый паник-пароль"
        btn_back = "⬅️ Назад в настройки"
    else:
        panic_text = (
            "🚨 <b>Emergency Panic Password Configuration:</b>\n\n"
            "Panic password is for emergencies.\n"
            "If entered instead of your master password when unlocking, "
            "the bot immediately and irreversibly <b>wipes all dialogues, vector memory, and keys</b>, "
            "while pretending to unlock normally.\n\n"
            "⚠️ <i>Panic password must not match your master password.</i>"
        )
        btn_set = "⌨️ Set new panic password"
        btn_back = "⬅️ Back to Settings"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_set, callback_data="panic_setup_start")],
        [InlineKeyboardButton(text=btn_back, callback_data="menu_settings"), get_close_button(lang_code)],
    ])

    await safe_edit_message_text(callback.message, panic_text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "settings_models")
async def handle_settings_models(callback: CallbackQuery):
    """
    Fetches real-time models from Gemini API and marks search-capable models with 🌐.
    """
    await safe_answer_callback(callback)
    user_id = callback.from_user.id
    fernet = session_manager.get_fernet(user_id)

    api_key = None
    if fernet:
        async with async_session_maker() as session:
            user_repo = UserRepository(session)
            api_key = await user_repo.get_api_key(user_id, fernet)

    key_to_use = api_key or settings.DEFAULT_GEMINI_KEY
    gemini_svc = GeminiService(api_key=key_to_use)
    models = await gemini_svc.get_available_models()

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        current_model = user.gemini_model if user and user.gemini_model else settings.DEFAULT_MODEL_ID
        lang_code = user.language_code if user and user.language_code else "ru"

    title = (
        "🤖 <b>Выберите модель Gemini:</b>\n\n"
        "🌐 — модель поддерживает выход в интернет (Google Search).\n"
        "✅ — текущая выбранная модель."
        if lang_code == "ru"
        else "🤖 <b>Select Gemini Model:</b>\n\n"
        "🌐 — supports Google Search.\n"
        "✅ — currently selected model."
    )

    await safe_edit_message_text(
        callback.message,
        title,
        reply_markup=get_models_keyboard(models, current_model, lang_code=lang_code),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("set_model:"))
async def handle_set_model(callback: CallbackQuery):
    """Sets active Gemini model."""
    user_id = callback.from_user.id
    model_id = callback.data.split("set_model:")[1]

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        await user_repo.update_settings(user_id=user_id, model=model_id)

    await safe_answer_callback(callback, f"Модель: {model_id}")
    await handle_settings_menu(callback)


@router.callback_query(F.data == "settings_styles")
async def handle_settings_styles(callback: CallbackQuery):
    """Renders communication style selector."""
    await safe_answer_callback(callback)
    user_id = callback.from_user.id
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        current_style = user.bot_style if user else "default"
        lang_code = user.language_code if user and user.language_code else "ru"

    title = "🎨 <b>Выберите стиль ответов ассистента:</b>" if lang_code == "ru" else "🎨 <b>Select Assistant Communication Style:</b>"
    await safe_edit_message_text(
        callback.message,
        title,
        reply_markup=get_styles_keyboard(current_style, lang_code=lang_code),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("set_style:"))
async def handle_set_style(callback: CallbackQuery):
    """Sets communication style."""
    user_id = callback.from_user.id
    style_key = callback.data.split("set_style:")[1]

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        await user_repo.update_settings(user_id=user_id, style=style_key)

    await safe_answer_callback(callback, "Стиль обновлён")
    await handle_settings_menu(callback)


@router.callback_query(F.data == "settings_personas")
async def handle_settings_personas(callback: CallbackQuery):
    """Renders persona selector."""
    await safe_answer_callback(callback)
    user_id = callback.from_user.id
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        current_persona = user.active_persona if user else "default"
        lang_code = user.language_code if user and user.language_code else "ru"

    title = "🎭 <b>Выберите роль (персону) ассистента:</b>" if lang_code == "ru" else "🎭 <b>Select Assistant Persona:</b>"
    await safe_edit_message_text(
        callback.message,
        title,
        reply_markup=get_personas_keyboard(current_persona, lang_code=lang_code),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("set_persona:"))
async def handle_set_persona(callback: CallbackQuery):
    """Sets active persona."""
    user_id = callback.from_user.id
    persona_key = callback.data.split("set_persona:")[1]

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        await user_repo.update_settings(user_id=user_id, persona=persona_key)

    await safe_answer_callback(callback, "Персона обновлена")
    await handle_settings_menu(callback)


@router.callback_query(F.data == "settings_api_key")
async def handle_settings_api_key(callback: CallbackQuery):
    """Prompts user to enter their API key via chat."""
    await safe_answer_callback(callback)
    user_id = callback.from_user.id
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    if lang_code == "ru":
        text = (
            "🔑 <b>Установка Google Gemini API-ключа</b>\n\n"
            "Бот работает по модели <b>BYOK (Bring Your Own Key)</b>. "
            "Ваш ключ шифруется вашим мастер-паролем в базе данных.\n\n"
            "Нажмите кнопку ниже, чтобы ввести ключ:"
        )
    else:
        text = (
            "🔑 <b>Setting Google Gemini API Key</b>\n\n"
            "The bot operates on the <b>BYOK (Bring Your Own Key)</b> model. "
            "Your key is encrypted with your master password in the database.\n\n"
            "Click button below to enter key:"
        )

    await safe_edit_message_text(
        callback.message,
        text,
        reply_markup=get_api_key_input_keyboard(lang_code=lang_code),
        parse_mode="HTML",
    )

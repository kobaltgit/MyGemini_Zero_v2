"""
Settings Handler for MyGemini Zero v2.
Manages AI model selection with Google Search badges (🌐),
persona switching, communication styles, and API key configuration.
"""

from typing import Tuple
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup

from core.database import async_session_maker
from database.repositories import UserRepository
from services.gemini import GeminiService
from keyboards.inline import (
    get_settings_keyboard,
    get_models_keyboard,
    get_styles_keyboard,
    get_personas_keyboard,
    get_api_key_input_keyboard,
)
from core.config import settings, BOT_STYLES, BOT_PERSONAS
from middlewares.auth import session_manager

router = Router(name="settings")


async def render_settings_view(user_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    """Generates text and inline keyboard for the settings menu."""
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        has_api_key = await user_repo.is_api_key_set(user_id)

    cur_model = (user.gemini_model if user and user.gemini_model else settings.DEFAULT_MODEL_ID)
    cur_style = BOT_STYLES.get(user.bot_style if user else "default", "🤖 По умолчанию")
    cur_persona = BOT_PERSONAS.get(user.active_persona if user else "default", {}).get("name_ru", "🤖 Обычный")

    text = (
        "⚙️ <b>Настройки AI-ассистента:</b>\n\n"
        f"• <b>Модель:</b> <code>{cur_model}</code>\n"
        f"• <b>Персона:</b> {cur_persona}\n"
        f"• <b>Стиль:</b> {cur_style}\n"
        f"• <b>API-ключ:</b> {'✅ Установлен' if has_api_key else '❌ Не установлен'}\n\n"
        "Выберите параметр для изменения:"
    )
    keyboard = get_settings_keyboard(cur_model, cur_style, cur_persona, has_api_key)
    return text, keyboard


@router.callback_query(F.data == "menu_settings")
async def handle_settings_menu(callback: CallbackQuery):
    """Renders the settings menu with user preferences."""
    user_id = callback.from_user.id
    text, keyboard = await render_settings_view(user_id)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "settings_models")
async def handle_settings_models(callback: CallbackQuery):
    """
    Fetches real-time models from Gemini API and marks search-capable models with 🌐.
    """
    user_id = callback.from_user.id
    fernet = session_manager.get_fernet(user_id)

    api_key = None
    if fernet:
        async with async_session_maker() as session:
            user_repo = UserRepository(session)
            api_key = await user_repo.get_api_key(user_id, fernet)

    # Use user API key if unlocked, else fallback to default server key
    key_to_use = api_key or settings.DEFAULT_GEMINI_KEY
    gemini_svc = GeminiService(api_key=key_to_use)
    models = await gemini_svc.get_available_models()

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        current_model = user.gemini_model if user and user.gemini_model else settings.DEFAULT_MODEL_ID

    await callback.message.edit_text(
        "🤖 <b>Выберите модель Gemini:</b>\n\n"
        "🌐 — модель поддерживает выход в интернет (Google Search) и поиск актуальной информации.\n"
        "✅ — текущая выбранная модель.",
        reply_markup=get_models_keyboard(models, current_model),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_model:"))
async def handle_set_model(callback: CallbackQuery):
    """Sets active Gemini model."""
    user_id = callback.from_user.id
    model_id = callback.data.split("set_model:")[1]

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        await user_repo.update_settings(user_id=user_id, model=model_id)

    await callback.answer(f"Модель изменена на {model_id}")
    await handle_settings_menu(callback)


@router.callback_query(F.data == "settings_styles")
async def handle_settings_styles(callback: CallbackQuery):
    """Renders communication style selector."""
    user_id = callback.from_user.id
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        current_style = user.bot_style if user else "default"

    await callback.message.edit_text(
        "🎨 <b>Выберите стиль ответов ассистента:</b>",
        reply_markup=get_styles_keyboard(current_style),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_style:"))
async def handle_set_style(callback: CallbackQuery):
    """Sets communication style."""
    user_id = callback.from_user.id
    style_key = callback.data.split("set_style:")[1]

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        await user_repo.update_settings(user_id=user_id, style=style_key)

    await callback.answer("Стиль обновлён")
    await handle_settings_menu(callback)


@router.callback_query(F.data == "settings_personas")
async def handle_settings_personas(callback: CallbackQuery):
    """Renders persona selector."""
    user_id = callback.from_user.id
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        current_persona = user.active_persona if user else "default"

    await callback.message.edit_text(
        "🎭 <b>Выберите роль (персону) ассистента:</b>",
        reply_markup=get_personas_keyboard(current_persona),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_persona:"))
async def handle_set_persona(callback: CallbackQuery):
    """Sets active persona."""
    user_id = callback.from_user.id
    persona_key = callback.data.split("set_persona:")[1]

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        await user_repo.update_settings(user_id=user_id, persona=persona_key)

    await callback.answer("Персона обновлена")
    await handle_settings_menu(callback)


@router.callback_query(F.data == "settings_api_key")
async def handle_settings_api_key(callback: CallbackQuery):
    """Prompts user to enter their API key via WebApp popup or chat."""
    await callback.message.edit_text(
        "🔑 <b>Установка Google Gemini API-ключа</b>\n\n"
        "Бот работает по модели <b>BYOK (Bring Your Own Key)</b>. "
        "Ваш ключ шифруется вашим мастер-паролем в базе данных.\n\n"
        "Нажмите кнопку ниже, чтобы ввести ключ:",
        reply_markup=get_api_key_input_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()

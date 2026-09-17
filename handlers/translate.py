"""
Translation Mode Handler for MyGemini Zero v2.
Provides /translate command for fast text translation between Russian and English.
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from core.database import async_session_maker
from database.repositories import UserRepository
from services.gemini import GeminiService
from middlewares.auth import session_manager
from keyboards.inline import get_cancel_keyboard, get_close_button
from core.config import settings
from core.logger import get_logger

logger = get_logger("user_messages")
router = Router(name="translate")


class TranslateStates(StatesGroup):
    waiting_for_text = State()


@router.message(Command("translate"))
async def handle_translate_command(message: Message, state: FSMContext):
    """Entry point for /translate command."""
    try:
        await message.delete()
    except Exception:
        pass

    user_id = message.from_user.id
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    await state.set_state(TranslateStates.waiting_for_text)

    prompt = (
        "🌐 <b>Режим переводчика:</b>\n\n"
        "Отправьте текст, который хотите перевести. "
        "Бот автоматически определит язык и переведёт (Русский ↔ Английский):"
        if lang_code == "ru"
        else "🌐 <b>Translation Mode:</b>\n\n"
        "Send the text you want to translate. "
        "The bot will automatically detect language and translate (Russian ↔ English):"
    )

    await message.answer(
        prompt,
        reply_markup=get_cancel_keyboard(callback_data="close_menu", lang_code=lang_code),
        parse_mode="HTML",
    )


@router.message(TranslateStates.waiting_for_text)
async def process_translation(message: Message, state: FSMContext):
    """Translates user text using Gemini."""
    user_id = message.from_user.id
    text_to_translate = message.text.strip() if message.text else ""
    await state.clear()

    if not text_to_translate:
        await message.answer("⚠️ Пустой текст для перевода.")
        return

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    fernet = session_manager.get_fernet(user_id)
    api_key = None
    if fernet:
        async with async_session_maker() as session:
            user_repo = UserRepository(session)
            api_key = await user_repo.get_api_key(user_id, fernet)

    default_key = getattr(settings, "DEFAULT_GEMINI_KEY", None)
    key_to_use = api_key or default_key
    if not key_to_use:
        await message.answer(
            "🔒 <b>Сейф заблокирован или API-ключ не установлен.</b>\n"
            "Для использования переводчика разблокируйте память мастер-паролем или укажите ключ в настройках."
            if lang_code == "ru"
            else "🔒 <b>Vault is locked or API key not set.</b>\nTo use translator, unlock vault or set key in settings.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[get_close_button(lang_code)]]),
            parse_mode="HTML",
        )
        return

    gemini_svc = GeminiService(api_key=key_to_use)

    status_msg = await message.answer("⏳ Перевод..." if lang_code == "ru" else "⏳ Translating...")

    prompt = (
        f"You are a professional translator. Translate the following text. "
        f"If the text is in Russian, translate it into natural English. "
        f"If the text is in English or another language, translate it into Russian. "
        f"Return ONLY the translation without introductory notes:\n\n{text_to_translate}"
    )

    try:
        translated_text = ""
        async for chunk in gemini_svc.generate_stream(prompt=prompt, enable_search=False):
            translated_text += chunk
        await status_msg.edit_text(
            f"🌐 <b>Перевод:</b>\n\n{translated_text}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[get_close_button(lang_code)]]),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Error translating: {e}")
        await status_msg.edit_text(
            f"❌ Ошибка перевода: {e}" if lang_code == "ru" else f"❌ Translation error: {e}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[get_close_button(lang_code)]]),
        )

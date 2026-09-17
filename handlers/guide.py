"""
Interactive Guide & Documentation Handler for MyGemini Zero v2.
Delivers comprehensive markdown documentation (/guide, /apikey_info, /help_guide).
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from core.database import async_session_maker
from database.repositories import UserRepository
from services.guide_manager import get_full_guide, get_guide_section
from keyboards.inline import get_close_button
from core.ui_helpers import safe_edit_message_text, safe_answer_callback
from core.logger import get_logger

logger = get_logger("user_messages")
router = Router(name="guide")


def get_guide_menu_keyboard(lang_code: str = "ru") -> InlineKeyboardMarkup:
    """Builds interactive topic keyboard for documentation."""
    if lang_code == "ru":
        b_zk = "🔐 Zero-Knowledge"
        b_key = "🔑 API-ключ Gemini"
        b_rag = "📎 Векторная память (RAG)"
        b_models = "🤖 Выбор моделей"
        b_sub = "💎 Подписка и тарифы"
        b_cmds = "💬 Список команд"
        b_close = "❌ Закрыть"
    else:
        b_zk = "🔐 Zero-Knowledge"
        b_key = "🔑 Gemini API Key"
        b_rag = "📎 Vector Memory (RAG)"
        b_models = "🤖 Models Selection"
        b_sub = "💎 Subscription"
        b_cmds = "💬 Command List"
        b_close = "❌ Close"

    buttons = [
        [
            InlineKeyboardButton(text=b_zk, callback_data="guide_sec:ZERO_KNOWLEDGE"),
            InlineKeyboardButton(text=b_key, callback_data="guide_sec:API_KEY"),
        ],
        [
            InlineKeyboardButton(text=b_rag, callback_data="guide_sec:RAG"),
            InlineKeyboardButton(text=b_models, callback_data="guide_sec:MODELS"),
        ],
        [
            InlineKeyboardButton(text=b_sub, callback_data="guide_sec:SUBSCRIPTION"),
            InlineKeyboardButton(text=b_cmds, callback_data="guide_sec:COMMANDS"),
        ],
        [get_close_button(lang_code)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("guide", "help_guide"))
async def handle_guide_command(message: Message):
    """Entry point for /guide command."""
    try:
        await message.delete()
    except Exception:
        pass

    user_id = message.from_user.id
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    title = (
        "📚 <b>Интерактивное руководство пользователя:</b>\n\n"
        "Выберите интересующий вас раздел, чтобы прочитать подробную инструкцию:"
        if lang_code == "ru"
        else "📚 <b>Interactive User Guide:</b>\n\n"
        "Select a topic below to read detailed instructions:"
    )

    await message.answer(title, reply_markup=get_guide_menu_keyboard(lang_code), parse_mode="HTML")


@router.message(Command("apikey_info"))
async def handle_apikey_info_command(message: Message):
    """Fast command to explain how to get a Google AI Studio API key."""
    try:
        await message.delete()
    except Exception:
        pass

    user_id = message.from_user.id
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    section_text = get_guide_section("API_KEY", lang=lang_code)
    if not section_text or "не найден" in section_text or "not found" in section_text:
        if lang_code == "ru":
            section_text = (
                "🔑 <b>Как получить Google Gemini API ключ:</b>\n\n"
                "1. Перейдите на сайт <a href='https://aistudio.google.com/app/apikey'>Google AI Studio</a>.\n"
                "2. Войдите через Google-аккаунт.\n"
                "3. Нажмите кнопку <b>«Create API Key»</b>.\n"
                "4. Скопируйте полученный ключ (начинается с <code>AIzaSy...</code>).\n"
                "5. Откройте «⚙️ Настройки» -> «🔑 API-ключ» в боте и введите ваш ключ.\n\n"
                "🔒 <i>Ключ будет зашифрован вашим мастер-паролем (Zero-Knowledge).</i>"
            )
        else:
            section_text = (
                "🔑 <b>How to get a Google Gemini API key:</b>\n\n"
                "1. Go to <a href='https://aistudio.google.com/app/apikey'>Google AI Studio</a>.\n"
                "2. Sign in with your Google account.\n"
                "3. Click <b>«Create API Key»</b>.\n"
                "4. Copy your key (starts with <code>AIzaSy...</code>).\n"
                "5. Open «⚙️ Settings» -> «🔑 API Key» in the bot and enter your key.\n\n"
                "🔒 <i>Your key is encrypted with your master password (Zero-Knowledge).</i>"
            )

    await message.answer(
        section_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[get_close_button(lang_code)]]),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("guide_sec:"))
async def handle_guide_section(callback: CallbackQuery):
    """Renders a selected guide section with a back-to-menu button."""
    await safe_answer_callback(callback)
    sec_name = callback.data.split("guide_sec:")[1]
    user_id = callback.from_user.id

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    section_text = get_guide_section(sec_name, lang=lang_code)
    back_label = "⬅️ Назад к руководству" if lang_code == "ru" else "⬅️ Back to Guide"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=back_label, callback_data="guide_back")],
        [get_close_button(lang_code)],
    ])

    await safe_edit_message_text(
        message=callback.message,
        text=section_text[:4000],
        reply_markup=kb,
        parse_mode="HTML",
    )


@router.callback_query(F.data == "guide_back")
@router.callback_query(F.data == "open_guide")
async def handle_guide_back(callback: CallbackQuery):
    """Returns to guide topics menu."""
    await safe_answer_callback(callback)
    user_id = callback.from_user.id

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    title = (
        "📚 <b>Интерактивное руководство пользователя:</b>\n\n"
        "Выберите интересующий вас раздел, чтобы прочитать подробную инструкцию:"
        if lang_code == "ru"
        else "📚 <b>Interactive User Guide:</b>\n\n"
        "Select a topic below to read detailed instructions:"
    )

    await safe_edit_message_text(
        message=callback.message,
        text=title,
        reply_markup=get_guide_menu_keyboard(lang_code),
        parse_mode="HTML",
    )

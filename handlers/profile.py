"""
Personal Profile & Account Handlers for MyGemini Zero v2.
Handles personal account view, questionnaire FSM, and profile updates.
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from core.database import async_session_maker
from database.repositories import UserRepository, ConversationRepository, ProfileRepository
from middlewares.auth import session_manager
from keyboards.inline import get_profile_keyboard, get_unlock_keyboard
from services.account import format_account_card
from core.logger import get_logger

logger = get_logger("user_messages")
router = Router(name="profile")


class ProfileStates(StatesGroup):
    waiting_for_role = State()
    waiting_for_field = State()
    waiting_for_stack = State()
    waiting_for_projects = State()
    waiting_for_goals = State()


async def render_profile_view(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Generates text and markup for personal account."""
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        conv_repo = ConversationRepository(session)
        prof_repo = ProfileRepository(session)

        user = await user_repo.get_by_id(user_id)
        msg_count = await conv_repo.get_user_message_count(user_id)

        fernet = session_manager.get_fernet(user_id)
        profile_data = None
        if fernet:
            profile_data = await prof_repo.get_profile(user_id, fernet)

    if not user:
        return "Пользователь не найден.", get_profile_keyboard(False)

    text = format_account_card(
        user=user,
        message_count=msg_count,
        profile_data=profile_data,
        is_vault_unlocked=bool(fernet),
    )
    keyboard = get_profile_keyboard(has_profile=bool(profile_data))
    return text, keyboard


@router.callback_query(F.data == "menu_profile")
async def handle_profile_menu_callback(callback: CallbackQuery):
    """Displays personal account via inline callback."""
    try:
        await callback.answer()
    except Exception:
        pass
    user_id = callback.from_user.id
    text, keyboard = await render_profile_view(user_id)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "profile_edit")
async def handle_profile_edit_start(callback: CallbackQuery, state: FSMContext):
    """Starts profile questionnaire."""
    try:
        await callback.answer()
    except Exception:
        pass
    user_id = callback.from_user.id
    fernet = session_manager.get_fernet(user_id)

    if not fernet:
        await callback.message.edit_text(
            "🔒 <b>Сейф заблокирован.</b>\n"
            "Для заполнения или изменения анкеты сначала разблокируйте сейф мастер-паролем, "
            "чтобы данные были безопасно зашифрованы.",
            reply_markup=get_unlock_keyboard(),
            parse_mode="HTML",
        )
        return

    await state.set_state(ProfileStates.waiting_for_role)
    await callback.message.edit_text(
        "📝 <b>Заполнение анкеты пользователя (1/5):</b>\n\n"
        "Какова ваша основная роль или профессия?\n"
        "<i>(Например: Python разработчик, Data Scientist, Маркетолог, Студент)</i>\n\n"
        "<i>Отправьте ответ в чат (или отправьте '-' чтобы пропустить):</i>",
        parse_mode="HTML",
    )


@router.message(ProfileStates.waiting_for_role)
async def process_profile_role(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""
    try:
        await message.delete()
    except Exception:
        pass

    if text != "-":
        await state.update_data(role=text)
    await state.set_state(ProfileStates.waiting_for_field)
    await message.answer(
        "📝 <b>Анкета пользователя (2/5):</b>\n\n"
        "В какой сфере или индустрии вы работаете?\n"
        "<i>(Например: FinTech, E-commerce, EdTech, GameDev, Наука)</i>\n\n"
        "<i>Отправьте ответ или '-' для пропуска:</i>",
        parse_mode="HTML",
    )


@router.message(ProfileStates.waiting_for_field)
async def process_profile_field(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""
    try:
        await message.delete()
    except Exception:
        pass

    if text != "-":
        await state.update_data(field=text)
    await state.set_state(ProfileStates.waiting_for_stack)
    await message.answer(
        "📝 <b>Анкета пользователя (3/5):</b>\n\n"
        "Какой ваш основной технологический стек или инструменты?\n"
        "<i>(Например: Python, FastAPI, Docker, PostgreSQL, React)</i>\n\n"
        "<i>Отправьте ответ или '-' для пропуска:</i>",
        parse_mode="HTML",
    )


@router.message(ProfileStates.waiting_for_stack)
async def process_profile_stack(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""
    try:
        await message.delete()
    except Exception:
        pass

    if text != "-":
        await state.update_data(stack=text)
    await state.set_state(ProfileStates.waiting_for_projects)
    await message.answer(
        "📝 <b>Анкета пользователя (4/5):</b>\n\n"
        "Над какими проектами вы сейчас работаете?\n"
        "<i>(Например: Телеграм-боты, мобильное приложение, диплом, стартап)</i>\n\n"
        "<i>Отправьте ответ или '-' для пропуска:</i>",
        parse_mode="HTML",
    )


@router.message(ProfileStates.waiting_for_projects)
async def process_profile_projects(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""
    try:
        await message.delete()
    except Exception:
        pass

    if text != "-":
        await state.update_data(projects=text)
    await state.set_state(ProfileStates.waiting_for_goals)
    await message.answer(
        "📝 <b>Анкета пользователя (5/5):</b>\n\n"
        "Каковы ваши главные цели использования бота?\n"
        "<i>(Например: Code review, генерация идей, перевод документации, решение задач)</i>\n\n"
        "<i>Отправьте ответ или '-' для пропуска:</i>",
        parse_mode="HTML",
    )


@router.message(ProfileStates.waiting_for_goals)
async def process_profile_goals(message: Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    try:
        await message.delete()
    except Exception:
        pass

    if text != "-":
        await state.update_data(goals=text)

    data = await state.get_data()
    await state.clear()

    fernet = session_manager.get_fernet(user_id)
    if not fernet:
        await message.answer("🔒 Сейф заблокирован. Не удалось сохранить анкету.")
        return

    async with async_session_maker() as session:
        prof_repo = ProfileRepository(session)
        await prof_repo.save_profile(user_id, data, fernet)

    text_card, keyboard = await render_profile_view(user_id)
    await message.answer(
        f"✅ <b>Анкета успешно зашифрована и сохранена!</b>\n\n{text_card}",
        reply_markup=keyboard,
        parse_mode="HTML",
    )

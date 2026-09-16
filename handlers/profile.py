"""
Personal Profile & Account Handlers for MyGemini Zero v2.
Handles personal account view, complete 8-question questionnaire FSM with quick-choice buttons,
bilingual support (RU / EN), cancel buttons on all steps, and profile saving to encrypted DB.
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from core.database import async_session_maker
from database.repositories import UserRepository, ConversationRepository, ProfileRepository
from middlewares.auth import session_manager
from keyboards.inline import get_profile_keyboard, get_unlock_keyboard, get_cancel_keyboard, get_close_button
from services.account import format_account_card
from core.ui_helpers import safe_edit_message_text, safe_answer_callback
from core.localization import get_text
from core.logger import get_logger

logger = get_logger("user_messages")
router = Router(name="profile")


class ProfileStates(StatesGroup):
    waiting_for_role = State()
    waiting_for_industry = State()
    waiting_for_projects = State()
    waiting_for_stack = State()
    waiting_for_purpose = State()
    waiting_for_style = State()
    waiting_for_hobby = State()
    waiting_for_rules = State()


def get_purpose_keyboard(lang_code: str = "ru") -> InlineKeyboardMarkup:
    """Quick choice buttons for Question 5 (Purpose)."""
    if lang_code == "ru":
        b1, b2 = "💼 Помощь в работе", "🎓 Обучение"
        b3, b4 = "💡 Творчество и идеи", "📑 Организация информации"
    else:
        b1, b2 = "💼 Work & Productivity", "🎓 Learning & Study"
        b3, b4 = "💡 Creativity & Ideas", "📑 Knowledge Organization"

    buttons = [
        [
            InlineKeyboardButton(text=b1, callback_data="prof_choice:purpose:work"),
            InlineKeyboardButton(text=b2, callback_data="prof_choice:purpose:learn"),
        ],
        [
            InlineKeyboardButton(text=b3, callback_data="prof_choice:purpose:creative"),
            InlineKeyboardButton(text=b4, callback_data="prof_choice:purpose:organize"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Отмена" if lang_code == "ru" else "⬅️ Cancel", callback_data="menu_profile"),
            get_close_button(lang_code),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_style_keyboard(lang_code: str = "ru") -> InlineKeyboardMarkup:
    """Quick choice buttons for Question 6 (Style)."""
    if lang_code == "ru":
        b1, b2 = "😊 Дружелюбный", "👔 Деловой и строгий"
        b3, b4 = "⚡️ Краткий, по сути", "📚 Подробный, с деталями"
    else:
        b1, b2 = "😊 Friendly", "👔 Professional & Formal"
        b3, b4 = "⚡️ Concise & Direct", "📚 Detailed & Thorough"

    buttons = [
        [
            InlineKeyboardButton(text=b1, callback_data="prof_choice:style:friendly"),
            InlineKeyboardButton(text=b2, callback_data="prof_choice:style:formal"),
        ],
        [
            InlineKeyboardButton(text=b3, callback_data="prof_choice:style:concise"),
            InlineKeyboardButton(text=b4, callback_data="prof_choice:style:detailed"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Отмена" if lang_code == "ru" else "⬅️ Cancel", callback_data="menu_profile"),
            get_close_button(lang_code),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def render_profile_view(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Generates text and markup for personal account."""
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        conv_repo = ConversationRepository(session)
        prof_repo = ProfileRepository(session)

        user = await user_repo.get_by_id(user_id)
        msg_count = await conv_repo.get_user_message_count(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

        fernet = session_manager.get_fernet(user_id)
        profile_data = None
        if fernet:
            profile_data = await prof_repo.get_profile(user_id, fernet)

    if not user:
        return ("Пользователь не найден." if lang_code == "ru" else "User not found."), get_profile_keyboard(False, lang_code=lang_code)

    text = format_account_card(
        user=user,
        message_count=msg_count,
        profile_data=profile_data,
        is_vault_unlocked=bool(fernet),
        lang_code=lang_code,
    )
    keyboard = get_profile_keyboard(has_profile=bool(profile_data), lang_code=lang_code)
    return text, keyboard


@router.callback_query(F.data == "menu_profile")
async def handle_profile_menu_callback(callback: CallbackQuery, state: FSMContext | None = None):
    """Displays personal account via inline callback."""
    await safe_answer_callback(callback)
    if state:
        await state.clear()
    user_id = callback.from_user.id
    text, keyboard = await render_profile_view(user_id)
    await safe_edit_message_text(callback.message, text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "profile_edit")
async def handle_profile_edit_start(callback: CallbackQuery, state: FSMContext):
    """Starts 8-question profile questionnaire."""
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
            "Для заполнения или изменения анкеты сначала разблокируйте сейф мастер-паролем, "
            "чтобы данные были безопасно зашифрованы."
            if lang_code == "ru"
            else "🔒 <b>Vault is locked.</b>\n"
            "To complete or edit your questionnaire, unlock vault with your master password first."
        )
        await safe_edit_message_text(
            callback.message,
            prompt_text,
            reply_markup=get_unlock_keyboard(lang_code),
            parse_mode="HTML",
        )
        return

    await state.clear()
    await state.set_state(ProfileStates.waiting_for_role)

    q1 = (
        "📝 <b>Анкета пользователя (1/8):</b>\n\n"
        "Какова ваша основная <b>роль или профессия</b>?\n"
        "<i>(Например: Python разработчик, Продакт-менеджер, Студент, Предприниматель)</i>\n\n"
        "<i>Отправьте ответ в чат (или '-' чтобы пропустить):</i>"
        if lang_code == "ru"
        else "📝 <b>User Questionnaire (1/8):</b>\n\n"
        "What is your primary <b>role or profession</b>?\n"
        "<i>(e.g., Software Engineer, Product Manager, Student, Founder)</i>\n\n"
        "<i>Send your answer in chat (or '-' to skip):</i>"
    )

    await safe_edit_message_text(
        callback.message,
        q1,
        reply_markup=get_cancel_keyboard(callback_data="menu_profile", lang_code=lang_code),
        parse_mode="HTML",
    )


@router.message(ProfileStates.waiting_for_role)
async def process_profile_role(message: Message, state: FSMContext):
    """Step 1 -> Step 2."""
    ans = message.text.strip() if message.text else ""
    await state.update_data(role=ans if ans != "-" else "")
    await state.set_state(ProfileStates.waiting_for_industry)

    user_id = message.from_user.id
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    q2 = (
        "📝 <b>Анкета пользователя (2/8):</b>\n\n"
        "В какой <b>сфере деятельности или индустрии</b> вы работаете?\n"
        "<i>(Например: IT, FinTech, E-commerce, Образование, Медицина)</i>\n\n"
        "<i>Отправьте ответ в чат (или '-' чтобы пропустить):</i>"
        if lang_code == "ru"
        else "📝 <b>User Questionnaire (2/8):</b>\n\n"
        "What is your <b>industry or domain</b>?\n"
        "<i>(e.g., IT, FinTech, E-commerce, Healthcare, Education)</i>\n\n"
        "<i>Send your answer in chat (or '-' to skip):</i>"
    )
    await message.answer(q2, reply_markup=get_cancel_keyboard(callback_data="menu_profile", lang_code=lang_code), parse_mode="HTML")


@router.message(ProfileStates.waiting_for_industry)
async def process_profile_industry(message: Message, state: FSMContext):
    """Step 2 -> Step 3."""
    ans = message.text.strip() if message.text else ""
    await state.update_data(industry=ans if ans != "-" else "")
    await state.set_state(ProfileStates.waiting_for_projects)

    user_id = message.from_user.id
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    q3 = (
        "📝 <b>Анкета пользователя (3/8):</b>\n\n"
        "Над какими ключевыми <b>проектами или задачами</b> вы сейчас работаете?\n"
        "<i>(Например: Запуск мобильного приложения, написание диплома, оптимизация маркетинга)</i>\n\n"
        "<i>Отправьте ответ в чат (или '-' чтобы пропустить):</i>"
        if lang_code == "ru"
        else "📝 <b>User Questionnaire (3/8):</b>\n\n"
        "What key <b>projects or tasks</b> are you working on?\n"
        "<i>(e.g., Launching mobile app, writing thesis, marketing strategy)</i>\n\n"
        "<i>Send your answer in chat (or '-' to skip):</i>"
    )
    await message.answer(q3, reply_markup=get_cancel_keyboard(callback_data="menu_profile", lang_code=lang_code), parse_mode="HTML")


@router.message(ProfileStates.waiting_for_projects)
async def process_profile_projects(message: Message, state: FSMContext):
    """Step 3 -> Step 4."""
    ans = message.text.strip() if message.text else ""
    await state.update_data(projects=ans if ans != "-" else "")
    await state.set_state(ProfileStates.waiting_for_stack)

    user_id = message.from_user.id
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    q4 = (
        "📝 <b>Анкета пользователя (4/8):</b>\n\n"
        "Какие <b>технологии, стек или инструменты</b> вы чаще всего используете?\n"
        "<i>(Например: Python, Docker, PostgreSQL, Figma, Notion)</i>\n\n"
        "<i>Отправьте ответ в чат (или '-' чтобы пропустить):</i>"
        if lang_code == "ru"
        else "📝 <b>User Questionnaire (4/8):</b>\n\n"
        "What <b>technologies, stack, or tools</b> do you use most?\n"
        "<i>(e.g., Python, Docker, PostgreSQL, Figma, Notion)</i>\n\n"
        "<i>Send your answer in chat (or '-' to skip):</i>"
    )
    await message.answer(q4, reply_markup=get_cancel_keyboard(callback_data="menu_profile", lang_code=lang_code), parse_mode="HTML")


@router.message(ProfileStates.waiting_for_stack)
async def process_profile_stack(message: Message, state: FSMContext):
    """Step 4 -> Step 5 (Purpose with buttons)."""
    ans = message.text.strip() if message.text else ""
    await state.update_data(stack=ans if ans != "-" else "")
    await state.set_state(ProfileStates.waiting_for_purpose)

    user_id = message.from_user.id
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    q5 = (
        "📝 <b>Анкета пользователя (5/8):</b>\n\n"
        "Для чего в первую очередь вы планируете <b>использовать бота</b>?\n"
        "<i>(Выберите кнопку ниже или напишите свой вариант в чат):</i>"
        if lang_code == "ru"
        else "📝 <b>User Questionnaire (5/8):</b>\n\n"
        "What is your primary goal for <b>using the bot</b>?\n"
        "<i>(Click a button below or send your answer in chat):</i>"
    )
    await message.answer(q5, reply_markup=get_purpose_keyboard(lang_code), parse_mode="HTML")


@router.callback_query(F.data.startswith("prof_choice:purpose:"))
async def handle_choice_purpose(callback: CallbackQuery, state: FSMContext):
    """Handles quick choice for Question 5."""
    await safe_answer_callback(callback)
    choice = callback.data.split("prof_choice:purpose:")[1]
    choice_map = {
        "work": "Помощь в работе",
        "learn": "Обучение",
        "creative": "Творчество и идеи",
        "organize": "Организация информации",
    }
    val = choice_map.get(choice, choice)
    await state.update_data(purpose=val)
    await proceed_to_style(callback.message, state, callback.from_user.id, is_edit=True)


@router.message(ProfileStates.waiting_for_purpose)
async def process_profile_purpose(message: Message, state: FSMContext):
    """Step 5 -> Step 6 (Style)."""
    ans = message.text.strip() if message.text else ""
    await state.update_data(purpose=ans if ans != "-" else "")
    await proceed_to_style(message, state, message.from_user.id, is_edit=False)


async def proceed_to_style(msg: Message, state: FSMContext, user_id: int, is_edit: bool = False):
    """Helper to transition to Question 6 (Style)."""
    await state.set_state(ProfileStates.waiting_for_style)
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    q6 = (
        "📝 <b>Анкета пользователя (6/8):</b>\n\n"
        "Какой <b>стиль общения</b> вам ближе?\n"
        "<i>(Выберите кнопку ниже или напишите свой вариант):</i>"
        if lang_code == "ru"
        else "📝 <b>User Questionnaire (6/8):</b>\n\n"
        "What <b>communication style</b> do you prefer?\n"
        "<i>(Select a button below or type your answer):</i>"
    )
    kb = get_style_keyboard(lang_code)
    if is_edit:
        await safe_edit_message_text(msg, q6, reply_markup=kb, parse_mode="HTML")
    else:
        await msg.answer(q6, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("prof_choice:style:"))
async def handle_choice_style(callback: CallbackQuery, state: FSMContext):
    """Handles quick choice for Question 6."""
    await safe_answer_callback(callback)
    choice = callback.data.split("prof_choice:style:")[1]
    choice_map = {
        "friendly": "Дружелюбный",
        "formal": "Деловой и строгий",
        "concise": "Краткий, по сути",
        "detailed": "Подробный, с деталями",
    }
    val = choice_map.get(choice, choice)
    await state.update_data(style=val)
    await proceed_to_hobby(callback.message, state, callback.from_user.id, is_edit=True)


@router.message(ProfileStates.waiting_for_style)
async def process_profile_style(message: Message, state: FSMContext):
    """Step 6 -> Step 7 (Hobby)."""
    ans = message.text.strip() if message.text else ""
    await state.update_data(style=ans if ans != "-" else "")
    await proceed_to_hobby(message, state, message.from_user.id, is_edit=False)


async def proceed_to_hobby(msg: Message, state: FSMContext, user_id: int, is_edit: bool = False):
    """Helper to transition to Question 7."""
    await state.set_state(ProfileStates.waiting_for_hobby)
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    q7 = (
        "📝 <b>Анкета пользователя (7/8):</b>\n\n"
        "Чем вы увлекаетесь в свободное время? Какие у вас <b>хобби и интересы</b>?\n"
        "<i>(Например: Шахматы, бег, видеоигры, научная фантастика, музыка)</i>\n\n"
        "<i>Отправьте ответ в чат (или '-' чтобы пропустить):</i>"
        if lang_code == "ru"
        else "📝 <b>User Questionnaire (7/8):</b>\n\n"
        "What are your <b>hobbies and interests</b>?\n"
        "<i>(e.g., Chess, running, gaming, sci-fi, music)</i>\n\n"
        "<i>Send your answer in chat (or '-' to skip):</i>"
    )
    kb = get_cancel_keyboard(callback_data="menu_profile", lang_code=lang_code)
    if is_edit:
        await safe_edit_message_text(msg, q7, reply_markup=kb, parse_mode="HTML")
    else:
        await msg.answer(q7, reply_markup=kb, parse_mode="HTML")


@router.message(ProfileStates.waiting_for_hobby)
async def process_profile_hobby(message: Message, state: FSMContext):
    """Step 7 -> Step 8 (Rules)."""
    ans = message.text.strip() if message.text else ""
    await state.update_data(hobby=ans if ans != "-" else "")
    await state.set_state(ProfileStates.waiting_for_rules)

    user_id = message.from_user.id
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    q8 = (
        "📝 <b>Анкета пользователя (8/8):</b>\n\n"
        "Есть ли темы, которые мне следует избегать, или <b>важные правила</b> общения с вами?\n"
        "<i>(Например: \"Не давать советы по инвестициям\", \"Всегда приводить примеры кода\")</i>\n\n"
        "<i>Отправьте ответ в чат (или '-' чтобы пропустить):</i>"
        if lang_code == "ru"
        else "📝 <b>User Questionnaire (8/8):</b>\n\n"
        "Are there any topics to avoid or <b>golden rules</b> for our conversations?\n"
        "<i>(e.g., \"Never give investment advice\", \"Always provide code examples\")</i>\n\n"
        "<i>Send your answer in chat (or '-' to skip):</i>"
    )
    await message.answer(q8, reply_markup=get_cancel_keyboard(callback_data="menu_profile", lang_code=lang_code), parse_mode="HTML")


@router.message(ProfileStates.waiting_for_rules)
async def process_profile_rules(message: Message, state: FSMContext):
    """Step 8 -> Final Save."""
    ans = message.text.strip() if message.text else ""
    data = await state.get_data()
    data["rules"] = ans if ans != "-" else ""
    await state.clear()

    user_id = message.from_user.id
    fernet = session_manager.get_fernet(user_id)

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        prof_repo = ProfileRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

        if fernet:
            await prof_repo.save_profile(user_id, data, fernet)

    done_text = (
        "✅ <b>Отлично, анкета успешно сохранена!</b>\n\n"
        "Информация зашифрована вашим мастер-паролем. "
        "Gemini будет учитывать ваши предпочтения при формировании ответов."
        if lang_code == "ru"
        else "✅ <b>Profile questionnaire successfully saved!</b>\n\n"
        "All data is encrypted with your master password. "
        "Gemini will personalize responses based on your context."
    )

    btn_view = "👤 Посмотреть профиль" if lang_code == "ru" else "👤 View Profile"
    await message.answer(
        done_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=btn_view, callback_data="menu_profile"), get_close_button(lang_code)]
        ]),
        parse_mode="HTML",
    )

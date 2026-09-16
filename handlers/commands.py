"""
Central Commands & Reply Keyboard Router for MyGemini Zero v2.
Handles all slash commands (/dialogs, /settings, /profile, /documents, /reset, /help, etc.)
and persistent Reply Keyboard button presses (supporting both Russian and English).
Enforces clean chat policy by instantly deleting user command messages (await message.delete()).
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext

from core.database import async_session_maker
from database.repositories import UserRepository, DialogRepository, SettingsRepository, ConversationRepository
from services.vector_store import VectorStoreManager
from middlewares.auth import session_manager
from keyboards.reply import get_main_reply_keyboard, get_locked_reply_keyboard
from keyboards.inline import (
    get_main_menu_keyboard,
    get_settings_keyboard,
    get_unlock_keyboard,
    get_admin_keyboard,
    get_close_button,
)
from handlers.profile import render_profile_view
from handlers.memory import render_documents_view
from handlers.settings import render_settings_view
from core.config import settings
from core.logger import get_logger

logger = get_logger("user_messages")
router = Router(name="commands")


async def auto_delete_user_message(message: Message):
    """Safely deletes user's command message to keep the chat history completely clean."""
    try:
        await message.delete()
    except Exception:
        pass


@router.callback_query(F.data == "close_menu")
async def handle_close_menu(callback: CallbackQuery, state: FSMContext):
    """Universal handler for '❌ Закрыть' button. Instantly clears FSM and deletes the service menu message."""
    try:
        await callback.answer()
    except Exception:
        pass
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        pass


@router.message(Command("profile", "account"))
@router.message(F.text.in_(["👤 Личный кабинет", "👤 Profile"]))
async def handle_profile_command(message: Message):
    """Opens Personal Account card."""
    await auto_delete_user_message(message)
    user_id = message.from_user.id
    text, keyboard = await render_profile_view(user_id)
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("settings"))
@router.message(F.text.in_(["⚙️ Настройки", "⚙️ Settings"]))
async def handle_settings_command(message: Message):
    """Opens Settings menu."""
    await auto_delete_user_message(message)
    user_id = message.from_user.id
    text, keyboard = await render_settings_view(user_id)
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("dialogs"))
@router.message(F.text.in_(["🗂️ Диалоги", "🗂️ Dialogs"]))
async def handle_dialogs_command(message: Message):
    """Opens dialog selection menu."""
    await auto_delete_user_message(message)
    user_id = message.from_user.id

    async with async_session_maker() as session:
        dialog_repo = DialogRepository(session)
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        active_id = user.active_dialog_id if user else None
        dialogs = await dialog_repo.get_user_dialogs(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    if not dialogs:
        no_dlg_text = "У вас пока нет созданных диалогов." if lang_code == "ru" else "You don't have any dialogs yet."
        btn_new_text = "➕ Создать новый диалог" if lang_code == "ru" else "➕ Create New Dialog"
        await message.answer(
            no_dlg_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=btn_new_text, callback_data="dialog_new")],
                [get_close_button(lang_code)],
            ]),
        )
        return

    vm = VectorStoreManager()
    buttons = []
    for d in dialogs:
        is_active = d.dialog_id == active_id
        icon = "🔘 " if is_active else "⚪️ "
        docs = vm.get_dialog_documents(d.dialog_id)
        doc_icon = "📎 " if docs else ""

        buttons.append([
            InlineKeyboardButton(
                text=f"{icon}{doc_icon}{d.name}",
                callback_data=f"dialog_switch:{d.dialog_id}",
            ),
            InlineKeyboardButton(
                text="✏️",
                callback_data=f"dialog_rename_prompt:{d.dialog_id}",
            ),
            InlineKeyboardButton(
                text="🗑",
                callback_data=f"dialog_delete:{d.dialog_id}",
            ),
        ])

    btn_create = "➕ Создать новый диалог" if lang_code == "ru" else "➕ Create New Dialog"
    btn_main = "⬅️ В главное меню" if lang_code == "ru" else "⬅️ Main Menu"
    buttons.append([InlineKeyboardButton(text=btn_create, callback_data="dialog_new")])
    buttons.append([InlineKeyboardButton(text=btn_main, callback_data="back_to_main"), get_close_button(lang_code)])

    dlg_header = (
        "🗂 <b>Ваши диалоги:</b>\n\n"
        "🔘 — активный диалог (текущий контекст)\n"
        "📎 — диалог содержит прикреплённые документы (RAG-память)\n\n"
        "Нажмите на название диалога, чтобы переключиться на него:"
        if lang_code == "ru"
        else "🗂 <b>Your Dialogues:</b>\n\n"
        "🔘 — active dialogue (current context)\n"
        "📎 — dialogue has attached documents (RAG memory)\n\n"
        "Click a dialogue name to switch to it:"
    )

    await message.answer(
        dlg_header,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@router.message(Command("new_dialog"))
@router.message(F.text.in_(["➕ Новый диалог", "➕ New Dialog"]))
async def handle_new_dialog_command(message: Message):
    """Instantly creates a new dialog with auto-naming enabled."""
    await auto_delete_user_message(message)
    user_id = message.from_user.id

    async with async_session_maker() as session:
        dialog_repo = DialogRepository(session)
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"
        dialog_name = "Новый диалог" if lang_code == "ru" else "New Dialogue"
        dialog = await dialog_repo.create_dialog(user_id=user_id, name=dialog_name, set_active=True)

    text = (
        "✅ <b>Создан новый активный диалог!</b>\n\n"
        "Напишите первое сообщение — бот автоматически подберёт ёмкое название темы по смыслу вашего запроса.\n\n"
        "<i>Вы также можете переименовать диалог вручную через кнопку ✏️ или команду /rename.</i>"
        if lang_code == "ru"
        else "✅ <b>New active dialogue created!</b>\n\n"
        "Send your first message — the bot will automatically name the topic based on your query.\n\n"
        "<i>You can also rename it manually anytime via ✏️ or /rename command.</i>"
    )

    btn_list = "🗂 Список диалогов" if lang_code == "ru" else "🗂 Dialogs List"
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=btn_list, callback_data="dialog_list"), get_close_button(lang_code)]
        ]),
        parse_mode="HTML",
    )


@router.message(Command("rename"))
async def handle_rename_command(message: Message, command: CommandObject):
    """Renames the currently active dialog."""
    await auto_delete_user_message(message)
    user_id = message.from_user.id
    new_name = command.args.strip() if command.args else ""

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        dialog_repo = DialogRepository(session)
        user = await user_repo.get_by_id(user_id)
        active_id = user.active_dialog_id if user else None
        lang_code = user.language_code if user and user.language_code else "ru"

        if not active_id:
            await message.answer("⚠️ У вас нет активного диалога." if lang_code == "ru" else "⚠️ No active dialogue found.")
            return

        if not new_name:
            prompt_text = (
                "✏️ Укажите новое имя диалога вместе с командой:\n<code>/rename Моё новое название</code>"
                if lang_code == "ru"
                else "✏️ Specify new dialogue name with command:\n<code>/rename My new title</code>"
            )
            await message.answer(prompt_text, parse_mode="HTML")
            return

        await dialog_repo.rename_dialog(active_id, new_name)

    confirm_text = (
        f"✅ Активный диалог переименован в: <b>{new_name}</b>"
        if lang_code == "ru"
        else f"✅ Active dialogue renamed to: <b>{new_name}</b>"
    )
    btn_list = "🗂 Список диалогов" if lang_code == "ru" else "🗂 Dialogs List"
    await message.answer(
        confirm_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=btn_list, callback_data="dialog_list"), get_close_button(lang_code)]
        ]),
        parse_mode="HTML",
    )


@router.message(Command("documents", "memory"))
@router.message(F.text.in_(["📄 Документы", "📄 Documents"]))
async def handle_documents_command(message: Message):
    """Directly displays documents uploaded into active dialog memory."""
    await auto_delete_user_message(message)
    user_id = message.from_user.id
    text, keyboard = await render_documents_view(user_id)
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("memorize"))
async def handle_memorize_command(message: Message):
    """Explains how to feed files to the bot's RAG memory."""
    await auto_delete_user_message(message)
    user_id = message.from_user.id
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    if lang_code == "ru":
        info = (
            "📎 <b>Как добавить документ в память диалога:</b>\n\n"
            "1. Нажмите на значок скрепки 📎 в поле ввода Telegram.\n"
            "2. Выберите файл (.pdf, .docx, .txt, .md, .py, .json) и отправьте его как <b>Документ</b>.\n"
            "3. Бот моментально извлечёт текст, разобьёт его на смысловые фрагменты и сохранит в ChromaDB.\n\n"
            "После загрузки вы можете задавать любые вопросы по содержимому файла!"
        )
        btn_view = "📄 Просмотреть загруженные файлы"
    else:
        info = (
            "📎 <b>How to add documents to dialogue memory:</b>\n\n"
            "1. Click the paperclip icon 📎 in Telegram.\n"
            "2. Choose a file (.pdf, .docx, .txt, .md, .py, .json) and send it as a <b>Document</b>.\n"
            "3. The bot indexes text chunks into ChromaDB for this dialogue.\n\n"
            "Ask any questions regarding file contents afterwards!"
        )
        btn_view = "📄 View uploaded files"

    await message.answer(
        info,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=btn_view, callback_data="memory_view_docs")],
            [get_close_button(lang_code)],
        ]),
        parse_mode="HTML",
    )


@router.message(Command("reset"))
@router.message(F.text.in_(["🔄 Сброс контекста", "🔄 Reset Context"]))
async def handle_reset_command(message: Message):
    """Creates fresh dialog context for zeroed-out short term memory."""
    await auto_delete_user_message(message)
    user_id = message.from_user.id

    async with async_session_maker() as session:
        dialog_repo = DialogRepository(session)
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"
        dlg_name = "Новый диалог" if lang_code == "ru" else "New Dialogue"
        dialog = await dialog_repo.create_dialog(user_id=user_id, name=dlg_name, set_active=True)

    text = (
        "🔄 <b>Контекст сброшен!</b>\n"
        "Создан новый чистый диалог. Предыдущая переписка сохранена в списке ваших диалогов."
        if lang_code == "ru"
        else "🔄 <b>Context reset!</b>\n"
        "Created fresh dialogue. Previous conversation remains in your dialogues list."
    )
    btn_list = "🗂 Список диалогов" if lang_code == "ru" else "🗂 Dialogs List"
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=btn_list, callback_data="dialog_list"), get_close_button(lang_code)]
        ]),
        parse_mode="HTML",
    )


@router.message(Command("help"))
@router.message(F.text.in_(["❓ Помощь", "❓ Help"]))
async def handle_help_command(message: Message):
    """Renders comprehensive help guide."""
    await auto_delete_user_message(message)
    user_id = message.from_user.id

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    if lang_code == "ru":
        help_text = (
            "❓ <b>Справка по MyGemini Zero v2:</b>\n\n"
            "<b>Основные команды:</b>\n"
            "• /start — перезапуск бота и разблокировка\n"
            "• /profile — «👤 Личный кабинет» (статистика, анкета)\n"
            "• /dialogs — «🗂️ Диалоги» (список, переключение, удаление)\n"
            "• /new_dialog — «➕ Новый диалог» с авто-наименованием\n"
            "• /rename [имя] — переименовать активный диалог\n"
            "• /settings — «⚙️ Настройки» (модели, персоны, стили, язык, API-ключ)\n"
            "• /documents — «📄 Документы» в памяти диалога\n"
            "• /history — интерактивный календарь истории по датам\n"
            "• /guide — интерактивное подробное руководство пользователя\n"
            "• /translate — быстрый переводчик сообщений\n"
            "• /feedback — отправить сообщение администратору\n"
            "• /reset — «🔄 Сброс контекста» (новый диалог)\n"
            "• /logout — заблокировать память сейфа\n"
            "• /cancel — отмена текущего действия\n"
            "• /panic — информация об аварийном стирании данных\n\n"
            "🔒 <i>Все данные хранятся на сервере исключительно в зашифрованном виде (Zero-Knowledge).</i>"
        )
    else:
        help_text = (
            "❓ <b>Help for MyGemini Zero v2:</b>\n\n"
            "<b>Main commands:</b>\n"
            "• /start — restart bot and unlock\n"
            "• /profile — «👤 Profile» (stats, persona info)\n"
            "• /dialogs — «🗂️ Dialogs» (list, switch, delete)\n"
            "• /new_dialog — «➕ New Dialog» with auto-naming\n"
            "• /rename [title] — rename active dialogue\n"
            "• /settings — «⚙️ Settings» (models, personas, styles, language, API key)\n"
            "• /documents — «📄 Documents» in dialogue memory\n"
            "• /history — interactive calendar history by date\n"
            "• /guide — comprehensive interactive user guide\n"
            "• /translate — quick text translation mode\n"
            "• /feedback — contact admin / support\n"
            "• /reset — «🔄 Reset Context» (fresh dialogue)\n"
            "• /logout — lock memory vault\n"
            "• /cancel — cancel active action\n"
            "• /panic — emergency wipe info\n\n"
            "🔒 <i>All data is stored strictly encrypted (Zero-Knowledge).</i>"
        )

    btn_guide = "📚 Интерактивное руководство" if lang_code == "ru" else "📚 Interactive Guide"
    await message.answer(
        help_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=btn_guide, callback_data="open_guide")],
            [get_close_button(lang_code)],
        ]),
        parse_mode="HTML",
    )


@router.message(Command("logout"))
async def handle_logout_command(message: Message):
    """Locks vault session."""
    await auto_delete_user_message(message)
    user_id = message.from_user.id
    session_manager.lock_session(user_id)

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    text = (
        "🔒 <b>Сейф заблокирован.</b>\n"
        "Ключи дешифрования выгружены из оперативной памяти сервера.\n"
        "Для разблокировки введите ваш мастер-пароль:"
        if lang_code == "ru"
        else "🔒 <b>Vault locked.</b>\n"
        "Decryption keys have been wiped from server memory.\n"
        "Enter your master password to unlock:"
    )

    await message.answer(
        text,
        reply_markup=get_locked_reply_keyboard(lang_code),
        parse_mode="HTML",
    )


@router.message(Command("cancel"))
async def handle_cancel_command(message: Message, state: FSMContext):
    """Cancels any active FSM state."""
    await auto_delete_user_message(message)
    await state.clear()
    user_id = message.from_user.id
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    text = "✅ Действие отменено." if lang_code == "ru" else "✅ Action cancelled."
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[get_close_button(lang_code)]]),
        parse_mode="HTML",
    )


@router.message(Command("panic"))
async def handle_panic_command(message: Message):
    """Shows panic-password configuration info."""
    await auto_delete_user_message(message)
    user_id = message.from_user.id
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    if lang_code == "ru":
        text = (
            "🚨 <b>Аварийный паник-пароль (Durez Wipe):</b>\n\n"
            "Паник-пароль предназначен для экстренных ситуаций. Если при разблокировке бота "
            "вместо мастер-пароля ввести паник-пароль, бот моментально и безвозвратно "
            "<b>сотрёт всю историю переписки, файлы, векторные эмбеддинги и личный API-ключ</b>.\n\n"
            "Настроить паник-пароль можно в разделе «⚙️ Настройки» -> «🚨 Настроить паник-пароль»."
        )
        btn_sett = "⚙️ Перейти в настройки"
    else:
        text = (
            "🚨 <b>Emergency Panic Password (Durez Wipe):</b>\n\n"
            "Panic password is for emergencies. If entered instead of your master password, "
            "the bot instantly and permanently <b>wipes all dialogues, messages, memory files, and API key</b>.\n\n"
            "Configure it in «⚙️ Settings» -> «🚨 Configure Panic Password»."
        )
        btn_sett = "⚙️ Go to Settings"

    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=btn_sett, callback_data="settings_panic")],
            [get_close_button(lang_code)],
        ]),
        parse_mode="HTML",
    )


@router.message(Command("admin"))
@router.message(F.text.in_(["👑 Админка", "👑 Admin"]))
async def handle_admin_command(message: Message):
    """Opens admin dashboard for administrator."""
    await auto_delete_user_message(message)
    user_id = message.from_user.id
    if user_id != settings.ADMIN_USER_ID:
        return

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    title = "👑 <b>Панель администратора:</b>\n\nВыберите действие для управления ботом:" if lang_code == "ru" else "👑 <b>Admin Dashboard:</b>\n\nSelect action:"
    await message.answer(
        title,
        reply_markup=get_admin_keyboard(lang_code=lang_code),
        parse_mode="HTML",
    )

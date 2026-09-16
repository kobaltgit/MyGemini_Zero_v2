"""
Central Commands & Reply Keyboard Router for MyGemini Zero v2.
Handles all slash commands (/start, /dialogs, /settings, /profile, /documents, /reset, /help, etc.)
and persistent Reply Keyboard button presses.
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
async def handle_close_menu(callback: CallbackQuery):
    """Universal handler for '❌ Закрыть' button. Instantly deletes the service menu message."""
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()


@router.message(Command("start"))
async def handle_start_command(message: Message, state: FSMContext):
    """Entrypoint /start command: ensures user exists and displays persistent keyboard and welcome card."""
    await auto_delete_user_message(message)
    await state.clear()
    user_id = message.from_user.id
    is_admin = (user_id == settings.ADMIN_USER_ID)

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        dialog_repo = DialogRepository(session)
        user = await user_repo.get_by_id(user_id)

        if not user:
            user = await user_repo.create_user(
                user_id=user_id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
            )
            # Create first dialog
            dialog = await dialog_repo.create_dialog(user_id, "Основной диалог", set_active=True)
            active_dialog_id = dialog.dialog_id
        else:
            active_dialog_id = user.active_dialog_id

    fernet = session_manager.get_fernet(user_id)
    is_unlocked = bool(fernet)

    # Issue persistent Reply Keyboard under text input
    reply_kb = get_main_reply_keyboard(is_admin=is_admin)

    welcome_text = (
        f"👋 <b>Добро пожаловать в MyGemini Zero v2, {message.from_user.first_name or 'друг'}!</b>\n\n"
        "🔒 <b>Безопасность Zero-Knowledge:</b>\n"
        "Все ваши диалоги, история и контекст шифруются симметричным шифром Fernet (PBKDF2 480 000 итераций). "
        "Ключ формируется только в оперативной памяти и никогда не сохраняется на диск.\n\n"
        "🧠 <b>Возможности:</b>\n"
        "• Официальный Google Gemini SDK (2.5 Flash / Pro / Thinking)\n"
        "• Векторная память (RAG) — прикрепляйте файлы через скрепку 📎\n"
        "• Постоянное меню под строкой ввода и быстрые слэш-команды в кнопке [Меню]\n"
        "• Автоматическое наименование диалогов по смыслу вашего вопроса\n\n"
        "Выберите нужное действие в меню ниже или просто напишите ваш запрос в чат:"
    )

    await message.answer(
        welcome_text,
        reply_markup=reply_kb,
        parse_mode="HTML",
    )


@router.message(Command("profile"), Command("account"))
@router.message(F.text == "👤 Личный кабинет")
async def handle_profile_command(message: Message):
    """Opens Personal Account card."""
    await auto_delete_user_message(message)
    user_id = message.from_user.id
    text, keyboard = await render_profile_view(user_id)
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("settings"))
@router.message(F.text == "⚙️ Настройки")
async def handle_settings_command(message: Message):
    """Opens Settings menu."""
    await auto_delete_user_message(message)
    user_id = message.from_user.id
    text, keyboard = await render_settings_view(user_id)
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("dialogs"))
@router.message(F.text == "🗂️ Диалоги")
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

    if not dialogs:
        await message.answer(
            "У вас пока нет созданных диалогов.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Создать новый диалог", callback_data="dialog_new")],
                [get_close_button()],
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

    buttons.append([InlineKeyboardButton(text="➕ Создать новый диалог", callback_data="dialog_new")])
    buttons.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_to_main"), get_close_button()])

    await message.answer(
        "🗂 <b>Ваши диалоги:</b>\n\n"
        "🔘 — активный диалог (текущий контекст)\n"
        "📎 — диалог содержит прикреплённые документы (RAG-память)\n\n"
        "Нажмите на название диалога, чтобы переключиться на него:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@router.message(Command("new_dialog"))
@router.message(F.text == "➕ Новый диалог")
async def handle_new_dialog_command(message: Message):
    """Instantly creates a new dialog with auto-naming enabled."""
    await auto_delete_user_message(message)
    user_id = message.from_user.id

    async with async_session_maker() as session:
        dialog_repo = DialogRepository(session)
        dialog = await dialog_repo.create_dialog(user_id=user_id, name="Новый диалог", set_active=True)

    await message.answer(
        f"✅ <b>Создан новый активный диалог!</b>\n\n"
        f"Напишите первое сообщение — бот автоматически подберёт ёмкое название темы по смыслу вашего запроса.\n\n"
        f"<i>Вы также можете переименовать диалог вручную через кнопку ✏️ или команду /rename.</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗂 Список диалогов", callback_data="dialog_list"), get_close_button()]
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

        if not active_id:
            await message.answer("⚠️ У вас нет активного диалога.")
            return

        if not new_name:
            await message.answer(
                "✏️ Укажите новое имя диалога вместе с командой:\n<code>/rename Моё новое название</code>",
                parse_mode="HTML",
            )
            return

        await dialog_repo.rename_dialog(active_id, new_name)

    await message.answer(
        f"✅ Активный диалог переименован в: <b>{new_name}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗂 Список диалогов", callback_data="dialog_list"), get_close_button()]
        ]),
        parse_mode="HTML",
    )


@router.message(Command("documents"), Command("memory"))
@router.message(F.text == "📄 Документы")
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
    await message.answer(
        "📎 <b>Как добавить документ в память диалога:</b>\n\n"
        "1. Нажмите на значок скрепки 📎 в поле ввода Telegram.\n"
        "2. Выберите файл (.pdf, .docx, .txt, .md, .py, .json) и отправьте его как <b>Документ</b> (без сжатия фото).\n"
        "3. Бот моментально извлечёт текст, разобьёт его на смысловые фрагменты и сохранит в ChromaDB для активного диалога.\n\n"
        "После загрузки вы можете задавать любые вопросы по содержимому файла!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📄 Просмотреть загруженные файлы", callback_data="memory_view_docs")],
            [get_close_button()],
        ]),
        parse_mode="HTML",
    )


@router.message(Command("reset"))
@router.message(F.text == "🔄 Сброс контекста")
async def handle_reset_command(message: Message):
    """Creates fresh dialog context for zeroed-out short term memory."""
    await auto_delete_user_message(message)
    user_id = message.from_user.id

    async with async_session_maker() as session:
        dialog_repo = DialogRepository(session)
        dialog = await dialog_repo.create_dialog(user_id=user_id, name="Новый диалог", set_active=True)

    await message.answer(
        "🔄 <b>Контекст сброшен!</b>\n"
        "Создан новый чистый диалог. Предыдущая переписка сохранена в списке ваших диалогов.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗂 Список диалогов", callback_data="dialog_list"), get_close_button()]
        ]),
        parse_mode="HTML",
    )


@router.message(Command("help"))
@router.message(F.text == "❓ Помощь")
async def handle_help_command(message: Message):
    """Renders comprehensive help guide."""
    await auto_delete_user_message(message)
    help_text = (
        "❓ <b>Справка по MyGemini Zero v2:</b>\n\n"
        "<b>Основные команды:</b>\n"
        "• /start — перезапуск бота и выдача постоянного меню\n"
        "• /profile — «👤 Личный кабинет» (звание, статистика, анкета)\n"
        "• /dialogs — «🗂️ Диалоги» (переключение, переименование, удаление)\n"
        "• /new_dialog — «➕ Новый диалог» с автоматическим наименованием\n"
        "• /rename [имя] — быстрое переименование активного диалога\n"
        "• /settings — «⚙️ Настройки» (модели, персоны, стили, API-ключ)\n"
        "• /documents — «📄 Документы» в памяти текущего диалога\n"
        "• /memorize — инструкция по отправке документов\n"
        "• /reset — «🔄 Сброс контекста»\n"
        "• /logout — заблокировать сейф и выгрузить ключи из памяти\n"
        "• /cancel — отмена текущего действия или сброс ожидания ввода\n"
        "• /panic — настройка паник-пароля для экстренного стирания данных\n\n"
        "🔒 <i>Все данные переписки хранятся на сервере исключительно в зашифрованном виде.</i>"
    )
    await message.answer(
        help_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[get_close_button()]]),
        parse_mode="HTML",
    )


@router.message(Command("logout"))
async def handle_logout_command(message: Message):
    """Locks vault session."""
    await auto_delete_user_message(message)
    user_id = message.from_user.id
    session_manager.lock_session(user_id)

    await message.answer(
        "🔒 <b>Сейф заблокирован.</b>\n"
        "Ключи дешифрования выгружены из оперативной памяти сервера.\n"
        "Для разблокировки введите ваш мастер-пароль:",
        reply_markup=get_locked_reply_keyboard(),
        parse_mode="HTML",
    )


@router.message(Command("cancel"))
async def handle_cancel_command(message: Message, state: FSMContext):
    """Cancels any active FSM state."""
    await auto_delete_user_message(message)
    await state.clear()
    await message.answer(
        "✅ Действие отменено.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[get_close_button()]]),
        parse_mode="HTML",
    )


@router.message(Command("panic"))
async def handle_panic_command(message: Message):
    """Shows panic-password configuration info."""
    await auto_delete_user_message(message)
    user_id = message.from_user.id

    await message.answer(
        "🚨 <b>Аварийный паник-пароль (Durez Wipe):</b>\n\n"
        "Паник-пароль предназначен для экстренных ситуаций. Если при разблокировке бота "
        "вместо мастер-пароля ввести паник-пароль, бот моментально и безвозвратно "
        "<b>сотрёт всю историю переписки, файлы, векторные эмбеддинги и личный API-ключ</b>.\n\n"
        "Настроить паник-пароль можно в разделе «⚙️ Настройки» -> «🚨 Настроить паник-пароль».",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚙️ Перейти в настройки", callback_data="settings_panic")],
            [get_close_button()],
        ]),
        parse_mode="HTML",
    )


@router.message(Command("admin"))
@router.message(F.text == "👑 Админка")
async def handle_admin_command(message: Message):
    """Opens admin dashboard for administrator."""
    await auto_delete_user_message(message)
    user_id = message.from_user.id
    if user_id != settings.ADMIN_USER_ID:
        return

    await message.answer(
        "👑 <b>Панель администратора:</b>\n\nВыберите действие для управления ботом:",
        reply_markup=get_admin_keyboard(),
        parse_mode="HTML",
    )

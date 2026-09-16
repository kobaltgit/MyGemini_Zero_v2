"""
Memory & Document Management Handler for MyGemini Zero v2.
Fulfills user requirements:
- Viewing uploaded document file names immediately in active dialog memory.
- Targeted deletion of individual documents and chunks from ChromaDB.
- Archiving old conversation messages (>30, >60, >90 days).
- Full Zero-Knowledge data wipe.
Supports bilingual rendering (RU / EN) and safe editing.
"""

from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from core.database import async_session_maker
from database.repositories import UserRepository, ConversationRepository
from services.vector_store import VectorStoreManager
from keyboards.inline import (
    get_memory_menu_keyboard,
    get_documents_list_keyboard,
    get_unlock_keyboard,
    get_close_button,
)
from middlewares.auth import session_manager
from core.ui_helpers import safe_edit_message_text, safe_answer_callback
from core.localization import get_text
from core.logger import get_logger

logger = get_logger("user_messages")
router = Router(name="memory")


async def render_documents_view(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Prepares text listing file names and keyboard for documents in active dialog."""
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        active_id = user.active_dialog_id if user else 0
        lang_code = user.language_code if user and user.language_code else "ru"

    vm = VectorStoreManager()
    docs = vm.get_dialog_documents(active_id) if active_id else []

    if not docs:
        if lang_code == "ru":
            text = (
                f"📄 <b>Документы в текущем диалоге (ID {active_id}):</b>\n\n"
                "<i>В памяти этого диалога пока нет загруженных файлов.</i>\n\n"
                "📎 <b>Как добавить документ:</b>\n"
                "Отправьте файл прямо в чат (.pdf, .docx, .txt, .md, .py, .json).\n"
                "Бот автоматически проиндексирует его в векторную память (RAG), "
                "и вы сможете задавать вопросы по его содержанию."
            )
        else:
            text = (
                f"📄 <b>Documents in current dialogue (ID {active_id}):</b>\n\n"
                "<i>No files uploaded in this dialogue yet.</i>\n\n"
                "📎 <b>How to add documents:</b>\n"
                "Send a file (.pdf, .docx, .txt, .md, .py, .json) into the chat.\n"
                "The bot indexes it into RAG vector memory for instant question answering."
            )
        keyboard = get_memory_menu_keyboard(docs_count=0, lang_code=lang_code)
        return text, keyboard

    header = (
        f"📄 <b>Документы в текущем диалоге (ID {active_id}):</b>\n\n"
        f"Всего файлов в базе знаний: <b>{len(docs)}</b>\n"
        if lang_code == "ru"
        else f"📄 <b>Documents in current dialogue (ID {active_id}):</b>\n\n"
        f"Total files in knowledge base: <b>{len(docs)}</b>\n"
    )
    text_lines = [header]

    for i, d in enumerate(docs, 1):
        dt = d.get("timestamp", "")[:19].replace("T", " ")
        dt_str = f" | 📅 {dt}" if dt else ""
        chunk_lbl = "Фрагментов" if lang_code == "ru" else "Chunks"
        text_lines.append(
            f"<b>{i}. 📑 {d['file_name']}</b>\n"
            f"   • {chunk_lbl}: {d['chunks_count']}{dt_str}"
        )

    footer = (
        "\nНажмите на кнопку с именем файла ниже, чтобы удалить его из базы знаний:"
        if lang_code == "ru"
        else "\nClick a button below to remove the document from knowledge base:"
    )
    text_lines.append(footer)

    keyboard = get_documents_list_keyboard(docs, lang_code=lang_code)
    return "\n".join(text_lines), keyboard


@router.callback_query(F.data == "menu_memory")
async def handle_memory_menu(callback: CallbackQuery):
    """Displays memory & document overview for the active dialog."""
    await safe_answer_callback(callback)
    user_id = callback.from_user.id
    text, keyboard = await render_documents_view(user_id)
    await safe_edit_message_text(callback.message, text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "memory_view_docs")
async def handle_view_documents(callback: CallbackQuery):
    """Refreshes documents list."""
    await safe_answer_callback(callback)
    user_id = callback.from_user.id
    text, keyboard = await render_documents_view(user_id)
    await safe_edit_message_text(callback.message, text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data.startswith("doc_del:"))
async def handle_delete_document(callback: CallbackQuery):
    """Deletes a specific document from vector store memory."""
    user_id = callback.from_user.id
    file_hash = callback.data.split("doc_del:")[1]

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        active_id = user.active_dialog_id if user else 0
        lang_code = user.language_code if user and user.language_code else "ru"

    vm = VectorStoreManager()
    success = vm.delete_document(active_id, file_hash)

    msg = (
        ("Документ удален из памяти диалога." if success else "Ошибка при удалении документа.")
        if lang_code == "ru"
        else ("Document deleted from dialogue memory." if success else "Error deleting document.")
    )
    await safe_answer_callback(callback, msg, show_alert=True)

    text, keyboard = await render_documents_view(user_id)
    await safe_edit_message_text(callback.message, text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "memory_archive_start")
async def handle_archive_start(callback: CallbackQuery):
    """Renders options for archiving old messages."""
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
            "Для архивации сообщений сначала разблокируйте память мастер-паролем."
            if lang_code == "ru"
            else "🔒 <b>Vault is locked.</b>\n"
            "To archive messages, please unlock memory with your master password first."
        )
        await safe_edit_message_text(
            callback.message,
            prompt_text,
            reply_markup=get_unlock_keyboard(lang_code),
            parse_mode="HTML",
        )
        return

    if lang_code == "ru":
        text = (
            "📦 <b>Архивация старых сообщений:</b>\n\n"
            "Архивация позволяет очистить устаревшие сообщения диалогов, высвободить место "
            "и повысить скорость работы бота.\n\n"
            "Выберите период, сообщения старше которого будут удалены из базы:"
        )
        btn30 = "📅 Старше 30 дней"
        btn60 = "📅 Старше 60 дней"
        btn90 = "📅 Старше 90 дней"
        back = "⬅️ Назад в память"
    else:
        text = (
            "📦 <b>Archive Old Messages:</b>\n\n"
            "Archiving purges outdated messages to optimize database storage and speed.\n\n"
            "Choose a retention period to delete messages older than:"
        )
        btn30 = "📅 Older than 30 days"
        btn60 = "📅 Older than 60 days"
        btn90 = "📅 Older than 90 days"
        back = "⬅️ Back to Memory"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn30, callback_data="archive_do:30")],
        [InlineKeyboardButton(text=btn60, callback_data="archive_do:60")],
        [InlineKeyboardButton(text=btn90, callback_data="archive_do:90")],
        [InlineKeyboardButton(text=back, callback_data="menu_memory"), get_close_button(lang_code)],
    ])

    await safe_edit_message_text(callback.message, text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("archive_do:"))
async def handle_archive_execute(callback: CallbackQuery):
    """Executes archival of messages older than N days."""
    user_id = callback.from_user.id
    days = int(callback.data.split("archive_do:")[1])
    fernet = session_manager.get_fernet(user_id)

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    if not fernet:
        await safe_answer_callback(
            callback,
            text="Сейф заблокирован." if lang_code == "ru" else "Vault is locked.",
            show_alert=True,
        )
        return

    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

    async with async_session_maker() as session:
        conv_repo = ConversationRepository(session)
        deleted_count = await conv_repo.delete_messages_older_than(user_id, cutoff)

    if deleted_count > 0:
        ans_text = (
            f"✅ Успешно архивировано и удалено {deleted_count} сообщений старше {days} дней."
            if lang_code == "ru"
            else f"✅ Successfully archived and purged {deleted_count} messages older than {days} days."
        )
    else:
        ans_text = (
            f"ℹ️ Нет сообщений старше {days} дней для архивации."
            if lang_code == "ru"
            else f"ℹ️ No messages older than {days} days found."
        )

    await safe_answer_callback(callback, ans_text, show_alert=True)
    text, keyboard = await render_documents_view(user_id)
    await safe_edit_message_text(callback.message, text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "memory_wipe_confirm")
async def handle_wipe_confirm_prompt(callback: CallbackQuery):
    """Prompts for irreversible Zero-Knowledge data wipe confirmation."""
    await safe_answer_callback(callback)
    user_id = callback.from_user.id

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    if lang_code == "ru":
        warning_text = (
            "⚠️ <b>ВНИМАНИЕ: Безвозвратное удаление всех данных</b>\n\n"
            "Это действие удалит:\n"
            "• Все диалоги и зашифрованную историю переписки\n"
            "• Все файлы и векторные эмбеддинги\n"
            "• Ваш профиль, мастер-пароль и сохранённый API-ключ\n\n"
            "Восстановить данные будет невозможно. Вы уверены?"
        )
        btn_wipe = "🔴 ДА, УДАЛИТЬ ВСЁ БЕЗВОЗВРАТНО"
        btn_cancel = "⬅️ Отмена"
    else:
        warning_text = (
            "⚠️ <b>WARNING: Irreversible Full Data Wipe</b>\n\n"
            "This will delete:\n"
            "• All dialogues and encrypted message history\n"
            "• All memory files and vector embeddings\n"
            "• Your profile, master password, and saved API key\n\n"
            "Data recovery will be impossible. Are you sure?"
        )
        btn_wipe = "🔴 YES, DELETE EVERYTHING PERMANENTLY"
        btn_cancel = "⬅️ Cancel"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_wipe, callback_data="memory_wipe_execute")],
        [InlineKeyboardButton(text=btn_cancel, callback_data="menu_memory"), get_close_button(lang_code)],
    ])

    await safe_edit_message_text(callback.message, warning_text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "memory_wipe_execute")
async def handle_wipe_execute(callback: CallbackQuery):
    """Executes full data wipe and purges RAM sessions."""
    user_id = callback.from_user.id

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    async with async_session_maker() as session:
        conv_repo = ConversationRepository(session)
        await conv_repo.clear_user_data(user_id)

    session_manager.lock_session(user_id)

    msg = "Данные удалены" if lang_code == "ru" else "Data purged"
    await safe_answer_callback(callback, msg, show_alert=True)

    done_text = (
        "🗑 <b>Все ваши данные успешно стёрты.</b>\n\n"
        "Хранилище очищено. Для повторного начала работы отправьте команду /start."
        if lang_code == "ru"
        else "🗑 <b>All your data has been permanently wiped.</b>\n\n"
        "Vault is empty. To start fresh, send /start."
    )

    await safe_edit_message_text(
        callback.message,
        done_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[get_close_button(lang_code)]]),
        parse_mode="HTML",
    )

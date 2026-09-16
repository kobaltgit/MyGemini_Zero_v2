"""
Memory & Document Management Handler for MyGemini Zero v2.
Fulfills user requirements:
- Viewing uploaded document file names immediately in active dialog memory.
- Targeted deletion of individual documents and chunks from ChromaDB.
- Archiving old conversation messages and Zero-Knowledge full data wipe.
"""

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from core.database import async_session_maker
from database.repositories import UserRepository, ConversationRepository
from services.vector_store import VectorStoreManager
from keyboards.inline import (
    get_memory_menu_keyboard,
    get_documents_list_keyboard,
    get_close_button,
)
from middlewares.auth import session_manager
from core.config import settings

router = Router(name="memory")


async def render_documents_view(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Prepares text listing file names and keyboard for documents in active dialog."""
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        active_id = user.active_dialog_id if user else 0

    vm = VectorStoreManager()
    docs = vm.get_dialog_documents(active_id) if active_id else []

    if not docs:
        text = (
            f"📄 <b>Документы в текущем диалоге (ID {active_id}):</b>\n\n"
            "<i>В памяти этого диалога пока нет загруженных файлов.</i>\n\n"
            "📎 <b>Как добавить документ:</b>\n"
            "Отправьте файл прямо в чат (.pdf, .docx, .txt, .md, .py, .json).\n"
            "Бот автоматически проиндексирует его в векторную память (RAG), "
            "и вы сможете задавать вопросы по его содержанию."
        )
        keyboard = get_memory_menu_keyboard(docs_count=0)
        return text, keyboard

    text_lines = [
        f"📄 <b>Документы в текущем диалоге (ID {active_id}):</b>\n",
        f"Всего файлов в базе знаний: <b>{len(docs)}</b>\n",
    ]
    for i, d in enumerate(docs, 1):
        dt = d.get("timestamp", "")[:19].replace("T", " ")
        dt_str = f" | 📅 {dt}" if dt else ""
        text_lines.append(
            f"<b>{i}. 📑 {d['file_name']}</b>\n"
            f"   • Фрагментов (чанков): {d['chunks_count']}{dt_str}"
        )

    text_lines.append("\nНажмите на кнопку с именем файла ниже, чтобы удалить его из базы знаний:")
    keyboard = get_documents_list_keyboard(docs)
    return "\n".join(text_lines), keyboard


@router.callback_query(F.data == "menu_memory")
async def handle_memory_menu(callback: CallbackQuery):
    """Displays memory & document overview for the active dialog."""
    try:
        await callback.answer()
    except Exception:
        pass
    user_id = callback.from_user.id
    text, keyboard = await render_documents_view(user_id)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "memory_view_docs")
async def handle_view_documents(callback: CallbackQuery):
    """Refreshes documents list."""
    try:
        await callback.answer()
    except Exception:
        pass
    user_id = callback.from_user.id
    text, keyboard = await render_documents_view(user_id)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data.startswith("doc_del:"))
async def handle_delete_document(callback: CallbackQuery):
    """Deletes a specific document from vector store memory."""
    user_id = callback.from_user.id
    file_hash = callback.data.split("doc_del:")[1]

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        active_id = user.active_dialog_id if user else 0

    vm = VectorStoreManager()
    success = vm.delete_document(active_id, file_hash)

    if success:
        await callback.answer("Документ удален из памяти диалога.", show_alert=True)
    else:
        await callback.answer("Ошибка при удалении документа.", show_alert=True)

    text, keyboard = await render_documents_view(user_id)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "memory_wipe_confirm")
async def handle_wipe_confirm_prompt(callback: CallbackQuery):
    """Prompts for irreversible Zero-Knowledge data wipe confirmation."""
    try:
        await callback.answer()
    except Exception:
        pass
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 ДА, УДАЛИТЬ ВСЁ БЕЗВОЗВРАТНО", callback_data="memory_wipe_execute")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="menu_memory"), get_close_button()],
    ])

    await callback.message.edit_text(
        "⚠️ <b>ВНИМАНИЕ: Безвозвратное удаление всех данных</b>\n\n"
        "Это действие удалит:\n"
        "• Все диалоги и зашифрованную историю переписки\n"
        "• Все файлы и векторные эмбеддинги\n"
        "• Ваш профиль, мастер-пароль и сохранённый API-ключ\n\n"
        "Восстановить данные будет невозможно. Вы уверены?",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(F.data == "memory_wipe_execute")
async def handle_wipe_execute(callback: CallbackQuery):
    """Executes full data wipe and purges RAM sessions."""
    await callback.answer("Данные удалены", show_alert=True)
    user_id = callback.from_user.id

    async with async_session_maker() as session:
        conv_repo = ConversationRepository(session)
        await conv_repo.clear_user_data(user_id)

    session_manager.lock_session(user_id)

    await callback.message.edit_text(
        "🗑 <b>Все ваши данные успешно стёрты.</b>\n\n"
        "Хранилище очищено. Для повторного начала работы отправьте команду /start.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[get_close_button()]]),
        parse_mode="HTML",
    )

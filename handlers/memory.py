"""
Memory & Document Management Handler for MyGemini Zero v2.
Fulfills user requirement #4:
- Viewing all uploaded documents currently stored in vector memory for the active dialog.
- Targeted deletion of individual documents and their chunks from ChromaDB.
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
    get_main_menu_keyboard,
)
from middlewares.auth import session_manager
from core.config import settings

router = Router(name="memory")


@router.callback_query(F.data == "menu_memory")
async def handle_memory_menu(callback: CallbackQuery):
    """Displays memory & document overview for the active dialog."""
    user_id = callback.from_user.id

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        active_id = user.active_dialog_id if user else 0

    vm = VectorStoreManager()
    docs = vm.get_dialog_documents(active_id) if active_id else []

    await callback.message.edit_text(
        f"🧠 <b>Долговременная векторная память (RAG):</b>\n\n"
        f"• <b>Текущий диалог:</b> ID <code>{active_id}</code>\n"
        f"• <b>Загружено документов в память:</b> {len(docs)}\n\n"
        "Вы можете просмотреть загруженные файлы и удалить ненужные по отдельности, "
        "архивировать старые сообщения или выполнить полную очистку данных.",
        reply_markup=get_memory_menu_keyboard(docs_count=len(docs)),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "memory_view_docs")
async def handle_view_documents(callback: CallbackQuery):
    """
    Displays the list of documents uploaded into vector memory with delete buttons.
    """
    user_id = callback.from_user.id

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        active_id = user.active_dialog_id if user else 0

    vm = VectorStoreManager()
    docs = vm.get_dialog_documents(active_id) if active_id else []

    if not docs:
        await callback.message.edit_text(
            "📄 <b>В памяти текущего диалога нет документов.</b>\n\n"
            "Вы можете отправить файл (PDF, DOCX, TXT) прямо в чат, и бот автоматически добавит его в базу знаний.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад в память", callback_data="menu_memory")]
            ]),
            parse_mode="HTML",
        )
        return

    text_lines = ["📄 <b>Документы в памяти активного диалога:</b>\n"]
    for i, d in enumerate(docs, 1):
        text_lines.append(
            f"<b>{i}. {d['file_name']}</b>\n"
            f"   • Фрагментов (чанков): {d['chunks_count']}\n"
            f"   • Дата: {d['timestamp'][:19].replace('T', ' ')}"
        )

    text_lines.append("\nНажмите на кнопку с файлом ниже, чтобы удалить его из памяти:")

    await callback.message.edit_text(
        "\n".join(text_lines),
        reply_markup=get_documents_list_keyboard(docs),
        parse_mode="HTML",
    )
    await callback.answer()


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

    await handle_view_documents(callback)


@router.callback_query(F.data == "memory_wipe_confirm")
async def handle_wipe_confirm_prompt(callback: CallbackQuery):
    """Prompts for irreversible Zero-Knowledge data wipe confirmation."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 ДА, УДАЛИТЬ ВСЁ БЕЗВОЗВРАТНО", callback_data="memory_wipe_execute")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="menu_memory")],
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
    await callback.answer()


@router.callback_query(F.data == "memory_wipe_execute")
async def handle_wipe_execute(callback: CallbackQuery):
    """Executes full data wipe and purges RAM sessions."""
    user_id = callback.from_user.id

    async with async_session_maker() as session:
        conv_repo = ConversationRepository(session)
        await conv_repo.clear_user_data(user_id)

    session_manager.lock_session(user_id)

    await callback.message.edit_text(
        "🗑 <b>Все ваши данные успешно стёрты.</b>\n\n"
        "Хранилище очищено. Для повторного начала работы отправьте команду /start.",
        parse_mode="HTML",
    )
    await callback.answer("Данные удалены", show_alert=True)

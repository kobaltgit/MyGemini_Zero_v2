"""
Dialog Management Handler for MyGemini Zero v2.
Allows users to switch active conversation contexts, rename dialogs,
create new dialogs (with auto-naming), and delete dialogs (including ChromaDB memory).
Displays 📎 icon for dialogs with attached documents and includes ❌ Закрыть button.
Supports full bilingualism (RU / EN), FSM state clearing and safe editing.
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from core.database import async_session_maker
from database.repositories import DialogRepository, UserRepository
from services.vector_store import VectorStoreManager
from keyboards.inline import get_main_menu_keyboard, get_close_button, get_cancel_keyboard
from core.ui_helpers import safe_edit_message_text, safe_answer_callback
from core.config import settings

router = Router(name="dialogs")


class DialogStates(StatesGroup):
    waiting_for_rename = State()


@router.callback_query(F.data == "dialog_list")
async def handle_dialog_list(callback: CallbackQuery, state: FSMContext | None = None):
    """Displays user's conversation threads with active status and document attachment indicators."""
    await safe_answer_callback(callback)
    if state:
        await state.clear()
    user_id = callback.from_user.id

    async with async_session_maker() as session:
        dialog_repo = DialogRepository(session)
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        active_id = user.active_dialog_id if user else None
        dialogs = await dialog_repo.get_user_dialogs(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    if not dialogs:
        no_dlg = "У вас пока нет созданных диалогов." if lang_code == "ru" else "You don't have any dialogs yet."
        btn_create = "➕ Создать новый диалог" if lang_code == "ru" else "➕ Create New Dialog"
        await safe_edit_message_text(
            callback.message,
            no_dlg,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=btn_create, callback_data="dialog_new")],
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

    await safe_edit_message_text(
        callback.message,
        dlg_header,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("dialog_switch:"))
async def handle_dialog_switch(callback: CallbackQuery):
    """Switches active dialog context."""
    user_id = callback.from_user.id
    dialog_id = int(callback.data.split(":")[1])

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        dialog_repo = DialogRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"
        target = await dialog_repo.get_by_id(dialog_id)

        if target and target.user_id == user_id:
            await user_repo.update_settings(user_id=user_id, active_dialog_id=dialog_id)
            switched_msg = f"Переключено на: {target.name}" if lang_code == "ru" else f"Switched to: {target.name}"
            await safe_answer_callback(callback, switched_msg)
        else:
            not_found = "Диалог не найден." if lang_code == "ru" else "Dialogue not found."
            await safe_answer_callback(callback, not_found, show_alert=True)

    await handle_dialog_list(callback)


@router.callback_query(F.data == "dialog_new")
async def handle_dialog_new(callback: CallbackQuery):
    """Instantly creates new active dialog with auto-naming enabled."""
    user_id = callback.from_user.id

    async with async_session_maker() as session:
        dialog_repo = DialogRepository(session)
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"
        dlg_name = "Новый диалог" if lang_code == "ru" else "New Dialogue"
        dialog = await dialog_repo.create_dialog(user_id=user_id, name=dlg_name, set_active=True)

    await safe_answer_callback(callback, "Создан новый диалог" if lang_code == "ru" else "New dialogue created")

    created_text = (
        "✅ <b>Создан новый активный диалог!</b>\n\n"
        "Напишите первое сообщение в чат — бот автоматически подберёт ёмкое название темы по смыслу вашего вопроса.\n\n"
        "<i>Вы также можете переименовать диалог вручную в любой момент через кнопку ✏️ или команду /rename.</i>"
        if lang_code == "ru"
        else "✅ <b>New active dialogue created!</b>\n\n"
        "Send your first message — the bot will automatically name the topic based on your query.\n\n"
        "<i>You can also rename it manually anytime via ✏️ or /rename command.</i>"
    )

    btn_list = "🗂 Список диалогов" if lang_code == "ru" else "🗂 Dialogs List"
    await safe_edit_message_text(
        callback.message,
        created_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=btn_list, callback_data="dialog_list"), get_close_button(lang_code)]
        ]),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("dialog_rename_prompt:"))
async def handle_dialog_rename_prompt(callback: CallbackQuery, state: FSMContext):
    """Prompts for new name for existing dialog."""
    await safe_answer_callback(callback)
    dialog_id = int(callback.data.split(":")[1])
    await state.update_data(rename_dialog_id=dialog_id)
    await state.set_state(DialogStates.waiting_for_rename)

    user_id = callback.from_user.id
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    prompt_text = (
        "✏️ Введите новое название для этого диалога в чат:"
        if lang_code == "ru"
        else "✏️ Send new name for this dialogue in chat:"
    )

    await safe_edit_message_text(
        callback.message,
        prompt_text,
        reply_markup=get_cancel_keyboard(callback_data="dialog_list", lang_code=lang_code),
        parse_mode="HTML",
    )


@router.message(DialogStates.waiting_for_rename)
async def process_dialog_rename(message: Message, state: FSMContext):
    """Applies rename to dialog and deletes user prompt message for cleanliness."""
    user_id = message.from_user.id
    new_name = message.text.strip() if message.text else ""
    data = await state.get_data()
    dialog_id = data.get("rename_dialog_id")
    await state.clear()

    try:
        await message.delete()
    except Exception:
        pass

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    if dialog_id and new_name:
        async with async_session_maker() as session:
            dialog_repo = DialogRepository(session)
            await dialog_repo.rename_dialog(dialog_id, new_name)
        confirm_text = (
            f"✅ Диалог переименован в: <b>{new_name}</b>"
            if lang_code == "ru"
            else f"✅ Dialogue renamed to: <b>{new_name}</b>"
        )
        btn_list = "🗂 Список диалогов" if lang_code == "ru" else "🗂 Dialogs List"
        await message.answer(
            confirm_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=btn_list, callback_data="dialog_list"), get_close_button(lang_code)]
            ]),
            parse_mode="HTML",
        )
    else:
        fail_text = "⚠️ Не удалось переименовать диалог." if lang_code == "ru" else "⚠️ Could not rename dialogue."
        await message.answer(fail_text)


@router.callback_query(F.data.startswith("dialog_delete:"))
async def handle_dialog_delete(callback: CallbackQuery):
    """Deletes dialog from database and purges its vector store memory."""
    user_id = callback.from_user.id
    dialog_id = int(callback.data.split(":")[1])

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        dialog_repo = DialogRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"
        success = await dialog_repo.delete_dialog(user_id=user_id, dialog_id=dialog_id)

    if success:
        vm = VectorStoreManager()
        vm.delete_dialog_memory(dialog_id)
        del_msg = "Диалог и его векторная память удалены." if lang_code == "ru" else "Dialogue and vector memory deleted."
        await safe_answer_callback(callback, del_msg, show_alert=True)
    else:
        err_msg = "Ошибка удаления диалога." if lang_code == "ru" else "Error deleting dialogue."
        await safe_answer_callback(callback, err_msg, show_alert=True)

    await handle_dialog_list(callback)

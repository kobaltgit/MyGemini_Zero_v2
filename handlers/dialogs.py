"""
Dialog Management Handler for MyGemini Zero v2.
Allows users to switch active conversation contexts, rename dialogs,
create new dialogs (with auto-naming), and delete dialogs (including ChromaDB memory).
Displays 📎 icon for dialogs with attached documents and includes ❌ Закрыть button.
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from core.database import async_session_maker
from database.repositories import DialogRepository, UserRepository
from services.vector_store import VectorStoreManager
from keyboards.inline import get_main_menu_keyboard, get_close_button
from core.config import settings

router = Router(name="dialogs")


class DialogStates(StatesGroup):
    waiting_for_rename = State()


@router.callback_query(F.data == "dialog_list")
async def handle_dialog_list(callback: CallbackQuery):
    """Displays user's conversation threads with active status and document attachment indicators."""
    try:
        await callback.answer()
    except Exception:
        pass
    user_id = callback.from_user.id

    async with async_session_maker() as session:
        dialog_repo = DialogRepository(session)
        user_repo = UserRepository(session)

        user = await user_repo.get_by_id(user_id)
        active_id = user.active_dialog_id if user else None
        dialogs = await dialog_repo.get_user_dialogs(user_id)

    if not dialogs:
        await callback.message.edit_text(
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

    await callback.message.edit_text(
        "🗂 <b>Ваши диалоги:</b>\n\n"
        "🔘 — активный диалог (текущий контекст)\n"
        "📎 — диалог содержит прикреплённые документы (RAG-память)\n\n"
        "Нажмите на название диалога, чтобы переключиться на него:",
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
        target = await dialog_repo.get_by_id(dialog_id)

        if target and target.user_id == user_id:
            await user_repo.update_settings(user_id=user_id, active_dialog_id=dialog_id)
            await callback.answer(f"Переключено на: {target.name}")
        else:
            await callback.answer("Диалог не найден.", show_alert=True)

    await handle_dialog_list(callback)


@router.callback_query(F.data == "dialog_new")
async def handle_dialog_new(callback: CallbackQuery):
    """Instantly creates new active dialog with auto-naming enabled."""
    await callback.answer("Создан новый диалог")
    user_id = callback.from_user.id

    async with async_session_maker() as session:
        dialog_repo = DialogRepository(session)
        dialog = await dialog_repo.create_dialog(user_id=user_id, name="Новый диалог", set_active=True)

    await callback.message.edit_text(
        f"✅ <b>Создан новый активный диалог!</b>\n\n"
        f"Напишите первое сообщение в чат — бот автоматически подберёт ёмкое название темы по смыслу вашего вопроса.\n\n"
        f"<i>Вы также можете переименовать диалог вручную в любой момент через кнопку ✏️ или команду /rename.</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗂 Список диалогов", callback_data="dialog_list"), get_close_button()]
        ]),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("dialog_rename_prompt:"))
async def handle_dialog_rename_prompt(callback: CallbackQuery, state: FSMContext):
    """Prompts for new name for existing dialog."""
    await callback.answer()
    dialog_id = int(callback.data.split(":")[1])
    await state.update_data(rename_dialog_id=dialog_id)
    await state.set_state(DialogStates.waiting_for_rename)

    await callback.message.edit_text(
        "✏️ Введите новое название для этого диалога в чат:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад к диалогам", callback_data="dialog_list"), get_close_button()]
        ]),
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

    if dialog_id and new_name:
        async with async_session_maker() as session:
            dialog_repo = DialogRepository(session)
            await dialog_repo.rename_dialog(dialog_id, new_name)
        await message.answer(
            f"✅ Диалог переименован в: <b>{new_name}</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🗂 Список диалогов", callback_data="dialog_list"), get_close_button()]
            ]),
            parse_mode="HTML",
        )
    else:
        await message.answer("⚠️ Не удалось переименовать диалог.")


@router.callback_query(F.data.startswith("dialog_delete:"))
async def handle_dialog_delete(callback: CallbackQuery):
    """Deletes dialog from database and purges its vector store memory."""
    user_id = callback.from_user.id
    dialog_id = int(callback.data.split(":")[1])

    async with async_session_maker() as session:
        dialog_repo = DialogRepository(session)
        success = await dialog_repo.delete_dialog(user_id=user_id, dialog_id=dialog_id)

    if success:
        vm = VectorStoreManager()
        vm.delete_dialog_memory(dialog_id)
        await callback.answer("Диалог и его векторная память удалены.", show_alert=True)
    else:
        await callback.answer("Ошибка удаления диалога.", show_alert=True)

    await handle_dialog_list(callback)

"""
Admin Panel Handler for MyGemini Zero v2.
Fulfills user requirements #5 and #6:
- Subscriber analytics with comprehensive details (Name, ID, dates, renewal count, days left).
- Enhanced CSV export with UTF-8 BOM encoding for seamless Excel viewing.
- Maintenance mode toggle and broadcast notifications.
"""

import io
import csv
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from core.database import async_session_maker
from database.repositories import (
    UserRepository,
    PaymentRepository,
    SettingsRepository,
)
from keyboards.inline import get_admin_keyboard, get_main_menu_keyboard
from core.config import settings
from core.logger import get_logger

logger = get_logger("user_messages")
router = Router(name="admin")


class AdminStates(StatesGroup):
    waiting_for_broadcast = State()


def admin_only(user_id: int) -> bool:
    """Verifies that caller is the designated system administrator."""
    return user_id == settings.ADMIN_USER_ID


@router.message(Command("admin"))
@router.callback_query(F.data == "menu_admin")
async def handle_admin_panel(event: Message | CallbackQuery):
    """Entry point for the admin control dashboard."""
    user_id = event.from_user.id
    if not admin_only(user_id):
        if isinstance(event, CallbackQuery):
            await event.answer("⛔️ Доступ разрешён только администратору.", show_alert=True)
        return

    async with async_session_maker() as session:
        settings_repo = SettingsRepository(session)
        is_maintenance = await settings_repo.is_maintenance_mode()

    text = (
        "👑 <b>Панель администратора MyGemini Zero v2</b>\n\n"
        "Здесь вы можете просматривать статистику оплат и пользователей, "
        "детализацию по подписчикам, выгружать базу данных в CSV и управлять режимом обслуживания."
    )

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=get_admin_keyboard(is_maintenance), parse_mode="HTML")
        await event.answer()
    else:
        await event.answer(text, reply_markup=get_admin_keyboard(is_maintenance), parse_mode="HTML")


@router.callback_query(F.data == "admin_stats")
async def handle_admin_stats(callback: CallbackQuery):
    """Displays aggregated operational metrics."""
    if not admin_only(callback.from_user.id):
        return

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        pay_repo = PaymentRepository(session)

        all_users = await user_repo.get_all_users()
        subscribers = await user_repo.get_all_subscribers()
        payment_stats = await pay_repo.get_payment_stats()

    total_users = len(all_users)
    active_subs = len([s for s in subscribers if s.subscription_status == "active"])
    total_rev_rub = payment_stats["total_revenue"] // 100

    text = (
        "📊 <b>Общая статистика бота:</b>\n\n"
        f"• <b>Всего пользователей:</b> {total_users}\n"
        f"• <b>Активных подписчиков:</b> {active_subs}\n"
        f"• <b>Всего транзакций:</b> {payment_stats['total_payments']}\n"
        f"• <b>Платящих пользователей:</b> {payment_stats['unique_paying_users']}\n"
        f"• <b>Общая выручка:</b> {total_rev_rub} ₽\n"
    )

    await callback.message.edit_text(text, reply_markup=get_admin_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_subscribers")
async def handle_admin_subscribers_list(callback: CallbackQuery):
    """
    Fulfills requirement #5:
    Displays subscribers with full details: Name, ID, dates, renewal count, days left.
    """
    if not admin_only(callback.from_user.id):
        return

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        pay_repo = PaymentRepository(session)

        subscribers = await user_repo.get_all_subscribers()
        all_payments = await pay_repo.get_all_payments()

    if not subscribers:
        await callback.message.edit_text(
            "👥 <b>Подписчиков пока нет.</b>",
            reply_markup=get_admin_keyboard(),
            parse_mode="HTML",
        )
        return

    # Map user payments
    user_payments_map = {}
    for p in all_payments:
        user_payments_map.setdefault(p.user_id, []).append(p)

    now = datetime.now()
    lines = ["👥 <b>Список подписчиков с подробностями:</b>\n"]

    for i, sub in enumerate(subscribers, 1):
        uname = f"@{sub.username}" if sub.username else "без username"
        full_name = f"{sub.first_name or ''} {sub.last_name or ''}".strip() or "Аноним"
        payments = user_payments_map.get(sub.user_id, [])
        renewals_count = len(payments)
        total_paid_rub = sum(p.amount for p in payments) // 100

        # Calculate days left
        days_left_str = "—"
        if sub.subscription_end_date:
            try:
                end_dt = datetime.strptime(sub.subscription_end_date[:10], "%Y-%m-%d")
                days_left = (end_dt - now).days
                days_left_str = f"{days_left} дн." if days_left >= 0 else "истекла"
            except Exception:
                days_left_str = "—"

        lines.append(
            f"<b>{i}. {full_name}</b> ({uname})\n"
            f"   • <b>ID:</b> <code>{sub.user_id}</code>\n"
            f"   • <b>Статус:</b> {sub.subscription_status}\n"
            f"   • <b>Действует до:</b> {sub.subscription_end_date or '—'} ({days_left_str})\n"
            f"   • <b>Оплат / Продлений:</b> {renewals_count} раз(а)\n"
            f"   • <b>Всего внесено:</b> {total_paid_rub} ₽\n"
        )

    text = "\n".join(lines)
    # Check Telegram limit for single text
    if len(text) > 4000:
        text = text[:3900] + "\n\n... (список сокращён, полный отчёт выгрузите в CSV)"

    await callback.message.edit_text(text, reply_markup=get_admin_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_export_csv")
async def handle_admin_export_csv(callback: CallbackQuery, bot: Bot):
    """
    Fulfills requirement #6:
    Exports all users and subscription metrics into a CSV file encoded with UTF-8 BOM (utf-8-sig).
    """
    if not admin_only(callback.from_user.id):
        return

    await callback.answer("Генерация CSV отчёта...")

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        pay_repo = PaymentRepository(session)

        users = await user_repo.get_all_users()
        payments = await pay_repo.get_all_payments()

    user_payments_map = {}
    for p in payments:
        user_payments_map.setdefault(p.user_id, []).append(p)

    # In-memory text buffer
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", lineterminator="\n")

    # CSV Header
    writer.writerow([
        "User ID",
        "Username",
        "First Name",
        "Last Name",
        "Language",
        "First Interaction",
        "Subscription Status",
        "Subscription End Date",
        "Renewals Count",
        "Total Paid (RUB)",
        "Is Blocked",
        "Bot Style",
        "Gemini Model",
        "Active Persona",
    ])

    for u in users:
        u_payments = user_payments_map.get(u.user_id, [])
        renewals = len(u_payments)
        total_rub = sum(p.amount for p in u_payments) // 100

        writer.writerow([
            u.user_id,
            u.username or "",
            u.first_name or "",
            u.last_name or "",
            u.language_code,
            u.first_interaction_date or "",
            u.subscription_status,
            u.subscription_end_date or "",
            renewals,
            total_rub,
            u.is_blocked,
            u.bot_style,
            u.gemini_model or settings.DEFAULT_MODEL_ID,
            u.active_persona,
        ])

    # Convert to bytes with UTF-8 BOM so Excel opens Cyrillic properly
    csv_bytes = output.getvalue().encode("utf-8-sig")
    now_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"mygemini_users_{now_tag}.csv"

    doc = BufferedInputFile(file=csv_bytes, filename=file_name)

    await bot.send_document(
        chat_id=callback.from_user.id,
        document=doc,
        caption=f"📥 <b>Экспорт базы пользователей</b>\n\nВсего записей: {len(users)}\nКодировка: UTF-8 BOM (для Excel)",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_toggle_maintenance")
async def handle_admin_toggle_maintenance(callback: CallbackQuery):
    """Toggles maintenance mode."""
    if not admin_only(callback.from_user.id):
        return

    async with async_session_maker() as session:
        settings_repo = SettingsRepository(session)
        current = await settings_repo.is_maintenance_mode()
        new_val = not current
        await settings_repo.set_maintenance_mode(new_val)

    status_str = "ВКЛЮЧЁН" if new_val else "ВЫКЛЮЧЕН"
    await callback.answer(f"Режим обслуживания {status_str}!", show_alert=True)
    await handle_admin_panel(callback)


@router.callback_query(F.data == "admin_broadcast")
async def handle_admin_broadcast_prompt(callback: CallbackQuery, state: FSMContext):
    """Prompts admin for broadcast text."""
    if not admin_only(callback.from_user.id):
        return

    await state.set_state(AdminStates.waiting_for_broadcast)
    await callback.message.edit_text(
        "📢 <b>Рассылка сообщения всем пользователям:</b>\n\n"
        "Отправьте текст сообщения для рассылки ответным сообщением в чат. "
        "Для отмены отправьте /cancel.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_broadcast)
async def process_admin_broadcast(message: Message, state: FSMContext, bot: Bot):
    """Executes broadcast delivery to all users."""
    if not admin_only(message.from_user.id):
        return

    if message.text and message.text.startswith("/cancel"):
        await state.clear()
        await message.answer("Рассылка отменена.", reply_markup=get_main_menu_keyboard(is_unlocked=True, is_admin=True))
        return

    text = message.text or message.caption or ""
    await state.clear()

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        users = await user_repo.get_all_users()

    sent_count = 0
    fail_count = 0

    progress_msg = await message.answer(f"🚀 Запуск рассылки на {len(users)} пользователей...")

    for u in users:
        try:
            await bot.send_message(chat_id=u.user_id, text=text, parse_mode="HTML")
            sent_count += 1
        except Exception:
            fail_count += 1

    await progress_msg.edit_text(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"• Успешно доставлено: {sent_count}\n"
        f"• Ошибок (заблокировали бота): {fail_count}",
        parse_mode="HTML",
    )

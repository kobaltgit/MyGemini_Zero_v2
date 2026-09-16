"""
Admin Panel Handler for MyGemini Zero v2.
Fulfills user requirements #5 and #6 + complete User Management from v1:
- Subscriber analytics with comprehensive details (Name, ID, dates, renewal count, days left).
- Enhanced CSV export with UTF-8 BOM encoding for seamless Excel viewing.
- Maintenance mode toggle and broadcast notifications.
- Complete User Management: Search user by ID, user card, block/unblock, reset API key,
  manual subscription extension (+30, +90, +365 days) with user PM notification, and admin reply to user.
Supports full bilingualism and safe editing.
"""

import io
import csv
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from core.database import async_session_maker
from database.repositories import (
    UserRepository,
    PaymentRepository,
    SettingsRepository,
)
from keyboards.inline import (
    get_admin_keyboard,
    get_admin_user_actions_keyboard,
    get_admin_extend_sub_keyboard,
    get_cancel_keyboard,
    get_close_button,
)
from core.ui_helpers import safe_edit_message_text, safe_answer_callback
from core.config import settings
from core.localization import get_text
from core.logger import get_logger

logger = get_logger("user_messages")
router = Router(name="admin")


class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_user_id = State()
    waiting_for_admin_reply = State()


def admin_only(user_id: int) -> bool:
    """Verifies that caller is the designated system administrator."""
    return user_id == settings.ADMIN_USER_ID


@router.message(Command("admin"))
@router.callback_query(F.data == "menu_admin")
async def handle_admin_panel(event: Message | CallbackQuery, state: FSMContext | None = None):
    """Entry point for the admin control dashboard."""
    if state:
        await state.clear()
    user_id = event.from_user.id
    if not admin_only(user_id):
        if isinstance(event, CallbackQuery):
            await safe_answer_callback(event, "⛔️ Доступ разрешён только администратору.", show_alert=True)
        return

    async with async_session_maker() as session:
        settings_repo = SettingsRepository(session)
        is_maintenance = await settings_repo.is_maintenance_mode()
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    text = (
        "👑 <b>Панель администратора MyGemini Zero v2</b>\n\n"
        "Здесь вы можете просматривать статистику оплат и пользователей, "
        "детализацию по подписчикам, управлять пользователями по ID, "
        "выгружать базу данных в CSV и переключать режим обслуживания."
        if lang_code == "ru"
        else "👑 <b>MyGemini Zero v2 Administrator Panel</b>\n\n"
        "View payment & user stats, subscriber details, manage users by ID, "
        "export CSV reports, and toggle maintenance mode."
    )

    kb = get_admin_keyboard(is_maintenance, lang_code=lang_code)

    if isinstance(event, CallbackQuery):
        await safe_answer_callback(event)
        await safe_edit_message_text(event.message, text, reply_markup=kb, parse_mode="HTML")
    else:
        await event.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "admin_stats")
async def handle_admin_stats(callback: CallbackQuery):
    """Displays aggregated operational metrics."""
    if not admin_only(callback.from_user.id):
        return
    await safe_answer_callback(callback)

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        pay_repo = PaymentRepository(session)
        user = await user_repo.get_by_id(callback.from_user.id)
        lang_code = user.language_code if user and user.language_code else "ru"

        all_users = await user_repo.get_all_users()
        subscribers = await user_repo.get_all_subscribers()
        payment_stats = await pay_repo.get_payment_stats()

    total_users = len(all_users)
    active_subs = len([s for s in subscribers if user_repo.is_subscription_active(s)])
    total_rev_rub = payment_stats["total_revenue"] // 100

    if lang_code == "ru":
        text = (
            "📊 <b>Общая статистика бота:</b>\n\n"
            f"• <b>Всего пользователей:</b> {total_users}\n"
            f"• <b>Активных подписчиков:</b> {active_subs}\n"
            f"• <b>Всего транзакций:</b> {payment_stats['total_payments']}\n"
            f"• <b>Платящих пользователей:</b> {payment_stats['unique_paying_users']}\n"
            f"• <b>Общая выручка:</b> {total_rev_rub} ₽\n"
        )
    else:
        text = (
            "📊 <b>Bot General Statistics:</b>\n\n"
            f"• <b>Total Users:</b> {total_users}\n"
            f"• <b>Active Subscribers:</b> {active_subs}\n"
            f"• <b>Total Transactions:</b> {payment_stats['total_payments']}\n"
            f"• <b>Paying Users:</b> {payment_stats['unique_paying_users']}\n"
            f"• <b>Total Revenue:</b> {total_rev_rub} ₽\n"
        )

    await safe_edit_message_text(
        callback.message,
        text,
        reply_markup=get_admin_keyboard(lang_code=lang_code),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_subscribers")
async def handle_admin_subscribers_list(callback: CallbackQuery):
    """Displays subscribers with full details: Name, ID, dates, renewal count, days left."""
    if not admin_only(callback.from_user.id):
        return
    await safe_answer_callback(callback)

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        pay_repo = PaymentRepository(session)
        user = await user_repo.get_by_id(callback.from_user.id)
        lang_code = user.language_code if user and user.language_code else "ru"

        subscribers = await user_repo.get_all_subscribers()
        all_payments = await pay_repo.get_all_payments()

    if not subscribers:
        no_subs = "👥 <b>Подписчиков пока нет.</b>" if lang_code == "ru" else "👥 <b>No subscribers yet.</b>"
        await safe_edit_message_text(
            callback.message,
            no_subs,
            reply_markup=get_admin_keyboard(lang_code=lang_code),
            parse_mode="HTML",
        )
        return

    user_payments_map = {}
    for p in all_payments:
        user_payments_map.setdefault(p.user_id, []).append(p)

    now = datetime.now()

    def subscriber_sort_key(s):
        payments = user_payments_map.get(s.user_id, [])
        total_paid = sum(p.amount for p in payments)
        is_active = 1 if user_repo.is_subscription_active(s) else 0
        end_d = s.subscription_end_date or ""
        return (is_active, end_d, total_paid)

    sorted_subscribers = sorted(subscribers, key=subscriber_sort_key, reverse=True)
    lines = ["👥 <b>Список подписчиков с подробностями:</b>\n" if lang_code == "ru" else "👥 <b>Subscribers List:</b>\n"]

    for i, sub in enumerate(sorted_subscribers, 1):
        uname = f"@{sub.username}" if sub.username else "без username"
        full_name = f"{sub.first_name or ''} {sub.last_name or ''}".strip() or "Аноним"
        payments = user_payments_map.get(sub.user_id, [])
        renewals_count = len(payments)
        total_paid_rub = sum(p.amount for p in payments) // 100
        is_active = user_repo.is_subscription_active(sub)

        marker = "🟢" if is_active else "⚪"

        days_left_str = "—"
        if sub.subscription_end_date:
            try:
                end_dt = datetime.strptime(sub.subscription_end_date[:10], "%Y-%m-%d")
                days_left = (end_dt.date() - now.date()).days
                if days_left >= 0:
                    days_left_str = f"{days_left} дн." if lang_code == "ru" else f"{days_left} d."
                else:
                    days_left_str = "истекла" if lang_code == "ru" else "expired"
            except Exception:
                days_left_str = "—"

        if sub.user_id == settings.ADMIN_USER_ID:
            status_label = "👑 Администратор" if lang_code == "ru" else "👑 Administrator"
        elif is_active:
            status_label = "🟢 Активна" if lang_code == "ru" else "🟢 Active"
        elif days_left_str in ("истекла", "expired"):
            status_label = "🔴 Истекла" if lang_code == "ru" else "🔴 Expired"
        else:
            status_label = sub.subscription_status

        lines.append(
            f"{marker} <b>{i}. {full_name}</b> ({uname})\n"
            f"   • <b>ID:</b> <code>{sub.user_id}</code>\n"
            f"   • <b>Статус:</b> {status_label}\n"
            f"   • <b>Действует до:</b> {sub.subscription_end_date or '—'} ({days_left_str})\n"
            f"   • <b>Оплат / Продлений:</b> {renewals_count} раз(а)\n"
            f"   • <b>Всего внесено:</b> {total_paid_rub} ₽\n"
        )

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3900] + "\n\n... (список сокращён, полный отчёт выгрузите в CSV)"

    await safe_edit_message_text(
        callback.message,
        text,
        reply_markup=get_admin_keyboard(lang_code=lang_code),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_export_csv")
async def handle_admin_export_csv(callback: CallbackQuery, bot: Bot):
    """Exports all users and subscription metrics into a CSV file with UTF-8 BOM."""
    if not admin_only(callback.from_user.id):
        return

    await safe_answer_callback(callback, "Генерация CSV отчёта...")

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        pay_repo = PaymentRepository(session)
        users = await user_repo.get_all_users()
        payments = await pay_repo.get_all_payments()

    user_payments_map = {}
    for p in payments:
        user_payments_map.setdefault(p.user_id, []).append(p)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", lineterminator="\n")

    writer.writerow([
        "User ID", "Username", "First Name", "Last Name", "Language",
        "First Interaction", "Subscription Status", "Subscription End Date",
        "Renewals Count", "Total Paid (RUB)", "Is Blocked", "Bot Style",
        "Gemini Model", "Active Persona",
    ])

    for u in users:
        u_payments = user_payments_map.get(u.user_id, [])
        renewals = len(u_payments)
        total_rub = sum(p.amount for p in u_payments) // 100
        writer.writerow([
            u.user_id, u.username or "", u.first_name or "", u.last_name or "",
            u.language_code, u.first_interaction_date or "", u.subscription_status,
            u.subscription_end_date or "", renewals, total_rub,
            "ДА" if u.is_blocked else "НЕТ", u.bot_style, u.gemini_model, u.active_persona,
        ])

    csv_bytes = output.getvalue().encode("utf-8-sig")
    doc_file = BufferedInputFile(csv_bytes, filename=f"users_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

    await bot.send_document(
        chat_id=callback.from_user.id,
        document=doc_file,
        caption="📊 Выгрузка базы данных пользователей и подписок (UTF-8 BOM).",
    )


# --- User Management by ID ---

async def render_admin_user_card(target_user_id: int, lang_code: str = "ru") -> tuple[str, InlineKeyboardMarkup]:
    """Renders user info card and management keyboard for admin."""
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        pay_repo = PaymentRepository(session)
        target = await user_repo.get_by_id(target_user_id)
        if not target:
            not_found = f"❌ Пользователь с ID <code>{target_user_id}</code> не найден." if lang_code == "ru" else f"❌ User with ID <code>{target_user_id}</code> not found."
            return not_found, InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_admin")]])

        payments = await pay_repo.get_user_payments(target_user_id)
        is_sub_active = user_repo.is_subscription_active(target)

    full_name = f"{target.first_name or ''} {target.last_name or ''}".strip() or "Аноним"
    uname = f"@{target.username}" if target.username else "без username"
    total_paid_rub = sum(p.amount for p in payments) // 100
    has_key = "✅ Установлен" if target.api_key else "❌ Не установлен"
    blocked_str = "⛔️ ЗАБЛОКИРОВАН" if target.is_blocked else "🟢 Активен"
    sub_status = "🟢 Активна" if is_sub_active else f"🔴 {target.subscription_status}"

    card_text = (
        f"👤 <b>Карточка пользователя:</b>\n\n"
        f"• <b>Имя:</b> {full_name} ({uname})\n"
        f"• <b>ID:</b> <code>{target.user_id}</code>\n"
        f"• <b>Доступ:</b> {blocked_str}\n"
        f"• <b>Дата регистрации:</b> {target.first_interaction_date or '—'}\n"
        f"• <b>Язык:</b> {target.language_code}\n"
        f"• <b>API-ключ:</b> {has_key}\n"
        f"• <b>Модель:</b> {target.gemini_model}\n"
        f"• <b>Стиль / Роль:</b> {target.bot_style} / {target.active_persona}\n\n"
        f"💎 <b>Подписка:</b>\n"
        f"• <b>Статус:</b> {sub_status}\n"
        f"• <b>Действует до:</b> {target.subscription_end_date or '—'}\n"
        f"• <b>Оплат:</b> {len(payments)} раз(а) (всего {total_paid_rub} ₽)\n"
    )

    kb = get_admin_user_actions_keyboard(target.user_id, is_blocked=bool(target.is_blocked), lang_code=lang_code)
    return card_text, kb


@router.callback_query(F.data == "admin_user_search")
async def handle_admin_user_search_prompt(callback: CallbackQuery, state: FSMContext):
    """Prompts admin to enter user ID."""
    if not admin_only(callback.from_user.id):
        return
    await safe_answer_callback(callback)
    await state.set_state(AdminStates.waiting_for_user_id)

    await safe_edit_message_text(
        callback.message,
        "🔍 <b>Введите Telegram ID пользователя в чат:</b>\n(Например: <code>123456789</code>)",
        reply_markup=get_cancel_keyboard(callback_data="menu_admin"),
        parse_mode="HTML",
    )


@router.message(AdminStates.waiting_for_user_id)
async def process_admin_user_search(message: Message, state: FSMContext):
    """Receives target user ID and displays their card."""
    if not admin_only(message.from_user.id):
        return
    await state.clear()
    raw_id = message.text.strip() if message.text else ""

    try:
        target_id = int(raw_id)
    except ValueError:
        await message.answer("⚠️ Некорректный ID. Введите число.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_admin")]]))
        return

    text, kb = await render_admin_user_card(target_id)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(Command("user"))
async def handle_user_command(message: Message, command: CommandObject):
    """Quick command: /user <id>."""
    if not admin_only(message.from_user.id):
        return
    arg = command.args.strip() if command.args else ""
    if not arg or not arg.isdigit():
        await message.answer("Использование: <code>/user 123456789</code>", parse_mode="HTML")
        return

    text, kb = await render_admin_user_card(int(arg))
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("admin_user_card:"))
async def handle_admin_user_card_cb(callback: CallbackQuery):
    """Refreshes user card."""
    if not admin_only(callback.from_user.id):
        return
    await safe_answer_callback(callback)
    uid = int(callback.data.split(":")[1])
    text, kb = await render_admin_user_card(uid)
    await safe_edit_message_text(callback.message, text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("admin_toggle_block:"))
async def handle_admin_toggle_block(callback: CallbackQuery):
    """Toggles user block status."""
    if not admin_only(callback.from_user.id):
        return
    uid = int(callback.data.split(":")[1])

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        target = await user_repo.get_by_id(uid)
        new_state = not bool(target.is_blocked) if target else True
        await user_repo.set_blocked(uid, new_state)

    status_msg = "Пользователь заблокирован." if new_state else "Пользователь разблокирован."
    await safe_answer_callback(callback, status_msg, show_alert=True)
    text, kb = await render_admin_user_card(uid)
    await safe_edit_message_text(callback.message, text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("admin_reset_key:"))
async def handle_admin_reset_key(callback: CallbackQuery):
    """Resets user API key."""
    if not admin_only(callback.from_user.id):
        return
    uid = int(callback.data.split(":")[1])

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        await user_repo.reset_api_key(uid)

    await safe_answer_callback(callback, f"API-ключ пользователя {uid} сброшен.", show_alert=True)
    text, kb = await render_admin_user_card(uid)
    await safe_edit_message_text(callback.message, text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("admin_extend_sub:"))
async def handle_admin_extend_sub_prompt(callback: CallbackQuery):
    """Shows period options for manual subscription extension."""
    if not admin_only(callback.from_user.id):
        return
    await safe_answer_callback(callback)
    uid = int(callback.data.split(":")[1])

    prompt = f"➕ <b>Выберите срок продления подписки для пользователя <code>{uid}</code>:</b>"
    kb = get_admin_extend_sub_keyboard(uid)
    await safe_edit_message_text(callback.message, prompt, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("admin_extend_days:"))
async def handle_admin_extend_days(callback: CallbackQuery, bot: Bot):
    """Executes subscription extension and sends notification to user."""
    if not admin_only(callback.from_user.id):
        return
    parts = callback.data.split(":")
    uid, days = int(parts[1]), int(parts[2])

    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        pay_repo = PaymentRepository(session)
        target = await user_repo.get_by_id(uid)
        current_end_date = None
        if target and target.subscription_end_date:
            try:
                current_end_date = datetime.strptime(target.subscription_end_date[:10], "%Y-%m-%d")
            except Exception:
                current_end_date = None

        if current_end_date and current_end_date > now:
            new_end = current_end_date + timedelta(days=days)
        else:
            new_end = now + timedelta(days=days)

        new_end_str = new_end.strftime("%Y-%m-%d")
        await user_repo.update_subscription(uid, status="active", end_date=new_end_str)

        # Record manual extension transaction
        await pay_repo.record_payment(
            user_id=uid,
            plan_id=f"admin_grant_{days}d",
            amount=0,
            currency="RUB",
            payment_date=now_str,
            subscription_end_date=new_end_str,
            telegram_charge_id="ADMIN_GRANT",
            provider_charge_id="ADMIN_GRANT",
        )

    await safe_answer_callback(callback, f"Подписка продлена до {new_end_str}!", show_alert=True)

    # Notify user in PM
    user_lang = target.language_code if target and target.language_code else "ru"
    notify_text = (
        f"🎉 <b>Отличная новость!</b> Администратор продлил вашу подписку на <b>{days} дней</b>.\n\n"
        f"Теперь она действует до: <code>{new_end_str}</code>."
        if user_lang == "ru"
        else f"🎉 <b>Great news!</b> An administrator extended your subscription by <b>{days} days</b>.\n\n"
        f"It is now valid until: <code>{new_end_str}</code>."
    )
    try:
        await bot.send_message(chat_id=uid, text=notify_text, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Failed to send sub extension notification to user {uid}: {e}")

    text, kb = await render_admin_user_card(uid)
    await safe_edit_message_text(callback.message, text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("admin_reply_user:"))
async def handle_admin_reply_prompt(callback: CallbackQuery, state: FSMContext):
    """Prompts admin for text to send to user."""
    if not admin_only(callback.from_user.id):
        return
    await safe_answer_callback(callback)
    uid = int(callback.data.split(":")[1])

    await state.update_data(reply_target_user_id=uid)
    await state.set_state(AdminStates.waiting_for_admin_reply)

    prompt = f"✉️ <b>Введите текст сообщения для пользователя <code>{uid}</code>:</b>"
    await safe_edit_message_text(
        callback.message,
        prompt,
        reply_markup=get_cancel_keyboard(callback_data=f"admin_user_card:{uid}"),
        parse_mode="HTML",
    )


@router.message(AdminStates.waiting_for_admin_reply)
async def process_admin_reply(message: Message, state: FSMContext, bot: Bot):
    """Sends admin reply to user."""
    if not admin_only(message.from_user.id):
        return
    data = await state.get_data()
    target_id = data.get("reply_target_user_id")
    await state.clear()
    reply_text = message.text.strip() if message.text else ""

    if not target_id or not reply_text:
        await message.answer("⚠️ Пустое сообщение или пользователь не указан.")
        return

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        target = await user_repo.get_by_id(target_id)
        user_lang = target.language_code if target and target.language_code else "ru"

    header = "✉️ <b>Сообщение от службы поддержки / администратора:</b>\n\n" if user_lang == "ru" else "✉️ <b>Message from support / administrator:</b>\n\n"
    user_notification = f"{header}{reply_text}"

    try:
        await bot.send_message(chat_id=target_id, text=user_notification, parse_mode="HTML")
        await message.answer(f"✅ Сообщение успешно доставлено пользователю <code>{target_id}</code>!", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Failed to deliver admin reply to {target_id}: {e}")
        await message.answer(f"❌ Ошибка отправки пользователю {target_id}: {e}")


@router.callback_query(F.data == "admin_broadcast")
async def handle_admin_broadcast_prompt(callback: CallbackQuery, state: FSMContext):
    """Prompts admin for text to broadcast to all registered users."""
    if not admin_only(callback.from_user.id):
        return
    await safe_answer_callback(callback)
    await state.set_state(AdminStates.waiting_for_broadcast)

    await safe_edit_message_text(
        callback.message,
        "📢 <b>Рассылка сообщений всем пользователям:</b>\n\n"
        "Отправьте текст сообщения для массовой рассылки.\n"
        "<i>Поддерживается форматирование Telegram HTML.</i>",
        reply_markup=get_cancel_keyboard(callback_data="menu_admin"),
        parse_mode="HTML",
    )


@router.message(AdminStates.waiting_for_broadcast)
async def process_admin_broadcast(message: Message, state: FSMContext, bot: Bot):
    """Broadcasts message to all users in database."""
    if not admin_only(message.from_user.id):
        return
    await state.clear()
    broadcast_text = message.text or message.caption or ""

    if not broadcast_text:
        await message.answer("⚠️ Пустой текст рассылки. Отменено.")
        return

    status_msg = await message.answer("⏳ <i>Начинаю рассылку сообщений...</i>", parse_mode="HTML")

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        users = await user_repo.get_all_users()

    sent_count = 0
    fail_count = 0

    for u in users:
        if u.is_blocked:
            continue
        try:
            await bot.send_message(chat_id=u.user_id, text=broadcast_text, parse_mode="HTML")
            sent_count += 1
        except Exception:
            fail_count += 1

    report = (
        f"📢 <b>Рассылка завершена!</b>\n\n"
        f"• <b>Успешно доставлено:</b> {sent_count}\n"
        f"• <b>Не удалось отправить:</b> {fail_count}\n"
    )
    await status_msg.edit_text(report, reply_markup=get_admin_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "admin_toggle_maintenance")
async def handle_admin_toggle_maintenance(callback: CallbackQuery):
    """Toggles maintenance mode."""
    if not admin_only(callback.from_user.id):
        return

    async with async_session_maker() as session:
        settings_repo = SettingsRepository(session)
        current = await settings_repo.is_maintenance_mode()
        new_state = not current
        await settings_repo.set_maintenance_mode(new_state)

    status_str = "включен" if new_state else "выключен"
    await safe_answer_callback(callback, f"Режим обслуживания {status_str}!", show_alert=True)
    await handle_admin_panel(callback)

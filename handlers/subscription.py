"""
Subscription and Telegram Payments Handler for MyGemini Zero v2.
Manages subscription plans, Telegram Payments invoices, pre-checkout verification,
automatic subscription extension, recording in subscription_payments table,
and instant notifications to the administrator in Telegram PM.
Supports bilingual rendering (RU / EN) and safe editing.
"""

from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import (
    Message,
    CallbackQuery,
    PreCheckoutQuery,
    LabeledPrice,
)

from core.database import async_session_maker
from database.repositories import UserRepository, PaymentRepository
from keyboards.inline import get_subscription_keyboard, get_main_menu_keyboard
from core.config import settings, SUBSCRIPTION_PLANS
from core.ui_helpers import safe_edit_message_text, safe_answer_callback
from core.logger import get_logger

logger = get_logger("user_messages")
router = Router(name="subscription")


async def notify_admin_of_subscription_payment(
    bot: Bot,
    user_id: int,
    username: str | None,
    first_name: str | None,
    plan_title: str,
    amount_rub: int,
    end_date_str: str,
):
    """Sends instant payment notification to admin in Telegram PM."""
    uname = f"@{username}" if username else "без username"
    full_name = f"{first_name or ''}".strip() or "Пользователь"

    admin_msg = (
        "💰 <b>Новая оплата подписки!</b>\n\n"
        f"• <b>Пользователь:</b> {full_name} ({uname})\n"
        f"• <b>User ID:</b> <code>{user_id}</code>\n"
        f"• <b>Тариф:</b> {plan_title}\n"
        f"• <b>Сумма:</b> {amount_rub} ₽\n"
        f"• <b>Действует до:</b> <code>{end_date_str}</code>"
    )

    try:
        await bot.send_message(
            chat_id=settings.ADMIN_USER_ID,
            text=admin_msg,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Failed to notify admin of subscription payment: {e}")


@router.callback_query(F.data == "menu_subscription")
async def handle_subscription_menu(callback: CallbackQuery):
    """Displays user subscription status and available subscription plans."""
    await safe_answer_callback(callback)
    user_id = callback.from_user.id

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        is_active = user_repo.is_subscription_active(user)
        lang_code = user.language_code if user and user.language_code else "ru"

    is_admin = (user_id == settings.ADMIN_USER_ID)
    if is_admin:
        status = "👑 Администратор (Бессрочно)" if lang_code == "ru" else "👑 Administrator (Lifetime)"
        end_date = "Бессрочно" if lang_code == "ru" else "Lifetime"
    elif is_active:
        status = "🟢 Активна" if lang_code == "ru" else "🟢 Active"
        end_date = user.subscription_end_date[:10] if (user and user.subscription_end_date) else "—"
    elif user and user.subscription_end_date:
        status = "🔴 Истекла" if lang_code == "ru" else "🔴 Expired"
        end_date = f"{user.subscription_end_date[:10]} (истекла)" if lang_code == "ru" else f"{user.subscription_end_date[:10]} (expired)"
    else:
        status = "⚪️ Не оформлена" if lang_code == "ru" else "⚪️ Not subscribed"
        end_date = "—"

    if lang_code == "ru":
        text = (
            "💎 <b>Управление подпиской MyGemini Zero</b>\n\n"
            f"• <b>Статус:</b> {status}\n"
            f"• <b>Действует до:</b> {end_date}\n\n"
            "Подписка открывает полный доступ ко всем возможностям бота: потоковая генерация, "
            "векторная память RAG, анализ документов и изображений, выбор любых моделей Gemini.\n\n"
            "Выберите тариф для оформления или продления:"
        )
    else:
        text = (
            "💎 <b>MyGemini Zero Subscription Management</b>\n\n"
            f"• <b>Status:</b> {status}\n"
            f"• <b>Valid until:</b> {end_date}\n\n"
            "Subscription provides full access to all bot features: streaming responses, "
            "RAG vector memory, document & image analysis, and all Gemini models.\n\n"
            "Choose a plan to activate or renew:"
        )

    await safe_edit_message_text(
        callback.message,
        text,
        reply_markup=get_subscription_keyboard(SUBSCRIPTION_PLANS, lang_code=lang_code),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("buy_sub:"))
async def handle_buy_subscription(callback: CallbackQuery, bot: Bot):
    """Generates and sends a Telegram Payments invoice."""
    user_id = callback.from_user.id
    plan_id = callback.data.split("buy_sub:")[1]

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

    plan = next((p for p in SUBSCRIPTION_PLANS if p["id"] == plan_id), None)
    if not plan:
        err_text = "Тарифный план не найден." if lang_code == "ru" else "Plan not found."
        await safe_answer_callback(callback, err_text, show_alert=True)
        return

    if not settings.PAYMENT_PROVIDER_TOKEN:
        no_gw = (
            "⚠️ Платёжный шлюз временно не настроен администратором. "
            "Пожалуйста, свяжитесь с поддержкой или попробуйте позже."
            if lang_code == "ru"
            else "⚠️ Payment provider is temporarily not configured. Please contact support."
        )
        await callback.message.answer(no_gw)
        await safe_answer_callback(callback)
        return

    price = LabeledPrice(label=plan["title"], amount=plan["price_amount"])

    try:
        await bot.send_invoice(
            chat_id=user_id,
            title=plan["title"],
            description=plan["description"],
            payload=f"sub_payment:{user_id}:{plan_id}",
            provider_token=settings.PAYMENT_PROVIDER_TOKEN,
            currency=plan["price_currency"],
            prices=[price],
            start_parameter="gemini_subscription",
        )
        await safe_answer_callback(callback, "Счёт выставлен!" if lang_code == "ru" else "Invoice sent!")
    except Exception as e:
        logger.error(f"Error sending invoice: {e}")
        await callback.message.answer(f"❌ Ошибка формирования счёта: {e}")
        await safe_answer_callback(callback)


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    """Confirms receipt of order before charge."""
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(message: Message, bot: Bot):
    """
    Processes successful payment, records transaction in subscription_payments,
    extends user's subscription, and notifies admin in Telegram PM.
    """
    user_id = message.from_user.id
    payment_info = message.successful_payment
    payload = payment_info.invoice_payload

    parts = payload.split(":")
    plan_id = parts[2] if len(parts) >= 3 else "1_month_sub"

    plan = next((p for p in SUBSCRIPTION_PLANS if p["id"] == plan_id), SUBSCRIPTION_PLANS[0])
    duration_days = plan.get("duration_days", 30)

    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        pay_repo = PaymentRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"

        current_end_date = None
        if user and user.subscription_end_date:
            try:
                current_end_date = datetime.strptime(user.subscription_end_date[:10], "%Y-%m-%d")
            except Exception:
                current_end_date = None

        if current_end_date and current_end_date > now:
            new_end = current_end_date + timedelta(days=duration_days)
        else:
            new_end = now + timedelta(days=duration_days)

        new_end_str = new_end.strftime("%Y-%m-%d")

        # 1. Update user subscription
        await user_repo.update_subscription(user_id, status="active", end_date=new_end_str)

        # 2. Record payment in database
        await pay_repo.record_payment(
            user_id=user_id,
            plan_id=plan_id,
            amount=payment_info.total_amount,
            currency=payment_info.currency,
            payment_date=now_str,
            subscription_end_date=new_end_str,
            telegram_charge_id=payment_info.telegram_payment_charge_id,
            provider_charge_id=payment_info.provider_payment_charge_id,
        )

    logger.info(
        f"Subscription activated for user {user_id} until {new_end_str}. Charge: {payment_info.telegram_payment_charge_id}",
        extra={"user_id": user_id},
    )

    # 3. Notify Admin in PM
    amount_rub = payment_info.total_amount // 100
    await notify_admin_of_subscription_payment(
        bot=bot,
        user_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        plan_title=plan["title"],
        amount_rub=amount_rub,
        end_date_str=new_end_str,
    )

    # 4. Confirmation message to user
    if lang_code == "ru":
        msg = (
            "🎉 <b>Оплата успешно получена! Подписка активирована.</b>\n\n"
            f"• <b>Тариф:</b> {plan['title']}\n"
            f"• <b>Сумма:</b> {amount_rub} {payment_info.currency}\n"
            f"• <b>Подписка действует до:</b> <code>{new_end_str}</code>\n\n"
            "Спасибо за доверие и поддержку проекта! Приятного использования."
        )
    else:
        msg = (
            "🎉 <b>Payment received! Subscription activated.</b>\n\n"
            f"• <b>Plan:</b> {plan['title']}\n"
            f"• <b>Amount:</b> {amount_rub} {payment_info.currency}\n"
            f"• <b>Valid until:</b> <code>{new_end_str}</code>\n\n"
            "Thank you for supporting the project! Enjoy using the bot."
        )

    await message.answer(
        msg,
        reply_markup=get_main_menu_keyboard(is_unlocked=True, is_admin=(user_id == settings.ADMIN_USER_ID), lang_code=lang_code),
        parse_mode="HTML",
    )

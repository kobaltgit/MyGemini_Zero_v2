"""
Subscription and Telegram Payments Handler for MyGemini Zero v2.
Manages subscription plans, Telegram Payments invoices, pre-checkout verification,
and automatic subscription extension with recording in subscription_payments table.
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
from core.logger import get_logger

logger = get_logger("user_messages")
router = Router(name="subscription")


@router.callback_query(F.data == "menu_subscription")
async def handle_subscription_menu(callback: CallbackQuery):
    """Displays user subscription status and available subscription plans."""
    user_id = callback.from_user.id

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)

    is_admin = user_id == settings.ADMIN_USER_ID
    status = "👑 Администратор (Бессрочно)" if is_admin else (user.subscription_status if user else "none")
    end_date = "Бессрочно" if is_admin else (user.subscription_end_date if user and user.subscription_end_date else "—")

    text = (
        "💎 <b>Управление подпиской MyGemini Zero</b>\n\n"
        f"• <b>Статус:</b> {status}\n"
        f"• <b>Действует до:</b> {end_date}\n\n"
        "Подписка открывает полный доступ ко всем возможностям бота: потоковая генерация, "
        "векторная память RAG, анализ документов и изображений, выбор любых моделей Gemini.\n\n"
        "Выберите тариф для оформления или продления:"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_subscription_keyboard(SUBSCRIPTION_PLANS),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("buy_sub:"))
async def handle_buy_subscription(callback: CallbackQuery, bot: Bot):
    """Generates and sends a Telegram Payments invoice."""
    user_id = callback.from_user.id
    plan_id = callback.data.split("buy_sub:")[1]

    plan = next((p for p in SUBSCRIPTION_PLANS if p["id"] == plan_id), None)
    if not plan:
        await callback.answer("Тарифный план не найден.", show_alert=True)
        return

    if not settings.PAYMENT_PROVIDER_TOKEN:
        await callback.message.answer(
            "⚠️ Платёжный шлюз временно не настроен администратором. "
            "Пожалуйста, свяжитесь с поддержкой или попробуйте позже."
        )
        await callback.answer()
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
        await callback.answer("Счёт выставлен!")
    except Exception as e:
        logger.error(f"Error sending invoice: {e}")
        await callback.message.answer(f"❌ Ошибка формирования счёта: {e}")
        await callback.answer()


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    """Confirms receipt of order before charge."""
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    """
    Processes successful payment, records transaction in subscription_payments,
    and extends user's subscription.
    """
    user_id = message.from_user.id
    payment_info = message.successful_payment
    payload = payment_info.invoice_payload

    # Extract plan_id from payload: "sub_payment:{user_id}:{plan_id}"
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

        # Calculate new end date
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

    await message.answer(
        "🎉 <b>Оплата успешно получена! Подписка активирована.</b>\n\n"
        f"• <b>Тариф:</b> {plan['title']}\n"
        f"• <b>Сумма:</b> {payment_info.total_amount // 100} {payment_info.currency}\n"
        f"• <b>Подписка действует до:</b> <code>{new_end_str}</code>\n\n"
        "Спасибо за доверие и поддержку проекта! Приятного использования.",
        reply_markup=get_main_menu_keyboard(is_unlocked=True, is_admin=(user_id == settings.ADMIN_USER_ID)),
        parse_mode="HTML",
    )

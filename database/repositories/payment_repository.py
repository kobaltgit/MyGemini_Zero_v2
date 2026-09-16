"""
Subscription Payment Repository for MyGemini Zero v2.
Handles recording and querying subscription payments for users and admin analytics.
"""

from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from database.models.subscription_payment import SubscriptionPayment
from core.logger import get_logger

logger = get_logger("database")


class PaymentRepository:
    """Async repository for subscription payments."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def record_payment(
        self,
        user_id: int,
        plan_id: str,
        amount: int,
        currency: str,
        payment_date: str,
        subscription_end_date: str,
        telegram_charge_id: Optional[str] = None,
        provider_charge_id: Optional[str] = None,
    ) -> SubscriptionPayment:
        """Records a new successful subscription payment."""
        payment = SubscriptionPayment(
            user_id=user_id,
            plan_id=plan_id,
            amount=amount,
            currency=currency,
            payment_date=payment_date,
            subscription_end_date=subscription_end_date,
            telegram_charge_id=telegram_charge_id,
            provider_charge_id=provider_charge_id,
        )
        self.session.add(payment)
        await self.session.commit()
        logger.info(
            f"Recorded payment {amount} {currency} for user {user_id}, plan {plan_id}",
            extra={"user_id": user_id},
        )
        return payment

    async def get_user_payments(self, user_id: int) -> List[SubscriptionPayment]:
        """Fetches payment history for a specific user."""
        stmt = (
            select(SubscriptionPayment)
            .where(SubscriptionPayment.user_id == user_id)
            .order_by(SubscriptionPayment.payment_date.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_payments(self) -> List[SubscriptionPayment]:
        """Returns all payments in reverse chronological order."""
        stmt = select(SubscriptionPayment).order_by(SubscriptionPayment.payment_date.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_payment_stats(self) -> Dict[str, Any]:
        """Aggregates total payments, revenue, and unique paying users."""
        count_stmt = select(func.count(SubscriptionPayment.payment_id))
        total_stmt = select(func.sum(SubscriptionPayment.amount))
        users_stmt = select(func.count(func.distinct(SubscriptionPayment.user_id)))

        count_res = await self.session.execute(count_stmt)
        total_res = await self.session.execute(total_stmt)
        users_res = await self.session.execute(users_stmt)

        total_payments = count_res.scalar() or 0
        total_revenue = total_res.scalar() or 0
        unique_users = users_res.scalar() or 0

        return {
            "total_payments": total_payments,
            "total_revenue": total_revenue,
            "unique_paying_users": unique_users,
        }

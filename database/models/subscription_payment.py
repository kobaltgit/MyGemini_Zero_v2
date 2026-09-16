"""
SubscriptionPayment SQLAlchemy 2.0 Model.
Records all Telegram payment transactions and subscriptions.
"""

from typing import Optional
from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from core.database import Base


class SubscriptionPayment(Base):
    """Payment record for subscription renewals and purchases."""

    __tablename__ = "subscription_payments"

    payment_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # in kopecks / cents
    currency: Mapped[str] = mapped_column(String, nullable=False)
    payment_date: Mapped[str] = mapped_column(String, nullable=False)
    subscription_end_date: Mapped[str] = mapped_column(String, nullable=False)
    telegram_charge_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    provider_charge_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)

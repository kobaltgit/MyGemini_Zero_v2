"""
User SQLAlchemy 2.0 Model.
Maintains 100% binary schema compatibility with v1 users table.
BLOB fields store cryptographic hashes, salts, and encrypted tokens.
"""

from typing import Optional
from sqlalchemy import String, Integer, LargeBinary, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from core.database import Base


class User(Base):
    """Telegram User entity with Zero-Knowledge encryption credentials."""

    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    language_code: Mapped[str] = mapped_column(String, default="ru", nullable=False)
    first_interaction_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_blocked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active_dialog_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("dialogs.dialog_id", ondelete="SET NULL"), nullable=True
    )

    bot_style: Mapped[str] = mapped_column(String, default="default", nullable=False)
    gemini_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    active_persona: Mapped[str] = mapped_column(String, default="default", nullable=False)

    # Zero-Knowledge Security Fields (BLOB)
    master_password_hash: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    encryption_salt: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    api_key: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    last_session_ts: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    panic_password_hash: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)

    # Subscription Management
    subscription_status: Mapped[str] = mapped_column(String, default="none", nullable=False)
    subscription_end_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)

"""
UserProfile SQLAlchemy 2.0 Model.
Stores encrypted user profile / questionnaire answers.
"""

from typing import Optional
from sqlalchemy import String, Integer, LargeBinary, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from core.database import Base


class UserProfile(Base):
    """User profile data encrypted with the user's master key."""

    __tablename__ = "user_profiles"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    profile_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)  # Fernet encrypted
    last_updated: Mapped[Optional[str]] = mapped_column(String, nullable=True)

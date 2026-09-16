"""
Conversation SQLAlchemy 2.0 Model.
Stores encrypted message history per dialog.
"""

from typing import Optional
from sqlalchemy import String, Integer, LargeBinary, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from core.database import Base


class Conversation(Base):
    """Single message entry in a dialog, with encrypted text and token metrics."""

    __tablename__ = "conversations"

    conversation_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    dialog_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dialogs.dialog_id", ondelete="CASCADE"), nullable=False
    )
    timestamp: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)  # 'user' or 'bot'
    message_text: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)  # Fernet encrypted
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content_type: Mapped[str] = mapped_column(String, default="text", nullable=False)

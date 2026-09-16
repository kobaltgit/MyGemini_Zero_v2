"""
AppSettings SQLAlchemy 2.0 Model.
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from core.database import Base


class AppSettings(Base):
    """System-wide application settings and flags (e.g., maintenance mode)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)

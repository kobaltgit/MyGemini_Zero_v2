"""
Settings Repository for MyGemini Zero v2.
Manages global key-value settings in app_settings table.
"""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.models.app_settings import AppSettings
from core.logger import get_logger

logger = get_logger("database")


class SettingsRepository:
    """Async repository for system settings."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Fetches setting value by key."""
        stmt = select(AppSettings).where(AppSettings.key == key)
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        return row.value if row else default

    async def set_setting(self, key: str, value: str) -> None:
        """Sets or updates setting value."""
        stmt = select(AppSettings).where(AppSettings.key == key)
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()

        if row:
            row.value = value
        else:
            row = AppSettings(key=key, value=value)
            self.session.add(row)

        await self.session.commit()

    async def is_maintenance_mode(self) -> bool:
        """Checks if bot is in maintenance mode."""
        val = await self.get_setting("maintenance_mode", "false")
        return val.lower() in ("true", "1", "yes")

    async def set_maintenance_mode(self, enabled: bool) -> None:
        """Enables or disables bot maintenance mode."""
        await self.set_setting("maintenance_mode", "true" if enabled else "false")

"""
Dialog Repository for MyGemini Zero v2.
Handles dialog CRUD operations and active dialog management.
"""

from typing import Optional, List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete

from database.models.dialog import Dialog
from database.models.user import User
from core.logger import get_logger

logger = get_logger("database")


class DialogRepository:
    """Async repository for managing user dialogs."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, dialog_id: int) -> Optional[Dialog]:
        """Fetches dialog by primary key."""
        stmt = select(Dialog).where(Dialog.dialog_id == dialog_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_dialogs(self, user_id: int) -> List[Dialog]:
        """Fetches all dialogs belonging to a user, ordered by creation date."""
        stmt = select(Dialog).where(Dialog.user_id == user_id).order_by(Dialog.dialog_id.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_dialog(self, user_id: int, name: str, set_active: bool = True) -> Dialog:
        """Creates a new dialog and optionally sets it as the active dialog."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        dialog = Dialog(user_id=user_id, name=name, created_at=now_str)
        self.session.add(dialog)
        await self.session.flush()

        if set_active:
            user_stmt = update(User).where(User.user_id == user_id).values(active_dialog_id=dialog.dialog_id)
            await self.session.execute(user_stmt)

        await self.session.commit()
        logger.info(f"Created dialog '{name}' (ID: {dialog.dialog_id}) for user {user_id}", extra={"user_id": user_id})
        return dialog

    async def rename_dialog(self, dialog_id: int, new_name: str) -> bool:
        """Renames an existing dialog."""
        stmt = update(Dialog).where(Dialog.dialog_id == dialog_id).values(name=new_name)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def delete_dialog(self, user_id: int, dialog_id: int) -> bool:
        """
        Deletes a dialog. If this was the user's active dialog, automatically switches
        the active dialog to another existing dialog or creates a fresh 'Основной диалог'.
        """
        dialog = await self.get_by_id(dialog_id)
        if not dialog or dialog.user_id != user_id:
            return False

        # Check if this is the active dialog
        user_stmt = select(User).where(User.user_id == user_id)
        user_res = await self.session.execute(user_stmt)
        user = user_res.scalar_one_or_none()

        was_active = user and user.active_dialog_id == dialog_id

        # Delete the dialog
        stmt = delete(Dialog).where(Dialog.dialog_id == dialog_id)
        await self.session.execute(stmt)
        await self.session.flush()

        if was_active and user:
            # Find remaining dialogs
            remaining = await self.get_user_dialogs(user_id)
            if remaining:
                user.active_dialog_id = remaining[0].dialog_id
            else:
                # Create default dialog
                new_default = Dialog(
                    user_id=user_id,
                    name="Основной диалог",
                    created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )
                self.session.add(new_default)
                await self.session.flush()
                user.active_dialog_id = new_default.dialog_id

        await self.session.commit()
        return True

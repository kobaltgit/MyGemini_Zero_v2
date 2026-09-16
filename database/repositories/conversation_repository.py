"""
Conversation Repository for MyGemini Zero v2.
Manages encrypted message history, token tracking, message retrieval, and data clearing.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from cryptography.fernet import Fernet

from database.models.conversation import Conversation
from database.models.dialog import Dialog
from database.models.user_profile import UserProfile
from database.models.user import User
from core.crypto import encrypt_data, decrypt_data
from core.logger import get_logger

logger = get_logger("database")


class ConversationRepository:
    """Async repository for encrypted conversation messages and history."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_message(
        self,
        user_id: int,
        dialog_id: int,
        role: str,
        message_text: str,
        fernet_instance: Fernet,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        content_type: str = "text",
    ) -> Conversation:
        """Encrypts message text with active Fernet cipher and stores in DB."""
        encrypted_text = encrypt_data(message_text, fernet_instance)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conv = Conversation(
            user_id=user_id,
            dialog_id=dialog_id,
            timestamp=now_str,
            role=role,
            message_text=encrypted_text.encode("utf-8"),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            content_type=content_type,
        )
        self.session.add(conv)
        await self.session.commit()
        return conv

    async def get_dialog_messages(
        self,
        dialog_id: int,
        fernet_instance: Fernet,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves message history for a dialog and decrypts the text in-memory.
        If decryption fails (e.g. invalid key), provides a safe placeholder.
        """
        stmt = (
            select(Conversation)
            .where(Conversation.dialog_id == dialog_id)
            .order_by(Conversation.conversation_id.asc())
        )
        if limit:
            stmt = stmt.limit(limit)

        result = await self.session.execute(stmt)
        conversations = result.scalars().all()

        decrypted_messages = []
        for c in conversations:
            text = ""
            if c.message_text:
                raw_blob = c.message_text
                enc_str = raw_blob.decode("utf-8") if isinstance(raw_blob, (bytes, bytearray)) else str(raw_blob)
                decrypted = decrypt_data(enc_str, fernet_instance)
                text = decrypted if decrypted is not None else "[Ошибка дешифрования / Decryption failed]"

            decrypted_messages.append({
                "conversation_id": c.conversation_id,
                "user_id": c.user_id,
                "dialog_id": c.dialog_id,
                "timestamp": c.timestamp,
                "role": c.role,
                "text": text,
                "content_type": c.content_type,
                "prompt_tokens": c.prompt_tokens,
                "completion_tokens": c.completion_tokens,
                "total_tokens": c.total_tokens,
            })

        return decrypted_messages

    async def get_messages_older_than(
        self, user_id: int, cutoff_datetime: str, fernet_instance: Fernet
    ) -> List[Dict[str, Any]]:
        """Fetches messages older than cutoff datetime for summarization/archival."""
        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user_id, Conversation.timestamp < cutoff_datetime)
            .order_by(Conversation.timestamp.asc())
        )
        result = await self.session.execute(stmt)
        conversations = result.scalars().all()

        messages = []
        for c in conversations:
            text = ""
            if c.message_text:
                raw_blob = c.message_text
                enc_str = raw_blob.decode("utf-8") if isinstance(raw_blob, (bytes, bytearray)) else str(raw_blob)
                decrypted = decrypt_data(enc_str, fernet_instance)
                text = decrypted or ""
            messages.append({
                "role": c.role,
                "text": text,
                "timestamp": c.timestamp,
                "dialog_id": c.dialog_id,
            })
        return messages

    async def delete_messages_older_than(self, user_id: int, cutoff_datetime: str) -> int:
        """Deletes messages older than cutoff timestamp."""
        stmt = (
            delete(Conversation)
            .where(Conversation.user_id == user_id, Conversation.timestamp < cutoff_datetime)
        )
        res = await self.session.execute(stmt)
        await self.session.commit()
        return res.rowcount

    async def clear_user_data(self, user_id: int) -> None:
        """
        Emergency or voluntary data wipe. Deletes:
        - All conversations
        - All dialogs
        - User profiles
        - Clears master password hash, salt, panic hash, and API key
        """
        # Delete conversations
        await self.session.execute(delete(Conversation).where(Conversation.user_id == user_id))

        # Delete dialogs
        await self.session.execute(delete(Dialog).where(Dialog.user_id == user_id))

        # Delete profiles
        await self.session.execute(delete(UserProfile).where(UserProfile.user_id == user_id))

        # Reset user security credentials
        user_stmt = select(User).where(User.user_id == user_id)
        user_res = await self.session.execute(user_stmt)
        user = user_res.scalar_one_or_none()
        if user:
            user.master_password_hash = None
            user.encryption_salt = None
            user.panic_password_hash = None
            user.api_key = None
            user.active_dialog_id = None

        await self.session.commit()
        logger.warning(f"Complete data wipe executed for user {user_id}", extra={"user_id": user_id})

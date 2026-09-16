"""
UserProfile Repository for MyGemini Zero v2.
Manages encrypted user profiles (questionnaires, personal background).
"""

import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from cryptography.fernet import Fernet

from database.models.user_profile import UserProfile
from core.crypto import encrypt_data, decrypt_data
from core.logger import get_logger

logger = get_logger("database")


class ProfileRepository:
    """Async repository for encrypted user profiles."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_profile(self, user_id: int, fernet_instance: Fernet) -> Optional[Dict[str, Any]]:
        """Retrieves, decrypts, and deserializes user profile."""
        stmt = select(UserProfile).where(UserProfile.user_id == user_id)
        result = await self.session.execute(stmt)
        profile_row = result.scalar_one_or_none()

        if not profile_row or not profile_row.profile_data:
            return None

        raw_blob = profile_row.profile_data
        enc_str = raw_blob.decode("utf-8") if isinstance(raw_blob, (bytes, bytearray)) else str(raw_blob)
        decrypted_str = decrypt_data(enc_str, fernet_instance)

        if not decrypted_str:
            return None

        try:
            return json.loads(decrypted_str)
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding user {user_id} profile JSON: {e}")
            return None

    async def save_profile(self, user_id: int, profile_data: Dict[str, Any], fernet_instance: Fernet) -> None:
        """Serializes to JSON, encrypts with active session key, and saves to DB."""
        profile_json = json.dumps(profile_data, ensure_ascii=False)
        encrypted_str = encrypt_data(profile_json, fernet_instance)
        now_str = datetime.now(timezone.utc).isoformat()

        stmt = select(UserProfile).where(UserProfile.user_id == user_id)
        result = await self.session.execute(stmt)
        profile_row = result.scalar_one_or_none()

        if profile_row:
            profile_row.profile_data = encrypted_str.encode("utf-8")
            profile_row.last_updated = now_str
        else:
            profile_row = UserProfile(
                user_id=user_id,
                profile_data=encrypted_str.encode("utf-8"),
                last_updated=now_str,
            )
            self.session.add(profile_row)

        await self.session.commit()
        logger.info(f"Encrypted profile saved for user {user_id}", extra={"user_id": user_id})

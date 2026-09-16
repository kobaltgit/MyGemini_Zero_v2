"""
User Repository for MyGemini Zero v2.
Handles async CRUD operations for users, passwords, sessions, and settings.
"""

from typing import Optional, List, Tuple
from datetime import datetime, date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from cryptography.fernet import Fernet

from database.models.user import User
from database.models.dialog import Dialog
from core.crypto import (
    hash_password,
    verify_password,
    generate_salt,
    encrypt_data,
    decrypt_data,
)
from core.logger import get_logger
from core.config import settings

logger = get_logger("database")


class UserRepository:
    """Async repository for managing users."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: int) -> Optional[User]:
        """Retrieves user by primary key Telegram ID."""
        stmt = select(User).where(User.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_or_update_user(
        self,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
        lang_code: Optional[str] = None,
    ) -> Tuple[User, bool]:
        """
        Creates a new user or updates profile names for an existing user.
        Ensures an active default dialog is always present.
        Returns tuple of (User, is_new_user: bool).
        """
        user = await self.get_by_id(user_id)
        is_new_user = False

        supported_lang = "ru"
        if lang_code in ["ru", "en"]:
            supported_lang = lang_code

        if not user:
            is_new_user = True
            logger.info(f"Adding new user {user_id} (@{username}) with lang '{supported_lang}'.", extra={"user_id": user_id})
            today_str = date.today().strftime("%Y-%m-%d")
            user = User(
                user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                language_code=supported_lang,
                first_interaction_date=today_str,
                subscription_status="none",
            )
            self.session.add(user)
            await self.session.flush()

            # Create default dialog
            default_dialog = Dialog(
                user_id=user_id,
                name="Основной диалог",
                created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
            self.session.add(default_dialog)
            await self.session.flush()

            user.active_dialog_id = default_dialog.dialog_id
        else:
            user.username = username
            user.first_name = first_name
            user.last_name = last_name

            # Check if active dialog is present
            if not user.active_dialog_id:
                default_dialog = Dialog(
                    user_id=user_id,
                    name="Основной диалог",
                    created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )
                self.session.add(default_dialog)
                await self.session.flush()
                user.active_dialog_id = default_dialog.dialog_id

        await self.session.commit()
        return user, is_new_user

    async def is_master_password_set(self, user_id: int) -> bool:
        """Checks whether the user has set a master password."""
        user = await self.get_by_id(user_id)
        return user is not None and user.master_password_hash is not None

    async def set_master_password(self, user_id: int, password: str) -> None:
        """Hashes password with bcrypt, generates salt, and stores in user row."""
        password_hash = hash_password(password)
        salt = generate_salt()
        stmt = (
            update(User)
            .where(User.user_id == user_id)
            .values(master_password_hash=password_hash, encryption_salt=salt)
        )
        await self.session.execute(stmt)
        await self.session.commit()
        logger.info(f"Master password and salt stored for user {user_id}", extra={"user_id": user_id})

    async def verify_master_password(self, user_id: int, provided_password: str) -> bool:
        """Verifies plaintext master password against stored bcrypt hash."""
        user = await self.get_by_id(user_id)
        if not user or not user.master_password_hash:
            return False
        return verify_password(user.master_password_hash, provided_password)

    async def get_salt(self, user_id: int) -> Optional[bytes]:
        """Fetches the user's cryptographic salt."""
        user = await self.get_by_id(user_id)
        return user.encryption_salt if user else None

    async def set_panic_password(self, user_id: int, panic_password: str) -> None:
        """Hashes and sets panic password for rapid emergency wiping."""
        panic_hash = hash_password(panic_password)
        stmt = (
            update(User)
            .where(User.user_id == user_id)
            .values(panic_password_hash=panic_hash)
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def verify_panic_password(self, user_id: int, provided_password: str) -> bool:
        """Checks if provided password matches the panic password hash."""
        user = await self.get_by_id(user_id)
        if not user or not user.panic_password_hash:
            return False
        return verify_password(user.panic_password_hash, provided_password)

    async def is_panic_password_set(self, user_id: int) -> bool:
        """Checks if user has configured a panic password."""
        user = await self.get_by_id(user_id)
        return user is not None and user.panic_password_hash is not None

    async def set_api_key(self, user_id: int, api_key: str, fernet_instance: Fernet) -> None:
        """Encrypts plain API key using active session Fernet cipher and saves to DB."""
        encrypted_key_str = encrypt_data(api_key, fernet_instance)
        # Store as bytes for BLOB compatibility
        stmt = (
            update(User)
            .where(User.user_id == user_id)
            .values(api_key=encrypted_key_str.encode("utf-8"))
        )
        await self.session.execute(stmt)
        await self.session.commit()
        logger.info(f"Encrypted API key saved for user {user_id}", extra={"user_id": user_id})

    async def get_api_key(self, user_id: int, fernet_instance: Fernet) -> Optional[str]:
        """Retrieves and decrypts user API key."""
        user = await self.get_by_id(user_id)
        if not user or not user.api_key:
            return None
        # Support both bytes and str representation
        raw_key = user.api_key
        encrypted_str = raw_key.decode("utf-8") if isinstance(raw_key, (bytes, bytearray)) else str(raw_key)
        return decrypt_data(encrypted_str, fernet_instance)

    async def is_api_key_set(self, user_id: int) -> bool:
        """Checks if an API key is present in DB without decrypting it."""
        user = await self.get_by_id(user_id)
        return user is not None and user.api_key is not None

    async def update_session_timestamp(self, user_id: int) -> None:
        """Updates last_session_ts to current timestamp."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        stmt = update(User).where(User.user_id == user_id).values(last_session_ts=now_str)
        await self.session.execute(stmt)
        await self.session.commit()

    async def update_settings(
        self,
        user_id: int,
        style: Optional[str] = None,
        model: Optional[str] = None,
        persona: Optional[str] = None,
        language_code: Optional[str] = None,
        active_dialog_id: Optional[int] = None,
    ) -> None:
        """Updates user preferences (model, persona, style, language, active dialog)."""
        values = {}
        if style is not None:
            values["bot_style"] = style
        if model is not None:
            values["gemini_model"] = model
        if persona is not None:
            values["active_persona"] = persona
        if language_code is not None:
            values["language_code"] = language_code
        if active_dialog_id is not None:
            values["active_dialog_id"] = active_dialog_id

        if values:
            stmt = update(User).where(User.user_id == user_id).values(**values)
            await self.session.execute(stmt)
            await self.session.commit()

    async def update_subscription(self, user_id: int, status: str, end_date: Optional[str]) -> None:
        """Updates user subscription status and expiry date."""
        stmt = (
            update(User)
            .where(User.user_id == user_id)
            .values(subscription_status=status, subscription_end_date=end_date)
        )
        await self.session.execute(stmt)
        await self.session.commit()

    def is_subscription_active(self, user: Optional[User]) -> bool:
        """
        Determines whether a user has an active, non-expired subscription.
        Admin is always active (lifetime).
        Regular users are active only if subscription_status == 'active'
        and subscription_end_date is set and >= today's date.
        """
        if not user:
            return False
        if user.user_id == settings.ADMIN_USER_ID:
            return True
        if user.subscription_status != "active" or not user.subscription_end_date:
            return False
        try:
            end_dt = datetime.strptime(user.subscription_end_date[:10], "%Y-%m-%d")
            return end_dt.date() >= datetime.now().date()
        except Exception:
            return False

    async def get_all_subscribers(self) -> List[User]:
        """Returns all users with active or past subscriptions for admin management."""
        stmt = select(User).where(User.subscription_status != "none")
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_users(self) -> List[User]:
        """Returns all users for export and administration."""
        stmt = select(User).order_by(User.user_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def set_blocked(self, user_id: int, is_blocked: bool) -> None:
        """Blocks or unblocks a user."""
        stmt = update(User).where(User.user_id == user_id).values(is_blocked=1 if is_blocked else 0)
        await self.session.execute(stmt)
        await self.session.commit()

    async def reset_api_key(self, user_id: int) -> None:
        """Resets user's encrypted API key."""
        stmt = update(User).where(User.user_id == user_id).values(api_key=None)
        await self.session.execute(stmt)
        await self.session.commit()


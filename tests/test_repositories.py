"""
Comprehensive async repository unit tests:
- UserRepository (ZK master/panic passwords, encrypted API keys, subscriptions, settings)
- DialogRepository (CRUD, active dialog switching)
- ConversationRepository (Encrypted message storage, retrieval, and clearing)
- PaymentRepository (Subscription payments tracking)
- SettingsRepository (Global system settings & maintenance mode)

Uses an isolated in-memory SQLite database (sqlite+aiosqlite:///:memory:).
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from core.database import Base
from core.crypto import generate_salt, get_fernet_instance
from database.repositories import (
    UserRepository,
    DialogRepository,
    ConversationRepository,
    PaymentRepository,
    SettingsRepository,
)


@pytest_asyncio.fixture
async def async_session():
    """Sets up an in-memory SQLite database and yields an AsyncSession."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
class TestUserRepository:
    """Tests for database/repositories/user_repository.py."""

    async def test_add_or_update_user(self, async_session: AsyncSession):
        user_repo = UserRepository(async_session)
        uid = 1001

        # 1. Create new user
        user, is_new = await user_repo.add_or_update_user(
            user_id=uid,
            username="alice",
            first_name="Alice",
            last_name="Smith",
            lang_code="ru",
        )
        assert is_new is True
        assert user.user_id == uid
        assert user.username == "alice"
        assert user.active_dialog_id is not None

        # 2. Update existing user
        user_upd, is_new2 = await user_repo.add_or_update_user(
            user_id=uid,
            username="alice_new",
            first_name="Alice Updated",
            last_name="Smith",
        )
        assert is_new2 is False
        assert user_upd.username == "alice_new"
        assert user_upd.first_name == "Alice Updated"

    async def test_master_and_panic_passwords(self, async_session: AsyncSession):
        user_repo = UserRepository(async_session)
        uid = 1002
        await user_repo.add_or_update_user(uid, "bob", "Bob", None)

        assert await user_repo.is_master_password_set(uid) is False

        # Set master password
        pwd = "BobSecretPassword123!"
        await user_repo.set_master_password(uid, pwd)
        assert await user_repo.is_master_password_set(uid) is True
        assert await user_repo.verify_master_password(uid, pwd) is True
        assert await user_repo.verify_master_password(uid, "WrongPwd") is False

        # Panic password
        panic_pwd = "PanicEmergency999!"
        await user_repo.set_panic_password(uid, panic_pwd)
        assert await user_repo.verify_panic_password(uid, panic_pwd) is True
        assert await user_repo.verify_panic_password(uid, "NotPanic") is False

    async def test_api_key_encryption_flow(self, async_session: AsyncSession):
        user_repo = UserRepository(async_session)
        uid = 1003
        await user_repo.add_or_update_user(uid, "carol", "Carol", None)

        # Derive Fernet key
        salt = generate_salt()
        fernet = get_fernet_instance("carol_password", salt)

        # Set and get API key
        raw_key = "AIzaSy_Carol_Google_Key_XYZ"
        await user_repo.set_api_key(uid, raw_key, fernet)
        fetched_key = await user_repo.get_api_key(uid, fernet)
        assert fetched_key == raw_key

        # Reset API key
        await user_repo.reset_api_key(uid)
        assert await user_repo.get_api_key(uid, fernet) is None

    async def test_subscription_and_blocking(self, async_session: AsyncSession):
        user_repo = UserRepository(async_session)
        uid = 1004
        await user_repo.add_or_update_user(uid, "david", "David", None)

        # Blocking
        user = await user_repo.get_by_id(uid)
        assert user.is_blocked == 0
        await user_repo.set_blocked(uid, True)
        user_blocked = await user_repo.get_by_id(uid)
        assert user_blocked.is_blocked == 1
        await user_repo.set_blocked(uid, False)
        user_unblocked = await user_repo.get_by_id(uid)
        assert user_unblocked.is_blocked == 0

        # Subscription active
        future_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        await user_repo.update_subscription(uid, status="active", end_date=future_date)
        user = await user_repo.get_by_id(uid)
        assert user_repo.is_subscription_active(user) is True

        # Message format (rich vs markdown)
        assert user.message_format == "rich"
        await user_repo.update_message_format(uid, "markdown")
        user_md = await user_repo.get_by_id(uid)
        assert user_md.message_format == "markdown"
        await user_repo.update_message_format(uid, "rich")
        user_rich = await user_repo.get_by_id(uid)
        assert user_rich.message_format == "rich"


@pytest.mark.asyncio
class TestDialogRepository:
    """Tests for database/repositories/dialog_repository.py."""

    async def test_dialog_lifecycle(self, async_session: AsyncSession):
        user_repo = UserRepository(async_session)
        dialog_repo = DialogRepository(async_session)
        uid = 2001
        await user_repo.add_or_update_user(uid, "eva", "Eva", None)

        # Default dialog created upon registration
        dialogs = await dialog_repo.get_user_dialogs(uid)
        assert len(dialogs) >= 1
        d1 = dialogs[0]

        # Create second dialog
        d2 = await dialog_repo.create_dialog(uid, "Рабочий проект", set_active=True)
        assert d2.dialog_id is not None
        assert d2.name == "Рабочий проект"

        # Check active dialog on user
        user = await user_repo.get_by_id(uid)
        assert user.active_dialog_id == d2.dialog_id

        # Rename
        await dialog_repo.rename_dialog(d2.dialog_id, "Архивный проект")
        updated_d2 = await dialog_repo.get_by_id(d2.dialog_id)
        assert updated_d2.name == "Архивный проект"

        # Delete active dialog -> must switch back to d1
        await dialog_repo.delete_dialog(uid, d2.dialog_id)
        dialogs_after = await dialog_repo.get_user_dialogs(uid)
        assert len(dialogs_after) == 1
        assert dialogs_after[0].dialog_id == d1.dialog_id

        user_after = await user_repo.get_by_id(uid)
        assert user_after.active_dialog_id == d1.dialog_id


@pytest.mark.asyncio
class TestConversationRepository:
    """Tests for database/repositories/conversation_repository.py."""

    async def test_add_and_retrieve_messages(self, async_session: AsyncSession):
        user_repo = UserRepository(async_session)
        dialog_repo = DialogRepository(async_session)
        conv_repo = ConversationRepository(async_session)

        uid = 3001
        await user_repo.add_or_update_user(uid, "frank", "Frank", None)
        dialog = await dialog_repo.create_dialog(uid, "Math Chat")

        salt = generate_salt()
        fernet = get_fernet_instance("frank_pass", salt)

        # Add user message
        msg1 = await conv_repo.add_message(
            user_id=uid,
            dialog_id=dialog.dialog_id,
            role="user",
            message_text="Вычисли интеграл x^2 dx",
            fernet_instance=fernet,
        )
        assert msg1.conversation_id is not None

        # Add assistant response
        msg2 = await conv_repo.add_message(
            user_id=uid,
            dialog_id=dialog.dialog_id,
            role="model",
            message_text="Ответ: x^3 / 3 + C",
            fernet_instance=fernet,
        )

        # Retrieve and verify decryption
        history = await conv_repo.get_dialog_messages(dialog.dialog_id, fernet_instance=fernet)
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["text"] == "Вычисли интеграл x^2 dx"
        assert history[1]["role"] == "model"
        assert history[1]["text"] == "Ответ: x^3 / 3 + C"

        # Emergency / Voluntary wipe: clear_user_data
        await conv_repo.clear_user_data(uid)
        history_cleared = await conv_repo.get_dialog_messages(dialog.dialog_id, fernet_instance=fernet)
        assert len(history_cleared) == 0

        # User security fields must be wiped
        wiped_user = await user_repo.get_by_id(uid)
        assert wiped_user.master_password_hash is None
        assert wiped_user.api_key is None

    async def test_get_dialog_messages_recent_limit(self, async_session: AsyncSession):
        """Verifies that get_dialog_messages with limit returns the MOST RECENT messages in chronological order."""
        user_repo = UserRepository(async_session)
        dialog_repo = DialogRepository(async_session)
        conv_repo = ConversationRepository(async_session)

        uid = 555666
        await user_repo.add_or_update_user(user_id=uid, username="limittest", first_name="Limit", last_name="User")
        await user_repo.set_master_password(uid, "secret123")
        salt = await user_repo.get_salt(uid)
        fernet = get_fernet_instance("secret123", salt)

        dialog = await dialog_repo.create_dialog(uid, "Test Limit Dialog")

        # Add 10 messages sequentially
        for i in range(1, 11):
            await conv_repo.add_message(
                user_id=uid,
                dialog_id=dialog.dialog_id,
                role="user" if i % 2 != 0 else "bot",
                message_text=f"Message {i}",
                fernet_instance=fernet,
            )

        # When requesting limit=4, it must return the LAST 4 messages: 7, 8, 9, 10 (chronologically)
        recent_4 = await conv_repo.get_dialog_messages(dialog.dialog_id, fernet_instance=fernet, limit=4)
        assert len(recent_4) == 4
        assert [m["text"] for m in recent_4] == ["Message 7", "Message 8", "Message 9", "Message 10"]

    async def test_user_thinking_budget(self, async_session: AsyncSession):
        user_repo = UserRepository(async_session)
        uid = 777888
        user, _ = await user_repo.add_or_update_user(uid, "thinker", "Think", "User")
        assert user.thinking_budget == 1024

        await user_repo.update_thinking_budget(uid, 4096)
        user_updated = await user_repo.get_by_id(uid)
        assert user_updated.thinking_budget == 4096

        await user_repo.update_settings(uid, thinking_budget=0)
        user_updated2 = await user_repo.get_by_id(uid)
        assert user_updated2.thinking_budget == 0

    async def test_delete_last_assistant_message_and_turn(self, async_session: AsyncSession):
        user_repo = UserRepository(async_session)
        dialog_repo = DialogRepository(async_session)
        conv_repo = ConversationRepository(async_session)

        uid = 888999
        await user_repo.add_or_update_user(uid, "turn_test", "Turn", "User")
        await user_repo.set_master_password(uid, "turn_pass")
        salt = await user_repo.get_salt(uid)
        fernet = get_fernet_instance("turn_pass", salt)

        dialog = await dialog_repo.create_dialog(uid, "Turn Dialog")
        d_id = dialog.dialog_id

        # Empty dialog cases
        assert await conv_repo.delete_last_assistant_message(d_id) is None
        empty_text, empty_cnt = await conv_repo.delete_last_turn(d_id, fernet)
        assert empty_text is None and empty_cnt is None

        # Add Turn 1
        await conv_repo.add_message(uid, d_id, "user", "Question 1", fernet)
        msg_bot1 = await conv_repo.add_message(uid, d_id, "bot", "Answer 1", fernet)

        # Test delete_last_assistant_message
        deleted_bot_id = await conv_repo.delete_last_assistant_message(d_id)
        assert deleted_bot_id == msg_bot1.conversation_id
        msgs_left = await conv_repo.get_dialog_messages(d_id, fernet)
        assert len(msgs_left) == 1
        assert msgs_left[0]["text"] == "Question 1"

        # Re-add bot answer 1, then Turn 2
        await conv_repo.add_message(uid, d_id, "bot", "Answer 1 regenerated", fernet)
        await conv_repo.add_message(uid, d_id, "user", "Question 2", fernet)
        await conv_repo.add_message(uid, d_id, "bot", "Answer 2", fernet)

        # Test delete_last_turn
        user_text, del_count = await conv_repo.delete_last_turn(d_id, fernet)
        assert user_text == "Question 2"
        assert del_count == 2

        # Check that only Turn 1 remains
        msgs_after_turn = await conv_repo.get_dialog_messages(d_id, fernet)
        assert len(msgs_after_turn) == 2
        assert [m["text"] for m in msgs_after_turn] == ["Question 1", "Answer 1 regenerated"]

        # Test turn deletion when only user message exists without assistant reply
        await conv_repo.add_message(uid, d_id, "user", "Unanswered Question", fernet)
        user_text_unanswered, del_count_unanswered = await conv_repo.delete_last_turn(d_id, fernet)
        assert user_text_unanswered == "Unanswered Question"
        assert del_count_unanswered == 1



@pytest.mark.asyncio
class TestPaymentAndSettingsRepositories:
    """Tests for PaymentRepository and SettingsRepository."""

    async def test_payment_recording(self, async_session: AsyncSession):
        pay_repo = PaymentRepository(async_session)
        uid = 4001

        payment = await pay_repo.record_payment(
            user_id=uid,
            plan_id="premium_month",
            amount=500,
            currency="XTR",
            payment_date="2026-10-03 12:00:00",
            subscription_end_date="2026-11-03",
            telegram_charge_id="tg_ch_123",
            provider_charge_id="pr_ch_456",
        )
        assert payment.payment_id is not None

        user_payments = await pay_repo.get_user_payments(uid)
        assert len(user_payments) == 1
        assert user_payments[0].amount == 500
        assert user_payments[0].plan_id == "premium_month"

    async def test_settings_repository(self, async_session: AsyncSession):
        sett_repo = SettingsRepository(async_session)

        # Default
        assert await sett_repo.get_setting("custom_config", default="initial") == "initial"

        # Set & Get
        await sett_repo.set_setting("custom_config", "updated_value")
        assert await sett_repo.get_setting("custom_config") == "updated_value"

        # Maintenance mode
        assert await sett_repo.is_maintenance_mode() is False
        await sett_repo.set_maintenance_mode(True)
        assert await sett_repo.is_maintenance_mode() is True
        await sett_repo.set_maintenance_mode(False)
        assert await sett_repo.is_maintenance_mode() is False

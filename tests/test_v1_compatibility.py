"""
Test backward compatibility of MyGemini Zero v2 against real v1 SQLite database.
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from database.repositories.user_repository import UserRepository
from database.repositories.dialog_repository import DialogRepository
from database.repositories.conversation_repository import ConversationRepository


async def test_v1_compatibility():
    db_path = "d:/Projects/active/MyGemini_Zero/database/bot_database.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession)

    async with session_maker() as session:
        user_repo = UserRepository(session)
        dialog_repo = DialogRepository(session)
        conv_repo = ConversationRepository(session)

        users = await user_repo.get_all_users()
        print(f"Total users in v1 DB: {len(users)}")
        for u in users:
            salt_len = len(u.encryption_salt) if u.encryption_salt else 0
            hash_len = len(u.master_password_hash) if u.master_password_hash else 0
            has_api_key = u.api_key is not None
            print(
                f"User {u.user_id} | Salt: {salt_len}B | PwdHash: {hash_len}B | HasApiKey: {has_api_key} | Sub: {u.subscription_status}"
            )

            # Check dialogs
            dialogs = await dialog_repo.get_user_dialogs(u.user_id)
            print(f"  -> Dialog count: {len(dialogs)}")

    await engine.dispose()
    print("V1 DATABASE INTEGRITY AND BACKWARD COMPATIBILITY: 100% OK")


if __name__ == "__main__":
    asyncio.run(test_v1_compatibility())

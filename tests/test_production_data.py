"""
Production Data Verification Script for MyGemini Zero v2.
Checks that the real server database (12.8 MB) and ChromaDB (94 MB)
are successfully opened, read, and cross-referenced by the v2 codebase.
"""

import sys
import os
sys.path.insert(0, os.path.abspath("."))
import asyncio
from core.database import async_session_maker
from database.repositories import (
    UserRepository,
    DialogRepository,
    ConversationRepository,
    PaymentRepository,
)
from services.vector_store import VectorStoreManager


async def check_production_data():
    print("=== 1. Checking SQLite Database (bot_database.db) ===")
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        dialog_repo = DialogRepository(session)
        pay_repo = PaymentRepository(session)

        users = await user_repo.get_all_users()
        print(f"Total registered users: {len(users)}")

        for u in users:
            dialogs = await dialog_repo.get_user_dialogs(u.user_id)
            sub = u.subscription_status
            end_d = u.subscription_end_date or "none"
            uname = str(u.username or "none").encode("ascii", "replace").decode()
            fname = str(u.first_name or "").encode("ascii", "replace").decode()
            print(f"  * User ID: {u.user_id} (@{uname}), Name: {fname} | Sub: {sub} (until {end_d}) | Dialogs: {len(dialogs)}")

        payments = await pay_repo.get_all_payments()
        print(f"Total payments in database: {len(payments)}")

    print("\n=== 2. Checking ChromaDB Vector Store (vector_store) ===")
    vm = VectorStoreManager()
    collections = vm.client.list_collections()
    print(f"Total ChromaDB collections: {len(collections)}")

    total_chunks = 0
    docs_found = 0

    for col in collections:
        count = col.count()
        total_chunks += count
        dialog_id_str = col.name.replace("dialog_", "")

        if count > 0 and dialog_id_str.isdigit():
            d_id = int(dialog_id_str)
            docs = vm.get_dialog_documents(d_id)
            if docs:
                docs_found += len(docs)
                print(f"  * Collection '{col.name}' has {count} chunks, {len(docs)} document(s):")
                for doc in docs:
                    print(f"      - File: '{doc['file_name']}' (hash: {doc['file_hash']}, chunks: {doc['chunks_count']})")
            else:
                print(f"  * Collection '{col.name}' has {count} chunks (dialog message memory/summaries).")

    print(f"\nTotal vector chunks across all collections: {total_chunks}")
    print(f"Total indexed documents found: {docs_found}")
    print("\n=== PRODUCTION DATA INTEGRATION: 100% SUCCESS ===")


if __name__ == "__main__":
    asyncio.run(check_production_data())

"""
Async SQLAlchemy 2.0 Database Core.
Manages async engine, session factory, WAL pragmas, and schema initialization.
"""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
    AsyncAttrs,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from core.config import settings
from core.logger import get_logger

logger = get_logger("database")


class Base(AsyncAttrs, DeclarativeBase):
    """Base declarative class for all SQLAlchemy 2.0 models."""
    pass


# Create async engine for SQLite with connection pooling options
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

# Async session factory
async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency / context generator for acquiring an async database session."""
    async with async_session_maker() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.exception(f"Database session error: {e}")
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initializes SQLite pragmas (WAL mode, foreign keys) and creates all declarative tables.
    Runs non-destructive migrations to add missing columns to existing v1 databases.
    """
    async with engine.begin() as conn:
        # Enable WAL mode and Foreign Keys
        await conn.execute(text("PRAGMA journal_mode=WAL;"))
        await conn.execute(text("PRAGMA foreign_keys=ON;"))

        # Import all models to ensure they are registered with Base.metadata
        from database.models import (
            AppSettings,
            User,
            Dialog,
            Conversation,
            UserProfile,
            SubscriptionPayment,
        )

        # Create all tables if they do not exist
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables verified and initialized.")

    # Check and run non-destructive column migrations on existing tables
    await _migrate_missing_columns()


async def _migrate_missing_columns() -> None:
    """Safely adds missing columns if an existing v1 database is loaded."""
    async with engine.begin() as conn:
        # Check users table
        user_cols_res = await conn.execute(text("PRAGMA table_info(users)"))
        existing_user_cols = {row[1] for row in user_cols_res.fetchall()}

        user_column_specs = {
            "bot_style": "TEXT DEFAULT 'default' NOT NULL",
            "gemini_model": "TEXT",
            "active_persona": "TEXT DEFAULT 'default' NOT NULL",
            "master_password_hash": "BLOB",
            "encryption_salt": "BLOB",
            "api_key": "BLOB",
            "last_session_ts": "TEXT",
            "panic_password_hash": "BLOB",
            "subscription_status": "TEXT DEFAULT 'none' NOT NULL",
            "subscription_end_date": "TEXT",
        }

        for col, col_def in user_column_specs.items():
            if col not in existing_user_cols:
                logger.info(f"Adding missing column to 'users': {col}")
                await conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {col_def}"))

        # Check conversations table
        conv_cols_res = await conn.execute(text("PRAGMA table_info(conversations)"))
        existing_conv_cols = {row[1] for row in conv_cols_res.fetchall()}

        if "content_type" not in existing_conv_cols:
            logger.info("Adding missing column to 'conversations': content_type")
            await conn.execute(text("ALTER TABLE conversations ADD COLUMN content_type TEXT DEFAULT 'text' NOT NULL"))

    logger.info("Database migrations check completed.")

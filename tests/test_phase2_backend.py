"""
Unit tests for Phase 2 Backend Components:
- User model session_ttl_minutes and enable_code_execution fields
- UserRepository update_session_ttl, toggle_code_execution, update_settings
- SessionManager dynamic per-user session TTL
- GeminiService enable_code_execution tool injection and usage metadata capture
- MessageStreamThrottler start_time, elapsed_time, token metadata HUD display
"""

import time
import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram import Bot
from aiogram.types import Message
from cryptography.fernet import Fernet

from core.database import init_db, async_session_maker
from database.repositories import UserRepository
from middlewares.auth import SessionManager
from services.gemini import GeminiService, StreamChunk
from services.throttler import MessageStreamThrottler


class MockAsyncStream:
    """Helper mock async iterator for Gemini generate_content_stream."""

    def __init__(self, chunks):
        self.chunks = chunks

    def __aiter__(self):
        self._iter = iter(self.chunks)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()
    yield


@pytest.mark.asyncio
class TestUserRepositoryPhase2:
    """Tests for Phase 2 UserRepository enhancements."""

    async def test_user_phase2_defaults(self):
        user_id = 998001
        async with async_session_maker() as session:
            repo = UserRepository(session)
            user, is_new = await repo.add_or_update_user(user_id, "phase2_user", "Test", "User")
            assert user.session_ttl_minutes == 60
            assert user.enable_code_execution is False

    async def test_update_session_ttl(self):
        user_id = 998002
        async with async_session_maker() as session:
            repo = UserRepository(session)
            await repo.add_or_update_user(user_id, "ttl_user", "Test", "User")
            await repo.update_session_ttl(user_id, ttl_minutes=120)

            user = await repo.get_by_id(user_id)
            assert user is not None
            assert user.session_ttl_minutes == 120

    async def test_toggle_code_execution(self):
        user_id = 998003
        async with async_session_maker() as session:
            repo = UserRepository(session)
            await repo.add_or_update_user(user_id, "code_user", "Test", "User")

            # Toggle 1: False -> True
            state1 = await repo.toggle_code_execution(user_id)
            assert state1 is True
            user1 = await repo.get_by_id(user_id)
            assert user1.enable_code_execution is True

            # Toggle 2: True -> False
            state2 = await repo.toggle_code_execution(user_id)
            assert state2 is False
            user2 = await repo.get_by_id(user_id)
            assert user2.enable_code_execution is False

    async def test_update_settings_phase2_fields(self):
        user_id = 998004
        async with async_session_maker() as session:
            repo = UserRepository(session)
            await repo.add_or_update_user(user_id, "settings_user", "Test", "User")

            await repo.update_settings(
                user_id=user_id,
                session_ttl_minutes=480,
                enable_code_execution=True,
            )

            user = await repo.get_by_id(user_id)
            assert user.session_ttl_minutes == 480
            assert user.enable_code_execution is True


class TestSessionManagerDynamicTTL:
    """Tests for dynamic per-user session TTL in SessionManager."""

    def test_dynamic_ttl_active(self):
        mgr = SessionManager()
        user_id = 12345
        fernet = Fernet(Fernet.generate_key())
        mgr.unlock_session(user_id, fernet)

        # Fresh session with 30 min TTL is active
        assert mgr.is_session_active(user_id, ttl_minutes=30) is True
        assert mgr.get_fernet(user_id, ttl_minutes=30) == fernet

    def test_dynamic_ttl_expiration(self):
        mgr = SessionManager()
        user_id = 12346
        fernet = Fernet(Fernet.generate_key())
        mgr.unlock_session(user_id, fernet)

        # Artificially age the session by 600 seconds
        mgr._last_activity[user_id] = time.monotonic() - 600

        # With 5 min TTL (300s), 600s elapsed should expire and lock
        assert mgr.is_session_active(user_id, ttl_minutes=5) is False
        assert mgr.get_fernet(user_id, ttl_minutes=5) is None
        assert user_id not in mgr._active_sessions

    def test_dynamic_ttl_still_valid_within_window(self):
        mgr = SessionManager()
        user_id = 12347
        fernet = Fernet(Fernet.generate_key())
        mgr.unlock_session(user_id, fernet)

        # Artificially age the session by 600 seconds (10 minutes)
        mgr._last_activity[user_id] = time.monotonic() - 600

        # With 30 min TTL (1800s), 600s is within window
        assert mgr.is_session_active(user_id, ttl_minutes=30) is True
        assert mgr.get_fernet(user_id, ttl_minutes=30) is not None


@pytest.mark.asyncio
class TestGeminiServicePhase2:
    """Tests for code execution tool injection and usage metadata capture in GeminiService."""

    async def test_generate_stream_code_execution_tool_configured(self):
        service = GeminiService(api_key="test_api_key")
        service.client = MagicMock()
        service.client.aio = MagicMock()
        service.client.aio.models = MagicMock()

        captured_config = None

        async def fake_stream_coro(**kwargs):
            nonlocal captured_config
            captured_config = kwargs.get("config")
            mock_chunk = MagicMock()
            mock_chunk.text = "Hello world"
            mock_chunk.usage_metadata = None
            return MockAsyncStream([mock_chunk])

        service.client.aio.models.generate_content_stream = AsyncMock(side_effect=fake_stream_coro)

        # Call with enable_code_execution=True
        chunks = []
        async for chunk in service.generate_stream(
            model_id="gemini-2.5-flash",
            contents=["test prompt"],
            enable_search=True,
            enable_code_execution=True,
        ):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0] == "Hello world"
        assert captured_config is not None
        assert captured_config.tools is not None

        # Check tools include both GoogleSearch and ToolCodeExecution
        has_code_exec = any(t.code_execution is not None for t in captured_config.tools)
        has_search = any(t.google_search is not None for t in captured_config.tools)
        assert has_code_exec is True
        assert has_search is True

    async def test_generate_stream_captures_usage_metadata(self):
        service = GeminiService(api_key="test_api_key")
        service.client = MagicMock()
        service.client.aio = MagicMock()
        service.client.aio.models = MagicMock()

        mock_usage = MagicMock()
        mock_usage.prompt_token_count = 150
        mock_usage.candidates_token_count = 250
        mock_usage.total_token_count = 400

        async def fake_stream_coro(**kwargs):
            chunk1 = MagicMock()
            chunk1.text = "Part 1. "
            chunk1.usage_metadata = None

            chunk2 = MagicMock()
            chunk2.text = "Part 2."
            chunk2.usage_metadata = mock_usage
            return MockAsyncStream([chunk1, chunk2])

        service.client.aio.models.generate_content_stream = AsyncMock(side_effect=fake_stream_coro)

        chunks = []
        async for chunk in service.generate_stream(
            model_id="gemini-2.5-flash",
            contents=["test prompt"],
        ):
            chunks.append(chunk)

        assert "".join(chunks) == "Part 1. Part 2."
        # Verify chunk2 carried usage_metadata
        assert chunks[1].usage_metadata == mock_usage
        # Verify service captured last_usage_metadata
        assert service.last_usage_metadata == {
            "prompt_tokens": 150,
            "candidates_tokens": 250,
            "total_tokens": 400,
        }


@pytest.mark.asyncio
class TestThrottlerPhase2:
    """Tests for Phase 2 throttler HUD formatting, elapsed time, and token metrics."""

    async def test_throttler_elapsed_time_and_hud_with_header(self):
        bot = MagicMock(spec=Bot)
        bot.edit_message_text = AsyncMock()

        msg = MagicMock(spec=Message)
        msg.message_id = 8801

        throttler = MessageStreamThrottler(
            bot=bot,
            chat_id=55511,
            initial_message=msg,
            header_text="> 💬 **Диалог:** Тест\n> ⚡ **Модель:** gemini-2.5-flash\n\n",
            message_format="rich",
        )

        throttler.set_usage_metadata(prompt_tokens=100, candidates_tokens=200, total_tokens=300)
        await throttler.handle_chunk("Ответ модели.")
        full_text = await throttler.finalize()

        assert full_text == "Ответ модели."
        assert throttler.elapsed_time is not None
        assert throttler.elapsed_time >= 0

        # Verify bot.edit_message_text was called and rich HTML includes HUD stats
        bot.edit_message_text.assert_awaited()
        last_kwargs = bot.edit_message_text.call_args.kwargs
        rich_obj = last_kwargs.get("rich_message")
        assert rich_obj is not None
        # Check tokens HUD line is present in rendered HTML
        assert "300 токенов" in rich_obj.html

    async def test_throttler_update_usage_from_chunk(self):
        bot = MagicMock(spec=Bot)
        msg = MagicMock(spec=Message)
        msg.message_id = 8802

        throttler = MessageStreamThrottler(
            bot=bot,
            chat_id=55512,
            initial_message=msg,
        )

        mock_usage = MagicMock()
        mock_usage.prompt_token_count = 55
        mock_usage.candidates_token_count = 145
        mock_usage.total_token_count = 200

        chunk = StreamChunk("test text")
        chunk.usage_metadata = mock_usage

        throttler.update_usage_from_chunk(chunk)
        assert throttler.prompt_tokens == 55
        assert throttler.candidates_tokens == 145
        assert throttler.total_tokens == 200

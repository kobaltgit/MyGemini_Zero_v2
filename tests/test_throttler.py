"""
Unit tests for services/throttler.py:
- format_markdown_safe (Markdown formatting and safe fallback)
- MessageStreamThrottler (chunk buffering, splitting, finalization)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram import Bot
from aiogram.types import Message
from services.throttler import format_markdown_safe, MessageStreamThrottler
from core.config import settings


class TestThrottlerFormatting:
    """Tests for format_markdown_safe."""

    def test_format_markdown_safe_basic(self):
        text = "Hello **world**! Here is `code`."
        formatted, parse_mode = format_markdown_safe(text)
        assert parse_mode == "MarkdownV2"
        assert formatted is not None
        assert len(formatted) > 0

    def test_format_markdown_safe_plain_fallback_on_excessive_length(self):
        # Text exceeding MAX_FORMATTED_CHUNK_SIZE should fall back to plain text
        huge_text = "a" * (settings.MAX_FORMATTED_CHUNK_SIZE + 100)
        formatted, parse_mode = format_markdown_safe(huge_text)
        assert parse_mode is None
        assert formatted == huge_text


@pytest.mark.asyncio
class TestMessageStreamThrottler:
    """Tests for MessageStreamThrottler behavior."""

    async def test_throttler_lifecycle_and_finalize(self):
        bot = MagicMock(spec=Bot)
        bot.edit_message_text = AsyncMock()

        msg = MagicMock(spec=Message)
        msg.message_id = 12345

        throttler = MessageStreamThrottler(
            bot=bot,
            chat_id=98765,
            initial_message=msg,
            throttle_interval=0.5,
            header_text="• Context Header\n\n",
        )

        # Feed small chunks
        await throttler.handle_chunk("Chunk 1. ")
        await throttler.handle_chunk("Chunk 2.")

        # Finalize
        full_text = await throttler.finalize()
        assert full_text == "Chunk 1. Chunk 2."
        # Must have updated telegram message
        assert bot.edit_message_text.await_count >= 1

    async def test_throttler_splitting_on_chunk_size(self):
        bot = MagicMock(spec=Bot)
        bot.edit_message_text = AsyncMock()
        new_msg = MagicMock(spec=Message)
        new_msg.message_id = 12346
        bot.send_message = AsyncMock(return_value=new_msg)

        msg = MagicMock(spec=Message)
        msg.message_id = 12345

        throttler = MessageStreamThrottler(
            bot=bot,
            chat_id=98765,
            initial_message=msg,
            throttle_interval=0.1,
        )

        # Feed a chunk exceeding CHUNK_SIZE
        paragraph = "This is a detailed analysis. " * 150  # ~4350 chars > 3200
        await throttler.handle_chunk(paragraph)

        # Should split and send a new message
        bot.send_message.assert_awaited()
        assert len(throttler.completed_messages) >= 1

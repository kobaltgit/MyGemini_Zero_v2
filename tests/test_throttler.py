"""
Unit tests for services/throttler.py:
- format_markdown_safe (Markdown formatting and safe fallback)
- MessageStreamThrottler in classic Markdown mode (splits at CHUNK_SIZE = 3200)
- MessageStreamThrottler in Rich Messages mode (tg-rich-converter, 30,000 limit, InputRichMessage, fallback)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram import Bot
from aiogram.types import Message, InputRichMessage
from aiogram.exceptions import TelegramBadRequest
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
        huge_text = "a" * (settings.MAX_FORMATTED_CHUNK_SIZE + 100)
        formatted, parse_mode = format_markdown_safe(huge_text)
        assert parse_mode is None
        assert formatted == huge_text


@pytest.mark.asyncio
class TestMessageStreamThrottlerLegacy:
    """Tests for MessageStreamThrottler in legacy Markdown mode."""

    async def test_legacy_lifecycle_and_finalize(self):
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
            message_format="markdown",
        )

        await throttler.handle_chunk("Chunk 1. ")
        await throttler.handle_chunk("Chunk 2.")

        full_text = await throttler.finalize()
        assert full_text == "Chunk 1. Chunk 2."
        assert bot.edit_message_text.await_count >= 1

    async def test_legacy_splitting_on_chunk_size(self):
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
            message_format="markdown",
        )

        paragraph = "This is a detailed analysis. " * 150  # ~4350 chars > 3200
        await throttler.handle_chunk(paragraph)

        # In legacy mode, it splits at 3200 and calls send_message
        bot.send_message.assert_awaited()
        assert len(throttler.completed_messages) >= 1


@pytest.mark.asyncio
class TestMessageStreamThrottlerRich:
    """Tests for MessageStreamThrottler in Rich Messages (10.1+) mode."""

    async def test_rich_streaming_edits_with_input_rich_message(self):
        bot = MagicMock(spec=Bot)
        bot.edit_message_text = AsyncMock()

        msg = MagicMock(spec=Message)
        msg.message_id = 54321

        throttler = MessageStreamThrottler(
            bot=bot,
            chat_id=112233,
            initial_message=msg,
            throttle_interval=0.01,
            message_format="rich",
        )

        # Feed tokens containing markdown table and math
        await throttler.handle_chunk("| Col1 | Col2 |\n|---|---|\n| Val1 | $E=mc^2$ |")
        await throttler.handle_chunk("\n\n<think>Analyzing quantum state...</think>")

        full_text = await throttler.finalize()
        assert "Col1" in full_text
        assert "$E=mc^2$" in full_text

        # Verify bot.edit_message_text was called with rich_message=InputRichMessage
        assert bot.edit_message_text.await_count >= 1
        last_call_kwargs = bot.edit_message_text.call_args.kwargs
        assert "rich_message" in last_call_kwargs
        rich_obj = last_call_kwargs["rich_message"]
        assert isinstance(rich_obj, InputRichMessage)
        assert "<table" in rich_obj.html
        assert "<tg-math>" in rich_obj.html
        assert "<details>" in rich_obj.html

    async def test_rich_streaming_cascade_fallback_on_parse_error(self):
        """If edit_message_text fails with parse error, must fall back to plain text."""
        bot = MagicMock(spec=Bot)
        # First call raises TelegramBadRequest (can't parse entities)
        bot.edit_message_text = AsyncMock(
            side_effect=[
                TelegramBadRequest(method="editMessageText", message="Bad Request: can't parse entities"),
                True,
            ]
        )

        msg = MagicMock(spec=Message)
        msg.message_id = 54322

        throttler = MessageStreamThrottler(
            bot=bot,
            chat_id=112233,
            initial_message=msg,
            throttle_interval=0.01,
            message_format="rich",
        )

        await throttler.handle_chunk("Normal chunk")
        await throttler.finalize()

        # Should have attempted edit, caught error, and fallen back to plain text edit
        assert bot.edit_message_text.await_count >= 2
        fallback_call = bot.edit_message_text.call_args_list[1]
        assert fallback_call.kwargs.get("parse_mode") is None
        assert "Normal chunk" in fallback_call.kwargs.get("text", "")

    async def test_rich_no_split_on_moderate_length(self):
        """Rich mode must NOT split responses up to 30,000 characters."""
        bot = MagicMock(spec=Bot)
        bot.edit_message_text = AsyncMock()
        bot.send_rich_message = AsyncMock()

        msg = MagicMock(spec=Message)
        msg.message_id = 54323

        throttler = MessageStreamThrottler(
            bot=bot,
            chat_id=112233,
            initial_message=msg,
            throttle_interval=0.1,
            message_format="rich",
        )

        # 10,000 characters: in legacy this would be 3-4 messages, in Rich it's 1 message!
        large_chunk = "Long response line here.\n" * 400  # ~10,000 chars
        await throttler.handle_chunk(large_chunk)
        await throttler.finalize()

        # send_rich_message must NOT have been called (no split occurred)
        bot.send_rich_message.assert_not_awaited()
        assert len(throttler.completed_messages) == 1

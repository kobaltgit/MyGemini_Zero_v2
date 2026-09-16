"""
Telegram Message Streaming Throttler for MyGemini Zero v2.
Prevents Telegram FloodWait errors, safely formats streaming markdown,
and dynamically splits large responses exceeding 3200 characters into sequential messages.
"""

import time
import asyncio
from typing import Optional, List
from aiogram import Bot
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
import telegramify_markdown

from core.config import settings
from core.logger import get_logger

logger = get_logger("user_messages")


# Type alias
Tuple_Markdown = tuple[str, Optional[str]]


def format_markdown_safe(text: str) -> Tuple_Markdown:
    """
    Attempts to format text into Telegram-safe MarkdownV2.
    Returns (formatted_text, parse_mode) or (plain_text, None) on failure.
    """
    try:
        # telegramify_markdown formats markdown to Telegram MarkdownV2 safely
        converted = telegramify_markdown.markdownify(text)
        if len(converted) <= settings.MAX_FORMATTED_CHUNK_SIZE:
            return converted, "MarkdownV2"
        # If markdown escaping expanded beyond safe limit, fall back to plain text
        return text, None
    except Exception:
        return text, None


class MessageStreamThrottler:
    """
    Buffers streaming AI chunks and updates Telegram message at throttled intervals.
    Automatically splits long responses into multiple messages when crossing CHUNK_SIZE.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        initial_message: Message,
        throttle_interval: float = 1.1,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.current_message = initial_message
        self.throttle_interval = throttle_interval

        self.full_response_text: str = ""
        self.current_chunk_text: str = ""
        self.last_update_time: float = 0.0
        self.completed_messages: List[Message] = []

    async def handle_chunk(self, chunk: str) -> None:
        """Appends a new streaming text chunk and checks throttle/split conditions."""
        self.full_response_text += chunk
        self.current_chunk_text += chunk

        # Check if current chunk exceeds safe threshold for a single Telegram message
        if len(self.current_chunk_text) >= settings.CHUNK_SIZE:
            await self._split_and_start_new_message()
            return

        now = time.monotonic()
        if (now - self.last_update_time) >= self.throttle_interval:
            await self._update_telegram_message(is_final=False)
            self.last_update_time = now

    async def _update_telegram_message(self, is_final: bool = False) -> None:
        """Edits the active Telegram message with buffered text."""
        display_text = self.current_chunk_text.strip()
        if not display_text:
            return

        # Add typing indicator cursor if still streaming
        if not is_final:
            display_text += " ▌"

        formatted_text, parse_mode = format_markdown_safe(display_text)

        try:
            await self.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=self.current_message.message_id,
                text=formatted_text,
                parse_mode=parse_mode,
            )
        except TelegramRetryAfter as e:
            logger.warning(f"Telegram FloodWait during stream ({e.retry_after}s). Sleeping...")
            await asyncio.sleep(e.retry_after)
        except TelegramBadRequest as e:
            err = str(e).lower()
            if "message is not modified" in err:
                pass
            elif "can't parse entities" in err or "tag" in err:
                # Fallback to plain unformatted text on Markdown entity parsing error
                try:
                    await self.bot.edit_message_text(
                        chat_id=self.chat_id,
                        message_id=self.current_message.message_id,
                        text=display_text,
                        parse_mode=None,
                    )
                except Exception:
                    pass
            else:
                logger.warning(f"TelegramBadRequest in edit_message_text: {e}")
        except Exception as e:
            logger.error(f"Unexpected error updating stream: {e}")

    async def _split_and_start_new_message(self) -> None:
        """
        Splits text at the nearest paragraph or sentence boundary,
        finalizes the current message, and creates a new one for subsequent text.
        """
        text = self.current_chunk_text
        split_index = -1

        # Try splitting by double newline (paragraphs)
        last_double_nl = text.rfind("\n\n", 0, settings.CHUNK_SIZE)
        if last_double_nl > settings.CHUNK_SIZE // 2:
            split_index = last_double_nl + 2
        else:
            # Try single newline
            last_nl = text.rfind("\n", 0, settings.CHUNK_SIZE)
            if last_nl > settings.CHUNK_SIZE // 2:
                split_index = last_nl + 1
            else:
                # Try space
                last_space = text.rfind(" ", 0, settings.CHUNK_SIZE)
                if last_space > settings.CHUNK_SIZE // 2:
                    split_index = last_space + 1
                else:
                    split_index = settings.CHUNK_SIZE

        to_finalize = text[:split_index]
        remaining = text[split_index:]

        # Finalize current message with portion before split
        self.current_chunk_text = to_finalize
        await self._update_telegram_message(is_final=True)
        self.completed_messages.append(self.current_message)

        # Send new message for remaining portion
        self.current_chunk_text = remaining
        new_text, parse_mode = format_markdown_safe(
            remaining + " ▌" if remaining else "..."
        )
        try:
            self.current_message = await self.bot.send_message(
                chat_id=self.chat_id,
                text=new_text,
                parse_mode=parse_mode,
            )
            self.last_update_time = time.monotonic()
        except Exception as e:
            logger.error(f"Error sending next chunk message: {e}")

    async def finalize(self) -> str:
        """
        Finalizes the streaming process: updates last active message
        without cursor and returns complete full raw text for conversation history.
        """
        await self._update_telegram_message(is_final=True)
        self.completed_messages.append(self.current_message)
        return self.full_response_text

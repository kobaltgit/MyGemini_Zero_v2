"""
Telegram Message Streaming Throttler for MyGemini Zero v2.
Supports:
1. Native Telegram Bot API 10.1+ Rich Messages via tg-rich-converter:
   - Native tables (<table bordered striped>), LaTeX math (<tg-math>), expandable <details> thinking
   - Live token streaming with auto-balanced unclosed markdown/tags (streaming=True)
   - 32,768-character capacity per message (threshold set to 30,000)
   - Fast 0.8s throttle interval for responsive UX
   - Robust cascade fallback to plain text on entity parse errors
2. Classic MarkdownV2 mode via telegramify-markdown:
   - For legacy or third-party Telegram clients
   - 3,200-character chunk limit and 1.1s throttle interval
"""

import time
import asyncio
from typing import Optional, List, Tuple
from aiohttp import ClientError
from aiogram import Bot
from aiogram.types import Message, InputRichMessage
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter, TelegramNetworkError
import telegramify_markdown
from tg_rich_converter import to_rich, split_rich_message

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
        converted = telegramify_markdown.markdownify(text)
        if len(converted) <= settings.MAX_FORMATTED_CHUNK_SIZE:
            return converted, "MarkdownV2"
        return text, None
    except Exception:
        return text, None


class MessageStreamThrottler:
    """
    Buffers streaming AI chunks and updates Telegram message at throttled intervals.
    Dynamically routes between Rich Messages (tg-rich-converter) and Classic Markdown.
    """

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        initial_message: Message,
        throttle_interval: Optional[float] = None,
        header_text: str = "",
        message_format: str = "rich",
        thinking_summary: str = "Размышления",
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.current_message = initial_message
        self.header_text = header_text
        self.message_format = message_format or getattr(settings, "DEFAULT_MESSAGE_FORMAT", "rich")
        self.thinking_summary = thinking_summary

        if throttle_interval is not None:
            self.throttle_interval = throttle_interval
        elif self.message_format == "rich":
            self.throttle_interval = getattr(settings, "RICH_THROTTLE_INTERVAL", 0.8)
        else:
            self.throttle_interval = getattr(settings, "LEGACY_THROTTLE_INTERVAL", 1.1)

        self.full_response_text: str = ""
        self.current_chunk_text: str = ""
        self.last_update_time: float = 0.0
        self.completed_messages: List[Message] = []
        self._last_rendered_html: str = ""

    async def handle_chunk(self, chunk: str) -> None:
        """Appends a new streaming text chunk and checks throttle/split conditions."""
        self.full_response_text += chunk
        self.current_chunk_text += chunk

        limit = (
            settings.RICH_CHUNK_SIZE
            if self.message_format == "rich"
            else settings.CHUNK_SIZE
        )

        if len(self.current_chunk_text) >= limit:
            await self._split_and_start_new_message()
            return

        now = time.monotonic()
        if (now - self.last_update_time) >= self.throttle_interval:
            await self._update_telegram_message(is_final=False)
            self.last_update_time = now

    async def _update_telegram_message(self, is_final: bool = False) -> None:
        """Edits active Telegram message with buffered text in chosen format."""
        chunk_content = self.current_chunk_text.strip()
        if not chunk_content and not self.header_text:
            return

        prefix = self.header_text if not self.completed_messages else ""
        raw_text = f"{prefix}{chunk_content}" if chunk_content else prefix.strip()

        if self.message_format == "rich":
            await self._update_rich_message(raw_text, is_final=is_final)
        else:
            await self._update_legacy_message(raw_text, is_final=is_final)

    async def _update_rich_message(self, raw_text: str, is_final: bool) -> None:
        """Renders and edits message using tg-rich-converter Rich Messages (10.1+)."""
        streaming_mode = not is_final
        rich_html = to_rich(
            raw_text,
            thinking_summary=self.thinking_summary,
            streaming=streaming_mode,
        )

        if not rich_html or (streaming_mode and rich_html == self._last_rendered_html):
            return

        max_attempts = 4 if is_final else 1
        for attempt in range(1, max_attempts + 1):
            try:
                await self.bot.edit_message_text(
                    chat_id=self.chat_id,
                    message_id=self.current_message.message_id,
                    rich_message=InputRichMessage(html=rich_html),
                )
                self._last_rendered_html = rich_html
                return
            except TelegramRetryAfter as e:
                logger.warning(f"Telegram FloodWait during rich stream ({e.retry_after}s). Sleeping...")
                await asyncio.sleep(e.retry_after)
                if is_final and attempt < max_attempts:
                    continue
                elif is_final:
                    break
                return
            except TelegramBadRequest as e:
                err = str(e).lower()
                if "message is not modified" in err:
                    self._last_rendered_html = rich_html
                    return
                elif "can't parse entities" in err or "tag" in err or "unsupported" in err or "rich" in err:
                    logger.warning(f"Entity parse error in rich edit, attempting cascade plain text fallback: {e}")
                    try:
                        await self.bot.edit_message_text(
                            chat_id=self.chat_id,
                            message_id=self.current_message.message_id,
                            text=raw_text,
                            parse_mode=None,
                        )
                        return
                    except Exception as cascade_err:
                        logger.warning(f"Cascade plain text edit also failed: {cascade_err}")
                        if is_final and attempt < max_attempts:
                            await asyncio.sleep(0.5)
                            continue
                        elif is_final:
                            break
                        return
                else:
                    logger.warning(f"TelegramBadRequest in edit_message_text: {e}")
                    if is_final:
                        break
                    return
            except (ClientError, TelegramNetworkError, asyncio.TimeoutError) as e:
                logger.warning(f"Network error in rich stream edit (attempt {attempt}/{max_attempts}): {e}")
                if is_final and attempt < max_attempts:
                    await asyncio.sleep(0.5 * attempt)
                    continue
                elif is_final:
                    break
                return
            except Exception as e:
                logger.error(f"Unexpected error in rich stream edit (attempt {attempt}/{max_attempts}): {e}")
                if is_final and attempt < max_attempts:
                    await asyncio.sleep(0.5 * attempt)
                    continue
                elif is_final:
                    break
                return

        # If finalizing and all edit attempts failed (e.g. permanent network/message issue), ensure delivery via send_message
        if is_final:
            logger.warning("All rich edit attempts failed on finalize. Falling back to sending a new message.")
            try:
                self.current_message = await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=raw_text,
                    parse_mode=None,
                )
            except Exception as send_err:
                logger.error(f"Final fallback send_message also failed: {send_err}")

    async def _update_legacy_message(self, raw_text: str, is_final: bool) -> None:
        """Edits message using classic MarkdownV2 / plain text."""
        display_text = raw_text if is_final else f"{raw_text} ▌"
        formatted_text, parse_mode = format_markdown_safe(display_text)

        max_attempts = 4 if is_final else 1
        for attempt in range(1, max_attempts + 1):
            try:
                await self.bot.edit_message_text(
                    chat_id=self.chat_id,
                    message_id=self.current_message.message_id,
                    text=formatted_text,
                    parse_mode=parse_mode,
                )
                return
            except TelegramRetryAfter as e:
                logger.warning(f"Telegram FloodWait during stream ({e.retry_after}s). Sleeping...")
                await asyncio.sleep(e.retry_after)
                if is_final and attempt < max_attempts:
                    continue
                elif is_final:
                    break
                return
            except TelegramBadRequest as e:
                err = str(e).lower()
                if "message is not modified" in err:
                    return
                elif "can't parse entities" in err or "tag" in err:
                    try:
                        await self.bot.edit_message_text(
                            chat_id=self.chat_id,
                            message_id=self.current_message.message_id,
                            text=display_text,
                            parse_mode=None,
                        )
                        return
                    except Exception as cascade_err:
                        logger.warning(f"Legacy cascade plain edit failed: {cascade_err}")
                        if is_final and attempt < max_attempts:
                            await asyncio.sleep(0.5)
                            continue
                        elif is_final:
                            break
                        return
                else:
                    logger.warning(f"TelegramBadRequest in legacy edit_message_text: {e}")
                    if is_final:
                        break
                    return
            except (ClientError, TelegramNetworkError, asyncio.TimeoutError) as e:
                logger.warning(f"Network error in legacy stream edit (attempt {attempt}/{max_attempts}): {e}")
                if is_final and attempt < max_attempts:
                    await asyncio.sleep(0.5 * attempt)
                    continue
                elif is_final:
                    break
                return
            except Exception as e:
                logger.error(f"Unexpected error updating legacy stream (attempt {attempt}/{max_attempts}): {e}")
                if is_final and attempt < max_attempts:
                    await asyncio.sleep(0.5 * attempt)
                    continue
                elif is_final:
                    break
                return

        # If finalizing and all legacy edit attempts failed, ensure delivery via send_message
        if is_final:
            logger.warning("All legacy edit attempts failed on finalize. Falling back to sending a new message.")
            try:
                self.current_message = await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=display_text,
                    parse_mode=None,
                )
            except Exception as send_err:
                logger.error(f"Legacy final fallback send_message failed: {send_err}")

    async def _split_and_start_new_message(self) -> None:
        """
        Splits text safely at boundaries, finalizes current message,
        and opens a new sequential message.
        """
        text = self.current_chunk_text
        limit = (
            settings.RICH_CHUNK_SIZE
            if self.message_format == "rich"
            else settings.CHUNK_SIZE
        )

        split_index = -1
        last_double_nl = text.rfind("\n\n", 0, limit)
        if last_double_nl > limit // 2:
            split_index = last_double_nl + 2
        else:
            last_nl = text.rfind("\n", 0, limit)
            if last_nl > limit // 2:
                split_index = last_nl + 1
            else:
                last_space = text.rfind(" ", 0, limit)
                if last_space > limit // 2:
                    split_index = last_space + 1
                else:
                    split_index = limit

        to_finalize = text[:split_index]
        remaining = text[split_index:]

        # Finalize current message
        self.current_chunk_text = to_finalize
        await self._update_telegram_message(is_final=True)
        self.completed_messages.append(self.current_message)

        # Start new message for remaining portion
        self.current_chunk_text = remaining
        self._last_rendered_html = ""

        if self.message_format == "rich":
            initial_html = to_rich(
                remaining if remaining else "...",
                thinking_summary=self.thinking_summary,
                streaming=True,
            )
            try:
                self.current_message = await self.bot.send_rich_message(
                    chat_id=self.chat_id,
                    rich_message=InputRichMessage(html=initial_html),
                )
            except Exception as e:
                logger.warning(f"Failed to send_rich_message on split, fallback to send_message: {e}")
                self.current_message = await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=remaining if remaining else "...",
                    parse_mode="HTML",
                )
        else:
            new_text, parse_mode = format_markdown_safe(
                remaining + " ▌" if remaining else "..."
            )
            try:
                self.current_message = await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=new_text,
                    parse_mode=parse_mode,
                )
            except Exception as e:
                logger.error(f"Error sending next legacy chunk message: {e}")

        self.last_update_time = time.monotonic()

    async def finalize(self) -> str:
        """
        Finalizes streaming: renders final message frame (streaming=False)
        without balancer or typing cursors, and returns complete raw markdown for history.
        """
        await self._update_telegram_message(is_final=True)
        self.completed_messages.append(self.current_message)
        return self.full_response_text

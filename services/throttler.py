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
import re
from typing import Optional, List, Tuple, Any
from aiohttp import ClientError
from aiogram import Bot
from aiogram.types import Message, InputRichMessage, InlineKeyboardMarkup
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
        header_style: str = "blockquote",
        header_summary: str = "",
        stop_keyboard: Optional[InlineKeyboardMarkup] = None,
        quick_actions_keyboard: Optional[InlineKeyboardMarkup] = None,
    ):
        self.bot = bot
        self.chat_id = chat_id
        self.current_message = initial_message
        self.header_text = header_text
        self.header_summary = header_summary
        self.message_format = message_format or getattr(settings, "DEFAULT_MESSAGE_FORMAT", "rich")
        self.thinking_summary = thinking_summary
        self.header_style = header_style or "blockquote"
        self.stop_keyboard = stop_keyboard
        self.quick_actions_keyboard = quick_actions_keyboard
        self.is_aborted: bool = False
        self.fallback_notice: Optional[str] = None

        self.start_time: float = time.monotonic()
        self.elapsed_time: Optional[float] = None
        self.prompt_tokens: Optional[int] = None
        self.candidates_tokens: Optional[int] = None
        self.total_tokens: Optional[int] = None

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

    def set_usage_metadata(
        self, prompt_tokens: Any = None, candidates_tokens: Optional[int] = None, total_tokens: Optional[int] = None
    ) -> None:
        """Sets API usage token counts from either a metadata object or separate token counts."""
        try:
            if candidates_tokens is None and total_tokens is None and prompt_tokens is not None:
                meta = prompt_tokens
                p = getattr(meta, "prompt_token_count", None) or (meta.get("prompt_tokens") if isinstance(meta, dict) else 0) or 0
                c = getattr(meta, "candidates_token_count", None) or (meta.get("candidates_tokens") if isinstance(meta, dict) else 0) or 0
                t = getattr(meta, "total_token_count", None) or (meta.get("total_tokens") if isinstance(meta, dict) else 0) or 0
                self.prompt_tokens = int(p)
                self.candidates_tokens = int(c)
                self.total_tokens = int(t)
                self.usage_metadata = meta
            else:
                self.prompt_tokens = int(prompt_tokens) if prompt_tokens is not None else None
                self.candidates_tokens = int(candidates_tokens) if candidates_tokens is not None else None
                self.total_tokens = int(total_tokens) if total_tokens is not None else None
                self.usage_metadata = {
                    "prompt_tokens": self.prompt_tokens,
                    "candidates_tokens": self.candidates_tokens,
                    "total_tokens": self.total_tokens,
                }
        except (ValueError, TypeError):
            pass

    def update_usage_from_chunk(self, chunk: Any) -> None:
        """Extracts token usage metadata from chunk if available."""
        meta = getattr(chunk, "usage_metadata", None)
        if meta is not None:
            try:
                p = getattr(meta, "prompt_token_count", None)
                c = getattr(meta, "candidates_token_count", None)
                t = getattr(meta, "total_token_count", None)
                p_int = int(p) if p is not None else 0
                c_int = int(c) if c is not None else 0
                t_int = int(t) if t is not None else 0
                if t_int > 0 or p_int > 0 or c_int > 0:
                    self.set_usage_metadata(p_int, c_int, t_int)
            except (ValueError, TypeError):
                pass

    def abort(self) -> None:
        """Flags the throttler as aborted, stopping any subsequent updates."""
        self.is_aborted = True

    def set_fallback_notice(self, notice: str) -> None:
        """Sets an informational footnote notice (e.g. model fallback notification)."""
        self.fallback_notice = notice

    async def handle_chunk(self, chunk: str) -> None:
        """Appends a new streaming text chunk and checks throttle/split conditions."""
        if self.is_aborted:
            return
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

    async def _update_telegram_message(
        self,
        is_final: bool = False,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
    ) -> None:
        """Edits active Telegram message with buffered text in chosen format."""
        chunk_content = self.current_chunk_text.strip()
        if not chunk_content and not self.header_text:
            return

        prefix = self.header_text if not self.completed_messages else ""
        raw_text = f"{prefix}{chunk_content}" if chunk_content else prefix.strip()

        target_markup = (
            reply_markup
            if reply_markup is not None
            else (self.quick_actions_keyboard if is_final else self.stop_keyboard)
        )

        if self.message_format == "rich":
            await self._update_rich_message(raw_text, is_final=is_final, reply_markup=target_markup)
        else:
            await self._update_legacy_message(raw_text, is_final=is_final, reply_markup=target_markup)

    async def _update_rich_message(
        self,
        raw_text: str,
        is_final: bool,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
    ) -> None:
        """Renders and edits message using tg-rich-converter Rich Messages (10.1+)."""
        streaming_mode = not is_final
        rich_html = to_rich(
            raw_text,
            thinking_summary=self.thinking_summary,
            streaming=streaming_mode,
        )

        # Ensure line breaks inside <blockquote> are rendered as distinct lines (<br/>)
        if "<blockquote" in rich_html:
            def fix_quote_newlines(match: re.Match) -> str:
                tag = match.group(1)
                body = match.group(2)
                return f"{tag}{body.replace(chr(10), '<br/>')}</blockquote>"

            rich_html = re.sub(r"(<blockquote[^>]*>)(.*?)</blockquote>", fix_quote_newlines, rich_html, flags=re.DOTALL)

        # If expandable spoiler mode is chosen, wrap the header blockquote into a collapsible <details> block
        if not self.completed_messages and self.header_style == "expandable":
            summary = self.header_summary or "💬 Инфо о диалоге"
            end_quote = rich_html.find("</blockquote>")
            if end_quote != -1 and rich_html.startswith("<blockquote>"):
                quote_block = rich_html[: end_quote + len("</blockquote>")].strip()
                rest = rich_html[end_quote + len("</blockquote>") :].strip()
                rich_html = f"<details><summary>{summary}</summary>{quote_block}</details>\n{rest}"

        if not rich_html or (streaming_mode and rich_html == self._last_rendered_html):
            return

        edit_kwargs: dict = {
            "chat_id": self.chat_id,
            "message_id": self.current_message.message_id,
            "rich_message": InputRichMessage(html=rich_html),
        }
        if reply_markup is not None or self.stop_keyboard is not None or self.quick_actions_keyboard is not None:
            edit_kwargs["reply_markup"] = reply_markup

        max_attempts = 4 if is_final else 1
        for attempt in range(1, max_attempts + 1):
            try:
                await self.bot.edit_message_text(**edit_kwargs)
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
                    fallback_kwargs: dict = {
                        "chat_id": self.chat_id,
                        "message_id": self.current_message.message_id,
                        "text": raw_text,
                        "parse_mode": None,
                    }
                    if reply_markup is not None or self.stop_keyboard is not None or self.quick_actions_keyboard is not None:
                        fallback_kwargs["reply_markup"] = reply_markup
                    try:
                        await self.bot.edit_message_text(**fallback_kwargs)
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
            send_kwargs: dict = {
                "chat_id": self.chat_id,
                "text": raw_text,
                "parse_mode": None,
            }
            if reply_markup is not None or self.stop_keyboard is not None or self.quick_actions_keyboard is not None:
                send_kwargs["reply_markup"] = reply_markup
            try:
                self.current_message = await self.bot.send_message(**send_kwargs)
            except Exception as send_err:
                logger.error(f"Final fallback send_message also failed: {send_err}")

    async def _update_legacy_message(
        self,
        raw_text: str,
        is_final: bool,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
    ) -> None:
        """Edits message using classic MarkdownV2 / plain text."""
        display_text = raw_text if is_final else f"{raw_text} ▌"
        formatted_text, parse_mode = format_markdown_safe(display_text)

        if not self.completed_messages and self.header_style == "expandable" and parse_mode == "MarkdownV2":
            if formatted_text.startswith(">"):
                lines = formatted_text.split("\n")
                quote_lines = []
                other_lines = []
                in_quote = True
                for line in lines:
                    if in_quote and (line.startswith(">") or (not line.strip() and quote_lines)):
                        if line.startswith(">"):
                            quote_lines.append(line)
                    else:
                        in_quote = False
                        other_lines.append(line)
                if quote_lines:
                    clean_lines = [q.lstrip(">").strip() for q in quote_lines]
                    joined_quote = "\n".join(clean_lines)
                    rest = "\n".join(other_lines)
                    formatted_text = f"||{joined_quote}||\n\n{rest}" if rest else f"||{joined_quote}||"

        edit_kwargs: dict = {
            "chat_id": self.chat_id,
            "message_id": self.current_message.message_id,
            "text": formatted_text,
            "parse_mode": parse_mode,
        }
        if reply_markup is not None or self.stop_keyboard is not None or self.quick_actions_keyboard is not None:
            edit_kwargs["reply_markup"] = reply_markup

        max_attempts = 4 if is_final else 1
        for attempt in range(1, max_attempts + 1):
            try:
                await self.bot.edit_message_text(**edit_kwargs)
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
                    fallback_kwargs: dict = {
                        "chat_id": self.chat_id,
                        "message_id": self.current_message.message_id,
                        "text": display_text,
                        "parse_mode": None,
                    }
                    if reply_markup is not None or self.stop_keyboard is not None or self.quick_actions_keyboard is not None:
                        fallback_kwargs["reply_markup"] = reply_markup
                    try:
                        await self.bot.edit_message_text(**fallback_kwargs)
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
            send_kwargs: dict = {
                "chat_id": self.chat_id,
                "text": display_text,
                "parse_mode": None,
            }
            if reply_markup is not None or self.stop_keyboard is not None or self.quick_actions_keyboard is not None:
                send_kwargs["reply_markup"] = reply_markup
            try:
                self.current_message = await self.bot.send_message(**send_kwargs)
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

        # Finalize current message (remove stop_keyboard)
        self.current_chunk_text = to_finalize
        await self._update_telegram_message(is_final=True, reply_markup=None)
        self.completed_messages.append(self.current_message)

        # Start new message for remaining portion
        self.current_chunk_text = remaining
        self._last_rendered_html = ""

        split_markup = self.stop_keyboard
        if self.message_format == "rich":
            initial_html = to_rich(
                remaining if remaining else "...",
                thinking_summary=self.thinking_summary,
                streaming=True,
            )
            send_kwargs: dict = {
                "chat_id": self.chat_id,
                "rich_message": InputRichMessage(html=initial_html),
            }
            if split_markup is not None:
                send_kwargs["reply_markup"] = split_markup
            try:
                self.current_message = await self.bot.send_rich_message(**send_kwargs)
            except Exception as e:
                logger.warning(f"Failed to send_rich_message on split, fallback to send_message: {e}")
                fallback_kwargs: dict = {
                    "chat_id": self.chat_id,
                    "text": remaining if remaining else "...",
                    "parse_mode": "HTML",
                }
                if split_markup is not None:
                    fallback_kwargs["reply_markup"] = split_markup
                self.current_message = await self.bot.send_message(**fallback_kwargs)
        else:
            new_text, parse_mode = format_markdown_safe(
                remaining + " ▌" if remaining else "..."
            )
            send_kwargs = {
                "chat_id": self.chat_id,
                "text": new_text,
                "parse_mode": parse_mode,
            }
            if split_markup is not None:
                send_kwargs["reply_markup"] = split_markup
            try:
                self.current_message = await self.bot.send_message(**send_kwargs)
            except Exception as e:
                logger.error(f"Error sending next legacy chunk message: {e}")

        self.last_update_time = time.monotonic()

    async def finalize(
        self, quick_actions_keyboard: Optional[InlineKeyboardMarkup] = None
    ) -> str:
        """
        Finalizes streaming: renders final message frame (streaming=False)
        without balancer or typing cursors, attaches quick actions keyboard (if provided),
        and returns complete raw markdown for history.
        """
        self.elapsed_time = time.monotonic() - self.start_time

        hud_parts = []
        if isinstance(self.elapsed_time, (int, float)):
            hud_parts.append(f"⚡ {self.elapsed_time:.1f}s")
        if isinstance(self.total_tokens, int) and self.total_tokens > 0:
            hud_parts.append(f"📊 {self.total_tokens} токенов")

        if hud_parts:
            hud_line = " • ".join(hud_parts)
            if self.header_text and not self.completed_messages:
                hdr = self.header_text.rstrip("\r\n")
                if any(line.strip().startswith(">") for line in hdr.splitlines()):
                    self.header_text = f"{hdr}\n> {hud_line}\n\n"
                else:
                    self.header_text = f"{hdr}\n{hud_line}\n\n"
            else:
                if self.current_chunk_text.strip():
                    self.current_chunk_text += f"\n\n> {hud_line}"
                else:
                    self.current_chunk_text = f"> {hud_line}"

        if self.fallback_notice:
            notice = self.fallback_notice.strip()
            if self.current_chunk_text.strip():
                self.current_chunk_text += f"\n\n{notice}"
            else:
                self.current_chunk_text = notice

        final_markup = (
            quick_actions_keyboard
            if quick_actions_keyboard is not None
            else self.quick_actions_keyboard
        )
        await self._update_telegram_message(is_final=True, reply_markup=final_markup)
        self.completed_messages.append(self.current_message)
        return self.full_response_text

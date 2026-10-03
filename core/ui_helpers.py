# File: core/ui_helpers.py

# Copyright (C) 2025-2026 kobaltgit
# AGPLv3 License

import logging
from typing import Union, Any
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup

from core.logger import get_logger

logger = get_logger("user_messages")


async def safe_edit_message_text(
    message: Message,
    text: str | None = None,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = "HTML",
    disable_web_page_preview: bool = True,
    rich_message: Any | None = None,
) -> Union[Message, bool]:
    """
    Safely edits message text or rich_message, gracefully ignoring 'message is not modified',
    handling rich message fallback to plain text, and catching cases where message was deleted.
    """
    try:
        if rich_message is not None:
            return await message.edit_text(
                text=text,
                reply_markup=reply_markup,
                disable_web_page_preview=disable_web_page_preview,
                rich_message=rich_message,
            )
        return await message.edit_text(
            text=text or "",
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
        )
    except TelegramBadRequest as e:
        err_msg = str(e).lower()
        if "message is not modified" in err_msg:
            # User clicked a button that produced the same text/markup - not an error
            logger.info(f"Message {message.message_id} text not modified (identical content)")
            return True
        if "message to edit not found" in err_msg or "message can't be edited" in err_msg:
            logger.warning(f"Could not edit message {message.message_id}: {e}")
            return False
        if "can't parse entities" in err_msg or "tag" in err_msg or "rich" in err_msg:
            logger.warning(f"Entity parse error in safe_edit_message_text, falling back to plain text: {e}")
            try:
                fallback_text = text or ""
                if not fallback_text and rich_message is not None:
                    if hasattr(rich_message, "html") and rich_message.html:
                        fallback_text = rich_message.html
                    elif isinstance(rich_message, dict) and "html" in rich_message:
                        fallback_text = rich_message["html"]
                return await message.edit_text(
                    text=fallback_text,
                    reply_markup=reply_markup,
                    parse_mode=None,
                    disable_web_page_preview=disable_web_page_preview,
                )
            except Exception:
                pass
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in safe_edit_message_text: {e}")
        return False


async def safe_answer_callback(callback: CallbackQuery, text: str | None = None, show_alert: bool = False):
    """
    Safely answers callback query, catching timeout or query expired errors.
    """
    try:
        await callback.answer(text=text, show_alert=show_alert)
    except TelegramBadRequest as e:
        if "query is too old" in str(e).lower():
            pass
        else:
            logger.warning(f"Error answering callback query: {e}")
    except Exception as e:
        logger.warning(f"Unexpected error answering callback query: {e}")

# File: core/ui_helpers.py

# Copyright (C) 2025-2026 kobaltgit
# AGPLv3 License

import logging
from typing import Union
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


async def safe_edit_message_text(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = "Markdown",
    disable_web_page_preview: bool = True
) -> Union[Message, bool]:
    """
    Safely edits message text, gracefully ignoring 'message is not modified'
    and catching cases where message was deleted or cannot be edited.
    """
    try:
        return await message.edit_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview
        )
    except TelegramBadRequest as e:
        err_msg = str(e).lower()
        if "message is not modified" in err_msg:
            # User clicked a button that produced the same text/markup - not an error
            return True
        if "message to edit not found" in err_msg or "message can't be edited" in err_msg:
            logger.warning(f"Could not edit message {message.message_id}: {e}")
            return False
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

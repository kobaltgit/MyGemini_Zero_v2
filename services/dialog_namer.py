"""
Dialog Auto-naming Service for MyGemini Zero v2.
Generates concise, human-readable 2-4 word dialog titles based on the user's initial message.
"""

import re
from typing import Optional
from google import genai
from google.genai import types
from core.config import settings
from core.logger import get_logger

logger = get_logger("gemini_api")


def fallback_title_from_text(text: str, max_length: int = 35) -> str:
    """Creates a clean fallback dialog title directly from raw message text."""
    clean = re.sub(r"[#*_`~\[\]()<>\"'\n\r]+", " ", text).strip()
    # Remove multiple spaces
    clean = re.sub(r"\s+", " ", clean)
    if not clean:
        return "Новый диалог"

    words = clean.split()
    title = ""
    for w in words:
        if len(title) + len(w) + 1 <= max_length:
            title = f"{title} {w}".strip()
        else:
            break

    if not title:
        title = clean[:max_length]

    # Capitalize first letter
    return title[:1].upper() + title[1:] if title else "Новый диалог"


async def generate_dialog_title(first_message: str, api_key: Optional[str] = None) -> str:
    """
    Generates a 2-4 word title for a dialog using Gemini or fallback text parser.
    """
    if not first_message or not first_message.strip():
        return "Новый диалог"

    key = api_key or settings.DEFAULT_GEMINI_KEY
    if not key:
        return fallback_title_from_text(first_message)

    try:
        client = genai.Client(api_key=key)
        prompt = (
            "Сгенерируй короткое, ёмкое название темы диалога (2-4 слова, до 30 символов) "
            "на русском языке на основе первого сообщения пользователя.\n"
            "Правила:\n"
            "- Ответь ТОЛЬКО названием темы, без кавычек, без точки в конце, без эмодзи.\n"
            "- Заголовок должен отражать суть темы (например: «Парсинг JSON в Python», «Анализ отчёта», «План поездки»).\n\n"
            f"Сообщение пользователя:\n{first_message[:500]}"
        )

        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=30,
            ),
        )

        if response and response.text:
            title = response.text.strip().strip("\"'«».,")
            title = re.sub(r"[\n\r]+", " ", title).strip()
            if 3 <= len(title) <= 45:
                return title

    except Exception as e:
        logger.warning(f"Failed to auto-generate dialog title via Gemini: {e}")

    return fallback_title_from_text(first_message)

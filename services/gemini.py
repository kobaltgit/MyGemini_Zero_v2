"""
Google Gemini Official Modern SDK Service for MyGemini Zero v2.
Handles client lifecycle, model listing with search badges, streaming inference,
token counting, 429 quota fallback, and tool error recovery.
"""

import asyncio
from typing import AsyncGenerator, List, Dict, Any, Optional
from google import genai
from google.genai import types
from google.genai.errors import APIError

from core.config import settings, MODELS_METADATA
from core.logger import get_logger

logger = get_logger("gemini_api")

# Dynamic cache for models that fail search tool calls
KNOWN_NO_SEARCH_MODELS: set = set()


def model_supports_search(model_name: str) -> bool:
    """
    Determines if a model supports Google Search tool grounding.
    - Excludes Gemma models (open-weights, no function/tool calling).
    - Excludes specialized non-text or utility models (tts, image, transcribe, embedding, aqa, veo).
    - Checks static metadata in MODELS_METADATA.
    - Defaults to True for all Gemini 2.x and 2.5 Flash / Pro models.
    """
    if not model_name:
        return False
    clean_name = model_name.lower().replace("models/", "").strip()
    if clean_name in KNOWN_NO_SEARCH_MODELS:
        return False

    if clean_name.startswith("gemma"):
        return False

    no_search_patterns = [
        "-image", "-tts", "-transcribe", "embedding", "aqa", "veo", "lyria",
        "computer-use", "robotics"
    ]
    if any(p in clean_name for p in no_search_patterns):
        return False

    if clean_name in MODELS_METADATA:
        return MODELS_METADATA[clean_name].get("supports_search", True)

    return clean_name.startswith("gemini-")


class GeminiAPIException(Exception):
    """Base exception for Gemini API errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


class GeminiQuotaExceededException(GeminiAPIException):
    """Raised when Google API returns HTTP 429 / RESOURCE_EXHAUSTED."""
    pass


class GeminiService:
    """Service wrapping modern google-genai SDK for Telegram bot."""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("API key must not be empty.")
        self.api_key = api_key
        self.client = genai.Client(api_key=api_key)

    async def get_available_models(self) -> List[Dict[str, Any]]:
        """
        Queries official Gemini API for available models.
        Filters for chat/content-generation models and badges models supporting Google Search.
        """
        try:
            # Sync SDK call offloaded to thread
            def _fetch_models():
                models_list = list(self.client.models.list())
                return models_list

            raw_models = await asyncio.to_thread(_fetch_models)
            parsed_models = []

            for m in raw_models:
                name = m.name or ""
                clean_id = name.replace("models/", "")
                display_name = m.display_name or clean_id

                # Only include models supporting content generation
                supported_actions = getattr(m, "supported_generation_methods", []) or []
                if supported_actions and "generateContent" not in supported_actions:
                    continue

                # Skip non-conversational models
                if any(x in clean_id for x in ["embedding", "aqa", "imagen", "veo"]):
                    continue

                supports_search = model_supports_search(clean_id)
                badge = " 🌐" if supports_search else ""

                parsed_models.append({
                    "id": clean_id,
                    "name": name,
                    "display_name": f"{display_name}{badge}",
                    "supports_search": supports_search,
                    "description": m.description or "",
                })

            # Sort models: gemini-2.5 and gemini-2.0 first
            parsed_models.sort(
                key=lambda x: (
                    not x["id"].startswith("gemini-2.5"),
                    not x["id"].startswith("gemini-2.0"),
                    x["id"],
                )
            )
            return parsed_models

        except Exception as e:
            logger.error(f"Error listing Gemini models: {e}")
            # Return standard fallback list from metadata if API list fails
            fallback = []
            for mid, meta in MODELS_METADATA.items():
                supports_search = meta.get("supports_search", False)
                badge = " 🌐" if supports_search else ""
                fallback.append({
                    "id": mid,
                    "name": f"models/{mid}",
                    "display_name": f"{mid}{badge}",
                    "supports_search": supports_search,
                    "description": "",
                })
            return fallback

    async def generate_stream(
        self,
        model_id: str,
        contents: List[Any],
        system_instruction: Optional[str] = None,
        enable_search: bool = True,
        temperature: float = 0.8,
        max_output_tokens: int = 24576,
    ) -> AsyncGenerator[str, None]:
        """
        Asynchronous streaming generation with automatic Google Search tool grounding,
        tool unsupported fallback, and 429 quota handling.
        """
        use_search = enable_search and model_supports_search(model_id)
        tools = [types.Tool(google_search=types.GoogleSearch())] if use_search else None

        config = types.GenerateContentConfig(
            temperature=temperature,
            top_p=1.0,
            max_output_tokens=max_output_tokens,
            system_instruction=system_instruction,
            tools=tools,
        )

        try:
            stream = await self.client.aio.models.generate_content_stream(
                model=model_id,
                contents=contents,
                config=config,
            )
            async for chunk in stream:
                if chunk.text:
                    yield chunk.text

        except APIError as e:
            err_msg = str(e)
            logger.warning(f"Gemini APIError ({e.code}): {err_msg}")

            # 1. Quota 429 handling
            if e.code == 429 or "RESOURCE_EXHAUSTED" in err_msg:
                # Try fallback to gemini-2.5-flash-lite if not already on it
                if model_id != "gemini-2.5-flash-lite":
                    logger.warning(f"Quota exceeded on {model_id}. Attempting fallback to gemini-2.5-flash-lite...")
                    fallback_config = types.GenerateContentConfig(
                        temperature=temperature,
                        max_output_tokens=max_output_tokens,
                        system_instruction=system_instruction,
                    )
                    stream = await self.client.aio.models.generate_content_stream(
                        model="gemini-2.5-flash-lite",
                        contents=contents,
                        config=fallback_config,
                    )
                    async for chunk in stream:
                        if chunk.text:
                            yield chunk.text
                    return
                else:
                    raise GeminiQuotaExceededException("Превышена квота запросов (429). Попробуйте позже.")

            # 2. Tool unsupported error handling
            if "tool" in err_msg.lower() and ("not supported" in err_msg.lower() or "invalid" in err_msg.lower()):
                clean_id = model_id.lower().replace("models/", "")
                KNOWN_NO_SEARCH_MODELS.add(clean_id)
                logger.warning(f"Search tool not supported on {model_id}. Retrying without tools...")

                retry_config = types.GenerateContentConfig(
                    temperature=temperature,
                    top_p=1.0,
                    max_output_tokens=max_output_tokens,
                    system_instruction=system_instruction,
                    tools=None,
                )
                stream = await self.client.aio.models.generate_content_stream(
                    model=model_id,
                    contents=contents,
                    config=retry_config,
                )
                async for chunk in stream:
                    if chunk.text:
                        yield chunk.text
                return

            raise GeminiAPIException(f"Gemini API Error: {err_msg}", status_code=e.code)

        except Exception as e:
            logger.exception(f"Unexpected error during streaming: {e}")
            raise GeminiAPIException(f"Ошибка генерации: {str(e)}")

    async def count_tokens(self, model_id: str, contents: List[Any]) -> int:
        """Counts input tokens for contents using model."""
        try:
            resp = await self.client.aio.models.count_tokens(
                model=model_id,
                contents=contents,
            )
            return resp.total_tokens or 0
        except Exception as e:
            logger.error(f"Error counting tokens: {e}")
            # Fallback approximation: 1 token ~= 4 characters
            total_chars = sum(len(str(c)) for c in contents)
            return max(1, total_chars // 4)

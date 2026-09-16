"""
Configuration module for MyGemini Zero v2.
Utilizes pydantic-settings for robust environment variable loading and validation,
retaining full backward compatibility with v1 settings, pricing, models, and subscription plans.
"""

import os
from pathlib import Path
from typing import Dict, Any, List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base project directory paths
BASE_DIR: Path = Path(__file__).resolve().parent.parent
LOGS_DIR: Path = BASE_DIR / "logs"
DATABASE_DIR: Path = BASE_DIR / "database"
STATIC_DIR: Path = BASE_DIR / "webapp"


class Settings(BaseSettings):
    """Core application settings loaded from environment variables (.env)."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # --- Telegram Bot Settings ---
    BOT_TOKEN: str = Field(default="", description="Telegram Bot API Token from @BotFather")
    PAYMENT_PROVIDER_TOKEN: str = Field(default="", description="Payment token for Telegram Payments")
    ADMIN_USER_ID: int = Field(default=0, description="Telegram User ID of the primary administrator")
    DONATION_URL: str = Field(default="", description="Link for donations / tips")

    # --- Gemini API Defaults ---
    DEFAULT_MODEL_ID: str = Field(default="gemini-2.5-flash", description="Default Gemini model ID")

    # --- Zero-Knowledge Security Settings ---
    PBKDF2_ITERATIONS: int = Field(default=480000, description="Strictly 480,000 iterations for v1 DB compatibility")
    SESSION_TIMEOUT_SECONDS: int = Field(default=3600, description="Inactivity timeout before vault lock (1 hour)")
    DEFAULT_ARCHIVE_DAYS: int = Field(default=30, description="Days after which chat messages are summarized")

    # --- Database & Storage ---
    DATABASE_URL: str = Field(
        default=f"sqlite+aiosqlite:///{DATABASE_DIR / 'bot_database.db'}",
        description="Async SQLAlchemy database connection string"
    )
    VECTOR_STORE_PATH: str = Field(default=str(BASE_DIR / "vector_store"), description="Path to ChromaDB storage")
    WEBAPP_URL: str = Field(default="", description="URL for Telegram WebApp modal popup")

    # --- Streaming & Message Safety Limits ---
    CHUNK_SIZE: int = Field(default=3200, description="Character threshold to split AI responses safely")
    MAX_FORMATTED_CHUNK_SIZE: int = Field(default=4000, description="Max character length after Markdown escaping")
    MESSAGE_BUFFER_TIMEOUT: float = Field(default=1.5, description="Seconds to buffer rapid user messages")


# Global settings singleton
settings = Settings()

# --- Generation Parameters ---
GENERATION_CONFIG: Dict[str, Any] = {
    "temperature": 0.8,
    "top_p": 1.0,
    "max_output_tokens": 24576,
}

# --- Known Models Metadata (Search & System Instruction support) ---
MODELS_METADATA: Dict[str, Dict[str, bool]] = {
    # Gemini 2.5 series
    "gemini-2.5-flash": {"supports_search": True, "supports_system_instruction": True},
    "gemini-2.5-pro": {"supports_search": True, "supports_system_instruction": True},
    "gemini-2.5-flash-preview-05-20": {"supports_search": False, "supports_system_instruction": True},
    "gemini-2.5-flash-lite-preview-06-17": {"supports_search": False, "supports_system_instruction": True},
    "gemini-2.5-flash-lite-preview-05-20": {"supports_search": False, "supports_system_instruction": True},
    "gemini-2.5-flash-preview-tts": {"supports_search": False, "supports_system_instruction": True},
    "gemini-2.5-pro-preview": {"supports_search": False, "supports_system_instruction": True},
    "gemini-2.5-pro-preview-05-06": {"supports_search": False, "supports_system_instruction": True},
    "gemini-2.5-pro-preview-03-25": {"supports_search": False, "supports_system_instruction": True},
    "gemini-2.5-pro-preview-tts": {"supports_search": False, "supports_system_instruction": True},

    # Gemini 2.0 series
    "gemini-2.0-flash": {"supports_search": True, "supports_system_instruction": True},
    "gemini-2.0-flash-001": {"supports_search": False, "supports_system_instruction": True},
    "gemini-2.0-flash-experimental": {"supports_search": False, "supports_system_instruction": True},
    "gemini-2.0-flash-lite": {"supports_search": False, "supports_system_instruction": True},
    "gemini-2.0-flash-lite-001": {"supports_search": False, "supports_system_instruction": True},
    "gemini-2.0-flash-lite-preview": {"supports_search": False, "supports_system_instruction": True},
    "gemini-2.0-flash-lite-preview-02-05": {"supports_search": False, "supports_system_instruction": True},
    "gemini-2.0-pro-experimental": {"supports_search": True, "supports_system_instruction": True},
    "gemini-2.0-pro-experimental-02-05": {"supports_search": True, "supports_system_instruction": True},

    # Gemini 1.5 series
    "gemini-1.5-flash": {"supports_search": False, "supports_system_instruction": True},
    "gemini-1.5-flash-002": {"supports_search": False, "supports_system_instruction": True},
    "gemini-1.5-flash-8b": {"supports_search": False, "supports_system_instruction": True},
    "gemini-1.5-flash-8b-001": {"supports_search": False, "supports_system_instruction": True},
    "gemini-1.5-flash-8b-latest": {"supports_search": False, "supports_system_instruction": True},
    "gemini-1.5-flash-latest": {"supports_search": False, "supports_system_instruction": True},
    "gemini-1.5-pro": {"supports_search": False, "supports_system_instruction": True},
    "gemini-1.5-pro-002": {"supports_search": False, "supports_system_instruction": True},
    "gemini-1.5-pro-latest": {"supports_search": False, "supports_system_instruction": True},
    "gemini-1.0-pro-vision": {"supports_search": False, "supports_system_instruction": True},

    # Gemma models
    "gemma-3-12b-it": {"supports_search": False, "supports_system_instruction": False},
    "gemma-3-1b-it": {"supports_search": False, "supports_system_instruction": False},
    "gemma-3-27b-it": {"supports_search": False, "supports_system_instruction": False},
    "gemma-3-4b-it": {"supports_search": False, "supports_system_instruction": False},
    "gemma-3n-e2b-it": {"supports_search": False, "supports_system_instruction": False},
    "gemma-3n-e4b-it": {"supports_search": False, "supports_system_instruction": False},
    "gemma-2b-it": {"supports_search": False, "supports_system_instruction": False},
    "gemma-7b-it": {"supports_search": False, "supports_system_instruction": False},
}

# --- Safety Thresholds ---
SAFETY_SETTINGS: List[Dict[str, str]] = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
]

# --- Token Cost Tracking (USD per 1M tokens) ---
TOKEN_PRICING: Dict[str, Dict[str, float]] = {
    "default": {
        "input_usd_per_million": 0.35,
        "output_usd_per_million": 1.05,
    },
    "gemini-1.5-pro-latest": {
        "input_usd_per_million": 3.50,
        "output_usd_per_million": 10.50,
    },
    "gemini-2.5-pro": {
        "input_usd_per_million": 3.50,
        "output_usd_per_million": 10.50,
    },
}

# --- Bot Communication Styles ---
BOT_STYLES: Dict[str, str] = {
    "default": "🤖 По умолчанию / Default",
    "formal": "💼 Официальный / Formal",
    "informal": "☕️ Неформальный / Informal",
    "concise": "⚡️ Краткий / Concise",
    "detailed": "🔍 Подробный / Detailed",
}

# --- Bot Personas ---
BOT_PERSONAS: Dict[str, Dict[str, str]] = {
    "default": {
        "name_ru": "🤖 Обычный ассистент",
        "name_en": "🤖 Default Assistant",
        "prompt_ru": "",
        "prompt_en": "",
    },
    "python_expert": {
        "name_ru": "🐍 Эксперт по Python",
        "name_en": "🐍 Python Expert",
        "prompt_ru": (
            "Ты — ведущий разработчик на Python с многолетним опытом. "
            "Твои ответы должны быть точными, ясными и подкреплены лучшими практиками. "
            "Всегда предоставляй работающие примеры кода, если это уместно. Будь вежлив и профессионален. "
            "ВАЖНО: Никогда не упоминай свою роль или имя в ответе. Отвечай напрямую на запрос пользователя. "
            "Никогда не изменяй и не анонимизируй фрагменты кода, имена переменных или технические термины, воспроизводи их в точности."
        ),
        "prompt_en": (
            "You are a lead Python developer with years of experience. Your answers must be accurate, clear, and backed by best practices. "
            "Always provide working code examples where appropriate. Be polite and professional. "
            "IMPORTANT: Never mention your role or name in the response. Respond directly to the user's query. "
            "Never alter or anonymize code snippets, variable names, or technical terms; reproduce them exactly."
        ),
    },
    "financial_advisor": {
        "name_ru": "💰 Финансовый советник",
        "name_en": "💰 Financial Advisor",
        "prompt_ru": (
            "Ты — независимый финансовый консультант. Твоя задача — предоставлять взвешенную и объективную информацию "
            "о личных финансах, принципах бюджетирования, видах инвестиций и управлении рисками. "
            "Всегда подчеркивай, что твои советы не являются прямой финансовой рекомендацией и требуют консультации с лицензированным специалистом. "
            "Стиль — ясный, структурированный, без лишней 'воды'. "
            "ВАЖНО: Никогда не упоминай свою роль или имя в ответе. Отвечай напрямую на запрос пользователя."
        ),
        "prompt_en": (
            "You are an independent financial consultant. Your task is to provide balanced and objective information "
            "about personal finance, budgeting principles, types of investments, and risk management. "
            "Always emphasize that your advice is not a direct financial recommendation and requires consultation with a licensed professional. "
            "Your style should be clear, structured, and concise. "
            "IMPORTANT: Never mention your role or name in the response. Respond directly to the user's query."
        ),
    },
    "copywriter": {
        "name_ru": "✍️ Копирайтер",
        "name_en": "✍️ Copywriter",
        "prompt_ru": (
            "Ты — профессиональный копирайтер, специализирующийся на создании яркого и убедительного контента. "
            "Твоя задача — генерировать креативные идеи, цепляющие заголовки и тексты, которые привлекают внимание аудитории. "
            "Стиль должен быть энергичным и вдохновляющим. "
            "ВАЖНО: Никогда не упоминай свою роль или имя в ответе. Отвечай напрямую на запрос пользователя."
        ),
        "prompt_en": (
            "You are a professional copywriter specializing in creating vibrant and persuasive content. "
            "Your task is to generate creative ideas, catchy headlines, and texts that capture the audience's attention. "
            "Your style should be energetic and inspiring. "
            "IMPORTANT: Never mention your role or name in the response. Respond directly to the user's query."
        ),
    },
    "academic_tutor": {
        "name_ru": "🎓 Академический наставник",
        "name_en": "🎓 Academic Tutor",
        "prompt_ru": (
            "Ты — опытный академический наставник и редактор. Твоя цель — помогать пользователям структурировать их мысли, "
            "улучшать аргументацию и писать ясные, хорошо организованные тексты (эссе, статьи, доклады). "
            "Объясняй сложные темы доступно и поощряй критическое мышление. "
            "ВАЖНО: Никогда не упоминай свою роль или имя в ответе. Отвечай напрямую на запрос пользователя."
        ),
        "prompt_en": (
            "You are an experienced academic tutor and editor. Your goal is to help users structure their thoughts, "
            "improve their arguments, and write clear, well-organized texts (essays, articles, reports). "
            "Explain complex topics in an accessible way and encourage critical thinking. "
            "IMPORTANT: Never mention your role or name in the response. Respond directly to the user's query."
        ),
    },
    "jungian_psychologist": {
        "name_ru": "🧠 Психолог (Юнг)",
        "name_en": "🧠 Psychologist (Jungian)",
        "prompt_ru": (
            "Ты — чат-бот, эмулирующий психолога, который использует принципы аналитической психологии Карла Густава Юнга. "
            "Твоя роль — помогать пользователю исследовать свой внутренний мир через анализ символов, архетипов и образов. "
            "Поощряй саморефлексию, задавай открытые вопросы. Всегда напоминай пользователю, что ты являешься искусственным интеллектом, "
            "а не реальным психотерапевтом, и твои сессии не заменяют профессиональную психологическую помощь. "
            "ВАЖНО: Никогда не упоминай свою роль или имя в ответе. Отвечай напрямую на запрос пользователя."
        ),
        "prompt_en": (
            "You are a chatbot emulating a psychologist who uses the principles of Carl Gustav Jung's analytical psychology. "
            "Your role is to help the user explore their inner world through the analysis of symbols, archetypes, and images. "
            "Encourage self-reflection and ask open-ended questions. Always remind the user that you are an artificial intelligence, "
            "not a real psychotherapist, and your sessions do not replace professional psychological help. "
            "IMPORTANT: Never mention your role or name in the response. Respond directly to the user's query."
        ),
    },
    "historian": {
        "name_ru": "📜 Историк",
        "name_en": "📜 Historian",
        "prompt_ru": (
            "Ты — эрудированный историк, способный увлекательно и точно рассказывать о любых исторических периодах. "
            "Твои ответы должны быть основаны на проверенных источниках. Старайся не только перечислять факты, "
            "но и объяснять причинно-следственные связи, контекст эпохи и значение событий. Будь объективен и беспристрастен. "
            "ВАЖНО: Никогда не упоминай свою роль или имя в ответе. Отвечай напрямую на запрос пользователя."
        ),
        "prompt_en": (
            "You are an erudite historian capable of engagingly and accurately narrating any historical period. "
            "Your answers should be based on verified sources. Strive not only to list facts but also to explain cause-and-effect relationships, "
            "the context of the era, and the significance of events. Be objective and impartial. "
            "IMPORTANT: Never mention your role or name in the response. Respond directly to the user's query."
        ),
    },
    "chef": {
        "name_ru": "👨‍🍳 Шеф-повар",
        "name_en": "👨‍🍳 Chef",
        "prompt_ru": (
            "Ты — опытный и креативный шеф-повар. Твоя страсть — помогать людям готовить вкусную и интересную еду. "
            "Давай пошаговые, понятные рецепты. Если пользователь перечисляет ингредиенты, предложи несколько вариантов блюд, "
            "которые можно из них приготовить. Делись кулинарными лайфхаками и секретами. "
            "ВАЖНО: Никогда не упоминай свою роль или имя в ответе. Отвечай напрямую на запрос пользователя."
        ),
        "prompt_en": (
            "You are an experienced and creative chef. Your passion is helping people cook delicious and interesting food. "
            "Provide step-by-step, easy-to-understand recipes. If a user lists ingredients, suggest several dish options that can be made from them. "
            "Share culinary life hacks and secrets. IMPORTANT: Never mention your role or name in the response. Respond directly to the user's query."
        ),
    },
    "travel_planner": {
        "name_ru": "✈️ Планировщик путешествий",
        "name_en": "✈️ Travel Planner",
        "prompt_ru": (
            "Ты — опытный планировщик путешествий. Твоя задача — помочь пользователю составить идеальный маршрут. "
            "Предлагай не только популярные достопримечательности, но и скрытые жемчужины. "
            "Давай практические советы по логистике (транспорт, проживание, лучшее время для посещения) и помогай составить сбалансированный план. "
            "ВАЖНО: Никогда не упоминай свою роль или имя в ответе. Отвечай напрямую на запрос пользователя."
        ),
        "prompt_en": (
            "You are an experienced travel planner. Your task is to help the user create the perfect itinerary. "
            "Suggest not only popular attractions but also hidden gems. Provide practical advice on logistics "
            "(transport, accommodation, best time to visit) and help create a balanced plan for each day of the trip. "
            "IMPORTANT: Never mention your role or name in the response. Respond directly to the user's query."
        ),
    },
    "translator": {
        "name_ru": "💬 Лингвист-переводчик",
        "name_en": "💬 Linguist-Translator",
        "prompt_ru": (
            "Ты — эксперт-лингвист и профессиональный переводчик. При запросе на перевод предоставляй не только дословный, "
            "но и идиоматический, стилистически верный вариант. Если в тексте есть культурные или языковые нюансы, кратко объясняй их. "
            "Твоя цель — максимально точная и естественная передача смысла. "
            "ВАЖНО: Никогда не упоминай свою роль или имя в ответе. Отвечай напрямую на запрос пользователя."
        ),
        "prompt_en": (
            "You are an expert linguist and professional translator. When requested to translate, provide not only a literal "
            "but also an idiomatic, stylistically correct version. If the text contains cultural or linguistic nuances, briefly explain them. "
            "Your goal is the most accurate and natural transfer of meaning. "
            "IMPORTANT: Never mention your role or name in the response. Respond directly to the user's query."
        ),
    },
}

# --- Translation Target Languages ---
TRANSLATE_LANGUAGES: Dict[str, str] = {
    "ru": "🇷🇺 Русский",
    "en": "🇺🇸 Английский",
    "de": "🇩🇪 Немецкий",
    "fr": "🇫🇷 Французский",
    "es": "🇪🇸 Испанский",
    "it": "🇮🇹 Итальянский",
}

# --- Subscription Plans Configuration ---
SUBSCRIPTION_PLANS: List[Dict[str, Any]] = [
    {
        "id": "1_month_sub",
        "title": "MyGemini Zero - 1 месяц",
        "description": "Полный доступ ко всем функциям на 30 дней.",
        "price_amount": 50000,  # 500.00 RUB in kopecks
        "price_currency": "RUB",
        "duration_days": 30,
    }
]

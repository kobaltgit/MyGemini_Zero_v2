"""
Chat and Multimodal Generation Handler for MyGemini Zero v2.
Coordinates Zero-Knowledge decryption, RAG retrieval from ChromaDB,
multimodal processing (Images, Audio, PDF/DOCX), and safe streaming via MessageStreamThrottler.
"""

from typing import List, Any
from io import BytesIO
from aiogram import Router, F, Bot
from aiogram.types import Message
from google.genai import types

from core.database import async_session_maker
from database.repositories import UserRepository, DialogRepository, ConversationRepository
from services.gemini import GeminiService
from services.throttler import MessageStreamThrottler
from services.media import format_image_part, format_audio_part, parse_document_text
from services.vector_store import VectorStoreManager
from services.dialog_namer import generate_dialog_title
from middlewares.auth import session_manager
from keyboards.inline import (
    get_unlock_keyboard,
    get_api_key_input_keyboard,
    get_subscription_keyboard,
)
from core.config import settings, BOT_STYLES, BOT_PERSONAS, SUBSCRIPTION_PLANS
from core.logger import get_logger

logger = get_logger("user_messages")
router = Router(name="chat")


@router.message(F.text | F.photo | F.voice | F.document)
async def handle_user_message(message: Message, bot: Bot):
    """Primary handler for all incoming conversational and multimodal user messages."""
    user_id = message.from_user.id

    # 1. Zero-Knowledge session check
    fernet = session_manager.get_fernet(user_id)
    if not fernet:
        await message.answer(
            "🔒 <b>Хранилище заблокировано.</b>\n\n"
            "Для общения с AI и расшифровки истории введите ваш мастер-пароль:",
            reply_markup=get_unlock_keyboard(),
            parse_mode="HTML",
        )
        return

    # 2. Database checks: user, active dialog, API key, subscription
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        dialog_repo = DialogRepository(session)
        conv_repo = ConversationRepository(session)

        user = await user_repo.get_by_id(user_id)
        if not user:
            user, _ = await user_repo.add_or_update_user(
                user_id, message.from_user.username, message.from_user.first_name, message.from_user.last_name
            )

        # Check API key
        api_key = await user_repo.get_api_key(user_id, fernet)
        if not api_key:
            await message.answer(
                "🔑 <b>API-ключ Google Gemini не установлен.</b>\n\n"
                "Бот работает по модели BYOK (Bring Your Own Key). "
                "Пожалуйста, установите ваш персональный ключ Google AI Studio:",
                reply_markup=get_api_key_input_keyboard(),
                parse_mode="HTML",
            )
            return

        # Check subscription
        is_admin = user_id == settings.ADMIN_USER_ID
        if not is_admin and not user_repo.is_subscription_active(user):
            await message.answer(
                "💎 <b>Для доступа к боту требуется активная подписка.</b>\n\n"
                "Оформите подписку для безлимитного общения, RAG-памяти и анализа документов:",
                reply_markup=get_subscription_keyboard(SUBSCRIPTION_PLANS),
                parse_mode="HTML",
            )
            return

        # Active dialog check
        active_dialog_id = user.active_dialog_id
        if not active_dialog_id:
            dialog = await dialog_repo.create_dialog(user_id, "Основной диалог", set_active=True)
            active_dialog_id = dialog.dialog_id

    # 3. Handle document upload (RAG indexing)
    if message.document:
        doc = message.document
        status_msg = await message.answer("📥 <i>Загружаю и анализирую документ...</i>", parse_mode="HTML")
        file_io = BytesIO()
        await bot.download(doc.file_id, destination=file_io)
        file_bytes = file_io.getvalue()

        extracted_text, doc_type = parse_document_text(file_bytes, doc.file_name or "document.txt")
        vm = VectorStoreManager(api_key=api_key)
        chunks_count = await vm.add_document(
            dialog_id=active_dialog_id,
            text_content=extracted_text,
            filename=doc.file_name or "document",
            file_size=doc.file_size,
        )

        await status_msg.edit_text(
            f"📄 <b>Документ добавлен в память диалога!</b>\n\n"
            f"• <b>Файл:</b> <code>{doc.file_name}</code>\n"
            f"• <b>Фрагментов сохранено:</b> {chunks_count}\n"
            f"• <b>Тип:</b> {doc_type.upper()}\n\n"
            "Теперь вы можете задавать любые вопросы по содержимому этого файла.",
            parse_mode="HTML",
        )
        return

    # 4. Extract user prompt & multimodal attachments
    user_text = message.text or message.caption or ""
    multimodal_parts: List[Any] = []

    # Handle photo
    if message.photo:
        photo = message.photo[-1]
        photo_io = BytesIO()
        await bot.download(photo.file_id, destination=photo_io)
        multimodal_parts.append(format_image_part(photo_io.getvalue(), "image/jpeg"))

    # Handle voice
    if message.voice:
        voice = message.voice
        voice_io = BytesIO()
        await bot.download(voice.file_id, destination=voice_io)
        multimodal_parts.append(format_audio_part(voice_io.getvalue(), "audio/ogg"))
        if not user_text:
            user_text = "[Голосовое сообщение]"

    # 5. Semantic RAG Search for context & Auto-naming
    rag_context = ""
    vm = VectorStoreManager(api_key=api_key)
    if user_text and user_text != "[Голосовое сообщение]":
        rag_context = await vm.search_context(active_dialog_id, user_text)

        # Auto-name dialog if it still has default placeholder name
        try:
            async with async_session_maker() as session:
                dialog_repo = DialogRepository(session)
                active_d = await dialog_repo.get_by_id(active_dialog_id)
                if active_d and active_d.name in ("Новый диалог", "Основной диалог"):
                    new_title = await generate_dialog_title(user_text, api_key=api_key)
                    if new_title and new_title != active_d.name:
                        await dialog_repo.rename_dialog(active_dialog_id, new_title)
        except Exception as e:
            logger.warning(f"Error auto-naming dialog {active_dialog_id}: {e}")

    # 6. Load conversation history
    async with async_session_maker() as session:
        conv_repo = ConversationRepository(session)
        history_records = await conv_repo.get_dialog_messages(active_dialog_id, fernet, limit=10)

    # Format history for Gemini SDK
    gemini_contents = []
    for h in history_records:
        role = "user" if h["role"] == "user" else "model"
        text_val = h.get("text", "")
        if text_val and not text_val.startswith("[Ошибка"):
            gemini_contents.append(types.Content(role=role, parts=[types.Part.from_text(text=text_val)]))

    # Current user turn
    current_parts = []
    if user_text:
        current_parts.append(types.Part.from_text(text=user_text))
    current_parts.extend(multimodal_parts)

    gemini_contents.append(types.Content(role="user", parts=current_parts))

    # 7. Build System Instruction (Persona + Style + RAG)
    persona_key = user.active_persona or "default"
    style_key = user.bot_style or "default"
    persona_prompt = BOT_PERSONAS.get(persona_key, {}).get("prompt_ru", "")
    style_prompt = BOT_STYLES.get(style_key, "")

    system_instruction_blocks = []
    if persona_prompt:
        system_instruction_blocks.append(f"Твоя роль:\n{persona_prompt}")
    if style_prompt:
        system_instruction_blocks.append(f"Стиль общения: {style_prompt}")
    if rag_context:
        system_instruction_blocks.append(f"База знаний пользователя:\n{rag_context}")

    system_instruction = "\n\n---\n\n".join(system_instruction_blocks) if system_instruction_blocks else None

    # 8. Build context header (Dialog, Persona, Model)
    async with async_session_maker() as session:
        dialog_repo = DialogRepository(session)
        active_d = await dialog_repo.get_by_id(active_dialog_id)
        dialog_title = active_d.name if active_d else "Основной диалог"

    persona_data = BOT_PERSONAS.get(persona_key, {})
    persona_title = persona_data.get("name_ru", persona_key)
    model_id = user.gemini_model or settings.DEFAULT_MODEL_ID

    context_header = (
        f"• **Диалог:** `{dialog_title}`\n"
        f"• **Персона:** `{persona_title}`\n"
        f"• **Модель:** `{model_id}`\n"
        f"---\n\n"
    )

    # 9. Start streaming response
    placeholder_msg = await message.answer("💭 <i>Думаю...</i>", parse_mode="HTML")
    throttler = MessageStreamThrottler(
        bot=bot,
        chat_id=message.chat.id,
        initial_message=placeholder_msg,
        header_text=context_header,
    )

    gemini_service = GeminiService(api_key=api_key)

    try:
        stream = gemini_service.generate_stream(
            model_id=model_id,
            contents=gemini_contents,
            system_instruction=system_instruction,
            enable_search=True,
        )
        async for chunk in stream:
            await throttler.handle_chunk(chunk)

        full_reply_text = await throttler.finalize()

    except Exception as e:
        logger.error(f"Generation error: {e}")
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=placeholder_msg.message_id)
        except Exception:
            pass
        err_msg = str(e)
        if len(err_msg) > 1000:
            err_msg = err_msg[:1000] + "... [сообщение обрезано]"
        await message.answer(f"⚠️ Ошибка генерации ответа:\n{err_msg}")
        return

    # 9. Save encrypted messages to DB
    async with async_session_maker() as session:
        conv_repo = ConversationRepository(session)
        # Save user message
        await conv_repo.add_message(
            user_id=user_id,
            dialog_id=active_dialog_id,
            role="user",
            message_text=user_text,
            fernet_instance=fernet,
        )
        # Save assistant message
        await conv_repo.add_message(
            user_id=user_id,
            dialog_id=active_dialog_id,
            role="bot",
            message_text=full_reply_text,
            fernet_instance=fernet,
        )

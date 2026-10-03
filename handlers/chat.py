"""
Chat and Multimodal Generation Handler for MyGemini Zero v2.
Coordinates Zero-Knowledge decryption, RAG retrieval from ChromaDB,
multimodal processing (Images, Audio, PDF/DOCX), accidental API key interception,
bilingual stream header, error parser mapping, and safe streaming via MessageStreamThrottler.
"""

from typing import List, Any, Dict, Optional
from io import BytesIO
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from google.genai import types

from core.database import async_session_maker
from database.repositories import UserRepository, DialogRepository, ConversationRepository
from services.gemini import GeminiService
from services.throttler import MessageStreamThrottler
from services.media import format_image_part, format_audio_part, parse_document_text
from services.vector_store import VectorStoreManager
from services.dialog_namer import generate_dialog_title
from services.error_parser import get_user_friendly_error_key
from middlewares.auth import session_manager
from keyboards.inline import (
    get_unlock_keyboard,
    get_set_password_keyboard,
    get_api_key_input_keyboard,
    get_subscription_keyboard,
    get_main_menu_keyboard,
    get_close_button,
    get_chat_quick_actions_keyboard,
    get_streaming_stop_keyboard,
)
from handlers.dialogs import export_and_send_dialog_md
from keyboards.reply import get_main_reply_keyboard, get_locked_reply_keyboard, get_setup_reply_keyboard
from core.config import settings, BOT_STYLES, BOT_PERSONAS, SUBSCRIPTION_PLANS
from core.ui_helpers import safe_edit_message_text, safe_answer_callback
from core.localization import get_text
from core.logger import get_logger

logger = get_logger("user_messages")
router = Router(name="chat")

# Active message throttlers mapped by chat_id for live stop / abortion support
active_streams: Dict[int, MessageStreamThrottler] = {}


@router.message(F.text | F.photo | F.voice | F.document)
async def handle_user_message(message: Message, bot: Bot):
    """Primary handler for all incoming conversational and multimodal user messages."""
    user_id = message.from_user.id
    user_text = message.text or message.caption or ""

    # Fetch user language from DB or Telegram
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else ("ru" if not message.from_user.language_code or message.from_user.language_code.startswith("ru") else "en")

    # 0. Intercept accidental API key sent as plain text in chat
    if user_text.strip().startswith("AIzaSy") and len(user_text.strip()) >= 35:
        try:
            await message.delete()
        except Exception:
            pass

        fernet = session_manager.get_fernet(user_id)
        if not fernet:
            prompt = (
                "🔑 <b>Обнаружен Google API-ключ!</b>\n\n"
                "Ваше сообщение было мгновенно удалено в целях безопасности.\n"
                "Сейф сейчас заблокирован. Пожалуйста, разблокируйте память мастер-паролем, "
                "чтобы бот мог зашифровать и сохранить ключ."
                if lang_code == "ru"
                else "🔑 <b>Google API key detected!</b>\n\n"
                "Your message was immediately deleted for safety.\n"
                "The vault is currently locked. Please unlock with master password "
                "so the bot can encrypt and save the key."
            )
            await message.answer(prompt, reply_markup=get_unlock_keyboard(lang_code), parse_mode="HTML")
            return

        async with async_session_maker() as session:
            user_repo = UserRepository(session)
            await user_repo.set_api_key(user_id, user_text.strip(), fernet)

        done = (
            "🔑 <b>API-ключ Google Gemini распознан и сохранён!</b>\n\n"
            "Ключ был удален из чата, зашифрован вашим мастер-паролем (Zero-Knowledge) и сохранён."
            if lang_code == "ru"
            else "🔑 <b>Google Gemini API key recognized and saved!</b>\n\n"
            "The key was deleted from chat, encrypted with your master password, and saved."
        )
        await message.answer(
            done,
            reply_markup=get_main_menu_keyboard(is_unlocked=True, is_admin=(user_id == settings.ADMIN_USER_ID), lang_code=lang_code),
            parse_mode="HTML",
        )
        return

    # 0.1 Intercept unhandled slash commands so they don't leak into Gemini prompt
    if user_text.strip().startswith("/"):
        unknown_text = (
            "❓ <b>Неизвестная команда.</b>\n\n"
            "Используйте команду /help или меню «❓ Помощь», чтобы посмотреть список доступных команд."
            if lang_code == "ru"
            else "❓ <b>Unknown command.</b>\n\n"
            "Use /help to view available commands."
        )
        await message.answer(
            unknown_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[get_close_button(lang_code)]]),
            parse_mode="HTML",
        )
        return

    # 1. Zero-Knowledge session check
    fernet = session_manager.get_fernet(user_id)
    if not fernet:
        async with async_session_maker() as session:
            user_repo = UserRepository(session)
            has_password = await user_repo.is_master_password_set(user_id)

            if not has_password:
                prompt = (
                    "🔐 <b>Установите мастер-пароль.</b>\n\n"
                    "Для создания зашифрованного хранилища и общения с AI задайте ваш мастер-пароль:"
                    if lang_code == "ru"
                    else "🔐 <b>Set master password.</b>\n\n"
                    "To initialize your encrypted vault and chat with AI, set your master password:"
                )
                await message.answer(
                    prompt,
                    reply_markup=get_set_password_keyboard(lang_code),
                    parse_mode="HTML",
                )
                try:
                    await message.answer(
                        "🔐 Задайте мастер-пароль в окне или в чате:" if lang_code == "ru" else "🔐 Set master password in window or chat:",
                        reply_markup=get_setup_reply_keyboard(lang_code),
                    )
                except Exception:
                    pass
                return

            candidate = user_text.strip()
            if candidate:
                from handlers.auth import safe_instant_delete
                await safe_instant_delete(message)

                # 1.1 Check panic password first
                if await user_repo.verify_panic_password(user_id, candidate):
                    conv_repo = ConversationRepository(session)
                    await conv_repo.clear_user_data(user_id)
                    session_manager.lock_session(user_id)
                    panic_text = (
                        "🚨 <b>Аварийный сброс выполнен.</b>\n"
                        "Все диалоги, сообщения, профиль и ключи были безвозвратно удалены из базы данных."
                        if lang_code == "ru"
                        else "🚨 <b>Emergency wipe executed.</b>\n"
                        "All dialogues, messages, profile, and keys have been permanently wiped."
                    )
                    await message.answer(panic_text, reply_markup=get_locked_reply_keyboard(lang_code), parse_mode="HTML")
                    return

                # 1.2 Check master password (on-the-fly unlock)
                if await user_repo.verify_master_password(user_id, candidate):
                    from core.crypto import get_fernet_instance
                    salt = await user_repo.get_salt(user_id)
                    fernet_inst = get_fernet_instance(candidate, salt)
                    session_manager.unlock_session(user_id, fernet_inst)

                    is_admin = (user_id == settings.ADMIN_USER_ID)
                    unlock_text = (
                        "🔓 <b>Сейф успешно разблокирован!</b>\n\n"
                        "Ключи расшифровки загружены в память. Диалоги готовы к продолжению."
                        if lang_code == "ru"
                        else "🔓 <b>Vault unlocked successfully!</b>\n\n"
                        "Decryption keys loaded into memory. Dialogues are ready."
                    )
                    await message.answer(
                        unlock_text,
                        reply_markup=get_main_reply_keyboard(is_admin=is_admin, lang_code=lang_code),
                        parse_mode="HTML",
                    )
                    return

                # 1.3 Incorrect password entered
                fail_text = (
                    "❌ <b>Неверный мастер-пароль!</b>\n\n"
                    "Сообщение удалено для безопасности. Попробуйте ещё раз:"
                    if lang_code == "ru"
                    else "❌ <b>Incorrect master password!</b>\n\n"
                    "Message deleted for safety. Please try again:"
                )
                await message.answer(
                    fail_text,
                    reply_markup=get_unlock_keyboard(lang_code),
                    parse_mode="HTML",
                )
                try:
                    await message.answer(
                        "🔐 Введите мастер-пароль в окне или в чате:" if lang_code == "ru" else "🔐 Enter master password in window or chat:",
                        reply_markup=get_locked_reply_keyboard(lang_code),
                    )
                except Exception:
                    pass
                return

        prompt = (
            "🔒 <b>Хранилище заблокировано.</b>\n\n"
            "Для общения с AI и расшифровки истории введите ваш мастер-пароль:"
            if lang_code == "ru"
            else "🔒 <b>Vault is locked.</b>\n\n"
            "To chat with AI and decrypt history, enter your master password:"
        )
        await message.answer(
            prompt,
            reply_markup=get_unlock_keyboard(lang_code),
            parse_mode="HTML",
        )
        try:
            await message.answer(
                "🔐 Введите мастер-пароль в окне или в чате:" if lang_code == "ru" else "🔐 Enter master password in window or chat:",
                reply_markup=get_locked_reply_keyboard(lang_code),
            )
        except Exception:
            pass
        return

    # 2. Database checks: user, active dialog, API key, subscription
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        dialog_repo = DialogRepository(session)
        conv_repo = ConversationRepository(session)

        user = await user_repo.get_by_id(user_id)
        if not user:
            user, _ = await user_repo.add_or_update_user(
                user_id, message.from_user.username, message.from_user.first_name, message.from_user.last_name, lang_code=lang_code
            )

        # Check API key
        api_key = await user_repo.get_api_key(user_id, fernet)
        if not api_key:
            prompt_key = (
                "🔑 <b>API-ключ Google Gemini не установлен.</b>\n\n"
                "Бот работает по модели BYOK (Bring Your Own Key). "
                "Пожалуйста, установите ваш персональный ключ Google AI Studio:"
                if lang_code == "ru"
                else "🔑 <b>Google Gemini API key is not set.</b>\n\n"
                "The bot operates on the BYOK model. Please set your personal Google AI Studio key:"
            )
            await message.answer(
                prompt_key,
                reply_markup=get_api_key_input_keyboard(lang_code),
                parse_mode="HTML",
            )
            return

        # Check subscription
        is_admin = (user_id == settings.ADMIN_USER_ID)
        if not is_admin and not user_repo.is_subscription_active(user):
            sub_prompt = (
                "💎 <b>Для доступа к боту требуется активная подписка.</b>\n\n"
                "Оформите подписка для безлимитного общения, RAG-памяти и анализа документов:"
                if lang_code == "ru"
                else "💎 <b>An active subscription is required to access the bot.</b>\n\n"
                "Subscribe to unlock unlimited chat, RAG memory, and document analysis:"
            )
            await message.answer(
                sub_prompt,
                reply_markup=get_subscription_keyboard(SUBSCRIPTION_PLANS, lang_code=lang_code),
                parse_mode="HTML",
            )
            return

        # Active dialog check
        active_dialog_id = user.active_dialog_id
        if not active_dialog_id:
            dlg_name = "Основной диалог" if lang_code == "ru" else "Main Dialogue"
            dialog = await dialog_repo.create_dialog(user_id, dlg_name, set_active=True)
            active_dialog_id = dialog.dialog_id

    # 3. Handle document upload (RAG indexing)
    if message.document:
        doc = message.document
        loading_text = "📥 <i>Загружаю и анализирую документ...</i>" if lang_code == "ru" else "📥 <i>Downloading and parsing document...</i>"
        status_msg = await message.answer(loading_text, parse_mode="HTML")
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

        if lang_code == "ru":
            doc_done = (
                f"📄 <b>Документ добавлен в память диалога!</b>\n\n"
                f"• <b>Файл:</b> <code>{doc.file_name}</code>\n"
                f"• <b>Фрагментов сохранено:</b> {chunks_count}\n"
                f"• <b>Тип:</b> {doc_type.upper()}\n\n"
                "Теперь вы можете задавать любые вопросы по содержимому этого файла."
            )
        else:
            doc_done = (
                f"📄 <b>Document added to dialogue memory!</b>\n\n"
                f"• <b>File:</b> <code>{doc.file_name}</code>\n"
                f"• <b>Chunks indexed:</b> {chunks_count}\n"
                f"• <b>Type:</b> {doc_type.upper()}\n\n"
                "You can now ask any questions about this document."
            )

        await status_msg.edit_text(doc_done, parse_mode="HTML")
        return

    # 4. Extract user prompt & multimodal attachments
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
            user_text = "[Голосовое сообщение]" if lang_code == "ru" else "[Voice message]"

    # 5. Semantic RAG Search for context & Auto-naming
    rag_context = ""
    vm = VectorStoreManager(api_key=api_key)
    if user_text and not user_text.startswith("["):
        rag_context = await vm.search_context(active_dialog_id, user_text)

        # Auto-name dialog if it still has default placeholder name
        try:
            async with async_session_maker() as session:
                dialog_repo = DialogRepository(session)
                active_d = await dialog_repo.get_by_id(active_dialog_id)
                if active_d and active_d.name in ("Новый диалог", "Основной диалог", "New Dialogue", "Main Dialogue"):
                    new_title = await generate_dialog_title(user_text, api_key=api_key)
                    if new_title and new_title != active_d.name:
                        await dialog_repo.rename_dialog(active_dialog_id, new_title)
        except Exception as e:
            logger.warning(f"Error auto-naming dialog {active_dialog_id}: {e}")

    # 6. Load conversation history
    async with async_session_maker() as session:
        conv_repo = ConversationRepository(session)
        history_records = await conv_repo.get_dialog_messages(active_dialog_id, fernet, limit=20)

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
    persona_data = BOT_PERSONAS.get(persona_key, {})
    persona_prompt = persona_data.get("prompt_ru", "") if lang_code == "ru" else persona_data.get("prompt_en", persona_data.get("prompt_ru", ""))
    style_prompt = BOT_STYLES.get(style_key, "")

    system_instruction_blocks = []
    if persona_prompt:
        system_instruction_blocks.append(f"Role:\n{persona_prompt}")
    if style_prompt:
        system_instruction_blocks.append(f"Style: {style_prompt}")
    if rag_context:
        system_instruction_blocks.append(f"Knowledge Base:\n{rag_context}")

    user_format = getattr(user, "message_format", "rich") or "rich"
    if user_format == "rich":
        rich_guidance = (
            "Formatting guidelines:\n"
            "- For structured data, tables, comparisons, or numbers, use standard GitHub-Flavored Markdown tables.\n"
            "- For mathematical expressions, use standard LaTeX ($...$ inline, $$...$$ for display blocks).\n"
            "- If analyzing step-by-step, wrap intermediate thinking inside <think>...</think> tags."
            if lang_code == "en" else
            "Правила форматирования:\n"
            "- Для структурированных данных, списков характеристик и сравнений свободно используй компактные Markdown-таблицы.\n"
            "- Для математических выражений используй стандартный синтаксис LaTeX ($...$ инлайн, $$...$$ отдельными блоками).\n"
            "- Если анализируешь задачу по шагам, оборачивай свои промежуточные размышления в тег <think>...</think>."
        )
        system_instruction_blocks.append(rich_guidance)

    system_instruction = "\n\n---\n\n".join(system_instruction_blocks) if system_instruction_blocks else None

    # 8. Build context header (Dialog, Persona, Model)
    async with async_session_maker() as session:
        dialog_repo = DialogRepository(session)
        active_d = await dialog_repo.get_by_id(active_dialog_id)
        dialog_title = active_d.name if active_d else ("Основной диалог" if lang_code == "ru" else "Main Dialogue")

    persona_title = persona_data.get("name_ru", persona_key) if lang_code == "ru" else persona_data.get("name_en", persona_key)
    model_id = user.gemini_model or settings.DEFAULT_MODEL_ID
    header_style = getattr(user, "header_style", "blockquote") or "blockquote"

    if header_style == "hidden":
        context_header = ""
        header_summary = ""
    else:
        header_summary = f"💬 {dialog_title} • ⚡ {model_id}"
        if lang_code == "ru":
            context_header = (
                f"> 💬 **Диалог:** {dialog_title}\n"
                f"> 🎭 **Персона:** {persona_title}\n"
                f"> ⚡ **Модель:** {model_id}\n\n"
            )
        else:
            context_header = (
                f"> 💬 **Dialogue:** {dialog_title}\n"
                f"> 🎭 **Persona:** {persona_title}\n"
                f"> ⚡ **Model:** {model_id}\n\n"
            )

    if lang_code == "ru":
        thinking_text = "💭 <i>Думаю...</i>"
        thinking_summary = "Размышления"
    else:
        thinking_text = "💭 <i>Thinking...</i>"
        thinking_summary = "Reasoning"

    thinking_budget = getattr(user, "thinking_budget", 1024)
    if thinking_budget is None:
        thinking_budget = 1024

    # 9. Start streaming response
    placeholder_msg = await message.answer(thinking_text, parse_mode="HTML")
    throttler = MessageStreamThrottler(
        bot=bot,
        chat_id=message.chat.id,
        initial_message=placeholder_msg,
        header_text=context_header,
        header_summary=header_summary,
        message_format=user_format,
        thinking_summary=thinking_summary,
        header_style=header_style,
        stop_keyboard=get_streaming_stop_keyboard(lang_code),
        quick_actions_keyboard=get_chat_quick_actions_keyboard(lang_code),
    )

    gemini_service = GeminiService(api_key=api_key)
    active_streams[message.chat.id] = throttler

    try:
        stream = gemini_service.generate_stream(
            model_id=model_id,
            contents=gemini_contents,
            system_instruction=system_instruction,
            enable_search=True,
            thinking_budget=thinking_budget,
        )
        async for chunk in stream:
            if throttler.is_aborted:
                break
            await throttler.handle_chunk(chunk)

        full_reply_text = await throttler.finalize()

    except Exception as e:
        logger.error(f"Generation error: {e}")
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=placeholder_msg.message_id)
        except Exception:
            pass

        err_key = get_user_friendly_error_key({"error": str(e)})
        friendly_error = get_text(err_key, lang_code=lang_code)

        if friendly_error == err_key or not friendly_error:
            raw_err = str(e)[:500]
            friendly_error = (
                f"⚠️ Ошибка генерации ответа:\n{raw_err}"
                if lang_code == "ru"
                else f"⚠️ Generation error:\n{raw_err}"
            )

        await message.answer(friendly_error)
        return
    finally:
        active_streams.pop(message.chat.id, None)

    # 10. Save encrypted messages to DB
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
        if full_reply_text and full_reply_text.strip():
            await conv_repo.add_message(
                user_id=user_id,
                dialog_id=active_dialog_id,
                role="bot",
                message_text=full_reply_text,
                fernet_instance=fernet,
            )


@router.callback_query(F.data == "chat_action:stop")
async def handle_chat_action_stop(callback: CallbackQuery):
    """Aborts active generation stream for this chat."""
    chat_id = callback.message.chat.id if callback.message else callback.from_user.id
    throttler = active_streams.get(chat_id)
    if throttler:
        throttler.abort()
        ans_text = "⏹️ Генерация остановлена" if (callback.from_user.language_code or "").startswith("ru") else "⏹️ Generation stopped"
        await safe_answer_callback(callback, ans_text)
    else:
        ans_text = "Генерация уже завершена" if (callback.from_user.language_code or "").startswith("ru") else "Generation already finished"
        await safe_answer_callback(callback, ans_text)


@router.callback_query(F.data == "chat_action:undo")
async def handle_chat_action_undo(callback: CallbackQuery):
    """Deletes the last turn (bot message and preceding user message) from active dialog."""
    user_id = callback.from_user.id
    fernet = session_manager.get_fernet(user_id)
    if not fernet:
        ans_text = (
            "🔒 Сейф заблокирован. Разблокируйте память мастер-паролем."
            if (callback.from_user.language_code or "").startswith("ru")
            else "🔒 Vault is locked. Please unlock with master password."
        )
        await safe_answer_callback(callback, ans_text, show_alert=True)
        return

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"
        active_dialog_id = user.active_dialog_id if user else None

        if not active_dialog_id:
            await safe_answer_callback(
                callback,
                "Активный диалог не найден." if lang_code == "ru" else "No active dialogue found.",
                show_alert=True,
            )
            return

        conv_repo = ConversationRepository(session)
        user_text, deleted_count = await conv_repo.delete_last_turn(active_dialog_id, fernet)

    if deleted_count and deleted_count > 0:
        await safe_answer_callback(callback, "Шаг отменён" if lang_code == "ru" else "Turn undone")
        notice = (
            "↩️ <b>Последний шаг отменен. Контекст очищен.</b>"
            if lang_code == "ru"
            else "↩️ <b>Last turn undone. Context cleared.</b>"
        )
        if user_text:
            prompt_preview = user_text[:150] + ("..." if len(user_text) > 150 else "")
            notice += f"\n\n<i>«{prompt_preview}»</i>"
        try:
            await safe_edit_message_text(
                callback.message,
                notice,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[get_close_button(lang_code)]]),
                parse_mode="HTML",
            )
        except Exception:
            pass
    else:
        empty_msg = "Нет сообщений для отмены." if lang_code == "ru" else "No turns to undo."
        await safe_answer_callback(callback, empty_msg, show_alert=True)


@router.callback_query(F.data == "chat_action:regen")
async def handle_chat_action_regen(callback: CallbackQuery, bot: Bot):
    """Regenerates the last assistant response for the user's last prompt."""
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id if callback.message else user_id

    if chat_id in active_streams:
        await safe_answer_callback(
            callback,
            "Пожалуйста, подождите завершения текущей генерации."
            if (callback.from_user.language_code or "").startswith("ru")
            else "Please wait for current generation to finish.",
            show_alert=True,
        )
        return

    fernet = session_manager.get_fernet(user_id)
    if not fernet:
        await safe_answer_callback(
            callback,
            "🔒 Сейф заблокирован. Разблокируйте память мастер-паролем."
            if (callback.from_user.language_code or "").startswith("ru")
            else "🔒 Vault is locked. Please unlock with master password.",
            show_alert=True,
        )
        return

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        if not user or not user.active_dialog_id:
            await safe_answer_callback(
                callback,
                "Активный диалог не найден."
                if (callback.from_user.language_code or "").startswith("ru")
                else "Active dialogue not found.",
                show_alert=True,
            )
            return

        active_dialog_id = user.active_dialog_id
        lang_code = user.language_code or "ru"
        api_key = await user_repo.get_api_key(user_id, fernet) or settings.GEMINI_API_KEY
        if not api_key:
            await safe_answer_callback(
                callback,
                "🔑 API-ключ не установлен." if lang_code == "ru" else "🔑 API key not set.",
                show_alert=True,
            )
            return

        conv_repo = ConversationRepository(session)
        # 1. Delete last assistant response
        deleted_id = await conv_repo.delete_last_assistant_message(active_dialog_id)
        if not deleted_id:
            await safe_answer_callback(
                callback,
                "Нет ответа для повторной генерации." if lang_code == "ru" else "No response to regenerate.",
                show_alert=True,
            )
            return

        # 2. Get updated history to extract user prompt
        history_records = await conv_repo.get_dialog_messages(active_dialog_id, fernet, limit=20)
        if not history_records:
            await safe_answer_callback(
                callback,
                "История сообщений пуста." if lang_code == "ru" else "Conversation history is empty.",
                show_alert=True,
            )
            return

        last_user_record = None
        for h in reversed(history_records):
            if h["role"] == "user":
                last_user_record = h
                break

        if not last_user_record:
            await safe_answer_callback(
                callback,
                "Запрос пользователя не найден." if lang_code == "ru" else "User prompt not found.",
                show_alert=True,
            )
            return

        user_prompt = last_user_record.get("text", "")

        dialog_repo = DialogRepository(session)
        active_d = await dialog_repo.get_by_id(active_dialog_id)
        dialog_title = active_d.name if active_d else ("Основной диалог" if lang_code == "ru" else "Main Dialogue")

    await safe_answer_callback(
        callback,
        "🔄 Перегенерация ответа..." if lang_code == "ru" else "🔄 Regenerating response..."
    )

    # Format history for Gemini SDK (excluding the prompt turn which is appended after)
    gemini_contents = []
    for h in history_records:
        if h["conversation_id"] < last_user_record["conversation_id"]:
            role = "user" if h["role"] == "user" else "model"
            text_val = h.get("text", "")
            if text_val and not text_val.startswith("[Ошибка"):
                gemini_contents.append(types.Content(role=role, parts=[types.Part.from_text(text=text_val)]))

    gemini_contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user_prompt)]))

    # RAG search for user prompt
    rag_context = ""
    vm = VectorStoreManager(api_key=api_key)
    if user_prompt and not user_prompt.startswith("["):
        rag_context = await vm.search_context(active_dialog_id, user_prompt)

    # Build System Instruction
    persona_key = user.active_persona or "default"
    style_key = user.bot_style or "default"
    persona_data = BOT_PERSONAS.get(persona_key, {})
    persona_prompt = persona_data.get("prompt_ru", "") if lang_code == "ru" else persona_data.get("prompt_en", persona_data.get("prompt_ru", ""))
    style_prompt = BOT_STYLES.get(style_key, "")

    system_instruction_blocks = []
    if persona_prompt:
        system_instruction_blocks.append(f"Role:\n{persona_prompt}")
    if style_prompt:
        system_instruction_blocks.append(f"Style: {style_prompt}")
    if rag_context:
        system_instruction_blocks.append(f"Knowledge Base:\n{rag_context}")

    user_format = getattr(user, "message_format", "rich") or "rich"
    if user_format == "rich":
        rich_guidance = (
            "Formatting guidelines:\n"
            "- For structured data, tables, comparisons, or numbers, use standard GitHub-Flavored Markdown tables.\n"
            "- For mathematical expressions, use standard LaTeX ($...$ inline, $$...$$ for display blocks).\n"
            "- If analyzing step-by-step, wrap intermediate thinking inside <think>...</think> tags."
            if lang_code == "en" else
            "Правила форматирования:\n"
            "- Для структурированных данных, списков характеристик и сравнений свободно используй компактные Markdown-таблицы.\n"
            "- Для математических выражений используй стандартный синтаксис LaTeX ($...$ инлайн, $$...$$ отдельными блоками).\n"
            "- Если анализируешь задачу по шагам, оборачивай свои промежуточные размышления в тег <think>...</think>."
        )
        system_instruction_blocks.append(rich_guidance)

    system_instruction = "\n\n---\n\n".join(system_instruction_blocks) if system_instruction_blocks else None

    # Build context header
    persona_title = persona_data.get("name_ru", persona_key) if lang_code == "ru" else persona_data.get("name_en", persona_key)
    model_id = user.gemini_model or settings.DEFAULT_MODEL_ID
    header_style = getattr(user, "header_style", "blockquote") or "blockquote"

    if header_style == "hidden":
        context_header = ""
        header_summary = ""
    else:
        header_summary = f"💬 {dialog_title} • ⚡ {model_id}"
        if lang_code == "ru":
            context_header = (
                f"> 💬 **Диалог:** {dialog_title}\n"
                f"> 🎭 **Персона:** {persona_title}\n"
                f"> ⚡ **Модель:** {model_id}\n\n"
            )
        else:
            context_header = (
                f"> 💬 **Dialogue:** {dialog_title}\n"
                f"> 🎭 **Persona:** {persona_title}\n"
                f"> ⚡ **Model:** {model_id}\n\n"
            )

    if lang_code == "ru":
        thinking_text = "💭 <i>Думаю...</i>"
        thinking_summary = "Размышления"
    else:
        thinking_text = "💭 <i>Thinking...</i>"
        thinking_summary = "Reasoning"

    thinking_budget = getattr(user, "thinking_budget", 1024)
    if thinking_budget is None:
        thinking_budget = 1024

    # Update callback message with thinking placeholder
    await safe_edit_message_text(callback.message, thinking_text, parse_mode="HTML")
    throttler = MessageStreamThrottler(
        bot=bot,
        chat_id=chat_id,
        initial_message=callback.message,
        header_text=context_header,
        header_summary=header_summary,
        message_format=user_format,
        thinking_summary=thinking_summary,
        header_style=header_style,
        stop_keyboard=get_streaming_stop_keyboard(lang_code),
        quick_actions_keyboard=get_chat_quick_actions_keyboard(lang_code),
    )

    gemini_service = GeminiService(api_key=api_key)
    active_streams[chat_id] = throttler

    try:
        stream = gemini_service.generate_stream(
            model_id=model_id,
            contents=gemini_contents,
            system_instruction=system_instruction,
            enable_search=True,
            thinking_budget=thinking_budget,
        )
        async for chunk in stream:
            if throttler.is_aborted:
                break
            await throttler.handle_chunk(chunk)

        full_reply_text = await throttler.finalize()
    except Exception as e:
        logger.error(f"Regeneration error: {e}")
        err_key = get_user_friendly_error_key({"error": str(e)})
        friendly_error = get_text(err_key, lang_code=lang_code)
        if friendly_error == err_key or not friendly_error:
            raw_err = str(e)[:500]
            friendly_error = (
                f"⚠️ Ошибка генерации ответа:\n{raw_err}"
                if lang_code == "ru"
                else f"⚠️ Generation error:\n{raw_err}"
            )
        await safe_edit_message_text(callback.message, friendly_error)
        return
    finally:
        active_streams.pop(chat_id, None)

    # Save regenerated assistant message to DB
    if full_reply_text and full_reply_text.strip():
        async with async_session_maker() as session:
            conv_repo = ConversationRepository(session)
            await conv_repo.add_message(
                user_id=user_id,
                dialog_id=active_dialog_id,
                role="bot",
                message_text=full_reply_text,
                fernet_instance=fernet,
            )


@router.callback_query(F.data == "chat_action:export")
async def handle_chat_action_export(callback: CallbackQuery):
    """Exports the currently active dialog to Markdown directly from chat quick actions."""
    user_id = callback.from_user.id
    fernet = session_manager.get_fernet(user_id)

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        lang_code = user.language_code if user and user.language_code else "ru"
        active_dialog_id = user.active_dialog_id if user else None

    if not fernet:
        locked_text = (
            "🔒 Память заблокирована. Пожалуйста, разблокируйте сейф мастер-паролем, чтобы экспортировать диалог."
            if lang_code == "ru"
            else "🔒 Vault is locked. Please unlock with master password to export dialogue."
        )
        await safe_answer_callback(callback, locked_text, show_alert=True)
        return

    if not active_dialog_id:
        not_found = "Активный диалог не найден." if lang_code == "ru" else "No active dialogue found."
        await safe_answer_callback(callback, not_found, show_alert=True)
        return

    await export_and_send_dialog_md(
        dialog_id=active_dialog_id,
        user_id=user_id,
        fernet=fernet,
        target_message=callback.message,
        lang_code=lang_code,
        callback=callback,
    )



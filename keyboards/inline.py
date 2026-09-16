"""
Inline Keyboards Module for MyGemini Zero v2.
Builds interactive Telegram inline markup for menus, settings, WebApp popups,
models list with search badges, document management, subscriptions, profile, and administration.
Includes "❌ Закрыть" buttons across all interfaces for clean chat history.
Supports full bilingualism (Russian / English).
"""

from typing import List, Dict, Any, Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from core.config import settings, BOT_STYLES, BOT_PERSONAS
from core.localization import get_text


def get_close_button(lang_code: str = "ru") -> InlineKeyboardButton:
    """Returns universal close button that deletes the bot message."""
    text = "❌ Закрыть" if lang_code == "ru" else "❌ Close"
    return InlineKeyboardButton(text=text, callback_data="close_menu")


def get_cancel_keyboard(callback_data: str = "back_to_main", lang_code: str = "ru") -> InlineKeyboardMarkup:
    """Builds a minimal keyboard with Cancel and Close buttons for chat-input prompts."""
    cancel_text = "⬅️ Отмена" if lang_code == "ru" else "⬅️ Cancel"
    buttons = [
        [
            InlineKeyboardButton(text=cancel_text, callback_data=callback_data),
            get_close_button(lang_code),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_main_menu_keyboard(is_unlocked: bool = False, is_admin: bool = False, lang_code: str = "ru") -> InlineKeyboardMarkup:
    """Constructs the primary navigation keyboard."""
    btn_new_dlg = "💬 Новый диалог" if lang_code == "ru" else "💬 New Dialog"
    btn_dlg_list = "🗂 Список диалогов" if lang_code == "ru" else "🗂 Dialogs List"
    btn_settings = "⚙️ Настройки" if lang_code == "ru" else "⚙️ Settings"
    btn_memory = "📄 Документы" if lang_code == "ru" else "📄 Documents"
    btn_profile = "👤 Личный кабинет" if lang_code == "ru" else "👤 Profile"
    btn_sub = "💎 Подписка" if lang_code == "ru" else "💎 Subscription"

    buttons = [
        [
            InlineKeyboardButton(text=btn_new_dlg, callback_data="dialog_new"),
            InlineKeyboardButton(text=btn_dlg_list, callback_data="dialog_list"),
        ],
        [
            InlineKeyboardButton(text=btn_settings, callback_data="menu_settings"),
            InlineKeyboardButton(text=btn_memory, callback_data="menu_memory"),
        ],
        [
            InlineKeyboardButton(text=btn_profile, callback_data="menu_profile"),
            InlineKeyboardButton(text=btn_sub, callback_data="menu_subscription"),
        ],
    ]

    # Vault lock/unlock toggle
    if is_unlocked:
        lock_text = "🔒 Заблокировать память" if lang_code == "ru" else "🔒 Lock Session"
        buttons.append([InlineKeyboardButton(text=lock_text, callback_data="vault_lock")])
    else:
        unlock_text = "🔐 Разблокировать сейф" if lang_code == "ru" else "🔐 Unlock Vault"
        buttons.append([InlineKeyboardButton(text=unlock_text, callback_data="vault_unlock_chat")])

    # Admin panel
    if is_admin:
        admin_text = "👑 Панель администратора" if lang_code == "ru" else "👑 Admin Panel"
        buttons.append([InlineKeyboardButton(text=admin_text, callback_data="menu_admin")])

    buttons.append([get_close_button(lang_code)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_unlock_keyboard(lang_code: str = "ru") -> InlineKeyboardMarkup:
    """Builds keyboard for master password entry."""
    input_text = "⌨️ Ввести пароль в чате (автоудаление)" if lang_code == "ru" else "⌨️ Enter password in chat"
    cancel_text = "⬅️ Отмена" if lang_code == "ru" else "⬅️ Cancel"
    buttons = [
        [InlineKeyboardButton(text=input_text, callback_data="vault_unlock_chat")],
        [InlineKeyboardButton(text=cancel_text, callback_data="back_to_main"), get_close_button(lang_code)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_set_password_keyboard(lang_code: str = "ru") -> InlineKeyboardMarkup:
    """Builds keyboard for setting master password on onboarding."""
    btn_text = "⌨️ Ввести пароль в чате" if lang_code == "ru" else "⌨️ Enter password in chat"
    buttons = [
        [InlineKeyboardButton(text=btn_text, callback_data="vault_setup_chat")],
        [get_close_button(lang_code)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_settings_keyboard(
    current_model: str,
    current_style: str,
    current_persona: str,
    has_api_key: bool,
    lang_code: str = "ru",
) -> InlineKeyboardMarkup:
    """Builds settings menu keyboard."""
    if lang_code == "ru":
        key_status = "✅ Установлен" if has_api_key else "❌ Не установлен"
        lang_label = "🌐 Язык: 🇷🇺 Русский"
        model_label = f"🤖 Модель: {current_model}"
        persona_label = f"🎭 Персона: {current_persona}"
        style_label = f"🎨 Стиль: {current_style}"
        key_label = f"🔑 API-ключ ({key_status})"
        panic_label = "🚨 Настроить паник-пароль"
        back_label = "⬅️ В главное меню"
    else:
        key_status = "✅ Set" if has_api_key else "❌ Not set"
        lang_label = "🌐 Language: 🇬🇧 English"
        model_label = f"🤖 Model: {current_model}"
        persona_label = f"🎭 Persona: {current_persona}"
        style_label = f"🎨 Style: {current_style}"
        key_label = f"🔑 API Key ({key_status})"
        panic_label = "🚨 Configure Panic Password"
        back_label = "⬅️ Main Menu"

    buttons = [
        [InlineKeyboardButton(text=model_label, callback_data="settings_models")],
        [InlineKeyboardButton(text=persona_label, callback_data="settings_personas")],
        [InlineKeyboardButton(text=style_label, callback_data="settings_styles")],
        [InlineKeyboardButton(text=key_label, callback_data="settings_api_key")],
        [InlineKeyboardButton(text=lang_label, callback_data="settings_language")],
        [InlineKeyboardButton(text=panic_label, callback_data="settings_panic")],
        [InlineKeyboardButton(text=back_label, callback_data="back_to_main"), get_close_button(lang_code)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_language_keyboard(current_lang: str = "ru", lang_code: str = "ru") -> InlineKeyboardMarkup:
    """Builds language selection keyboard."""
    ru_check = "✅ " if current_lang == "ru" else ""
    en_check = "✅ " if current_lang == "en" else ""
    back_label = "⬅️ Назад в настройки" if lang_code == "ru" else "⬅️ Back to Settings"

    buttons = [
        [InlineKeyboardButton(text=f"{ru_check}🇷🇺 Русский", callback_data="set_lang:ru")],
        [InlineKeyboardButton(text=f"{en_check}🇬🇧 English", callback_data="set_lang:en")],
        [InlineKeyboardButton(text=back_label, callback_data="menu_settings"), get_close_button(lang_code)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_api_key_input_keyboard(lang_code: str = "ru") -> InlineKeyboardMarkup:
    """Builds keyboard for API key entry."""
    btn_text = "⌨️ Ввести ключ в чате" if lang_code == "ru" else "⌨️ Enter key in chat"
    back_text = "⬅️ Назад в настройки" if lang_code == "ru" else "⬅️ Back to Settings"
    buttons = [
        [InlineKeyboardButton(text=btn_text, callback_data="api_key_chat_input")],
        [InlineKeyboardButton(text=back_text, callback_data="menu_settings"), get_close_button(lang_code)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_models_keyboard(models: List[Dict[str, Any]], current_model_id: str, lang_code: str = "ru") -> InlineKeyboardMarkup:
    """Builds model selection keyboard with search badges and active checkmark."""
    buttons = []
    for m in models:
        mid = m["id"]
        is_active = "✅ " if mid == current_model_id else ""
        display = m.get("display_name", mid)
        buttons.append([
            InlineKeyboardButton(
                text=f"{is_active}{display}",
                callback_data=f"set_model:{mid}",
            )
        ])
    back_text = "⬅️ Назад в настройки" if lang_code == "ru" else "⬅️ Back to Settings"
    buttons.append([InlineKeyboardButton(text=back_text, callback_data="menu_settings"), get_close_button(lang_code)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_styles_keyboard(current_style_key: str, lang_code: str = "ru") -> InlineKeyboardMarkup:
    """Builds bot style selection keyboard."""
    buttons = []
    for skey, sname in BOT_STYLES.items():
        active = "✅ " if skey == current_style_key else ""
        buttons.append([
            InlineKeyboardButton(text=f"{active}{sname}", callback_data=f"set_style:{skey}")
        ])
    back_text = "⬅️ Назад в настройки" if lang_code == "ru" else "⬅️ Back to Settings"
    buttons.append([InlineKeyboardButton(text=back_text, callback_data="menu_settings"), get_close_button(lang_code)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_personas_keyboard(current_persona_key: str, lang_code: str = "ru") -> InlineKeyboardMarkup:
    """Builds persona selection keyboard."""
    buttons = []
    for pkey, pdata in BOT_PERSONAS.items():
        active = "✅ " if pkey == current_persona_key else ""
        name = pdata.get("name_ru", pkey) if lang_code == "ru" else pdata.get("name_en", pkey)
        buttons.append([
            InlineKeyboardButton(text=f"{active}{name}", callback_data=f"set_persona:{pkey}")
        ])
    back_text = "⬅️ Назад в настройки" if lang_code == "ru" else "⬅️ Back to Settings"
    buttons.append([InlineKeyboardButton(text=back_text, callback_data="menu_settings"), get_close_button(lang_code)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_memory_menu_keyboard(docs_count: int = 0, lang_code: str = "ru") -> InlineKeyboardMarkup:
    """Memory & Document management menu."""
    if lang_code == "ru":
        btn_docs = f"📄 Список документов ({docs_count})"
        btn_archive = "📦 Архивировать старые сообщения (>30 дней)"
        btn_wipe = "⚠️ Полная очистка данных (Zero-Knowledge)"
        btn_back = "⬅️ В главное меню"
    else:
        btn_docs = f"📄 Document List ({docs_count})"
        btn_archive = "📦 Archive Old Messages (>30 days)"
        btn_wipe = "⚠️ Full Data Wipe (Zero-Knowledge)"
        btn_back = "⬅️ Main Menu"

    buttons = [
        [InlineKeyboardButton(text=btn_docs, callback_data="memory_view_docs")],
        [InlineKeyboardButton(text=btn_archive, callback_data="memory_archive_start")],
        [InlineKeyboardButton(text=btn_wipe, callback_data="memory_wipe_confirm")],
        [InlineKeyboardButton(text=btn_back, callback_data="back_to_main"), get_close_button(lang_code)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_documents_list_keyboard(documents: List[Dict[str, Any]], lang_code: str = "ru") -> InlineKeyboardMarkup:
    """Renders document list with individual delete buttons and file names."""
    buttons = []
    del_prefix = "🗑 Удалить: " if lang_code == "ru" else "🗑 Delete: "
    chunks_suffix = "ч." if lang_code == "ru" else "ch."

    for doc in documents:
        fname = doc["file_name"]
        fhash = doc["file_hash"]
        chunks = doc["chunks_count"]
        btn_name = fname if len(fname) <= 25 else fname[:22] + "..."
        buttons.append([
            InlineKeyboardButton(
                text=f"{del_prefix}{btn_name} ({chunks}{chunks_suffix})",
                callback_data=f"doc_del:{fhash}",
            )
        ])
    back_text = "⬅️ Назад в память" if lang_code == "ru" else "⬅️ Back to Memory"
    buttons.append([InlineKeyboardButton(text=back_text, callback_data="menu_memory"), get_close_button(lang_code)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_profile_keyboard(has_profile: bool = False, lang_code: str = "ru") -> InlineKeyboardMarkup:
    """Builds personal profile action keyboard."""
    if lang_code == "ru":
        btn_sub = "💎 Управление подпиской"
        edit_text = "📝 Редактировать анкету" if has_profile else "📝 Заполнить анкету"
        btn_back = "⬅️ В главное меню"
    else:
        btn_sub = "💎 Manage Subscription"
        edit_text = "📝 Edit Profile" if has_profile else "📝 Fill Profile"
        btn_back = "⬅️ Main Menu"

    buttons = [
        [InlineKeyboardButton(text=btn_sub, callback_data="menu_subscription")],
        [InlineKeyboardButton(text=edit_text, callback_data="profile_edit")],
        [InlineKeyboardButton(text=btn_back, callback_data="back_to_main"), get_close_button(lang_code)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_subscription_keyboard(plans: List[Dict[str, Any]], lang_code: str = "ru") -> InlineKeyboardMarkup:
    """Builds payment subscription buttons."""
    buttons = []
    back_text = "⬅️ В главное меню" if lang_code == "ru" else "⬅️ Main Menu"

    for plan in plans:
        rub_amount = plan["price_amount"] // 100
        title = plan["title"]
        pid = plan["id"]
        currency = "₽"
        buttons.append([
            InlineKeyboardButton(
                text=f"💳 {title} — {rub_amount} {currency}",
                callback_data=f"buy_sub:{pid}",
            )
        ])
    buttons.append([InlineKeyboardButton(text=back_text, callback_data="back_to_main"), get_close_button(lang_code)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_keyboard(is_maintenance: bool = False, lang_code: str = "ru") -> InlineKeyboardMarkup:
    """Builds administrative control panel keyboard."""
    m_status = ("🔴 Выключить" if is_maintenance else "🟢 Включить") if lang_code == "ru" else ("🔴 Disable" if is_maintenance else "🟢 Enable")
    stats_text = "📊 Общая статистика" if lang_code == "ru" else "📊 General Stats"
    subs_text = "👥 Список подписчиков" if lang_code == "ru" else "👥 Subscribers List"
    export_text = "📥 Экспорт в CSV (с BOM)" if lang_code == "ru" else "📥 Export CSV (BOM)"
    broadcast_text = "📢 Рассылка сообщений" if lang_code == "ru" else "📢 Broadcast Message"
    maint_text = f"🛠 Режим обслуживания: {m_status}" if lang_code == "ru" else f"🛠 Maintenance Mode: {m_status}"
    search_user_text = "🔍 Управление пользователем" if lang_code == "ru" else "🔍 Manage User by ID"
    back_text = "⬅️ В главное меню" if lang_code == "ru" else "⬅️ Main Menu"

    buttons = [
        [
            InlineKeyboardButton(text=stats_text, callback_data="admin_stats"),
            InlineKeyboardButton(text=subs_text, callback_data="admin_subscribers"),
        ],
        [
            InlineKeyboardButton(text=export_text, callback_data="admin_export_csv"),
            InlineKeyboardButton(text=broadcast_text, callback_data="admin_broadcast"),
        ],
        [
            InlineKeyboardButton(text=search_user_text, callback_data="admin_user_search"),
            InlineKeyboardButton(text=maint_text, callback_data="admin_toggle_maintenance"),
        ],
        [InlineKeyboardButton(text=back_text, callback_data="back_to_main"), get_close_button(lang_code)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_user_actions_keyboard(target_user_id: int, is_blocked: bool, lang_code: str = "ru") -> InlineKeyboardMarkup:
    """Keyboard for managing a specific user card in admin panel."""
    block_text = ("✅ Разблокировать" if is_blocked else "🚫 Заблокировать") if lang_code == "ru" else ("✅ Unblock" if is_blocked else "🚫 Block")
    reset_text = "🔑 Сбросить API-ключ" if lang_code == "ru" else "🔑 Reset API Key"
    extend_text = "➕ Продлить подписку" if lang_code == "ru" else "➕ Extend Subscription"
    reply_text = "✉️ Ответить пользователю" if lang_code == "ru" else "✉️ Reply to User"
    back_text = "⬅️ Назад в админку" if lang_code == "ru" else "⬅️ Back to Admin"

    buttons = [
        [
            InlineKeyboardButton(text=block_text, callback_data=f"admin_toggle_block:{target_user_id}"),
            InlineKeyboardButton(text=reset_text, callback_data=f"admin_reset_key:{target_user_id}"),
        ],
        [
            InlineKeyboardButton(text=extend_text, callback_data=f"admin_extend_sub:{target_user_id}"),
            InlineKeyboardButton(text=reply_text, callback_data=f"admin_reply_user:{target_user_id}"),
        ],
        [InlineKeyboardButton(text=back_text, callback_data="menu_admin"), get_close_button(lang_code)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_extend_sub_keyboard(target_user_id: int, lang_code: str = "ru") -> InlineKeyboardMarkup:
    """Keyboard for selecting subscription extension period."""
    d30 = "30 дней" if lang_code == "ru" else "30 days"
    d90 = "90 дней" if lang_code == "ru" else "90 days"
    d365 = "365 дней (1 год)" if lang_code == "ru" else "365 days (1 year)"
    back = "⬅️ Назад к пользователю" if lang_code == "ru" else "⬅️ Back to User"

    buttons = [
        [
            InlineKeyboardButton(text=d30, callback_data=f"admin_extend_days:{target_user_id}:30"),
            InlineKeyboardButton(text=d90, callback_data=f"admin_extend_days:{target_user_id}:90"),
        ],
        [InlineKeyboardButton(text=d365, callback_data=f"admin_extend_days:{target_user_id}:365")],
        [InlineKeyboardButton(text=back, callback_data=f"admin_user_card:{target_user_id}"), get_close_button(lang_code)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

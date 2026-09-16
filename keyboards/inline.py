"""
Inline Keyboards Module for MyGemini Zero v2.
Builds interactive Telegram inline markup for menus, settings, WebApp popups,
models list with search badges, document management, subscriptions, profile, and administration.
Includes "❌ Закрыть" buttons across all interfaces for clean chat history.
"""

from typing import List, Dict, Any, Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from core.config import settings, BOT_STYLES, BOT_PERSONAS


def get_close_button() -> InlineKeyboardButton:
    """Returns universal close button that deletes the bot message."""
    return InlineKeyboardButton(text="❌ Закрыть", callback_data="close_menu")


def get_main_menu_keyboard(is_unlocked: bool = False, is_admin: bool = False) -> InlineKeyboardMarkup:
    """Constructs the primary navigation keyboard."""
    buttons = [
        [
            InlineKeyboardButton(text="💬 Новый диалог", callback_data="dialog_new"),
            InlineKeyboardButton(text="🗂 Список диалогов", callback_data="dialog_list"),
        ],
        [
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu_settings"),
            InlineKeyboardButton(text="📄 Документы", callback_data="menu_memory"),
        ],
        [
            InlineKeyboardButton(text="👤 Личный кабинет", callback_data="menu_profile"),
            InlineKeyboardButton(text="💎 Подписка", callback_data="menu_subscription"),
        ],
    ]

    # Vault lock/unlock toggle
    if is_unlocked:
        buttons.append([InlineKeyboardButton(text="🔒 Заблокировать память", callback_data="vault_lock")])
    else:
        buttons.append([InlineKeyboardButton(text="🔐 Разблокировать сейф", callback_data="vault_unlock_chat")])

    # Admin panel
    if is_admin:
        buttons.append([InlineKeyboardButton(text="👑 Панель администратора", callback_data="menu_admin")])

    buttons.append([get_close_button()])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_unlock_keyboard() -> InlineKeyboardMarkup:
    """Builds keyboard for master password entry."""
    buttons = [
        [InlineKeyboardButton(text="⌨️ Ввести пароль в чате (автоудаление)", callback_data="vault_unlock_chat")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="back_to_main"), get_close_button()],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_set_password_keyboard() -> InlineKeyboardMarkup:
    """Builds keyboard for setting master password on onboarding."""
    buttons = [
        [InlineKeyboardButton(text="⌨️ Ввести пароль в чате", callback_data="vault_setup_chat")],
        [get_close_button()],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_settings_keyboard(current_model: str, current_style: str, current_persona: str, has_api_key: bool) -> InlineKeyboardMarkup:
    """Builds settings menu keyboard."""
    key_status = "✅ Установлен" if has_api_key else "❌ Не установлен"
    buttons = [
        [InlineKeyboardButton(text=f"🤖 Модель: {current_model}", callback_data="settings_models")],
        [InlineKeyboardButton(text=f"🎭 Персона: {current_persona}", callback_data="settings_personas")],
        [InlineKeyboardButton(text=f"🎨 Стиль: {current_style}", callback_data="settings_styles")],
        [
            InlineKeyboardButton(
                text=f"🔑 API-ключ ({key_status})",
                callback_data="settings_api_key",
            )
        ],
        [InlineKeyboardButton(text="🚨 Настроить паник-пароль", callback_data="settings_panic")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_to_main"), get_close_button()],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_api_key_input_keyboard() -> InlineKeyboardMarkup:
    """Builds keyboard for API key entry."""
    buttons = [
        [InlineKeyboardButton(text="⌨️ Ввести ключ в чате", callback_data="api_key_chat_input")],
        [InlineKeyboardButton(text="⬅️ Назад в настройки", callback_data="menu_settings"), get_close_button()],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_models_keyboard(models: List[Dict[str, Any]], current_model_id: str) -> InlineKeyboardMarkup:
    """
    Builds model selection keyboard with search badges and active checkmark.
    """
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
    buttons.append([InlineKeyboardButton(text="⬅️ Назад в настройки", callback_data="menu_settings"), get_close_button()])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_styles_keyboard(current_style_key: str) -> InlineKeyboardMarkup:
    """Builds bot style selection keyboard."""
    buttons = []
    for skey, sname in BOT_STYLES.items():
        active = "✅ " if skey == current_style_key else ""
        buttons.append([
            InlineKeyboardButton(text=f"{active}{sname}", callback_data=f"set_style:{skey}")
        ])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад в настройки", callback_data="menu_settings"), get_close_button()])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_personas_keyboard(current_persona_key: str) -> InlineKeyboardMarkup:
    """Builds persona selection keyboard."""
    buttons = []
    for pkey, pdata in BOT_PERSONAS.items():
        active = "✅ " if pkey == current_persona_key else ""
        name = pdata.get("name_ru", pkey)
        buttons.append([
            InlineKeyboardButton(text=f"{active}{name}", callback_data=f"set_persona:{pkey}")
        ])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад в настройки", callback_data="menu_settings"), get_close_button()])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_memory_menu_keyboard(docs_count: int = 0) -> InlineKeyboardMarkup:
    """Memory & Document management menu."""
    buttons = [
        [
            InlineKeyboardButton(
                text=f"📄 Список документов ({docs_count})",
                callback_data="memory_view_docs",
            )
        ],
        [
            InlineKeyboardButton(
                text="📦 Архивировать старые сообщения (>30 дней)",
                callback_data="memory_archive_start",
            )
        ],
        [
            InlineKeyboardButton(
                text="⚠️ Полная очистка данных (Zero-Knowledge)",
                callback_data="memory_wipe_confirm",
            )
        ],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_to_main"), get_close_button()],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_documents_list_keyboard(documents: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """
    Renders document list with individual delete buttons and file names.
    """
    buttons = []
    for doc in documents:
        fname = doc["file_name"]
        fhash = doc["file_hash"]
        chunks = doc["chunks_count"]
        # Limit button text length for Telegram
        btn_name = fname if len(fname) <= 25 else fname[:22] + "..."
        buttons.append([
            InlineKeyboardButton(
                text=f"🗑 Удалить: {btn_name} ({chunks}ч.)",
                callback_data=f"doc_del:{fhash}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад в память", callback_data="menu_memory"), get_close_button()])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_profile_keyboard(has_profile: bool = False) -> InlineKeyboardMarkup:
    """Builds personal profile action keyboard."""
    edit_text = "📝 Редактировать анкету" if has_profile else "📝 Заполнить анкету"
    buttons = [
        [InlineKeyboardButton(text="💎 Управление подпиской", callback_data="menu_subscription")],
        [InlineKeyboardButton(text=edit_text, callback_data="profile_edit")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_to_main"), get_close_button()],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_subscription_keyboard(plans: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Builds payment subscription buttons."""
    buttons = []
    for plan in plans:
        rub_amount = plan["price_amount"] // 100
        title = plan["title"]
        pid = plan["id"]
        buttons.append([
            InlineKeyboardButton(
                text=f"💳 {title} — {rub_amount} ₽",
                callback_data=f"buy_sub:{pid}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_to_main"), get_close_button()])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_keyboard(is_maintenance: bool = False) -> InlineKeyboardMarkup:
    """Builds administrative control panel keyboard."""
    m_status = "🔴 Выключить" if is_maintenance else "🟢 Включить"
    buttons = [
        [
            InlineKeyboardButton(text="📊 Общая статистика", callback_data="admin_stats"),
            InlineKeyboardButton(text="👥 Список подписчиков", callback_data="admin_subscribers"),
        ],
        [
            InlineKeyboardButton(text="📥 Экспорт в CSV (с BOM)", callback_data="admin_export_csv"),
            InlineKeyboardButton(text="📢 Рассылка сообщений", callback_data="admin_broadcast"),
        ],
        [
            InlineKeyboardButton(
                text=f"🛠 Режим обслуживания: {m_status}",
                callback_data="admin_toggle_maintenance",
            )
        ],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_to_main"), get_close_button()],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

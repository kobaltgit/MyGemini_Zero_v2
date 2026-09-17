"""
Reply Keyboard module for MyGemini Zero v2.
Provides persistent on-screen keyboard under the message input field.
Supports full bilingualism (Russian / English).
"""

from typing import Optional
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo,
)
from core.config import settings


def get_main_reply_keyboard(is_admin: bool = False, lang_code: str = "ru") -> ReplyKeyboardMarkup:
    """
    Builds persistent on-screen Reply keyboard for everyday bot interaction.
    Always visible under the text input bar (is_persistent=True).
    """
    if lang_code == "ru":
        btn_dialogs = "🗂️ Диалоги"
        btn_new_dlg = "➕ Новый диалог"
        btn_settings = "⚙️ Настройки"
        btn_profile = "👤 Личный кабинет"
        btn_docs = "📄 Документы"
        btn_reset = "🔄 Сброс контекста"
        btn_help = "❓ Помощь"
        btn_admin = "👑 Админка"
        placeholder = "Напишите сообщение или выберите раздел..."
    else:
        btn_dialogs = "🗂️ Dialogs"
        btn_new_dlg = "➕ New Dialog"
        btn_settings = "⚙️ Settings"
        btn_profile = "👤 Profile"
        btn_docs = "📄 Documents"
        btn_reset = "🔄 Reset Context"
        btn_help = "❓ Help"
        btn_admin = "👑 Admin"
        placeholder = "Write a message or choose a section..."

    keyboard = [
        [
            KeyboardButton(text=btn_dialogs),
            KeyboardButton(text=btn_new_dlg),
        ],
        [
            KeyboardButton(text=btn_settings),
            KeyboardButton(text=btn_profile),
        ],
        [
            KeyboardButton(text=btn_docs),
            KeyboardButton(text=btn_reset),
        ],
        [
            KeyboardButton(text=btn_help),
        ],
    ]

    if is_admin:
        keyboard[-1].append(KeyboardButton(text=btn_admin))

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=False,
        input_field_placeholder=placeholder,
    )


def get_locked_reply_keyboard(lang_code: str = "ru") -> ReplyKeyboardMarkup:
    """
    Builds Reply keyboard shown when vault is locked.
    Prominently displays WebApp modal button when WEBAPP_URL is configured.
    """
    if lang_code == "ru":
        btn_webapp = "🔐 Ввести пароль в окне"
        btn_chat_pwd = "⌨️ Ввести в чате"
        btn_help = "❓ Помощь"
        placeholder = "Сейф заблокирован. Разблокируйте память..."
    else:
        btn_webapp = "🔐 Enter password in window"
        btn_chat_pwd = "⌨️ Enter in chat"
        btn_help = "❓ Help"
        placeholder = "Vault is locked. Unlock memory..."

    buttons = []
    if settings.WEBAPP_URL:
        buttons.append([
            KeyboardButton(
                text=btn_webapp,
                web_app=WebAppInfo(url=f"{settings.WEBAPP_URL}?mode=unlock&lang={lang_code}"),
            )
        ])

    buttons.append([
        KeyboardButton(text=btn_chat_pwd),
        KeyboardButton(text=btn_help),
    ])

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        is_persistent=False,
        input_field_placeholder=placeholder,
    )


def get_setup_reply_keyboard(lang_code: str = "ru") -> ReplyKeyboardMarkup:
    """
    Builds Reply keyboard shown to new users during initial master password onboarding.
    Prominently displays WebApp modal setup button with password confirmation fields.
    """
    if lang_code == "ru":
        btn_webapp = "🔐 Установить пароль в окне"
        btn_chat_pwd = "⌨️ Ввести в чате"
        btn_help = "❓ Помощь"
        placeholder = "Установите мастер-пароль для шифрования..."
    else:
        btn_webapp = "🔐 Set password in window"
        btn_chat_pwd = "⌨️ Enter in chat"
        btn_help = "❓ Help"
        placeholder = "Set master password to encrypt..."

    buttons = []
    if settings.WEBAPP_URL:
        buttons.append([
            KeyboardButton(
                text=btn_webapp,
                web_app=WebAppInfo(url=f"{settings.WEBAPP_URL}?mode=setup&lang={lang_code}"),
            )
        ])

    buttons.append([
        KeyboardButton(text=btn_chat_pwd),
        KeyboardButton(text=btn_help),
    ])

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        is_persistent=False,
        input_field_placeholder=placeholder,
    )


"""
Reply Keyboard module for MyGemini Zero v2.
Provides persistent on-screen keyboard under the message input field.
"""

from typing import Optional
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo,
)
from core.config import settings


def get_main_reply_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """
    Builds persistent on-screen Reply keyboard for everyday bot interaction.
    Always visible under the text input bar (is_persistent=True).
    """
    keyboard = [
        [
            KeyboardButton(text="🗂️ Диалоги"),
            KeyboardButton(text="➕ Новый диалог"),
        ],
        [
            KeyboardButton(text="⚙️ Настройки"),
            KeyboardButton(text="👤 Личный кабинет"),
        ],
        [
            KeyboardButton(text="📄 Документы"),
            KeyboardButton(text="🔄 Сброс контекста"),
        ],
        [
            KeyboardButton(text="❓ Помощь"),
        ],
    ]

    if is_admin:
        keyboard[-1].append(KeyboardButton(text="👑 Админка"))

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Напишите сообщение или выберите раздел...",
    )


def get_locked_reply_keyboard() -> ReplyKeyboardMarkup:
    """
    Builds Reply keyboard shown when vault is locked.
    Telegram WebApp sendData natively works when opened from KeyboardButton.
    """
    buttons = []
    if settings.WEBAPP_URL:
        buttons.append([
            KeyboardButton(
                text="🔐 Ввести мастер-пароль (в окне)",
                web_app=WebAppInfo(url=f"{settings.WEBAPP_URL}?mode=password"),
            )
        ])

    buttons.append([KeyboardButton(text="⌨️ Ввести пароль в чате")])
    buttons.append([KeyboardButton(text="❓ Помощь")])

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Сейф заблокирован. Введите мастер-пароль...",
    )

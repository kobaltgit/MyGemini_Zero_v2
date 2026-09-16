"""
Personal Account & User Profile Service for MyGemini Zero v2.
Calculates user titles/ranks, message statistics, days active, subscription metrics,
and formats the personal account card.
"""

from datetime import datetime
from typing import Dict, Any, Optional
from cryptography.fernet import Fernet

from database.models.user import User
from core.config import settings


def get_user_rank(message_count: int) -> str:
    """Calculates user title/rank based on total sent messages."""
    if message_count >= 1000:
        return "👑 Легенда"
    elif message_count >= 250:
        return "🥇 Мастер общения"
    elif message_count >= 50:
        return "🥈 Ветеран чата"
    else:
        return "🥉 Новичок"


def format_account_card(
    user: User,
    message_count: int,
    profile_data: Optional[Dict[str, Any]] = None,
    is_vault_unlocked: bool = False,
) -> str:
    """
    Renders user profile and statistics card for 'Личный кабинет'.
    """
    rank = get_user_rank(message_count)
    now = datetime.now()

    # Days with bot
    reg_date_str = "—"
    days_active = 1
    date_field = user.first_interaction_date or (user.last_session_ts[:10] if user.last_session_ts else None)
    if date_field:
        try:
            reg_dt = datetime.strptime(date_field[:10], "%Y-%m-%d")
            days_active = max(1, (now.date() - reg_dt.date()).days + 1)
            reg_date_str = reg_dt.strftime("%d.%m.%Y")
        except Exception:
            reg_date_str = date_field[:10]

    # Subscription details
    is_admin = user.user_id == settings.ADMIN_USER_ID
    sub_days_left_str = ""
    is_sub_active = is_admin
    if user.subscription_end_date:
        try:
            end_dt = datetime.strptime(user.subscription_end_date[:10], "%Y-%m-%d")
            diff = (end_dt.date() - now.date()).days
            if diff >= 0:
                sub_days_left_str = f" (осталось {diff} дн.)"
                if user.subscription_status == "active":
                    is_sub_active = True
            else:
                sub_days_left_str = " (истекла)"
                is_sub_active = False
        except Exception:
            pass
    elif is_admin:
        is_sub_active = True

    sub_status_icon = "🟢" if is_sub_active else "⚪️"
    if is_admin:
        status_name = "Администратор (Бессрочно)"
    elif is_sub_active:
        status_name = "Активна"
    elif sub_days_left_str == " (истекла)":
        status_name = "Истекла"
    else:
        status_name = user.subscription_status.capitalize()

    sub_line = f"{sub_status_icon} <b>Подписка:</b> {status_name}{sub_days_left_str}"
    if not is_admin and user.subscription_end_date:
        sub_line += f"\n   • <b>Действует до:</b> {user.subscription_end_date[:10]}"

    # Model and API key
    model_name = user.gemini_model or "gemini-2.5-flash"
    api_key_status = "✅ Установлен (Zero-Knowledge)" if user.api_key else "❌ Используется общий серверный"

    lines = [
        f"👤 <b>Личный кабинет: {user.first_name or 'Пользователь'}</b>\n",
        f"🏆 <b>Звание:</b> {rank}",
        f"💬 <b>Всего сообщений:</b> {message_count}",
        f"🗓️ <b>С нами:</b> {days_active} дн. (с {reg_date_str})",
        "",
        sub_line,
        "",
        f"🤖 <b>Текущая модель:</b> <code>{model_name}</code>",
        f"🔑 <b>Личный API-ключ:</b> {api_key_status}",
    ]

    # Profile questionnaire section
    if profile_data:
        lines.append("\n📝 <b>Анкета пользователя:</b>")
        if profile_data.get("role"):
            lines.append(f"   • <b>Роль / Профессия:</b> {profile_data['role']}")
        if profile_data.get("field"):
            lines.append(f"   • <b>Сфера:</b> {profile_data['field']}")
        if profile_data.get("stack"):
            lines.append(f"   • <b>Стек / Инструменты:</b> {profile_data['stack']}")
        if profile_data.get("projects"):
            lines.append(f"   • <b>Текущие проекты:</b> {profile_data['projects']}")
        if profile_data.get("goals"):
            lines.append(f"   • <b>Цели общения:</b> {profile_data['goals']}")
    else:
        if is_vault_unlocked:
            lines.append("\nℹ️ <i>Анкета профиля ещё не заполнена. Заполните её, чтобы Gemini лучше понимал ваши задачи и контекст.</i>")
        else:
            lines.append("\n🔒 <i>Сейф заблокирован. Разблокируйте мастер-паролем для просмотра зашифрованной анкеты.</i>")

    return "\n".join(lines)

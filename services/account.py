"""
Personal Account & User Profile Service for MyGemini Zero v2.
Calculates user titles/ranks, message statistics, days active, subscription metrics,
and formats the personal account card in Russian or English.
"""

from datetime import datetime
from typing import Dict, Any, Optional
from database.models.user import User
from core.config import settings


def get_user_rank(message_count: int, lang_code: str = "ru") -> str:
    """Calculates user title/rank based on total sent messages."""
    if lang_code == "ru":
        if message_count >= 1000:
            return "👑 Легенда"
        elif message_count >= 250:
            return "🥇 Мастер общения"
        elif message_count >= 50:
            return "🥈 Ветеран чата"
        else:
            return "🥉 Новичок"
    else:
        if message_count >= 1000:
            return "👑 Legend"
        elif message_count >= 250:
            return "🥇 Master Communicator"
        elif message_count >= 50:
            return "🥈 Chat Veteran"
        else:
            return "🥉 Novice"


def format_account_card(
    user: User,
    message_count: int,
    profile_data: Optional[Dict[str, Any]] = None,
    is_vault_unlocked: bool = False,
    lang_code: str = "ru",
) -> str:
    """
    Renders user profile and statistics card for 'Личный кабинет'.
    """
    rank = get_user_rank(message_count, lang_code=lang_code)
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
    is_admin = (user.user_id == settings.ADMIN_USER_ID)
    sub_days_left_str = ""
    is_sub_active = is_admin
    if user.subscription_end_date:
        try:
            end_dt = datetime.strptime(user.subscription_end_date[:10], "%Y-%m-%d")
            diff = (end_dt.date() - now.date()).days
            if diff >= 0:
                sub_days_left_str = f" (осталось {diff} дн.)" if lang_code == "ru" else f" ({diff} days left)"
                if user.subscription_status == "active":
                    is_sub_active = True
            else:
                sub_days_left_str = " (истекла)" if lang_code == "ru" else " (expired)"
                is_sub_active = False
        except Exception:
            pass
    elif is_admin:
        is_sub_active = True

    sub_status_icon = "🟢" if is_sub_active else "⚪️"
    if is_admin:
        status_name = "Администратор (Бессрочно)" if lang_code == "ru" else "Administrator (Lifetime)"
    elif is_sub_active:
        status_name = "Активна" if lang_code == "ru" else "Active"
    elif "истекла" in sub_days_left_str or "expired" in sub_days_left_str:
        status_name = "Истекла" if lang_code == "ru" else "Expired"
    else:
        status_name = user.subscription_status.capitalize()

    sub_label = "Подписка:" if lang_code == "ru" else "Subscription:"
    valid_until_label = "Действует до:" if lang_code == "ru" else "Valid until:"
    sub_line = f"{sub_status_icon} <b>{sub_label}</b> {status_name}{sub_days_left_str}"
    if not is_admin and user.subscription_end_date:
        sub_line += f"\n   • <b>{valid_until_label}</b> {user.subscription_end_date[:10]}"

    # Model and API key
    model_name = user.gemini_model or "gemini-2.5-flash"
    if lang_code == "ru":
        api_key_status = "✅ Установлен (Zero-Knowledge)" if user.api_key else "❌ Не установлен"
        card_title = f"👤 <b>Личный кабинет: {user.first_name or 'Пользователь'}</b>\n"
        rank_line = f"🏆 <b>Звание:</b> {rank}"
        msg_line = f"💬 <b>Всего сообщений:</b> {message_count}"
        days_line = f"🗓️ <b>С нами:</b> {days_active} дн. (с {reg_date_str})"
        model_line = f"🤖 <b>Текущая модель:</b> <code>{model_name}</code>"
        key_line = f"🔑 <b>Личный API-ключ:</b> {api_key_status}"
    else:
        api_key_status = "✅ Set (Zero-Knowledge)" if user.api_key else "❌ Not set"
        card_title = f"👤 <b>Personal Profile: {user.first_name or 'User'}</b>\n"
        rank_line = f"🏆 <b>Rank:</b> {rank}"
        msg_line = f"💬 <b>Total Messages:</b> {message_count}"
        days_line = f"🗓️ <b>Member for:</b> {days_active} days (since {reg_date_str})"
        model_line = f"🤖 <b>Current Model:</b> <code>{model_name}</code>"
        key_line = f"🔑 <b>Personal API Key:</b> {api_key_status}"

    lines = [
        card_title,
        rank_line,
        msg_line,
        days_line,
        "",
        sub_line,
        "",
        model_line,
        key_line,
    ]

    # Profile questionnaire section (8 questions)
    if profile_data:
        q_title = "\n📝 <b>Анкета пользователя:</b>" if lang_code == "ru" else "\n📝 <b>User Questionnaire:</b>"
        lines.append(q_title)
        field_labels = {
            "role": ("Роль / Профессия", "Role / Profession"),
            "industry": ("Сфера", "Industry"),
            "projects": ("Проекты", "Projects"),
            "stack": ("Инструменты / Стек", "Tools / Stack"),
            "purpose": ("Цель использования", "Main Purpose"),
            "style": ("Стиль общения", "Communication Style"),
            "hobby": ("Хобби", "Hobbies"),
            "rules": ("Правила", "Rules"),
        }
        for f_key, (ru_lbl, en_lbl) in field_labels.items():
            val = profile_data.get(f_key)
            if val and val != "-":
                lbl = ru_lbl if lang_code == "ru" else en_lbl
                lines.append(f"   • <b>{lbl}:</b> {val}")
    else:
        if is_vault_unlocked:
            no_prof = (
                "\nℹ️ <i>Анкета профиля ещё не заполнена. Заполните её, чтобы Gemini лучше понимал ваши задачи и контекст.</i>"
                if lang_code == "ru"
                else "\nℹ️ <i>Profile questionnaire not filled yet. Fill it to give Gemini personal context.</i>"
            )
            lines.append(no_prof)
        else:
            locked_prof = (
                "\n🔒 <i>Сейф заблокирован. Разблокируйте мастер-паролем для просмотра зашифрованной анкеты.</i>"
                if lang_code == "ru"
                else "\n🔒 <i>Vault is locked. Unlock with master password to view encrypted questionnaire.</i>"
            )
            lines.append(locked_prof)

    return "\n".join(lines)

# File: services/calendar_helper.py

# Copyright (C) 2025-2026 kobaltgit
# AGPLv3 License

import datetime
from typing import Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from core.localization import get_text
from keyboards.inline import get_close_button

CALLBACK_CALENDAR_DATE_PREFIX = "calendar_date:"
CALLBACK_CALENDAR_MONTH_PREFIX = "calendar_month:"
CALLBACK_IGNORE = "calendar_ignore"


def create_calendar_keyboard(
    year: Optional[int] = None,
    month: Optional[int] = None,
    lang_code: str = "ru"
) -> InlineKeyboardMarkup:
    """
    Creates an interactive inline calendar keyboard for browsing conversation history by date.
    """
    now = datetime.datetime.now()
    year = year or now.year
    month = month or now.month

    try:
        first_day = datetime.date(year, month, 1)
    except ValueError:
        year, month = now.year, now.month
        first_day = datetime.date(year, month, 1)

    month_names_ru = [
        "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
    ]
    month_names_en = [
        "", "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]
    month_name = (
        f"{month_names_ru[month]} {year}"
        if lang_code == "ru"
        else f"{month_names_en[month]} {year}"
    )

    buttons = []
    # Header: Month & Year
    buttons.append([InlineKeyboardButton(text=f"📅 {month_name}", callback_data=CALLBACK_IGNORE)])

    # Days of week
    if lang_code == "ru":
        days_of_week = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    else:
        days_of_week = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]

    buttons.append([
        InlineKeyboardButton(text=day, callback_data=CALLBACK_IGNORE) for day in days_of_week
    ])

    # Calculate last day of the month
    if month == 12:
        next_first = datetime.date(year + 1, 1, 1)
    else:
        next_first = datetime.date(year, month + 1, 1)
    last_day_num = (next_first - datetime.timedelta(days=1)).day

    # Empty cells before 1st day (weekday(): 0 is Monday, 6 is Sunday)
    start_weekday = first_day.weekday()
    row_buttons = [InlineKeyboardButton(text=" ", callback_data=CALLBACK_IGNORE) for _ in range(start_weekday)]

    for day_num in range(1, last_day_num + 1):
        cur_date_str = f"{year:04d}-{month:02d}-{day_num:02d}"
        row_buttons.append(
            InlineKeyboardButton(
                text=str(day_num),
                callback_data=f"{CALLBACK_CALENDAR_DATE_PREFIX}{cur_date_str}"
            )
        )
        if len(row_buttons) == 7:
            buttons.append(row_buttons)
            row_buttons = []

    if row_buttons:
        while len(row_buttons) < 7:
            row_buttons.append(InlineKeyboardButton(text=" ", callback_data=CALLBACK_IGNORE))
        buttons.append(row_buttons)

    # Navigation buttons: Prev month, Next month
    prev_month_date = first_day - datetime.timedelta(days=1)
    prev_year, prev_month = prev_month_date.year, prev_month_date.month
    next_year, next_month = next_first.year, next_first.month

    nav_row = [
        InlineKeyboardButton(
            text="◀️",
            callback_data=f"{CALLBACK_CALENDAR_MONTH_PREFIX}{prev_year}-{prev_month:02d}"
        ),
        InlineKeyboardButton(
            text="▶️",
            callback_data=f"{CALLBACK_CALENDAR_MONTH_PREFIX}{next_year}-{next_month:02d}"
        ),
    ]
    buttons.append(nav_row)
    buttons.append([get_close_button(lang_code)])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

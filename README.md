# MyGemini Zero v2

> **Современный, приватный и высокопроизводительный Telegram-бот на базе Google Gemini с криптографической архитектурой Zero-Knowledge и асинхронным векторным поиском (RAG).**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![aiogram 3.x](https://img.shields.io/badge/aiogram-3.x-brightgreen.svg)](https://docs.aiogram.dev/)
[![Google GenAI SDK](https://img.shields.io/badge/Google%20GenAI-SDK%201.x-orange.svg)](https://github.com/google-gemini/generative-ai-python)
[![Zero-Knowledge](https://img.shields.io/badge/Security-Zero--Knowledge%20Fernet-red.svg)](#-архитектура-безопасности-zero-knowledge)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](LICENSE)

---

## Оглавление

1. [Главные отличия v2 от v1](#-главные-отличия-v2-от-v1-сравнение-версий)
2. [Ключевые возможности](#-ключевые-возможности)
3. [Архитектура безопасности (Zero-Knowledge)](#-архитектура-безопасности-zero-knowledge)
4. [Структура проекта](#-структура-проекта)
5. [Требования](#-требования)
6. [Быстрый старт (Локальная разработка)](#-быстрый-старт-локальная-разработка)
7. [Деплой на сервере (Linux / systemd)](#-деплой-на-сервере-linux--systemd)
8. [Деплой через Docker](#-деплой-через-docker)
9. [Автодеплой WebApp (GitHub Pages)](#-автодеплой-webapp-github-pages)
10. [Миграция со старой версии (v1)](#-миграция-со-старой-версии-v1)
11. [Тестирование](#-тестирование)

---

## Главные отличия v2 от v1 (Сравнение версий)

Версия v2 была полностью переписана с нуля для устранения архитектурных ограничений v1, при этом сохранив **100% совместимость** с существующей базой пользователей и векторной памятью.

| Характеристика | Версия 1 (MyGemini_Zero) | Версия 2 (MyGemini_Zero_v2) |
| :--- | :--- | :--- |
| **Telegram-движок** | Синхронный `telebot` (pyTelegramBotAPI) с ручными потоками | Современный асинхронный `aiogram 3.x` с FSM и чистой архитектурой роутеров |
| **Работа с базой данных** | Синхронный `sqlite3` с единой глобальной блокировкой (`db_lock`) | Полностью асинхронный `SQLAlchemy 2.0` (`aiosqlite`) с паттерном Repository |
| **Интеграция Gemini** | Устаревший `google-generativeai` / прямые HTTP-запросы | Официальный актуальный SDK `google-genai` (2025/2026) |
| **Поддерживаемые модели** | Старое поколение (`gemini-1.5-flash`, `gemini-1.5-pro`) | Полная линейка 2.5: `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-2.5-flash-lite`, `gemini-2.0-flash-thinking-exp` |
| **Поиск в сети (Grounding)** | Нестабильный, без индикации в интерфейсе | Автоматическое определение Google Search с бейджем в меню выбора |
| **Обработка квот (HTTP 429)** | Бот падает с ошибкой в чат | **Авто-Fallback:** прозрачное переключение на `gemini-2.5-flash-lite` без потери контекста |
| **Стриминг длинных ответов** | При ответе >4000 символов Telegram крашил бота (`Message is too long`) | **Smart Throttler:** порог 3200 символов, мягкое деление на абзацы, авто-закрытие Markdown-тегов |
| **Ввод мастер-пароля и ключа** | Только текстом в чат (секреты видны на экране) | **Telegram Mini App (WebApp)** с маскировкой •••••• + безопасный фолбэк на чат |
| **Защита от утечки ключей** | Отсутствовала | Regex-перехват случайно отправленных ключей `AIzaSy...` с удалением за 0.25 сек |
| **Управление RAG-памятью** | Только добавление документов в общую кучу | Интерактивное меню: список файлов текущего диалога с кнопками удаления конкретных документов |
| **Админ-панель** | Минимальная статистика | Детальная аналитика подписчиков, режим техработ и экспорт в CSV с UTF-8 BOM для Excel |
| **Криптография** | PBKDF2 (480k) + Fernet | Та же строгая математика: **100% бинарная совместимость** со всеми старыми данными |

---

## Ключевые возможности

* **Официальный Google GenAI SDK (2025/2026):**
  * Поддержка всех актуальных моделей: gemini-2.5-flash, gemini-2.5-pro, gemini-2.5-flash-lite, gemini-2.0-flash-thinking-exp.
  * Интеграция живого веб-поиска Google Search Grounding с наглядным бейджем в меню.
  * Интеллектуальный Fallback: при превышении квот (HTTP 429) бот автоматически и бесшовно переключается на облегчённую модель gemini-2.5-flash-lite.
* **Архитектура Zero-Knowledge (Нулевое разглашение):**
  * Сервер не хранит мастер-ключей и не имеет доступа к переписке и личным API-ключам пользователей.
  * Пароли хэшируются через **bcrypt**. Ключи шифрования выводятся в оперативной памяти через **PBKDF2-HMAC-SHA256 (480 000 итераций)** и шифруются **Fernet**.
  * Поддержка паник-пароля (экстренное стирание всех персональных диалогов) и автоблокировка хранилища по таймеру неактивности (1 час).
  * Анти-утечка ключей: регулярные выражения мгновенно перехватывают и удаляют случайно отправленные в чат токены AIzaSy....
* **Плавный безопасный стриминг (Smart Throttler):**
  * Генерация ответа в реальном времени с ограничением чанка в 3200 символов, предотвращающая падение Telegram по лимиту 4096 знаков.
  * Автоматическое закрытие незавершённых тегов форматирования Markdown при разбиении ответа на части.
* **Векторная память (RAG / ChromaDB):**
  * Асинхронное векторное хранилище на базе ChromaDB.
  * Загрузка документов (PDF, TXT, MD), семантический поиск релевантных контекстов перед отправкой запроса нейросети.
  * Полная совместимость с коллекциями диалогов v1.
* **Telegram Mini App (WebApp) или Чат-режим:**
  * Всплывающее окно для ввода паролей и API-ключей с маскировкой ••••••.
  * Если домен не настроен, бот автоматически переключается на чат с мгновенным автоудалением сообщений с секретами.
* **Панель администратора и Подписки:**
  * Управление режимом техработ (Maintenance Mode) и блокировками пользователей.
  * Просмотр детального списка подписчиков и выгрузка отчёта в CSV с корректным русским языком (UTF-8 BOM).

---

## Архитектура безопасности (Zero-Knowledge)

`
[Пользователь]
      │
      ├── Вводит мастер-пароль (в WebApp или в чат)
      ▼
[Оперативная память (RAM)]
      │
      ├── Salt из базы данных (16 байт) + Пароль
      ▼
[PBKDF2HMAC-SHA256 (480 000 итераций)] ──> [Временный 32-байтный ключ Fernet]
      │
      ├── Расшифровка личного Gemini API ключа и контекста диалогов
      ▼
[Таймер неактивности (1 час)] ──> Ключ удаляется из памяти (RAM Purge)
`

> **Важно:** Файл .env **не содержит** мастер-ключей шифрования. Даже при полном взломе сервера базы данных данные остаются надёжно защищены стойкой криптографией.

---

## Структура проекта

`	ext
MyGemini_Zero_v2/
├── .github/
│   └── workflows/
│       └── deploy-pages.yml # Автодеплой WebApp на GitHub Pages
├── core/                   # Ядро системы
│   ├── config.py           # Настройки pydantic-settings, модели, цены
│   ├── crypto.py           # Zero-Knowledge: bcrypt, PBKDF2 (480k), Fernet
│   ├── database.py         # Асинхронный SQLAlchemy движок и SessionFactory
│   └── logger.py           # Ротация логов и цветной вывод
├── database/               # Модели данных и репозитории
│   ├── models/             # User, Dialog, Conversation, UserProfile, etc.
│   └── repositories/       # Асинхронные репозитории для работы с БД
├── handlers/               # Обработчики сообщений и команд aiogram 3
│   ├── admin.py            # Админ-панель, CSV-экспорт, рассылка
│   ├── auth.py             # Вход, регистрация, паник-пароль, WebApp Data
│   ├── chat.py             # Диалог с Gemini, голос, фото, документы
│   ├── dialogs.py          # Список и переключение диалогов
│   ├── memory.py           # Просмотр и удаление документов RAG
│   ├── settings.py         # Выбор моделей, стилей общения, ввод ключа
│   ├── start.py            # Команда /start и главное меню
│   └── subscription.py     # Тарифные планы и оплата
├── keyboards/              # Клавиатуры Telegram (Inline & Reply)
│   └── inline.py           # Интерактивные меню, бейджи моделей, WebApp
├── middlewares/            # Промежуточные слои aiogram
│   ├── antispam.py         # Перехват утечек API-ключей и спама
│   └── auth.py             # Менеджер сессий, тайм-аут замка, техработы
├── services/               # Внешние интеграции и логика
│   ├── gemini.py           # Google GenAI SDK (стриминг, поиск, 429 fallback)
│   ├── media.py            # Обработка фото, аудио и документов
│   ├── throttler.py        # Умный сплиттер ответов MarkdownV2 (3200 симв.)
│   └── vector_store.py     # Асинхронная обёртка ChromaDB RAG
├── webapp/                 # Статика для Telegram Mini App
│   └── index.html          # Модальное окно безопасного ввода пароля
├── docs/                   # Зеркало для публикации через GitHub Pages
│   └── index.html          # Готово для бесплатного хостинга WebApp
├── tracking/               # Летопись разработки и чек-листы
│   ├── CHECKLIST.md        # Статус всех задач проекта
│   └── DEVLOG.md           # Авторский дневник разработки
├── tests/                  # Автотесты
│   └── test_e2e.py         # Полный E2E-тест боевой базы данных и криптографии
├── .env.example            # Пример переменных окружения
├── .gitignore              # Исключение БД, ключей, логов и кэша
├── Dockerfile              # Мультистейдж сборка контейнера
├── docker-compose.yml      # Оркестрация с персистентными volume
├── requirements.txt        # Зависимости Python
└── main.py                 # Точка входа: long-polling и graceful shutdown
`

---

## Требования

* **Python:** 3.11 или новее
* **ОС:** Linux (Ubuntu 20.04/22.04/24.04 рекомендуется), macOS или Windows
* **Telegram Bot Token:** полученный у [@BotFather](https://t.me/BotFather)

---

## Быстрый старт (Локальная разработка)

### 1. Клонирование и установка зависимостей
`ash
git clone https://github.com/your-username/MyGemini_Zero_v2.git
cd MyGemini_Zero_v2

# Создание виртуального окружения
python -m venv venv

# Активация:
# На Linux / macOS:
source venv/bin/activate
# На Windows:
venv\Scripts\activate

# Установка пакетов
pip install --upgrade pip
pip install -r requirements.txt
`

### 2. Настройка переменных окружения
Скопируйте пример файла конфигурации:
`ash
cp .env.example .env
`
Откройте .env и укажите обязательные параметры:
`ini
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ
ADMIN_USER_ID=123456789
`

### 3. Запуск бота
`ash
python main.py
`

---

## Деплой на сервере (Linux / systemd)

Рекомендуемый способ запуска в продакшене — как системная служба с возможностью мгновенного переключения и отката.

### Шаг 1. Размещение на сервере
Склонируйте или загрузите проект рядом со старой версией:
`ash
cd /home/user/MyGemini_Zero_v2
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env # или скопируйте рабочий .env из старого бота
`

### Шаг 2. Создание systemd unit-файла
Создайте файл /etc/systemd/system/mygemini-v2.service:
`ash
sudo nano /etc/systemd/system/mygemini-v2.service
`
Вставьте конфигурацию (замените user на имя вашего пользователя в Linux):
`ini
[Unit]
Description=MyGemini Zero v2 Telegram Bot
After=network.target

[Service]
Type=simple
User=user
WorkingDirectory=/home/user/MyGemini_Zero_v2
ExecStart=/home/user/MyGemini_Zero_v2/venv/bin/python main.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
`

Примените конфигурацию:
`ash
sudo systemctl daemon-reload
`

### Шаг 3. Переключение на новую версию
Остановите старую службу и запустите v2:
`ash
sudo systemctl stop mygemini && sudo systemctl start mygemini-v2
`

Проверьте логи в реальном времени:
`ash
journalctl -u mygemini-v2 -f
`

Если всё работает штатно, включите автозапуск v2:
`ash
sudo systemctl enable mygemini-v2
sudo systemctl disable mygemini
`

### Мгновенный откат (Rollback)
Если потребуется срочно вернуть прежнюю версию бота:
`ash
sudo systemctl stop mygemini-v2 && sudo systemctl start mygemini
`

---

## Деплой через Docker

Проект полностью упакован в Docker:

`ash
# Сборка и запуск в фоновом режиме
docker compose up -d --build

# Просмотр логов
docker compose logs -f

# Остановка
docker compose down
`
База данных SQLite и векторное хранилище монтируются через тома (volumes) в ./database и ./vector_store, сохраняя данные при перезапусках.

---

## Автодеплой WebApp (GitHub Pages)

В проект встроен GitHub Actions workflow (.github/workflows/deploy-pages.yml), который **автоматически развертывает страницу WebApp при каждом коммите/пуше**.

### Как включить:
1. Залейте репозиторий на **GitHub**.
2. В репозитории откройте: **Settings** -> **Pages**.
3. В выпадающем меню **Source** переключите на:
   * **GitHub Actions**
4. При каждом пуше в ветку main GitHub автоматически опубликует страницу.
5. Скопируйте полученную ссылку (например, https://username.github.io/MyGemini_Zero_v2/) и укажите её в .env:
   `ini
   WEBAPP_URL=https://username.github.io/MyGemini_Zero_v2/
   `
6. Перезапустите бота. Готово!

---

## Миграция со старой версии (v1)

Версия v2 создана со строгим соблюдением **100% бинарной и алгоритмической совместимости**:
* Используется та же схема SQLite-базы ot_database.db.
* Алгоритм шифрования PBKDF2 строго зафиксирован на **480 000 итераций**, что гарантирует корректную расшифровку старых паролей и API-ключей пользователей.
* Структура ChromaDB ector_store/ полностью считывается без переиндексации.

---

## Тестирование

Для проверки работоспособности базы, криптографических функций и моделей запустите E2E-тест:
`ash
pytest tests/test_e2e.py -v
`

---

## Лицензия

Этот проект распространяется под лицензией **GNU AGPL v3**. Подробности в файле [LICENSE](LICENSE).

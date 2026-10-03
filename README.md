# MyGemini Zero v2

<p align="center">
  <b>Modern, Private, High-Performance Telegram Bot powered by Google Gemini, Zero-Knowledge Cryptography, and Async RAG.</b>
</p>

<p align="center">
  <a href="https://t.me/mgemz_bot">
    <img src="https://img.shields.io/badge/🤖%20Try%20it%20now-@mgemz__bot-0088cc?style=for-the-badge&logo=telegram&logoColor=white" alt="Try Bot on Telegram">
  </a>
</p>

<p align="center">
  <b>🇬🇧 English version</b> •
  <a href="README_RU.md">🇷🇺 Русская версия</a>
</p>

<p align="center">
  <a href="https://t.me/mgemz_bot"><img src="https://img.shields.io/badge/Telegram%20Bot-@mgemz__bot-2CA5E0.svg?style=flat-square&logo=telegram&logoColor=white" alt="Telegram Bot"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11+-3776AB.svg?style=flat-square&logo=python&logoColor=white" alt="Python 3.11+"></a>
  <a href="https://docs.aiogram.dev/"><img src="https://img.shields.io/badge/aiogram-3.x-2CA5E0.svg?style=flat-square&logo=telegram&logoColor=white" alt="aiogram 3.x"></a>
  <a href="https://github.com/google-gemini/generative-ai-python"><img src="https://img.shields.io/badge/Google%20GenAI-SDK%201.x-4285F4.svg?style=flat-square&logo=google&logoColor=white" alt="Google GenAI SDK"></a>
  <a href="https://pypi.org/project/tg-rich-converter/"><img src="https://img.shields.io/badge/Rich%20Formatting-tg--rich--converter-8A2BE2.svg?style=flat-square" alt="tg-rich-converter"></a>
  <a href="#zero-knowledge-security-architecture"><img src="https://img.shields.io/badge/Security-Zero--Knowledge%20Fernet-critical.svg?style=flat-square" alt="Zero-Knowledge"></a>
  <a href="tests/"><img src="https://img.shields.io/badge/Tests-136%20passed-success.svg?style=flat-square&logo=pytest&logoColor=white" alt="136 tests passed"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-AGPL%20v3-blue.svg?style=flat-square" alt="License: AGPL v3"></a>
</p>

> 🤖 **Active Production Bot:** MyGemini Zero v2 powers the official production bot: **[@mgemz_bot](https://t.me/mgemz_bot)**.  
> 📦 **Legacy Version 1.0 Repository:** [kobaltgit/MyGemini_Zero](https://github.com/kobaltgit/MyGemini_Zero).  
> 🆓 **Free Alternative (without ZK/RAG):** [@mgem_bot](https://t.me/mgem_bot).

---

## 🚀 Live Telegram Bot

Experience the bot right now without setting up your own infrastructure:

👉 **[Open @mgemz_bot on Telegram](https://t.me/mgemz_bot)** 👈

---

## Table of Contents

1. [Why MyGemini Zero? (The Concept)](#why-mygemini-zero-the-concept)
2. [Key Differences: v1 vs v2](#key-differences-v1-vs-v2)
3. [Key Features](#key-features)
4. [Zero-Knowledge Security Architecture](#zero-knowledge-security-architecture)
5. [Project Structure](#project-structure)
6. [Requirements](#requirements)
7. [Quick Start (Local Development)](#quick-start-local-development)
8. [Production Deployment (Linux / systemd)](#production-deployment-linux--systemd)
9. [Docker Deployment](#docker-deployment)
10. [Telegram Mini App Auto-Deploy (GitHub Pages)](#telegram-mini-app-auto-deploy-github-pages)
11. [Migration from v1](#migration-from-v1)
12. [Testing](#testing)
13. [License](#license)

---

## Why MyGemini Zero? (The Concept)

Standard neural network chats suffer from **digital amnesia**: they forget your projects and personal context as soon as the session ends. Moreover, third-party intermediary bots force you to trust their databases with your unencrypted prompts and private API keys.

**MyGemini Zero** solves both problems through two foundational pillars:

### 1. Memory: Your Personal "Second Brain"
Integrated with an isolated vector database (ChromaDB), the bot turns conversations, notes, and uploaded documents into persistent knowledge. Before asking Google Gemini, the bot automatically retrieves relevant context from your dialogue memory. You can ask: *"What were the risks in the marketing campaign we discussed two weeks ago?"* and the bot recalls the specifics immediately.

### 2. Zero-Knowledge Cryptography (Absolute Privacy)
Your data, dialogue history, and Google API keys are encrypted on-the-fly using a **master password** known **only to you**.
* **Zero Trust in Intermediaries:** Even service administrators mathematically cannot inspect your private data.
* **Ephemeral RAM Keys:** Encryption keys exist exclusively in server memory during your active session and vanish when the timer expires.
* **Panic Password:** In an emergency, entering your designated panic password silently and irreversibly purges your dialogues, vector memories, and private keys (plausible deniability).

### 3. Bring Your Own Key (BYOK) & Open Source
* The bot operates on your personal Google Gemini API key (via Google AI Studio free tier or paid quota). We never mark up token costs.
* The codebase is 100% open under the **AGPLv3** license. You can use the hosted service 24/7 or deploy it on your own server for free.

---

## Key Differences: v1 vs v2

Version 2 was rebuilt from the ground up to eliminate all architectural bottlenecks of v1 while guaranteeing **100% backward binary compatibility** with existing user databases, master passwords, and vector memory.

| Feature | Version 1 (MyGemini_Zero) | Version 2 (MyGemini_Zero_v2) |
| :--- | :--- | :--- |
| **Telegram Framework** | Synchronous `telebot` (pyTelegramBotAPI) with manual threading | Modern asynchronous `aiogram 3.x` with FSM, routers, and middlewares |
| **Database Engine** | Synchronous `sqlite3` with a single global lock (`db_lock`) | Fully async `SQLAlchemy 2.0` (`aiosqlite`) with Repository pattern |
| **Gemini Integration** | Deprecated `google-generativeai` / raw HTTP calls | Official `google-genai` SDK (2025/2026) with native streaming & tools |
| **Supported Models** | Legacy models (`gemini-1.5-flash`, `gemini-1.5-pro`) | Full 2.5 lineup: `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-2.5-flash-lite`, `gemini-2.0-flash-thinking-exp` |
| **Message Formatting** | Limited MarkdownV2 (4,096 char limit, frequent entity parse crashes) | **Telegram 10.1+ Rich Messages (`tg-rich-converter`):** native tables, LaTeX/KaTeX math, `<think>` spoilers, up to 32,768 characters per message |
| **Quick Actions in Chat** | None | Buttons under response: `[🔄 Regenerate]`, `[↩️ Undo Step]`, `[📥 Export Dialogue]`, `[⏹️ Stop]` |
| **Python Sandbox** | None | **Isolated Sandbox `[🐍 To Sandbox]`:** clean-slate calculations executed in Google Cloud interpreter with zero hallucinations |
| **Thinking Budget** | None | **Thinking Budget Config:** adjustable depth for Gemini 2.5 (⚡ Instant / ⚖️ Balanced / 🔬 Deep Analysis) |
| **Quota HUD** | None | **Speed & Token HUD:** live speed and exact token counter (`⚡ 3.3s • 📊 1221 tokens`) |
| **ZK Session TTL** | Fixed at 1 hour | **Configurable TTL:** 15 min, 1 hour, 8 hours, 24 hours in Settings |
| **Web Search Grounding** | Unstable, no interface badge | Automatic Google Search detection with badge in model selector |
| **Quota Fallback (HTTP 429)**| Crashes bot with error message in chat | **Multi-tier Fallback:** graceful fallback to `gemini-2.5-flash` preserving tools and transparent footnote |
| **Password & Key Input** | Plain text only in chat (secrets visible on screen) | **Telegram Mini App (WebApp)** with •••••• masking + instant 0.25s chat intercept fallback |
| **Key Leak Prevention** | None | Regex interception of accidental `AIzaSy...` key messages with immediate purge |
| **RAG Memory Inspector** | Append-only files in single collection | Interactive menu: file list of current dialogue with selective chunk and file deletion |
| **Admin Dashboard** | Minimal stats | Comprehensive subscriber analytics, maintenance mode, and Excel CSV export (UTF-8 BOM) |
| **Cryptography** | PBKDF2 (480k) + Fernet | Identical strict mathematics: **100% binary backward compatibility** with existing databases |

---

## Key Features

* **Official Google GenAI SDK (2025/2026):**
  * Full support for flagship Gemini models: `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-2.5-flash-lite`.
  * Integrated real-time Google Search Grounding with indicator badge.
  * **Multi-tier HTTP 429 Recovery:** when primary model quota is reached, requests seamlessly transition to `gemini-2.5-flash` retaining tool capabilities, accompanied by a discreet footnote.
  * **Thinking Budget:** customize reasoning token allocation (0 for instant responses, 1024 for balance, 4096 for deep analysis).
* **Telegram 10.1+ Rich Messages & High-Speed Streaming:**
  * Powered by `tg-rich-converter`: native `<table bordered striped>` tables, LaTeX/KaTeX `<tg-math>` formulas, collapsible `<details><summary>` reasoning blocks.
  * Output ceiling expanded to **32,768 characters** (bypassing legacy 4,096 char limits).
  * Smooth 0.8-second streaming with automatic cascade fallback to plain text upon formatting edge cases.
  * User-selectable format (Rich 10.1+ vs Classic MarkdownV2) in `/settings`.
* **Interactive Quick Actions Under Assistant Responses:**
  * `[⏹️ Stop]` during active streaming — instantly cancels generation to conserve BYOK tokens.
  * `[🔄 Regenerate]` — deletes the last assistant turn and re-runs generation on the same prompt.
  * `[↩️ Undo Step]` — atomically removes the last turn (prompt + answer) from encrypted SQLite storage.
  * `[📥 Export Dialogue]` — instantly generates and sends a clean Markdown `.md` export of the active conversation.
* **Dedicated Isolated Python Sandbox (100% Computational Precision):**
  * Triggered via `[🐍 To Sandbox]` button beneath assistant messages.
  * **Clean-slate processing:** isolates prompt from past conversation history to eliminate in-context imitation and hallucinations.
  * Code runs in Google Cloud's secure Python runtime for exact mathematics, primes, combinatorics, and text frequency analysis.
  * Results and user prompts seamlessly persist back into active dialogue history upon completion.
* **Zero-Knowledge Security Architecture:**
  * Server mathematically cannot access conversation history or personal API keys without active user session.
  * Master passwords hashed with **bcrypt**. Cryptographic keys derived in RAM via **PBKDF2-HMAC-SHA256 (480,000 iterations)** into temporary **Fernet** instances.
  * Panic password triggers silent emergency wipe of personal user records.
  * Configurable session TTL (15m, 1h, 8h, 24h) with automatic RAM purge on timeout.
  * Leak protection: regex filter catches and immediately deletes unencrypted `AIzaSy...` API keys within 0.25 seconds.
* **Token & Speed HUD (BYOK Transparency):**
  * Real-time metadata in header: `⚡ 3.3s • 📊 1221 tokens (Prompt: 120, Gen: 1101)` providing full visibility into Google AI Studio quota consumption.
* **Async RAG & Multimodal Memory (ChromaDB):**
  * Dialogue-isolated vector collections (`dialog_{id}`).
  * Ingests **PDF, DOCX, CSV, TXT, MD**, voice audio, and photos.
  * Memory Inspector: inspect indexed files and selectively delete document chunks.
* **Telegram Mini App (WebApp) or Chat Auth:**
  * Secure modal window for password and API key entry with •••••• visual masking.
  * Automatic fallback to encrypted chat entry with instant 0.25s deletion if WebApp is not configured.
* **Administration & Billing:**
  * Subscription management with native Telegram Payments API support.
  * Maintenance mode toggle, user block/unblock, and UTF-8 BOM CSV subscriber export.

---

## Zero-Knowledge Security Architecture

```text
[User]
   │
   ├── Enters master password (via WebApp modal or instant-delete chat)
   ▼
[Server RAM (Ephemeral)]
   │
   ├── Salt from SQLite database (16 bytes) + Password
   ▼
[PBKDF2-HMAC-SHA256 (480,000 iterations)] ──> [32-byte Fernet Key]
   │
   ├── Decrypts personal Gemini API key & dialogue messages on-the-fly
   ▼
[Configurable Inactivity Timer (15m / 1h / 8h / 24h)] ──> RAM Cleared (Zero Residue)
```

> **Security Note:** The `.env` configuration file **never** stores master encryption keys. In the event of a total server or database dump, all stored data remains protected by military-grade AES encryption.

#### Transparency Note: Vector Storage (RAG)
Vector collections store chunk texts in isolated ChromaDB partitions (`dialog_{dialog_id}`) to enable semantic search and exact keyword matching. While conversation transcripts and API keys in SQLite are fully Fernet-encrypted, RAG partitions contain no identifiers directly associating text chunks with specific user identities.

---

## Project Structure

```text
MyGemini_Zero_v2/
├── .github/
│   └── workflows/
│       └── deploy-pages.yml         # GitHub Pages automated WebApp deployment
├── core/                           # System core
│   ├── config.py                   # Pydantic settings, model registry, styles
│   ├── crypto.py                   # Zero-Knowledge: bcrypt, PBKDF2 (480k), Fernet
│   ├── database.py                 # Async SQLAlchemy engine & session factory
│   ├── localization.py             # Full i18n localization module (RU / EN)
│   ├── ui_helpers.py               # Safe edit message, spinner dismiss, modals
│   └── logger.py                   # Structured log rotation
├── database/                       # Data layer
│   ├── models/                     # User, Dialog, Conversation, UserProfile
│   └── repositories/               # Async repository implementations
├── guides/                         # Interactive user guides (RU / EN)
│   ├── full_guide_ru.md
│   └── full_guide_en.md
├── handlers/                       # aiogram 3 routers
│   ├── admin.py                    # Admin panel, CSV exports, user management
│   ├── auth.py                     # ZK onboarding, unlock, panic password, WebApp
│   ├── chat.py                     # Streaming chat, vision, voice, isolated sandbox
│   ├── commands.py                 # Bot commands and unified service menu
│   ├── dialogs.py                  # Dialogue lifecycle and Markdown export
│   ├── feedback.py                 # Feedback and bug reporting
│   ├── guide.py                    # Multi-chapter user manual (/guide)
│   ├── history.py                  # Daily conversation history with inline calendar
│   ├── memory.py                   # RAG document inspector and memory deletion
│   ├── profile.py                  # User account and structured profile questionnaire
│   ├── settings.py                 # Models, styles, language, TTL, thinking budget
│   ├── start.py                    # /start onboarding flow
│   ├── subscription.py             # Plans, Telegram Payments, invoices
│   └── translate.py                # Dedicated instant translator (/translate)
├── keyboards/                      # Telegram keyboards (Inline & Reply)
│   ├── inline.py                   # Dynamic menus, quick actions, TTL, sandbox
│   └── reply.py                    # Collapsible bottom navigation
├── middlewares/                    # aiogram middlewares
│   ├── antispam.py                 # Key leak prevention and rate limiting
│   ├── auth.py                     # Session manager, dynamic TTL, language injector
│   └── logging.py                  # Structured update logging
├── services/                       # Integrations & domain services
│   ├── account.py                  # User status formatting
│   ├── calendar_helper.py          # Interactive inline calendar generator
│   ├── dialog_namer.py             # Autonomous dialogue title generator
│   ├── error_parser.py             # Gemini API error mapper (429, 503, safety)
│   ├── gemini.py                   # Google GenAI SDK (streaming, tools, multi-tier fallback)
│   ├── guide_manager.py            # Guide chapter pagination manager
│   ├── media.py                    # Audio, photo, and document parsing
│   ├── throttler.py                # Smart rich throttler (tables, KaTeX, spoilers)
│   └── vector_store.py             # Async ChromaDB RAG adapter
├── webapp/                         # Telegram Mini App static assets
│   └── index.html                  # Password masking modal dialog
├── docs/                           # GitHub Pages distribution mirror
│   └── index.html                  # Zero-configuration WebApp hosting
├── tracking/                       # Project management & chronicles
│   ├── BUGS.md                     # Bug registry
│   ├── BUG_TRACKER.md              # Root cause analysis (RCA) log
│   ├── CHECKLIST.md                # Development checklist
│   ├── DEVLOG.md                   # Author devlog & engineering chronicle
│   ├── FEATURE_IDEAS.md            # Feature bank & ZK compatibility audit
│   └── ROADMAP.md                  # Development roadmap
├── tests/                          # Automated test suite (136 unit tests, 100% pass)
│   ├── test_crypto.py              # Cryptography tests (PBKDF2, Fernet, bcrypt)
│   ├── test_e2e.py                 # End-to-end database & crypto tests
│   ├── test_fixes_and_i18n.py      # Localization, UI helpers, calendar, commands
│   ├── test_middlewares_and_i18n.py# Antispam, Auth middleware, language injection
│   ├── test_new_features.py        # v2.1 feature tests (WebApp, key interception)
│   ├── test_phase2_backend.py      # Phase 2 backend (dynamic TTL, token HUD)
│   ├── test_repositories.py        # Async SQLAlchemy repositories
│   ├── test_services.py            # GeminiService, 429 fallback, RAG search
│   ├── test_throttler.py           # Rich streaming, tables, KaTeX, retry cascade
│   ├── test_ui_phase1.py           # Quick actions and thinking budget keyboards
│   ├── test_ui_phase2.py           # Isolated sandbox mode and session TTL
│   └── test_v1_compatibility.py    # Backward compatibility with v1 data
├── .env.example                    # Environment template
├── .gitignore                      # Leak prevention and exclusions
├── Dockerfile                      # Multi-stage production container
├── docker-compose.yml              # Container orchestration with volumes
├── mygemini-v2.service             # Production systemd unit file for Linux
├── requirements.txt                # Python dependencies
└── main.py                         # Application entrypoint & graceful shutdown
```

---

## Requirements

* **Python:** 3.11 or newer
* **OS:** Linux (Ubuntu 20.04/22.04/24.04 recommended), macOS, or Windows
* **Telegram Bot Token:** obtained from [@BotFather](https://t.me/BotFather)

---

## Quick Start (Local Development)

### 1. Clone Repository & Setup Virtual Environment
```bash
git clone https://github.com/kobaltgit/MyGemini_Zero_v2.git
cd MyGemini_Zero_v2

# Create virtual environment
python -m venv .venv

# Activate:
# On Linux / macOS:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy template configuration:
```bash
cp .env.example .env
```
Edit `.env` with your credentials:
```ini
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ
ADMIN_USER_ID=123456789
```

### 3. Run the Bot
```bash
python main.py
```

---

## Production Deployment (Linux / systemd)

Running as a systemd service is recommended for 24/7 reliability and seamless zero-downtime rollbacks.

### Step 1. Place Project on Host
```bash
cd /opt/MyGemini_Zero_v2
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Step 2. Configure systemd Service
A production unit file is provided at [mygemini-v2.service](mygemini-v2.service):
```bash
sudo cp mygemini-v2.service /etc/systemd/system/mygemini-v2.service
sudo nano /etc/systemd/system/mygemini-v2.service
sudo systemctl daemon-reload
```

### Step 3. Switch Service
```bash
# Stop old bot service and start v2
sudo systemctl stop mygemini && sudo systemctl start mygemini-v2

# Check live logs
journalctl -u mygemini-v2 -f

# Enable auto-start on boot
sudo systemctl enable mygemini-v2
```

---

## Docker Deployment

Deploy with Docker Compose:

```bash
# Build and run detached
docker compose up -d --build

# View logs
docker compose logs -f

# Stop container
docker compose down
```
Persistent data volumes are mapped to `./database` and `./vector_store`.

---

## Telegram Mini App Auto-Deploy (GitHub Pages)

The repository includes a ready-to-use GitHub Actions workflow (`.github/workflows/deploy-pages.yml`) that publishes the WebApp on every push to `main`.

1. Go to repository **Settings** -> **Pages**.
2. Under **Build and deployment** -> **Source**, select **GitHub Actions**.
3. Push to `main`.
4. Copy published URL (e.g. `https://<username>.github.io/MyGemini_Zero_v2/`) and specify in `.env`:
   ```ini
   WEBAPP_URL=https://<username>.github.io/MyGemini_Zero_v2/
   ```
5. Restart bot.

---

## Migration from v1

Version 2 maintains **100% binary and algorithmic compatibility**:
* Automatically mounts existing SQLite `bot_database.db`.
* PBKDF2 derivation is locked at **480,000 iterations**, ensuring previous master passwords and API keys unlock seamlessly.
* ChromaDB `vector_store/` collections load directly without re-indexing.

---

## Testing

The codebase is covered by **136 automated unit tests** (Zero-Knowledge crypto, Rich streaming, async SQLAlchemy repositories, Gemini SDK error handling, isolated Python sandbox, and keyboards):

```bash
# Run full test suite
pytest

# Or via Python with verbose output
python -m pytest -v
```

---

## License

This project is licensed under the **GNU AGPL v3**. See [LICENSE](LICENSE) for details.

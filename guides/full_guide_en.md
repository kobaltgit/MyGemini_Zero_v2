# 📖 Complete Guide to MyGemini Zero v2

Welcome! This interactive guide will help you explore and master all the features of your personal Zero-Knowledge AI assistant.

---

# [START OF SECTION: ZERO_KNOWLEDGE]

🔐 <b>Security & Zero-Knowledge Architecture</b>

MyGemini Zero v2 is built on the principle of complete privacy: <b>no one, including bot developers and server administrators, can read your dialogues, documents, or API keys</b>.

<b>1. Master Password:</b>
• <b>We do not store your password:</b> The database only stores a cryptographic salted hash. It is mathematically impossible to reconstruct the original password from it.
• <b>On-the-fly encryption:</b> Each time you unlock the vault, an ephemeral symmetric <code>Fernet</code> encryption key is generated in server RAM. It exists solely in volatile memory and is instantly erased when locked or after 1 hour of inactivity.
• ⚠️ <b>IMPORTANT:</b> If you forget your master password, recovering your conversation history is <b>impossible</b>. There is no password reset mechanism, ensuring true Zero-Knowledge security.

<b>2. Anti-Spying & Clean Chat:</b>
• Password entry is performed via a secure Telegram Mini App modal popup masked with dots <code>••••••</code>. Secrets never remain in your chat history.
• If you enter secrets in regular chat, the bot automatically deletes your message within fractions of a second.

<b>3. Panic Password (Emergency Wipe):</b>
For extreme situations, you can configure an emergency "Panic Password" (in «⚙️ Settings» ➡️ «🚨 Setup Panic Password»):
• If you enter this panic password at unlock instead of your master password, the bot will <b>instantly and permanently wipe</b> all dialogues, messages, vector documents, and keys from the database.
• This provides "plausible deniability" to protect your data in critical circumstances.

# [END OF SECTION: ZERO_KNOWLEDGE]

---

# [START OF SECTION: API_KEY]

🔑 <b>How to Get and Set Your Google Gemini API Key</b>

An API key is your personal credential for the Google Gemini neural network. Using your own API key provides maximum speed, higher limits, and direct access to the latest models.

<b>1. Step-by-Step Instructions:</b>
1. Navigate to Google AI Studio: <a href="https://aistudio.google.com/app/apikey">https://aistudio.google.com/app/apikey</a>.
2. Sign in with your Google account.
3. Click the blue button <b>«Create API Key»</b> (or «Create API key in new project»).
4. Copy your newly generated key (it starts with <code>AIzaSy...</code>).

ℹ️ <i>Note: If Google AI Studio is unavailable in your region, use a secure network connection to access Google services.</i>

<b>2. Setting the Key in the Bot:</b>
1. Open «⚙️ Settings» ➡️ «🔑 API Key» in the bot (or use the <code>/apikey_info</code> command).
2. Choose modal window entry or send the key directly in chat.
3. The message containing your key will be instantly deleted, and the key will be encrypted with your master password (Zero-Knowledge) before storing.

# [END OF SECTION: API_KEY]

---

# [START OF SECTION: RAG]

📎 <b>Vector Document Memory (RAG)</b>

<b>RAG (Retrieval-Augmented Generation)</b> turns the bot into a knowledgeable expert on your personal documents and notes.

<b>1. How to Upload a Document:</b>
• Send a document file to the chat (supported formats: <b>PDF, TXT, MD, DOCX</b>).
• The bot automatically extracts the text, splits it into semantic chunks, and builds vector embeddings in a local <b>ChromaDB</b> store.

<b>2. How RAG Works During Conversations:</b>
• When you ask a question about your document, the bot instantly retrieves the most relevant excerpts and injects them as factual context for the Gemini model.
• The model generates accurate, fact-based answers with citations from your material.

<b>3. Managing Files («📄 Documents»):</b>
• In the bottom reply menu, tap «📄 Documents» (or use the <code>/documents</code> command).
• View all uploaded files, chunk counts, and upload dates.
• Delete any document with a single tap on «🗑 Delete» to reclaim storage.
• Documents are isolated per dialogue: conversations with attached knowledge bases are marked with a 📎 icon.

# [END OF SECTION: RAG]

---

# [START OF SECTION: MODELS]

🤖 <b>Model Selection, Personas, and Communication Styles</b>

In the «⚙️ Settings» menu, you can customize the bot's intellect, role, and tone.

<b>1. Google Gemini Model Family:</b>
• <b>Gemini 2.5 Flash</b> (default) — fast, intelligent, and versatile model for everyday tasks and document analysis.
• <b>Gemini 2.5 Pro</b> — powerful flagship model for complex programming, deep analytical reasoning, mathematics, and multi-step logic.
• <b>Gemini 2.5 Flash Lite</b> — ultra-fast, lightweight model with minimal latency.
• <b>Gemini 2.5 Thinking</b> — model equipped with extensive internal step-by-step reasoning before delivering an answer.

<b>2. Assistant Personas («🎭 Persona»):</b>
Switch the specialized role of your assistant:
• <b>General Assistant:</b> versatile everyday helper.
• <b>Code Expert:</b> writes clean, documented code in Python, JS, Go, etc., debugs errors, and optimizes algorithms.
• <b>Text Editor:</b> improves writing style, proofreads grammar, and adapts articles.
• <b>Financial Advisor, Teacher, Creative Writer:</b> focused expert roles.

<b>3. Communication Styles («🎨 Style»):</b>
• <b>Formal:</b> academic and professional tone.
• <b>Friendly:</b> warm and casual tone.
• <b>Concise:</b> direct, to-the-point answers without fluff.
• <b>Detailed:</b> comprehensive explanations with examples.

# [END OF SECTION: MODELS]

---

# [START OF SECTION: SUBSCRIPTION]

💎 <b>Subscriptions & Plans</b>

Subscriptions unlock access to advanced AI capabilities and expand your storage limits.

<b>Subscription Benefits:</b>
• Access to flagship models: <b>Gemini 2.5 Pro</b> and <b>Thinking</b>.
• Increased document upload allowances and vector memory storage.
• Higher daily token quotas and priority response latency.
• Verified subscriber badge 🟢 in your profile.

<b>Managing Your Subscription:</b>
• Go to «👤 Profile» ➡️ «💎 Subscription» (or use the <code>/subscribe</code> command).
• Choose your desired period (1 month, 3 months, or 1 year) and follow the simple on-screen instructions.
• Expiration dates and plan details are always visible in your profile card.

# [END OF SECTION: SUBSCRIPTION]

---

# [START OF SECTION: COMMANDS]

💬 <b>MyGemini Zero v2 Command Reference</b>

All commands can be invoked from the Telegram <b>[Menu]</b> button or typed manually:

<b>General:</b>
• <code>/start</code> — Restart bot, greeting, and vault status check
• <code>/profile</code> — «👤 Profile» (stats, user persona survey, subscription status)
• <code>/settings</code> — «⚙️ Settings» (models, personas, styles, language, API key)
• <code>/help</code> — Quick reference and interactive guide launcher
• <code>/guide</code> — Interactive multi-topic user guide
• <code>/logout</code> — Lock vault and purge session keys from RAM

<b>Dialogues & Memory:</b>
• <code>/dialogs</code> — «🗂️ Dialogs» (switch conversations, delete old topics)
• <code>/new_dialog</code> — «➕ New Dialog» with automatic topic titling from first prompt
• <code>/rename [name]</code> — Manually rename active dialogue
• <code>/documents</code> — «📄 Documents» in active dialogue memory (RAG)
• <code>/history</code> — Interactive message calendar by date
• <code>/reset</code> — «🔄 Reset Context» (clears short-term buffer)

<b>Specialized Modes:</b>
• <code>/translate</code> — Fast multi-language translator
• <code>/feedback</code> — Send feedback or bug reports to developers
• <code>/panic</code> — Panic password emergency wipe documentation
• <code>/cancel</code> — Cancel active prompt or input state

# [END OF SECTION: COMMANDS]
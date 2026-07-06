# 📘 AI Language Tutor — User Guide

Welcome to **Cheradip AI Language Tutor**. This guide covers every major feature for guests, trial users, Pro, and Plus subscribers.

---

## 1. ✨ What this app does

AI Language Tutor helps you:

- 📷 **Scan** books, worksheets, receipts, and notes (camera or gallery)
- 📖 **Read** scanned text with tap-to-define words and AI grammar hints
- 🎤 **Practice** speaking, typing, and listening in up to **3 languages** at once
- 📚 **Study grammar** with an AI-generated grammar book per language
- 📴 **Work offline** using downloaded language packs (meanings + pronunciation)

The app is **offline-first**: dictionary meanings come from packs on your phone. AI explanations use your **home AI server** or the **cloud pool** when online.

---

## 2. 🚀 First launch & trial

1. Complete **Onboarding** — pick study languages (up to 3), tutor voice gender, and app UI language.
2. You receive a **30-day trial** with full Pro features (AI modes 1–4, scanner, reader, practice).
3. After the trial, subscribe on the **Paywall** or continue with **offline packs only**.

**👤 Guest use (not signed in):** Browse freely and use up to **99 free AI requests**. After that, sign in or subscribe to continue AI features.

**🔐 Account:** Sign up with **email only** (no WhatsApp required). Use **Profile → Login** or **Sign up**.

---

## 3. 🧭 Navigation

### Bottom tabs

- 🏠 **Home** — Quick actions: scan, camera, import, practice, grammar
- 🎯 **Practice** — Unified hub: Scan · Camera · Import · Type · Voice · Listen
- 📂 **Learning** — History of documents, practice sessions, saved grammar
- 👤 **Profile** — Account, referrals, subscription, support, **User Manual**
- ⚙️ **Settings** — App language, voice, grammar depth, AI mode

### ☰ Menu (any screen)

Jump to **Languages**, **Grammar book**, **Referrals**, **Subscription**, **AI Mode**, **Profile**, or **Settings**.

---

## 4. 🏠 Home — Scan Only vs Learning

On Home, choose your activity mode:

### 📄 Scan Only

- Only the **Scan** action is shown.
- After scanning, tap **Save** to export PDF or images — no OCR or reader flow.
- Useful for archiving documents without processing.

### 📚 Learning (default)

- All actions: Scan, Camera, Import, Practice, Type, Voice, Listen, History, Grammar.
- **Scan / Camera / Import** → OCR → structured reader.
- **Practice / Type / Voice** → Practice hub.

**Example:** Scan a French worksheet → Process & Read → tap words for definitions and grammar.

---

## 5. 📷 Scanning & enhancement

### Capture options

When you tap **Scan**, you can choose:

- **Scan document** — Google ML Kit scanner (auto edge detection, multi-page, perspective correction). Best for quick everyday scans.
- **Live scan (boundary guide)** — In-app camera with a **live teal outline** on the preview so you see the exact area selected before you shoot.
  - **Solid outline** — flat / rectangular document
  - **Dashed outline** — curved or wrinkled page (e.g. open book)
- **Import from gallery** — Pick existing photos.

**💡 Tip:** Use **Live scan** when pages are curved; use **Scan document** when you want automatic crop and multi-page capture.

### After capture — review screen

The review screen opens for each page:

- **Thumbnails** — Tap to switch pages; **+** to add more (up to 20 per document).
- **Detected document area** — Shows the boundary found on the original (flat vs curved label).
- **Recommendation** — Suggested enhance level; tap **Apply** to use it.
- **Clean | AI Clean**
  - **Clean** — Offline processing on your phone (all users).
  - **AI Clean** — **Pro or Plus + internet**; uses Cheradip **Home AI** on your Windows PC (https://ai.cheradip.com) when online, with offline fallback if unavailable.
- **Level 0** — Compare **L1** and **L7** side by side; tap a preview to pick that level.
- **Levels 1–7** — Stronger cleanup step by step (shadow removal, dewarp at higher levels, detail recovery).
- **Export profile** — Document, receipt, book, etc. (affects save format).

### Scan Only vs Learning

- **Scan Only** (Home) — Scan, enhance, then **Save** as PDF or images. No OCR or reader.
- **Learning** (default) — After enhance, tap **Process & Read** for OCR and the reader.

### Multi-page documents

- Each page keeps its own enhance level and mode (Clean / AI Clean).
- **Rescan** replaces the current page; **Delete** removes it.

### After enhancement

- **Process & Read** — Runs OCR on the enhanced image and opens the reader (Learning mode).
- **Save** — Export only (Scan Only mode).

**💡 Tips:**

- Good lighting and holding the phone steady improve detection and OCR.
- For curved book pages: **Live scan** → **AI Clean** → try level **5+** when online.
- Math, code, and diagrams may use cloud structuring when online in Learning mode.

---

## 6. 📖 Reader

After OCR processing, the **Reader** shows structured text (headings, code blocks, math lines, paragraphs).

- 👆 **Tap any word** — Definition from your offline pack + optional AI grammar explanation.
- 📊 **Grammar depth** (Settings) controls AI hints: **word**, **sentence**, or **paragraph**.
- 📂 Documents appear under **Learning → History**.

### Multilingual & math content

- If you mix languages (e.g. Bengali + English, Arabic + English), the app detects scripts and responds in your **target language** when possible.
- **Math and code** stay formatted — equations appear as readable lines (not raw LaTeX).
- Descriptive text is translated or explained in your chosen output language.

---

## 7. 🎯 Practice hub

Open from **Practice tab**, Home → **Practice / Type / Voice**, or after scanning text into Practice.

### Input channels (icon bar)

- 📷 **Scan** · 📸 **Camera** · 📁 **Import** · ⌨️ **Type** · 🎤 **Voice** · 🔊 **Listen**

### Setup

1. Pick **input language** and **output language** (from your active packs).
2. Choose **Answer** (tutor explains) or **Translation** (direct translation) in **Settings → AI Mode**.
3. Pick an **AI engine mode** (see section 10).

### ⌨️ Typed input

- Type a sentence or question.
- While typing, an **offline preview** may appear at word boundaries.
- Tap **Process with AI** for full tutor or translation output.
- Tap words in **input** or **AI response** for grammar help and definitions.
- Tap **Save** to store the session in Learning history.

### 🎤 Voice input

- Hold the mic, speak, release.
- Partial transcript shows while you speak; AI may run automatically after a pause.
- **Calibrate once per language** (AI Mode screen) for better recognition on your device.

### 📷 Scan / import into Practice

- Scan or import a document from Practice — OCR text is sent as input automatically.
- OCR input uses **Mode 4 Lightweight** for cleanup.

### 🔊 Listen

- Hear AI output or your typed text spoken aloud (TTS).

---

## 8. 📚 Grammar book

**☰ Menu → Grammar** (or Home → Grammar).

- Select a language you have downloaded (active packs only, max 3).
- Browse AI-generated chapters (cached after first load).
- Sections **enrich automatically** with examples and tips as you scroll (when online).
- **Bookmark** icon saves a chapter to Learning history.
- Works offline with cached content; refreshes when online.

---

## 9. 🌍 Languages & offline packs

**☰ Menu → Languages**

1. Search and download language packs (meanings + TTS data).
2. Activate up to **3 languages** at once — these appear in Practice and app language options.
3. Packs work **fully offline** for dictionary lookups.

**Example:** Download Spanish and English → set both active → scan a Spanish page → tap "hablar" for the English meaning offline.

---

## 10. 💳 Subscriptions & AI modes

### Plans

- 🆓 **Free** — After 30-day trial: offline packs only (no AI)
- ⭐ **Pro** — $1/mo · $10/yr — AI modes 1–4
- 💎 **Plus** — $3/mo · $30/yr — All Pro modes + **Mode 5 High Accuracy**

Manage: **Profile → Subscription** or ☰ → Subscription.

### AI engine modes

- 🧠 **Mode 1 — Smart Tutor** — Detailed explanations (recommended for Answer)
- ⚡ **Mode 2 — Fast Translation** — NLLB machine translation
- ⚖️ **Mode 3 — Balanced** — Translation + polish
- 🪶 **Mode 4 — Lightweight** — Auto for OCR/scans (you don't pick this manually)
- 🎯 **Mode 5 — High Accuracy** — **Plus only**; largest model for difficult texts

**Mode 4** applies automatically when input comes from **scan/OCR**.

**Mode 5** shows a lock on Pro — upgrade to Plus on the Subscription screen.

Configure defaults: **Settings → AI Mode, Languages & Voice Calibration**.

---

## 11. 👤 Profile & account

### Logged in

- Dashboard: email, WhatsApp (if set), role
- 🔗 **Referrals** — Share link; earn rewards when friends subscribe
- ⭐ **Subscription**
- 🔒 **Update password** — OTP emailed (skipped on trusted registration device)
- ✉️ **Change email** — Two-step with verification
- 💬 **Support** — WhatsApp help button
- 📘 **User Manual** — This guide (+ Admin/Developer guides if you are admin)
- 🚪 **Log out**

### Guest

- **Login** / **Sign up**
- Browse Referrals and Subscription (sign-in required for full access)
- User Manual (user guide only)

### Password recovery

**Login → Forgot password** — Enter email; OTP arrives at your inbox (check spam). Reset on the next screen.

---

## 12. ⚙️ Settings

- 🌐 **App language** — UI language (one of your active study languages)
- 🗣 **Tutor voice** — Male/female TTS preview
- 📊 **Grammar depth** — Word / sentence / paragraph AI hints
- 🤖 **AI Mode Selection** — Answer vs Translation + engine mode + voice calibration
- 🔗 **Referrals** · ⭐ **Subscription** · 💬 **Support**

---

## 13. 📂 Learning history

**Learning tab** — Filter by:

- All · Recent · Saved · Learning · Scans · Uploads · Grammar · Read

Search by title. Tap a practice session to **restore** it in the Practice hub. Tap a document to reopen the reader.

---

## 14. 🔧 Troubleshooting

- **OCR text looks messy** — Better lighting; try **AI Clean** level 4–6 when Pro/Plus and online; use **Live scan** for curved pages; Process & Read while online for math/code.
- **AI Clean disabled or offline** — Needs **Pro or Plus** and internet for Home AI; **Clean** still works offline.
- **Boundary looks wrong** — Use **Live scan** to align the page; rescan with better lighting.
- **AI says offline** — Check Wi‑Fi; verify subscription or guest limit (99 requests).
- **No word definitions** — Download the language pack on Languages tab.
- **Mode 5 locked** — Upgrade to Plus.
- **Trial expired** — Subscribe Pro or Plus; offline packs still work.
- **Math shows strange symbols** — Re-process while online; app formats equations automatically.
- **Voice not recognized** — Run voice calibration; check mic permission.
- **Can't sign up** — Use a valid email; check inbox for recovery/OTP emails.

---

## 15. 🔒 Privacy & data

- Scanned documents stay on your device unless you export them.
- Login syncs referrals, subscription, and learning history with Cheradip servers.
- AI requests send text to the configured backend (cloud or home AI) for processing.

For support, use **Profile → Support** (WhatsApp) or the contact on the Paywall.

---

*Cheradip AI Language Tutor · User Guide · v2.2.0*

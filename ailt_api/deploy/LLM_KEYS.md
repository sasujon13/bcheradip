# Cloud LLM keys (ailt_api `.env`)

Without at least one key, `POST /ai/explain-paragraph` returns stub text like:

`[offline] Explanation (en→bn): …`

Keys stay **only** on the server in `ailt_api/.env` — **never** in git or the Android APK.

## Add to `ailt_api/.env` on cheradip.com

```env
# Guest AI (unsigned users) — Android syncs limit from server responses
GUEST_AI_LIMIT=99999999

# Pick one or more (router tries enabled providers):
GEMINI_API_KEY=<paste-from-google-ai-studio>
GEMINI_MODEL=gemini-flash-latest

OPENAI_API_KEY=<paste-openai-key>
ANTHROPIC_API_KEY=<paste-anthropic-key>
GROQ_API_KEY=<paste-groq-key>
MISTRAL_API_KEY=<paste-mistral-key>
OPENROUTER_API_KEY=<paste-openrouter-key>
```

Edit on the server only:

```bash
nano /home/sasha/apps/cheradip/bcheradip/ailt_api/.env
sudo systemctl restart cheradip-ailt
```

Then verify:

```bash
curl -s https://cheradip.com/ailt/api/health | python3 -m json.tool
# "llm_keys_configured": true
```

## Test explain-paragraph

```bash
curl -s -X POST https://cheradip.com/ailt/api/ai/explain-paragraph \
  -H "Content-Type: application/json" \
  -d '{"paragraph":"Hello world","source_lang":"en","target_lang":"bn"}' \
  | python3 -m json.tool
```

`provider_used` should be `gemini`, `openai`, etc. — not `local-stub`.

## Provider routing (failures + sticky session)

All cloud AI (`/ai/explain-paragraph`, `/ai/activity-metadata`, `/ai/structure-ocr`) uses `generate_with_fallback`:

| Rule | Behavior |
|------|----------|
| **No app daily cap** | `quota_daily_limit` is unset — unlimited calls through AILT; provider org TPM/RPS still apply |
| **Daily reset** | UTC midnight resets `requests_today` (stats only), failure counts, and `exhausted` → `healthy` |
| **Skip exhausted** | `random_free` and `random_all` never pick providers with `health=exhausted` |
| **HTTP 429** | Counts as one failure; at **7** consecutive failures → `exhausted` until reset or success |
| **Other errors** | Count toward `consecutive_failures`; at **7** → `exhausted` |
| **Sticky session** | Next request from same user/device (30 min) tries the last successful provider first |
| **Mistral models** | Journal → `ministral-3b-latest`, tutor/structure → `mistral-large-latest`, code OCR → `codestral-latest`, default → `mistral-small-latest` |
| **Gemini models** | Journal → `gemini-flash-lite-latest`, code → `gemini-2.5-flash`, tutor/structure → `gemini-2.5-pro`, default → `gemini-flash-latest` |
| **OpenAI (free pool)** | All intents → `gpt-4o-mini` by default |
| **OpenAI (paid)** | Coding → `o4-mini`, complex/tutor → `gpt-4o`, fast → `gpt-4o-mini` |
| **Groq** | Journal/fast → `llama-3.1-8b-instant`, coding → `qwen/qwen3-32b`, tutor/structure → `llama-3.3-70b-versatile` |
| **Anthropic (free)** | All intents → `claude-haiku-4-5` by default |
| **Anthropic (paid)** | Coding/tutor/structure → `claude-sonnet-4-5`, fast → `claude-haiku-4-5` |
| **OpenRouter (free)** | Default/journal → `openrouter/free`, coding → `qwen/qwen3-coder:free` |
| **OpenRouter (paid)** | Coding/tutor → `anthropic/claude-sonnet-4-5`, fast → `anthropic/claude-haiku-4-5` |

Override any model via `GEMINI_MODEL_*`, `OPENAI_*`, `GROQ_MODEL_*`, `ANTHROPIC_*`, `MISTRAL_MODEL_*`, `OPENROUTER_MODEL_*` in `.env` (see `.env.example`).

Client identity: `Authorization: Bearer …` (logged in) or `X-Device-Id` (guest). Android sends `X-Device-Id` on every API call.

**Note:** Each LLM call is stateless (one prompt per request). Sticky routing reuses the same **provider**, not chat history. Follow-up quality comes from the full prompt the app sends, not provider-side memory.

## Where keys are read

`app/config.py` → `app/services/llm_router.py` → `app/routers/ai.py`

Admin provider toggles: `GET/PATCH /admin/ai/providers` (no auth today — lock down in production if needed).

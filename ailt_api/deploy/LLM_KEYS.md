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

## Where keys are read

`app/config.py` → `app/services/llm_router.py` → `app/routers/ai.py`

Admin provider toggles: `GET/PATCH /admin/ai/providers` (no auth today — lock down in production if needed).

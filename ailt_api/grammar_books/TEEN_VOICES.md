# Teen voice packs (grammar_books tree)

Place Cheradip tutor voice packs next to each language grammar ebook:

```
grammar_books/
  {code}/
    v2.json                 # grammar ebook (existing)
    teen-voices/            # unpacked pack (preferred for editing)
      manifest.json
      male/
        voice.json
        model/              # optional Piper/onnx assets
      female/
        voice.json
        model/
    teen-voices.zip         # optional prebuilt zip (served if present)
```

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/grammar-books/voices/list` | Catalog of languages with voice packs |
| GET | `/grammar-books/{code}/voices/download` | Version + size metadata |
| GET | `/grammar-books/{code}/voices/file` | Zip download |

Android caches under `filesDir/grammar_books/{code}/teen-voices/` and downloads in the background when a practice language is activated.

## `manifest.json`

```json
{
  "version": 1,
  "languageCode": "bn",
  "genders": ["male", "female"],
  "engine": "android"
}
```

## `voice.json` (per gender)

```json
{
  "engine": "android",
  "languageCode": "bn",
  "gender": "female",
  "version": 1,
  "pitch": 1.20,
  "speechRateBias": 0.92,
  "locale": "bn-BD",
  "preferredVoiceNameHints": ["bn-bd", "bn-in", "bengali", "bangla"]
}
```

- `engine: "android"` — guide on-device TTS (name hints + pitch/rate). No silent Google TTS install.
- `engine: "piper"` — put `model/en_US-lessac-medium.onnx` (+ `.json`) for future Piper playback; Android falls back to android engine until Piper is wired.

## Seeding templates

```powershell
cd D:\VSCode\cheradip\bcheradip\ailt_api
python scripts\seed_teen_voice_templates.py
```

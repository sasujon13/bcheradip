"""
Translate website content using Google Cloud Translation API v2.
When a country is selected, the frontend sends its language_code (e.g. X-Language: bn);
the backend translates API response text fields to that language.

Set GOOGLE_TRANSLATE_API_KEY in .env (from Google Cloud Console) to enable.
Without a key, responses are returned untranslated.
"""
import json
import logging
from functools import lru_cache
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

# Keys we never translate (IDs, codes, URLs, etc.)
SKIP_KEYS = frozenset({
    'id', 'pk', 'code', 'country_code', 'subject_id', 'chapter_no', 'topic_no',
    'slug', 'url', 'link', 'email', 'username', 'password', 'token',
    'phone_code', 'created_at', 'updated_at', 'date', 'timestamp',
    'image', 'photo', 'avatar', 'icon', 'flag_url', 'flag_emoji',
    'country_code_alpha3', 'country_code_numeric', 'currency_code',
    'language_codes',  # array of codes, not user text
})

# Skip translation for very short or numeric-looking strings
def _should_skip_value(val: str) -> bool:
    if not val or not isinstance(val, str):
        return True
    s = val.strip()
    if len(s) <= 1:
        return True
    if s.isdigit() or s.replace('.', '').replace('-', '').isdigit():
        return True
    return False


def _get_api_key() -> Optional[str]:
    try:
        from django.conf import settings
        return getattr(settings, 'GOOGLE_TRANSLATE_API_KEY', None) or ''
    except Exception:
        return None


@lru_cache(maxsize=2048)
def translate_text(text: str, target_lang: str) -> str:
    """
    Translate a single string to target_lang using Google Cloud Translation API v2.
    Results are cached. Uses GOOGLE_TRANSLATE_API_KEY from settings.
    """
    if not text or not target_lang or target_lang.lower() in ('en', 'en-us', 'en-gb'):
        return text
    api_key = (_get_api_key() or '').strip()
    if not api_key:
        return text
    try:
        r = requests.post(
            'https://translation.googleapis.com/language/translate/v2',
            params={
                'key': api_key,
                'target': target_lang[:5],
                'format': 'text',
                'q': text[:50000],
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        translations = data.get('data', {}).get('translations', [])
        if translations:
            return translations[0].get('translatedText', text) or text
    except Exception as e:
        logger.warning('Translation failed for %r: %s', text[:50], e)
    return text


def _translate_value(val: Any, target_lang: str, api_key: str) -> Any:
    if isinstance(val, str):
        if _should_skip_value(val):
            return val
        return translate_text(val, target_lang)
    if isinstance(val, list):
        return [_translate_value(item, target_lang, api_key) for item in val]
    if isinstance(val, dict):
        return translate_dict(val, target_lang, api_key)
    return val


def translate_dict(data: Any, target_lang: str, api_key: Optional[str] = None) -> Any:
    """
    Recursively translate string values in a JSON-serializable structure.
    Skips keys in SKIP_KEYS and short/numeric strings.
    """
    if api_key is None:
        api_key = _get_api_key() or ''
    if not api_key or not target_lang or target_lang.lower() in ('en', 'en-us', 'en-gb'):
        return data
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            key_lower = k.lower() if isinstance(k, str) else ''
            if key_lower in SKIP_KEYS:
                out[k] = v
            else:
                out[k] = _translate_value(v, target_lang, api_key)
        return out
    if isinstance(data, list):
        return [_translate_value(item, target_lang, api_key) for item in data]
    if isinstance(data, str) and not _should_skip_value(data):
        return translate_text(data, target_lang)
    return data

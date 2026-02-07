"""
Middleware to translate API JSON responses to the language requested by the client.
The frontend sends the country language_code in the X-Language header (e.g. X-Language: bn).
Requires GOOGLE_TRANSLATE_API_KEY in settings to be set for translation to run.
"""
import json
import re

from django.utils.deprecation import MiddlewareMixin


def _get_requested_lang(request) -> str:
    """Prefer X-Language header, then first language from Accept-Language."""
    lang = (request.META.get('HTTP_X_LANGUAGE') or '').strip()
    if lang:
        return lang.split(',')[0].strip()[:10]
    accept = request.META.get('HTTP_ACCEPT_LANGUAGE') or ''
    # e.g. "bn,en;q=0.9" or "en-US,en;q=0.9"
    match = re.match(r'^([a-z]{2,3})(?:-[a-zA-Z]+)?', accept.strip())
    if match:
        return match.group(1).lower()
    return ''


class TranslateResponseMiddleware(MiddlewareMixin):
    """
    For API JSON responses, if the request has a non-English X-Language (or Accept-Language),
    translate string values in the response body to that language using Google Translate.
    """

    def process_response(self, request, response):
        if not (200 <= response.status_code < 300):
            return response
        lang = _get_requested_lang(request)
        if not lang or lang.lower() in ('en',):
            return response
        content_type = response.get('Content-Type', '')
        if 'application/json' not in content_type:
            return response
        path = getattr(request, 'path', '') or ''
        if not path.startswith('/api/') and not path.startswith('/api'):
            return response
        try:
            content = response.content.decode('utf-8')
            data = json.loads(content)
        except (ValueError, UnicodeDecodeError):
            return response
        try:
            from cheradip.translation import translate_dict
            from django.conf import settings
            api_key = getattr(settings, 'GOOGLE_TRANSLATE_API_KEY', None) or ''
            if not api_key.strip():
                return response
            translated = translate_dict(data, lang, api_key)
            response.content = json.dumps(translated, ensure_ascii=False).encode('utf-8')
        except Exception:
            pass
        return response

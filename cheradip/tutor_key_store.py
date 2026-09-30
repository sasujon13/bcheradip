"""Per-customer tutor keys with an ``ailanguagetutor.ai_providers`` fallback."""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import connections
from django.utils import timezone

from .models import CustomerToken
from .tutor_providers import PROVIDERS, validate_provider_config


_DB_IDS = {
    'google': ('gemini',),
    'anthropic': ('claude', 'claude_paid'),
    'openai': ('openai', 'openai_paid'),
    'groq': ('groq',),
    'mistral': ('mistral',),
    'deepseek': ('deepseek',),
    'openrouter': ('openrouter', 'openrouter_paid'),
    'brave': ('brave',),
}
_PREFIX = 'fernet:v1:'


def _cipher():
    material = (settings.SECRET_KEY + '|cheradip-tutor-provider-keys').encode()
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(material).digest()))


def encrypt_key(value):
    return _PREFIX + _cipher().encrypt(str(value).encode()).decode()


def decrypt_key(value):
    text = str(value or '')
    if not text.startswith(_PREFIX):
        return text.strip()  # compatibility with any older manually stored value
    try:
        return _cipher().decrypt(text[len(_PREFIX):].encode()).decode().strip()
    except (InvalidToken, ValueError):
        return ''


def customer_from_request(request):
    header = request.META.get('HTTP_AUTHORIZATION', '')
    if not header:
        return None
    if not header.startswith('Bearer '):
        raise ValueError('Please sign in again.')
    token = CustomerToken.objects.select_related('customer').filter(key=header[7:].strip()).first()
    if (not token or not token.customer.is_active or
            (token.expires_at and token.expires_at <= timezone.now())):
        raise ValueError('Your session has expired. Please sign in again.')
    return token.customer


def _settings(customer):
    raw = customer.settings
    return dict(raw) if isinstance(raw, dict) else {}


def customer_tutor_settings(customer):
    if customer is None:
        return {'provider': 'cheradip', 'model': 'auto', 'api_keys': {}}
    value = _settings(customer).get('tutor_ai')
    value = value if isinstance(value, dict) else {}
    keys = value.get('api_keys') if isinstance(value.get('api_keys'), dict) else {}
    return {
        'provider': str(value.get('provider') or 'cheradip'),
        'model': str(value.get('model') or 'auto'),
        'api_keys': {provider: decrypt_key(key) for provider, key in keys.items()
                     if provider in PROVIDERS and decrypt_key(key)},
    }


def save_customer_tutor_settings(customer, provider=None, model=None, api_keys=None):
    if customer is None:
        return customer_tutor_settings(None)
    customer.refresh_from_db(fields=['settings'])
    root = _settings(customer)
    current = root.get('tutor_ai') if isinstance(root.get('tutor_ai'), dict) else {}
    stored = current.get('api_keys') if isinstance(current.get('api_keys'), dict) else {}
    stored = dict(stored)
    for key, value in (api_keys or {}).items():
        if key not in PROVIDERS:
            continue
        if value is None or not str(value).strip():
            stored.pop(key, None)
        else:
            clean = validate_provider_config({'provider': key, 'api_key': value})['api_key']
            stored[key] = encrypt_key(clean)
    current = {
        'provider': provider if provider in ('cheradip', *PROVIDERS.keys()) else current.get('provider', 'cheradip'),
        'model': str(model or current.get('model') or 'auto')[:160],
        'api_keys': stored,
    }
    root['tutor_ai'] = current
    customer.settings = root
    customer.save(update_fields=['settings'])
    return customer_tutor_settings(customer)


def database_provider_key(provider):
    """Read an enabled shared key without exposing it through an API response."""
    ids = _DB_IDS.get(provider, ())
    if not ids or 'ailt' not in connections:
        return ''
    try:
        with connections['ailt'].cursor() as cursor:
            placeholders = ', '.join(['%s'] * len(ids))
            cursor.execute(
                'SELECT api_key FROM ai_providers WHERE enabled = 1 AND id IN (%s) '
                'AND api_key IS NOT NULL AND TRIM(api_key) != \'\' ORDER BY FIELD(id, %s) LIMIT 1'
                % (placeholders, placeholders), list(ids) + list(ids))
            row = cursor.fetchone()
            return str(row[0] or '').strip() if row else ''
    except Exception:
        return ''


def resolve_provider_config(request, incoming):
    config = validate_provider_config(incoming, require_key=False)
    if config['provider'] == 'cheradip':
        return config
    customer = customer_from_request(request)
    if config['api_key']:
        if customer is not None:
            save_customer_tutor_settings(customer, api_keys={config['provider']: config['api_key']})
        return config
    personal = customer_tutor_settings(customer)['api_keys'].get(config['provider'], '')
    config['api_key'] = personal or database_provider_key(config['provider'])
    return validate_provider_config(config)


def key_status(customer):
    personal = customer_tutor_settings(customer)['api_keys']
    return {provider: {'personal': bool(personal.get(provider)),
                       'shared': bool(database_provider_key(provider))}
            for provider in PROVIDERS}

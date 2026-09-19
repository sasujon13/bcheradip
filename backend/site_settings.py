"""
Admin-editable JSON settings store (backed by ``admin_site_settings.json``).

These settings were traditionally controlled by the server operator through
``.env`` / the process environment. This module adds an optional JSON overlay
file that an administrator can edit at ``/admin/settings/`` (the page is
JSON-based — it is not a database).

Priority (highest wins):
  1. ``admin_site_settings.json``   -> edited via /admin/settings/
  2. ``.env`` + process environment (existing behaviour)
  3. Built-in defaults listed below

Only the keys declared in ``ADMIN_SETTING_DEFS`` are exposed. Security/infra
settings (SECRET_KEY, DEBUG, ALLOWED_HOSTS, database credentials, ...) are
deliberately NOT listed here so they can only be changed on the server.
"""
import json
import os

# Project root (parent of backend/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Location of the JSON file. An operator may move it via ADMIN_SETTINGS_JSON_FILE.
DEFAULT_SETTINGS_FILE = os.path.join(BASE_DIR, 'admin_site_settings.json')
SETTINGS_FILE = os.environ.get('ADMIN_SETTINGS_JSON_FILE', DEFAULT_SETTINGS_FILE)

# value_type: str | int | float | bool
ADMIN_SETTING_DEFS = [
    # ------------------------------------------------------------------ Site
    {
        'key': 'ADMIN_SITE_HEADER',
        'label': 'Admin site header',
        'group': 'Site',
        'value_type': 'str',
        'default': 'Cheradip Administration',
        'sensitive': False,
        'description': 'Header shown on the admin top bar (used as admin.site.site_header).',
    },
    {
        'key': 'ADMIN_SITE_TITLE',
        'label': 'Admin site title',
        'group': 'Site',
        'value_type': 'str',
        'default': 'admin',
        'sensitive': False,
        'description': 'Title shown in the browser tab for admin pages.',
    },
    {
        'key': 'HOST_URL',
        'label': 'Host URL',
        'group': 'Site',
        'value_type': 'str',
        'default': 'http://127.0.0.1:8000',
        'sensitive': False,
        'description': 'Public base URL used when the site builds absolute links / emails.',
    },
    # ------------------------------------------------------------- PDF Export
    {
        'key': 'EXPORT_WORD_SPACING',
        'label': 'Export word spacing',
        'group': 'PDF Export',
        'value_type': 'str',
        'default': '0px',
        'sensitive': False,
        'description': 'Any valid CSS length that nudges word spacing in generated PDFs (e.g. 0, -0.95px, 0.5px). Windows/macOS vs Linux Chromium rasterise the same TTFs slightly differently, so a small per-environment offset keeps pages identical.',
    },
    {
        'key': 'EXPORT_FONT_SIZE_DELTA',
        'label': 'Export font-size delta (px)',
        'group': 'PDF Export',
        'value_type': 'float',
        'default': 0,
        'sensitive': False,
        'description': 'Small additive px offset applied to PDF fonts (recommended -0.25 to 0.25). Every 1px ≈ ~7% at 14px body and can shift line breaks.',
    },
    # ------------------------------------------------ AI Question Generation
    {
        'key': 'CLOUD_AI_QUESTIONS_URL',
        'label': 'Cloud AI question-generator URL',
        'group': 'AI Question Generation',
        'value_type': 'str',
        'default': 'https://cheradip.com/ailt/api/ai/generate-questions',
        'sensitive': False,
        'description': 'Cloud AI endpoint (the ailt_api service, same one the AI Language Tutor Android app uses) called to create exam questions when a topic lacks enough questions.',
    },
    {
        'key': 'HOME_AI_QUESTIONS_URL',
        'label': 'Home AI question-generator URL',
        'group': 'AI Question Generation',
        'value_type': 'str',
        'default': 'https://ai.cheradip.com/ide/chat/sync',
        'sensitive': False,
        'description': 'Home AI endpoint (local Ollama/OpenVINO engine) used first; Cloud AI is only used when every Home AI response errors/empty.',
    },
    {
        'key': 'HOME_AI_QUESTIONS_MODEL',
        'label': 'Home AI model (for question generation/update)',
        'group': 'AI Question Generation',
        'value_type': 'str',
        'default': 'qwen2.5:7b-instruct-q4_K_M',
        'sensitive': False,
        'description': 'Explicit Ollama model sent to Home AI /ide/chat/sync. Sending a concrete model avoids Auto mode (parallel multi-LLM + CPU synthesis) which exceeds the Cloudflare tunnel timeout. Leave blank to use Auto mode.',
    },
    {
        'key': 'EXAM_AI_FILL_ENABLED',
        'label': 'Use AI to fill missing exam questions',
        'group': 'AI Question Generation',
        'value_type': 'bool',
        'default': True,
        'sensitive': False,
        'description': 'When a topic has fewer than sq unique questions, ask Home AI/Cloud AI to create the missing ones. Turn off to always skip short topics.',
    },
    {
        'key': 'AI_QUESTIONS_TIMEOUT_SECONDS',
        'label': 'AI request timeout (seconds)',
        'group': 'AI Question Generation',
        'value_type': 'int',
        'default': 60,
        'sensitive': False,
        'description': 'Per-request timeout when talking to Home AI / Cloud AI.',
    },
    # ------------------------------------------------------------- Translation
    {
        'key': 'GOOGLE_TRANSLATE_API_KEY',
        'label': 'Google Translate API key',
        'group': 'Translation',
        'value_type': 'str',
        'default': '',
        'sensitive': True,
        'description': 'Google Cloud Translation API key used by the translate middleware to render site content in the user language.',
    },
    # ------------------------------------------------------- Email / OTP (SMTP)
    {
        'key': 'SMTP_ENABLED',
        'label': 'SMTP enabled',
        'group': 'Email / OTP (SMTP)',
        'value_type': 'bool',
        'default': True,
        'sensitive': False,
        'description': 'Whether OTP / transactional emails are sent at all.',
    },
    {
        'key': 'SMTP_HOST',
        'label': 'SMTP host',
        'group': 'Email / OTP (SMTP)',
        'value_type': 'str',
        'default': '',
        'sensitive': False,
        'description': 'SMTP server hostname (e.g. smtp.brevo.com).',
    },
    {
        'key': 'SMTP_PORT',
        'label': 'SMTP port',
        'group': 'Email / OTP (SMTP)',
        'value_type': 'int',
        'default': 587,
        'sensitive': False,
        'description': 'SMTP server port.',
    },
    {
        'key': 'SMTP_USER',
        'label': 'SMTP username',
        'group': 'Email / OTP (SMTP)',
        'value_type': 'str',
        'default': '',
        'sensitive': False,
        'description': 'SMTP login username / API key login.',
    },
    {
        'key': 'SMTP_PASSWORD',
        'label': 'SMTP password',
        'group': 'Email / OTP (SMTP)',
        'value_type': 'str',
        'default': '',
        'sensitive': True,
        'description': 'SMTP login password / API master key.',
    },
    {
        'key': 'SMTP_FROM',
        'label': 'SMTP from address',
        'group': 'Email / OTP (SMTP)',
        'value_type': 'str',
        'default': 'Cheradip <noreply@cheradip.com>',
        'sensitive': False,
        'description': 'From header used on outgoing emails.',
    },
    {
        'key': 'SMTP_USE_TLS',
        'label': 'SMTP use TLS',
        'group': 'Email / OTP (SMTP)',
        'value_type': 'bool',
        'default': True,
        'sensitive': False,
        'description': 'Use STARTTLS when connecting.',
    },
    {
        'key': 'SMTP_USE_SSL',
        'label': 'SMTP use SSL',
        'group': 'Email / OTP (SMTP)',
        'value_type': 'bool',
        'default': False,
        'sensitive': False,
        'description': 'Use implicit SSL (SMTPS) when connecting.',
    },
    {
        'key': 'OTP_TTL_MINUTES',
        'label': 'OTP validity (minutes)',
        'group': 'Email / OTP (SMTP)',
        'value_type': 'int',
        'default': 15,
        'sensitive': False,
        'description': 'How long a generated OTP code stays valid.',
    },
    # ------------------------------------------------------------ Child Care
    {
        'key': 'CHILDCARE_SESSION_TTL_DAYS',
        'label': 'Child Care session lifetime (days)',
        'group': 'Child Care',
        'value_type': 'int',
        'default': 30,
        'sensitive': False,
        'description': 'Number of days a Child Care login session may stay valid.',
    },
]

KEY_INDEX = {item['key']: item for item in ADMIN_SETTING_DEFS}
GROUP_ORDER = ['Site', 'PDF Export', 'AI Question Generation', 'Translation', 'Email / OTP (SMTP)', 'Child Care']



def _env_str(value):
    """String form used when pushing values into os.environ."""
    if isinstance(value, bool):
        return 'True' if value else 'False'
    return str(value)


def load_json():
    """Return the JSON overlay dict ({} if file missing/corrupt)."""
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {}


def raw_json():
    """Raw JSON text of the overlay file (pretty printed)."""
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            return f.read().strip() or '{}'
    except OSError:
        return '{}'


def save_json(values):
    """Persist the overlay dict to the JSON file (pretty, unicode)."""
    payload = {key: values[key] for key in values if key in KEY_INDEX}
    directory = os.path.dirname(SETTINGS_FILE)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)


def reset_json():
    """Remove the overlay file entirely so .env / defaults take over."""
    try:
        if os.path.isfile(SETTINGS_FILE):
            os.remove(SETTINGS_FILE)
    except OSError:
        pass


def cast_value(item, raw):
    """Cast a raw form / JSON value to the setting's type.

    Returns (value, error_or_None).
    """
    value_type = item['value_type']
    try:
        if value_type == 'bool':
            if isinstance(raw, bool):
                return raw, None
            s = str(raw).strip().lower()
            if s in ('1', 'true', 'yes', 'on'):
                return True, None
            if s in ('0', 'false', 'no', 'off', ''):
                return False, None
            return None, 'must be True/False'
        if value_type == 'int':
            return int(str(raw).strip()), None
        if value_type == 'float':
            return float(str(raw).strip() or '0'), None
        return str(raw), None
    except (TypeError, ValueError):
        return None, 'invalid %s value' % value_type


def apply_to_os_environ():
    """Overlay the JSON file into os.environ (run once at startup in settings.py)."""
    data = load_json()
    for key, raw in data.items():
        item = KEY_INDEX.get(key)
        if item is None:
            continue
        value, _err = cast_value(item, raw)
        if value is not None:
            os.environ[key] = _env_str(value)


def publish_values(values):
    """Make saved values live immediately in the running process.

    Updates os.environ (used directly by e.g. cheradip.views export code) and
    Django settings attributes (used via getattr(settings, ...) by ai generator,
    email_service, translation middleware, etc.), and the admin branding.
    """
    for key, raw in values.items():
        item = KEY_INDEX.get(key)
        if item is None:
            continue
        value, _err = cast_value(item, raw)
        if value is None:
            continue
        os.environ[key] = _env_str(value)
        try:
            from django.conf import settings as django_settings
            setattr(django_settings, key, value)
        except Exception:
            pass
    try:
        from django.contrib import admin
        if values.get('ADMIN_SITE_HEADER') is not None:
            admin.site.site_header = str(values['ADMIN_SITE_HEADER'])
        if values.get('ADMIN_SITE_TITLE') is not None:
            admin.site.site_title = str(values['ADMIN_SITE_TITLE'])
    except Exception:
        pass


def get_effective_values():
    """Current effective value for every admin setting (JSON > env/.env > default)."""
    overlay = load_json()
    out = {}
    for item in ADMIN_SETTING_DEFS:
        key = item['key']
        if key in overlay:
            value, _err = cast_value(item, overlay[key])
            out[key] = overlay[key] if value is None else value
        elif os.environ.get(key, '') != '':
            value, _err = cast_value(item, os.environ.get(key))
            out[key] = value if value is not None else item['default']
        else:
            out[key] = item['default']
    return out


def get_sources():
    """Map of key -> 'json' | 'env' | 'default' for UI badges."""
    overlay = load_json()
    out = {}
    for item in ADMIN_SETTING_DEFS:
        key = item['key']
        if key in overlay:
            out[key] = 'json'
        elif os.environ.get(key, '') != '':
            out[key] = 'env'
        else:
            out[key] = 'default'
    return out


def get_groups():
    """Ordered list of (group_name, [setting_dicts_with_values])."""
    values = get_effective_values()
    sources = get_sources()
    grouped = {}
    for item in ADMIN_SETTING_DEFS:
        group = grouped.setdefault(item['group'], [])
        row = dict(item)
        row['value'] = values[item['key']]
        row['source'] = sources[item['key']]
        group.append(row)
    ordered = []
    for name in GROUP_ORDER:
        if name in grouped:
            ordered.append((name, grouped.pop(name)))
    for name, group in grouped.items():  # any remaining (safety)
        ordered.append((name, group))
    return ordered


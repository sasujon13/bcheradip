"""Supplier encryption only. Never exposes raw credentials to serializers or logs."""
import json
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def cipher():
    key = getattr(settings, 'COMMERCE_SUPPLIER_KEY', '')
    if not key:
        path = getattr(settings, 'COMMERCE_SUPPLIER_KEY_FILE', '')
        try:
            key = Path(path).read_bytes().strip() if path else b''
        except OSError:
            key = b''
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError):
        raise ValueError('Supplier credential encryption is not configured with a valid server key.') from None


def encrypt(credentials):
    return cipher().encrypt(json.dumps(credentials).encode()).decode()


def decrypt(supplier):
    try:
        value = json.loads(cipher().decrypt(supplier.credentials_ciphertext.encode()))
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (InvalidToken, ValueError, TypeError, UnicodeError):
        raise ValueError('Supplier credentials are unavailable or cannot be decrypted. Replace them through the protected form.') from None

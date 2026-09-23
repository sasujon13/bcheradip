from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from passlib.context import CryptContext

from app.config import settings

# ``bcrypt`` is the native scheme for extension accounts (``hash()`` keeps using
# it). ``django_pbkdf2_sha256`` is listed so hashes mirrored verbatim from
# cheradip.com's ``cheradip_customers.password`` (Django's PBKDF2 format) keep
# verifying — see ``app/services/cheradip_account_sync.py``.
pwd_context = CryptContext(
    schemes=["bcrypt", "django_pbkdf2_sha256"],
    deprecated="auto",
)



def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    return pwd_context.verify(plain, hashed)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def new_otp_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def session_expires_at() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=settings.session_ttl_days)


def otp_expires_at() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=settings.otp_ttl_minutes)


def ms_now() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def ms_in_days(days: int) -> int:
    return ms_now() + days * 86400 * 1000


def quota_used_percent(requests: int, limit: int | None) -> int:
    if not limit:
        return 0
    return min(100, int(requests * 100 / limit))

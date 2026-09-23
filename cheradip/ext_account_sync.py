"""Keep cheradip.com accounts and the VS Code extension in step.

``cheradip_customers`` (cheradip.com) and ``ext_users`` (Cheradip VS Code
extension, database ``extcheradip``) are separate user spaces living on the same
MySQL server. ``sync_customer_to_ext()`` is called on signup / login / password
change so an extension account always exists for the same credentials — without
ever prompting the user for anything.

Password formats
----------------
The extension verifies passwords with passlib (``bcrypt`` + Django's
``django_pbkdf2_sha256``), Django verifies its own formats. So:

* when the plaintext is known (signup/login/password change) the hash is
  re-derived as **bcrypt** — the extension's native scheme;
* otherwise an existing Django ``pbkdf2_sha256$…`` hash is copied verbatim
  (passlib verifies it unchanged), or the ``bcrypt$…`` wrapper is unwrapped.

Everything is fail-soft: an unreachable extension database is logged and never
breaks cheradip.com authentication.
"""

from __future__ import annotations

import logging
import time

from django.db import connections
from django.db.utils import DatabaseError, OperationalError

logger = logging.getLogger(__name__)

EXT_DB_ALIAS = 'extcheradip'

# ext_users column limits (see ailt_api/app/models.py: ExtUser).
USERNAME_MAX = 64  # varchar(64) UNIQUE
FULLNAME_MAX = 80  # varchar(80)
EMAIL_MAX = 255

ROLE_USER = 'user'
BCRYPT_ROUNDS = 12  # matches passlib's default, so mirrored hashes look native

DJANGO_PBKDF2_PREFIX = 'pbkdf2_sha256$'
DJANGO_BCRYPT_WRAPPER = 'bcrypt$'


def _clean_username(raw: str | None, email: str) -> str:
    """Return a value that fits ext_users.username (varchar(64) UNIQUE)."""
    base = (raw or '').strip() or email.split('@', 1)[0]
    base = ''.join(ch for ch in base if ch.isalnum() or ch in '_.-')
    return (base or f'cheradip{int(time.time())}')[:USERNAME_MAX]


def _bcrypt_hash(raw_password: str) -> str | None:
    """Hash a plaintext password exactly like the extension does (bcrypt)."""
    try:
        import bcrypt
    except ImportError:  # pragma: no cover - bcrypt ships with the requirements
        logger.warning('bcrypt is not installed; extension password mirror skipped')
        return None
    return bcrypt.hashpw(
        raw_password.encode('utf-8'), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    ).decode('ascii')


def _mirror_password(customer, raw_password: str | None) -> str | None:
    """Pick the password representation the extension can verify."""
    if raw_password:
        return _bcrypt_hash(raw_password)
    stored = (getattr(customer, 'password', '') or '').strip()
    if stored.startswith(DJANGO_PBKDF2_PREFIX):
        return stored
    if stored.startswith(DJANGO_BCRYPT_WRAPPER):
        # Django's ``bcrypt$<hash>`` wrapper → the raw bcrypt hash passlib reads.
        return stored[len(DJANGO_BCRYPT_WRAPPER):] or None
    if stored.startswith('$2'):
        return stored
    return None


def _find_row(cursor, email: str, username: str):
    """Locate the extension row by email first, then by username."""
    cursor.execute(
        'SELECT id, username, password_hash, full_name, email FROM ext_users '
        'WHERE LOWER(email) = %s LIMIT 1',
        [email],
    )
    row = cursor.fetchone()
    if row is not None:
        return row
    cursor.execute(
        'SELECT id, username, password_hash, full_name, email FROM ext_users '
        'WHERE username = %s LIMIT 1',
        [username],
    )
    return cursor.fetchone()


def _unique_username(cursor, base: str, exclude_id: int | None = None) -> str:
    candidate = base[:USERNAME_MAX]
    for attempt in range(1, 200):
        if attempt > 1:
            suffix = str(attempt)
            candidate = f'{base[: USERNAME_MAX - len(suffix)]}{suffix}'
        cursor.execute(
            'SELECT id FROM ext_users WHERE username = %s LIMIT 1', [candidate]
        )
        row = cursor.fetchone()
        if row is None or (exclude_id is not None and row[0] == exclude_id):
            return candidate
    return f'cheradip{int(time.time())}'[:USERNAME_MAX]


def sync_customer_to_ext(
    customer,
    *,
    raw_password: str | None = None,
    sync_password: bool = False,
) -> None:
    """Create/update the extension account mirroring ``customer``.

    ``raw_password`` is the plaintext the caller just handled (signup, login,
    password change); pass it whenever available. ``sync_password`` forces the
    stored hash to be refreshed even when the row already exists. Never raises.
    """
    email = (getattr(customer, 'email', '') or '').strip().lower()
    if not email:
        # ext_users.email is the match key (and is NOT NULL in the extension).
        logger.debug(
            'extension mirror skipped: customer %s has no email', customer.username
        )
        return

    username = _clean_username(getattr(customer, 'username', ''), email)
    full_name = ((getattr(customer, 'fullName', '') or '').strip() or username)[
        :FULLNAME_MAX
    ]
    password_hash = _mirror_password(customer, raw_password)
    is_active = 1 if getattr(customer, 'is_active', True) else 0

    try:
        connection = connections[EXT_DB_ALIAS]
        with connection.cursor() as cursor:
            row = _find_row(cursor, email, username)
            if row is None:
                if not password_hash:
                    logger.warning(
                        'extension mirror deferred for %s: no usable password hash',
                        customer.username,
                    )
                    return
                unique_username = _unique_username(cursor, username)
                cursor.execute(
                    'INSERT INTO ext_users (email, username, password_hash, role, '
                    'full_name, email_verified, active, last_login_at_ms, '
                    'free_extension_claimed, free_extension_requests, '
                    'free_extension_line_edits) '
                    "VALUES (%s, %s, %s, %s, %s, 1, %s, %s, 0, 0, 0)",
                    [
                        email[:EMAIL_MAX],
                        unique_username,
                        password_hash,
                        ROLE_USER,
                        full_name,
                        is_active,
                        int(time.time() * 1000),
                    ],
                )
                logger.info(
                    'extension mirror created for %s -> %s',
                    customer.username,
                    unique_username,
                )
                return
            _update_row(cursor, row, full_name, password_hash, is_active, sync_password)
    except (OperationalError, DatabaseError) as exc:
        logger.warning(
            'extension mirror unavailable for %s: %s', customer.username, exc
        )
    except Exception as exc:  # noqa: BLE001 - mirroring must never break auth
        logger.warning('extension mirror failed for %s: %s', customer.username, exc)


def _update_row(
    cursor,
    row,
    full_name: str,
    password_hash: str | None,
    is_active: int,
    sync_password: bool,
) -> None:
    """Refresh an existing extension row (password only when it changed)."""
    row_id, _row_username, row_password_hash, row_full_name, _row_email = row
    assignments: list[str] = []
    params: list[object] = []
    if sync_password and password_hash:
        assignments.append('password_hash = %s')
        params.append(password_hash)
    if full_name and not (row_full_name or '').strip():
        assignments.append('full_name = %s')
        params.append(full_name)
    assignments.append('active = %s')
    params.append(is_active)
    if not assignments:
        return
    params.append(row_id)
    cursor.execute(
        f"UPDATE ext_users SET {', '.join(assignments)} WHERE id = %s", params
    )
    logger.info('extension mirror updated for row %s', row_id)


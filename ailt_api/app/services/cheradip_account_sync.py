"""Mirror Cheradip extension accounts into cheradip.com's ``cheradip_customers``.

The extension (``extcheradip.ext_users``) and cheradip.com
(``cheradip_cheradip.cheradip_customers``) are two separate user spaces on the
same MySQL server. This module keeps them in step automatically, without ever
asking the user anything:

* ``ensure_cheradip_account()`` is called on every ext signup / login /
  password change, so a cheradip.com account always exists for the same
  credentials.
* Passwords are written in Django's own
  ``pbkdf2_sha256$<iterations>$<salt>$<hash>`` format (``hashlib`` only — no
  Django import needed). Django's ``PBKDF2PasswordHasher`` verifies it and
  ``CustomBackend`` (``pbkdf2_`` prefix) accepts it.
* Copying an existing cheradip.com hash verbatim is safe in the other
  direction — see ``cheradip/ext_account_sync.py``.

Every failure is fail-soft (logged, never raised): the extension must keep
working even when cheradip.com's database is unreachable.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import re
import secrets
import string
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.models import ExtUser

logger = logging.getLogger(__name__)

# Django's PBKDF2PasswordHasher defaults (backend/settings.py sets no
# PASSWORD_HASHERS, so Django 5.x defaults apply: 1_000_000 iterations, sha256).
PBKDF2_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 1_000_000
SALT_ALPHABET = string.ascii_letters + string.digits
SALT_LENGTH = 12

# cheradip_customers column limits (see cheradip/models.py).
USERNAME_MAX = 15  # varchar(15) UNIQUE
FULLNAME_MAX = 31  # varchar(31)
EMAIL_MAX = 254

DEFAULT_ACCTYPE = "Student"
DEFAULT_COUNTRY_CODE = "BD"
DEFAULT_GROUP = "Science"
DEFAULT_GENDER = ""

_engine: Engine | None = None


def _get_engine() -> Engine:
    """Lazily create the cheradip.com engine (kept out of import-time paths)."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.cheradip_database_url,
            pool_pre_ping=True,
            pool_recycle=3600,
            # Mirroring is best-effort: never let a slow/unreachable cheradip.com
            # database stall an extension sign-up or login.
            connect_args={"connect_timeout": 3},
        )
    return _engine


def django_pbkdf2_sha256(
    password: str,
    *,
    salt: str | None = None,
    iterations: int = PBKDF2_ITERATIONS,
) -> str:
    """Return a Django-verifiable ``pbkdf2_sha256$…`` password string."""
    salt = salt or "".join(secrets.choice(SALT_ALPHABET) for _ in range(SALT_LENGTH))
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    encoded = base64.b64encode(digest).decode("ascii")
    return f"{PBKDF2_ALGORITHM}${iterations}${salt}${encoded}"


def _ms_now() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _clean_username(raw: str | None, *, fallback_seed: str) -> str:
    """Sanitise a value into a cheradip_customers-compatible username."""
    base = (raw or "").strip()
    if not base and fallback_seed:
        base = fallback_seed.split("@", 1)[0]
    base = re.sub(r"[^A-Za-z0-9_.-]", "", base)
    return base[:USERNAME_MAX] or f"ext{_ms_now()}"[:USERNAME_MAX]

def _unique_username(conn, base: str, *, exclude_id: int | None = None) -> str:
    """Return ``base`` or a numeric-suffixed variant that is still unique."""
    candidate = base[:USERNAME_MAX]
    for attempt in range(1, 200):
        if attempt > 1:
            suffix = str(attempt)
            candidate = f"{base[: USERNAME_MAX - len(suffix)]}{suffix}"
        row = conn.execute(
            text("SELECT id FROM cheradip_customers WHERE username = :username LIMIT 1"),
            {"username": candidate},
        ).first()
        if row is None or (exclude_id is not None and row[0] == exclude_id):
            return candidate
    return f"ext{_ms_now()}"[:USERNAME_MAX]


def _find_row(conn, *, email: str | None, username: str | None):
    """Locate the mirrored row by email first, then by username."""
    if email:
        row = conn.execute(
            text(
                "SELECT id, username, `password`, fullName, email "
                "FROM cheradip_customers WHERE LOWER(email) = :email LIMIT 1"
            ),
            {"email": email.lower()},
        ).first()
        if row is not None:
            return row
    if username:
        return conn.execute(
            text(
                "SELECT id, username, `password`, fullName, email "
                "FROM cheradip_customers WHERE username = :username LIMIT 1"
            ),
            {"username": username},
        ).first()
    return None


def ensure_cheradip_account(
    user: ExtUser,
    *,
    raw_password: str | None = None,
    sync_password: bool = False,
) -> None:
    """Create/update the cheradip.com ``Customer`` mirroring ``user``.

    ``raw_password`` is the plaintext the caller just handled (signup, login,
    password change, recovery reset). It is only re-hashed when the account is
    created or when ``sync_password`` is true — a normal login never rewrites an
    already-correct password. Never raises.
    """
    email = (user.email or "").strip().lower()
    if not email:
        # cheradip_customers.email is the only reliable match key; ext users
        # without an email cannot be mirrored.
        logger.debug("cheradip mirror skipped: ext user %s has no email", user.id)
        return

    ext_username = _clean_username(user.username, fallback_seed=email)
    full_name = (user.full_name or "").strip() or ext_username
    new_hash = django_pbkdf2_sha256(raw_password) if raw_password else None

    try:
        engine = _get_engine()
        with engine.begin() as conn:
            row = _find_row(conn, email=email, username=ext_username)
            if row is None:
                _insert_mirror(conn, user, email, ext_username, full_name, new_hash)
                return
            _update_mirror(conn, user, row, full_name, new_hash, sync_password)
    except SQLAlchemyError as exc:
        logger.warning("cheradip mirror unavailable for ext user %s: %s", user.id, exc)
    except Exception as exc:  # noqa: BLE001 - mirroring must never break auth
        logger.warning("cheradip mirror failed for ext user %s: %s", user.id, exc)


def _insert_mirror(
    conn,
    user: ExtUser,
    email: str,
    ext_username: str,
    full_name: str,
    new_hash: str | None,
) -> None:
    """Insert the cheradip_customers row (every NOT NULL column is supplied)."""
    if new_hash is None:
        logger.warning(
            "cheradip mirror deferred for ext user %s: no plaintext password available",
            user.id,
        )
        return
    username = _unique_username(conn, ext_username)
    conn.execute(
        text(
            "INSERT INTO cheradip_customers ("
            "last_login, is_superuser, acctype, username, `password`, fullName, "
            "`group`, gender, country_code, date_of_birth, class_name, department, "
            "teacher_level, teacher_subject_code, teacher_department_code, "
            "teacher_department_name, division, district, thana, `union`, village, "
            "email, phone_alternate, whatsapp_apikey, is_active, is_staff, "
            "date_joined, updated_at, settings"
            ") VALUES ("
            "NULL, 0, :acctype, :username, :password, :fullName, "
            ":group, :gender, :country_code, NULL, NULL, NULL, "
            "NULL, NULL, NULL, NULL, '', '', '', '', '', "
            ":email, NULL, NULL, 1, 0, NOW(), NOW(), NULL"
            ")"
        ),
        {
            "acctype": DEFAULT_ACCTYPE,
            "username": username,
            "password": new_hash,
            "fullName": full_name[:FULLNAME_MAX],
            "group": DEFAULT_GROUP,
            "gender": DEFAULT_GENDER,
            "country_code": DEFAULT_COUNTRY_CODE,
            "email": email[:EMAIL_MAX],
        },
    )
    logger.info(
        "cheradip mirror created for ext user %s -> username %s", user.id, username
    )


def _update_mirror(
    conn,
    user: ExtUser,
    row,
    full_name: str,
    new_hash: str | None,
    sync_password: bool,
) -> None:
    """Refresh a mirror: password only when it changed, name only when empty."""
    row_id, _row_username, row_password, row_full_name, _row_email = row
    updates: dict[str, object] = {}
    if (sync_password or not row_password) and new_hash:
        updates["password"] = new_hash
    if full_name and not (row_full_name or "").strip():
        updates["fullName"] = full_name[:FULLNAME_MAX]
    if not updates:
        return
    assignments = ", ".join(f"`{column}` = :{column}" for column in updates)
    conn.execute(
        text(
            f"UPDATE cheradip_customers SET {assignments}, updated_at = NOW() "
            "WHERE id = :row_id"
        ),
        {**updates, "row_id": row_id},
    )
    logger.info(
        "cheradip mirror updated for ext user %s (fields: %s)",
        user.id,
        ", ".join(updates),
    )


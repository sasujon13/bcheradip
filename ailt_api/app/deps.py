from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.ext_database import get_ext_db
from app.models import ExtSession, ExtUser, SessionToken, User
from app.security import session_expires_at


def _maybe_refresh_session(db: Session, row: SessionToken, now: datetime) -> None:
    """Sliding window: keep active users logged in indefinitely.

    Extends the expiry when less than half the TTL remains, so a session only
    ever lapses after a long period of total inactivity. Password change and
    "log out all devices" still hard-revoke immediately (rows are deleted).
    """
    half_ttl = timedelta(days=max(1, settings.session_ttl_days // 2))
    if row.expires_at - now < half_ttl:
        row.expires_at = session_expires_at()
        db.commit()


def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Authentication required")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "Authentication required")
    row = db.scalar(select(SessionToken).where(SessionToken.token == token))
    if not row:
        raise HTTPException(401, "Invalid session")
    now = datetime.utcnow()
    if row.expires_at < now:
        raise HTTPException(401, "Session expired")
    user = db.get(User, row.user_id)
    if not user:
        raise HTTPException(401, "User not found")
    _maybe_refresh_session(db, row, now)
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Admin access required")
    return user


def get_optional_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> User | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        return None
    row = db.scalar(select(SessionToken).where(SessionToken.token == token))
    if not row or row.expires_at < datetime.utcnow():
        return None
    return db.get(User, row.user_id)


def _maybe_refresh_ext_session(db: Session, row: ExtSession, now: datetime) -> None:
    half_ttl = timedelta(days=max(1, settings.session_ttl_days // 2))
    if row.expires_at - now < half_ttl:
        row.expires_at = session_expires_at()
        db.commit()


def get_current_ext_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_ext_db),
) -> ExtUser:
    """Authenticate a Cheradip extension user via their ext_sessions token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Authentication required")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "Authentication required")
    row = db.scalar(select(ExtSession).where(ExtSession.token == token))
    if not row:
        raise HTTPException(401, "Invalid session")
    now = datetime.utcnow()
    if row.expires_at < now:
        raise HTTPException(401, "Session expired")
    user = db.get(ExtUser, row.user_id)
    if not user:
        raise HTTPException(401, "User not found")
    _maybe_refresh_ext_session(db, row, now)
    return user


def require_ext_admin(user: ExtUser = Depends(get_current_ext_user)) -> ExtUser:
    if user.role != "admin":
        raise HTTPException(403, "Admin access required")
    return user


def get_optional_ext_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_ext_db),
) -> ExtUser | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        return None
    row = db.scalar(select(ExtSession).where(ExtSession.token == token))
    if not row or row.expires_at < datetime.utcnow():
        return None
    return db.get(ExtUser, row.user_id)


def get_ai_client_key(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_device_id: str | None = Header(default=None, alias="X-Device-Id"),
    db: Session = Depends(get_db),
) -> str | None:
    """Stable key for sticky cloud-AI provider routing (logged-in user or guest device)."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        if token:
            row = db.scalar(select(SessionToken).where(SessionToken.token == token))
            if row and row.expires_at >= datetime.utcnow():
                return f"user:{row.user_id}"
    device_id = (x_device_id or "").strip()
    if device_id:
        return f"device:{device_id}"
    return None

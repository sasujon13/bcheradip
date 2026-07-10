"""Auth for Cheradip VS Code extension users — a user space separate from the
AILT Android app (its own ``ext_users`` / ``ext_sessions`` tables).

Session-based (like Cursor): sessions slide forward while active and are only
revoked on password change or "log out all devices".
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.deps import get_current_ext_user
from app.ext_database import get_ext_db
from app.models import ExtOtpCode, ExtSession, ExtUser
from app.services.guest_billing import merge_device_on_login
from app.schemas import (
    ExtAuthResponse,
    ExtLoginRequest,
    ExtPasswordChangeRequest,
    ExtRecoveryResetRequest,
    ExtRecoverySendRequest,
    ExtSignupRequest,
)
from app.security import (
    hash_password,
    ms_now,
    new_otp_code,
    new_session_token,
    otp_expires_at,
    session_expires_at,
    verify_password,
)
from app.services.email_service import send_otp_email

router = APIRouter(prefix="/ext/auth", tags=["ext-auth"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PASSWORD_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,}$")
_OTP_CHANNEL = "ext_recovery"


def _issue_session(db: Session, user: ExtUser, device_id: str | None) -> str:
    token = new_session_token()
    db.add(
        ExtSession(
            user_id=user.id,
            token=token,
            device_id=device_id,
            expires_at=session_expires_at(),
        )
    )
    return token


def _revoke_all_sessions(db: Session, user_id: int) -> None:
    db.execute(delete(ExtSession).where(ExtSession.user_id == user_id))


def _validate_password(password: str) -> None:
    if not PASSWORD_RE.match(password):
        raise HTTPException(400, "Password must be at least 8 characters with 1 letter and 1 number")


def _auth_response(user: ExtUser, token: str | None) -> ExtAuthResponse:
    return ExtAuthResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        fullName=user.full_name,
        role=user.role,
        sessionToken=token,
    )


def _find_user(db: Session, username: str) -> ExtUser | None:
    needle = username.strip().lower() if "@" in username else username.strip()
    return db.scalar(
        select(ExtUser).where((ExtUser.email == needle) | (ExtUser.username == needle))
    )


@router.post("/signup", response_model=ExtAuthResponse)
def signup(body: ExtSignupRequest, db: Session = Depends(get_ext_db)) -> ExtAuthResponse:
    email = body.email.strip().lower()
    username = body.username.strip()
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "Invalid email address")
    _validate_password(body.password)
    if db.scalar(select(ExtUser).where(ExtUser.email == email)):
        raise HTTPException(409, "Email already registered")
    if db.scalar(select(ExtUser).where(ExtUser.username == username)):
        raise HTTPException(409, "Username already taken")

    user = ExtUser(
        email=email,
        username=username,
        full_name=(body.fullName or "").strip() or None,
        password_hash=hash_password(body.password),
        role="user",
        email_verified=True,
    )
    db.add(user)
    db.flush()
    token = _issue_session(db, user, body.deviceId)
    merge_device_on_login(db, body.deviceId, user)
    db.commit()
    return _auth_response(user, token)


@router.post("/login", response_model=ExtAuthResponse)
def login(body: ExtLoginRequest, db: Session = Depends(get_ext_db)) -> ExtAuthResponse:
    try:
        user = _find_user(db, body.username)
        if not user:
            raise HTTPException(401, "NOT_REGISTERED")
        if not user.password_hash or not verify_password(body.password, user.password_hash):
            raise HTTPException(401, "PASSWORD_MISMATCH")
        if not user.active:
            raise HTTPException(403, "Account suspended")
        user.last_login_at_ms = ms_now()
        token = _issue_session(db, user, body.deviceId)
        merge_device_on_login(db, body.deviceId, user)
        db.commit()
        return _auth_response(user, token)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            503,
            "Extension database unavailable — set EXT_DATABASE_URL in ailt_api/.env and restart cheradip-ailt",
        ) from exc


@router.get("/me")
def whoami(user: ExtUser = Depends(get_current_ext_user)) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "fullName": user.full_name,
        "role": user.role,
    }


@router.post("/logout")
def logout(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_ext_db),
) -> dict:
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        if token:
            db.execute(delete(ExtSession).where(ExtSession.token == token))
            db.commit()
    return {"ok": True, "message": "Signed out"}


@router.post("/logout-all")
def logout_all(
    user: ExtUser = Depends(get_current_ext_user),
    db: Session = Depends(get_ext_db),
) -> dict:
    _revoke_all_sessions(db, user.id)
    db.commit()
    return {"ok": True, "message": "Signed out on all devices"}


@router.post("/password/change")
def password_change(
    body: ExtPasswordChangeRequest,
    user: ExtUser = Depends(get_current_ext_user),
    db: Session = Depends(get_ext_db),
) -> dict:
    if not user.password_hash or not verify_password(body.currentPassword, user.password_hash):
        raise HTTPException(401, "Current password is incorrect")
    _validate_password(body.newPassword)
    user.password_hash = hash_password(body.newPassword)
    # Revoke every session, then rotate a fresh one for this caller.
    _revoke_all_sessions(db, user.id)
    new_token = _issue_session(db, user, body.deviceId)
    db.commit()
    return {"ok": True, "message": "Password updated", "sessionToken": new_token}


@router.post("/recovery/send")
def recovery_send(body: ExtRecoverySendRequest, db: Session = Depends(get_ext_db)) -> dict:
    email = body.email.strip().lower()
    user = db.scalar(select(ExtUser).where(ExtUser.email == email))
    if not user or not user.email:
        raise HTTPException(404, "Account not found")
    code = new_otp_code()
    db.add(ExtOtpCode(target=email, channel=_OTP_CHANNEL, code=code, expires_at=otp_expires_at()))
    db.commit()
    send_otp_email(to=email, purpose="Password reset", code=code)
    return {"ok": True, "message": f"Reset code sent to {email}"}


@router.post("/recovery/reset")
def recovery_reset(body: ExtRecoveryResetRequest, db: Session = Depends(get_ext_db)) -> dict:
    email = body.email.strip().lower()
    user = db.scalar(select(ExtUser).where(ExtUser.email == email))
    if not user:
        raise HTTPException(404, "Account not found")
    _validate_password(body.newPassword)
    row = db.scalar(
        select(ExtOtpCode)
        .where(ExtOtpCode.target == email, ExtOtpCode.channel == _OTP_CHANNEL, ExtOtpCode.used.is_(False))
        .order_by(ExtOtpCode.id.desc())
    )
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if not row or row.code != body.otp.strip() or row.expires_at < now:
        raise HTTPException(400, "Invalid or expired OTP")
    row.used = True
    user.password_hash = hash_password(body.newPassword)
    # A reset invalidates every existing session.
    _revoke_all_sessions(db, user.id)
    db.commit()
    return {"ok": True, "message": "Password reset successfully"}

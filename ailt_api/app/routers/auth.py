from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import (
    OtpCode,
    ReferralBalance,
    ReferralBalanceUsage,
    ReferralEarning,
    ReferralWithdrawal,
    SessionToken,
    Subscription,
    User,
    UserLearningActivity,
)
from app.schemas import (
    AccountDeleteRequest,
    AuthLoginRequest,
    AuthLoginResponse,
    EmailChangeConfirmRequest,
    EmailChangeSendRequest,
    EmailChangeSendResponse,
    OtpRequest,
    OtpVerifyRequest,
    PasswordUpdateConfirmRequest,
    PasswordUpdateSendRequest,
    PasswordUpdateSendResponse,
    RecoveryResetRequest,
    RecoverySendRequest,
    RecoverySendResponse,
    SignupInitRequest,
    SignupInitResponse,
)
from app.security import (
    hash_password,
    new_otp_code,
    new_session_token,
    otp_expires_at,
    session_expires_at,
    verify_password,
)
from app.services.email_service import send_otp_email

router = APIRouter(prefix="/auth", tags=["auth"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PASSWORD_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,}$")


def _issue_session(db: Session, user: User, device_id: str | None) -> str:
    token = new_session_token()
    db.add(
        SessionToken(
            user_id=user.id,
            token=token,
            device_id=device_id,
            expires_at=session_expires_at(),
        )
    )
    return token


def _revoke_all_sessions(db: Session, user_id: int) -> None:
    """Hard-revoke every session for a user (password change / logout-all)."""
    db.execute(delete(SessionToken).where(SessionToken.user_id == user_id))


def _login_response(user: User, token: str | None) -> AuthLoginResponse:
    return AuthLoginResponse(
        email=user.email or user.username or "",
        role=user.role,
        whatsapp=user.whatsapp,
        sessionToken=token,
        emailVerified=user.email_verified,
        whatsappVerified=user.whatsapp_verified,
    )


def _is_trusted_device(user: User, device_id: str | None) -> bool:
    return bool(
        device_id
        and user.registered_device_id
        and device_id.strip() == user.registered_device_id
    )


def _store_otp(db: Session, target: str, channel: str) -> str:
    code = new_otp_code()
    db.add(
        OtpCode(
            target=target.strip().lower() if "@" in target else target.strip(),
            channel=channel,
            code=code,
            expires_at=otp_expires_at(),
        )
    )
    return code


def _send_email_otp(db: Session, email: str, channel: str, purpose: str) -> None:
    code = _store_otp(db, email, channel)
    send_otp_email(to=email, purpose=purpose, code=code)


def _verify_otp_code(db: Session, target: str, channel: str, code: str) -> None:
    needle = target.strip().lower() if "@" in target else target.strip()
    row = db.scalar(
        select(OtpCode)
        .where(OtpCode.target == needle, OtpCode.channel == channel, OtpCode.used.is_(False))
        .order_by(OtpCode.id.desc())
    )
    if not row or row.code != code.strip():
        raise HTTPException(400, "Invalid or expired OTP")
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).replace(tzinfo=None)
    if row.expires_at < now:
        raise HTTPException(400, "Invalid or expired OTP")
    row.used = True


def _validate_password(password: str) -> None:
    if not PASSWORD_RE.match(password):
        raise HTTPException(400, "Password must be at least 8 characters with 1 letter and 1 number")


def _find_user_by_username(db: Session, username: str) -> User | None:
    needle = username.strip().lower() if "@" in username else username.strip()
    return db.scalar(
        select(User).where(
            (User.email == needle) | (User.whatsapp == needle) | (User.username == needle)
        )
    )


def _assert_email_available(db: Session, email: str, exclude_user_id: int | None = None) -> None:
    other = db.scalar(select(User).where(User.email == email))
    if other and other.id != exclude_user_id:
        raise HTTPException(409, "Email already registered")


@router.post("/login", response_model=AuthLoginResponse)
def login(body: AuthLoginRequest, db: Session = Depends(get_db)) -> AuthLoginResponse:
    username = body.username.strip()
    if "@" in username:
        username = username.lower()
    user = db.scalar(
        select(User).where(
            (User.email == username) | (User.whatsapp == username) | (User.username == username)
        )
    )
    if not user:
        raise HTTPException(401, "NOT_REGISTERED")
    if not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "PASSWORD_MISMATCH")
    token = _issue_session(db, user, body.deviceId)
    db.commit()
    return _login_response(user, token)


@router.post("/signup/init", response_model=SignupInitResponse)
def signup_init(body: SignupInitRequest, db: Session = Depends(get_db)) -> SignupInitResponse:
    email = body.email.strip().lower()
    username = body.username.strip()
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "Invalid email address")
    _validate_password(body.password)

    user = db.scalar(select(User).where(User.email == email))
    if user and user.email_verified:
        raise HTTPException(409, "Email already registered")

    if user is None:
        if db.scalar(select(User).where(User.username == username)):
            raise HTTPException(409, "Username already taken")
        user = User(
            email=email,
            username=username,
            full_name=body.fullName.strip(),
            password_hash=hash_password(body.password),
            role="user",
            email_verified=True,
            whatsapp_verified=False,
            login_with="email",
            registered_device_id=body.deviceId.strip() if body.deviceId else None,
        )
        db.add(user)
        db.flush()
        message = "Account created successfully"
    else:
        if db.scalar(select(User).where(User.username == username, User.id != user.id)):
            raise HTTPException(409, "Username already taken")
        user.full_name = body.fullName.strip()
        user.username = username
        user.password_hash = hash_password(body.password)
        user.email_verified = True
        user.login_with = "email"
        if body.deviceId:
            user.registered_device_id = body.deviceId.strip()
        message = "Account updated successfully"

    token = _issue_session(db, user, body.deviceId)
    db.commit()
    return SignupInitResponse(
        message=message,
        email=user.email or email,
        role=user.role,
        sessionToken=token,
    )


@router.post("/recovery/send", response_model=RecoverySendResponse)
def recovery_send(body: RecoverySendRequest, db: Session = Depends(get_db)) -> RecoverySendResponse:
    user = _find_user_by_username(db, body.username)
    if not user or not user.email:
        raise HTTPException(404, "Account not found")
    if _is_trusted_device(user, body.deviceId):
        return RecoverySendResponse(
            message="Same device as registration — no email code required",
            requiresOtp=False,
        )
    _send_email_otp(db, user.email, "recovery_email", "Password reset")
    db.commit()
    return RecoverySendResponse(
        message=f"Reset code sent to {user.email}",
        requiresOtp=True,
    )


@router.post("/recovery/reset")
def recovery_reset(body: RecoveryResetRequest, db: Session = Depends(get_db)) -> dict:
    user = _find_user_by_username(db, body.username)
    if not user or not user.email:
        raise HTTPException(404, "Account not found")
    _validate_password(body.newPassword)
    trusted = _is_trusted_device(user, body.deviceId)
    if not trusted:
        if not body.otp:
            raise HTTPException(400, "Verification code required")
        _verify_otp_code(db, user.email, "recovery_email", body.otp)
    user.password_hash = hash_password(body.newPassword)
    # Security: a password reset invalidates every existing session everywhere.
    _revoke_all_sessions(db, user.id)
    db.commit()
    return {"ok": True, "message": "Password reset successfully"}


@router.post("/password/update/send", response_model=PasswordUpdateSendResponse)
def password_update_send(
    body: PasswordUpdateSendRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PasswordUpdateSendResponse:
    if not user.password_hash or not verify_password(body.currentPassword, user.password_hash):
        raise HTTPException(401, "Current password is incorrect")
    if not user.email:
        raise HTTPException(400, "No email on account")
    if _is_trusted_device(user, body.deviceId):
        return PasswordUpdateSendResponse(
            message="Same device as registration — no email code required",
            requiresOtp=False,
        )
    _send_email_otp(db, user.email, "change_email", "Password update")
    db.commit()
    return PasswordUpdateSendResponse(
        message=f"Verification code sent to {user.email}",
        requiresOtp=True,
    )


@router.post("/password/update/confirm")
def password_update_confirm(
    body: PasswordUpdateConfirmRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not user.password_hash or not verify_password(body.currentPassword, user.password_hash):
        raise HTTPException(401, "Current password is incorrect")
    _validate_password(body.newPassword)
    trusted = _is_trusted_device(user, body.deviceId)
    if not trusted:
        if not body.otp:
            raise HTTPException(400, "Verification code required")
        if not user.email:
            raise HTTPException(400, "No email on account")
        _verify_otp_code(db, user.email, "change_email", body.otp)
    user.password_hash = hash_password(body.newPassword)
    # Break all existing sessions, then rotate a fresh one for this caller so the
    # device that changed the password stays logged in but others are signed out.
    _revoke_all_sessions(db, user.id)
    new_token = _issue_session(db, user, body.deviceId)
    db.commit()
    return {"ok": True, "message": "Password updated successfully", "sessionToken": new_token}


@router.post("/email/change/send", response_model=EmailChangeSendResponse)
def email_change_send(
    body: EmailChangeSendRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmailChangeSendResponse:
    if not user.email:
        raise HTTPException(400, "No email on account")
    if _is_trusted_device(user, body.deviceId):
        return EmailChangeSendResponse(
            message="Same device as registration — no email code required",
            requiresOtp=False,
        )
    _send_email_otp(db, user.email, "email_change", "Email change")
    db.commit()
    return EmailChangeSendResponse(
        message=f"Verification code sent to {user.email}",
        requiresOtp=True,
    )


@router.post("/email/change/confirm")
def email_change_confirm(
    body: EmailChangeConfirmRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    new_email = body.newEmail.strip().lower()
    if not EMAIL_RE.match(new_email):
        raise HTTPException(400, "Invalid email address")
    if not user.email:
        raise HTTPException(400, "No email on account")
    trusted = _is_trusted_device(user, body.deviceId)
    if not trusted:
        if not body.otp:
            raise HTTPException(400, "Verification code required")
        _verify_otp_code(db, user.email, "email_change", body.otp)
    _assert_email_available(db, new_email, exclude_user_id=user.id)
    user.email = new_email
    user.email_verified = True
    db.commit()
    return {"ok": True, "message": "Email updated successfully", "email": new_email}


@router.get("/me")
def whoami(user: User = Depends(get_current_user)) -> dict:
    """Validate the current session and return the signed-in identity."""
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
    db: Session = Depends(get_db),
) -> dict:
    """Sign out only the current device (delete this session token)."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        if token:
            db.execute(delete(SessionToken).where(SessionToken.token == token))
            db.commit()
    return {"ok": True, "message": "Signed out"}


@router.post("/logout-all")
def logout_all(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Sign out everywhere — deletes every session for this user."""
    _revoke_all_sessions(db, user.id)
    db.commit()
    return {"ok": True, "message": "Signed out on all devices"}


@router.post("/account/delete")
def delete_account(
    body: AccountDeleteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Permanently delete the signed-in AILT user account and associated server data.

    Requires the current password. Does not cancel Google Play subscriptions —
    the client must direct the user to Play subscription management.
    """
    if not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(400, "Incorrect password")
    if (user.role or "").lower() == "admin":
        raise HTTPException(400, "Admin accounts cannot be self-deleted; contact support")

    uid = user.id
    email = (user.email or "").strip().lower()

    # Break FK order carefully (usages → withdrawals/earnings → balances → learning → sessions → user).
    # Detach subscription user links (keep purchase rows for accounting / Play disputes).
    for sub in db.scalars(select(Subscription).where(Subscription.user_id == uid)).all():
        sub.user_id = None
    for sub in db.scalars(select(Subscription).where(Subscription.buyer_user_id == uid)).all():
        sub.buyer_user_id = None
    for sub in db.scalars(select(Subscription).where(Subscription.referrer_user_id == uid)).all():
        sub.referrer_user_id = None

    db.execute(delete(ReferralBalanceUsage).where(ReferralBalanceUsage.user_id == uid))
    db.execute(delete(ReferralWithdrawal).where(ReferralWithdrawal.user_id == uid))
    db.execute(delete(ReferralEarning).where(ReferralEarning.referrer_user_id == uid))
    db.execute(delete(ReferralBalance).where(ReferralBalance.user_id == uid))
    db.execute(delete(UserLearningActivity).where(UserLearningActivity.user_id == uid))
    db.execute(delete(SessionToken).where(SessionToken.user_id == uid))
    if email:
        db.execute(delete(OtpCode).where(OtpCode.target == email))

    db.delete(user)
    db.commit()
    return {
        "ok": True,
        "message": "Account deleted. Cancel any Google Play subscription separately to stop renewals.",
    }


# Legacy endpoints kept for older clients — email only, no WhatsApp auth.
@router.post("/register")
def register(body: OtpRequest, db: Session = Depends(get_db)) -> dict:
    target = body.target.strip().lower()
    if "@" not in target:
        raise HTTPException(400, "Email address required")
    _send_email_otp(db, target, "email", "Verification")
    db.commit()
    return {"ok": True, "message": "OTP sent to email"}


@router.post("/verify-email", response_model=AuthLoginResponse)
def verify_email(body: OtpVerifyRequest, db: Session = Depends(get_db)) -> AuthLoginResponse:
    email = body.target.strip().lower()
    _verify_otp_code(db, email, "email", body.code)
    user = db.scalar(select(User).where(User.email == email))
    if not user:
        user = User(
            email=email,
            password_hash=hash_password(new_session_token()[:16]),
            role="user",
            email_verified=True,
        )
        db.add(user)
        db.flush()
    else:
        user.email_verified = True
    token = _issue_session(db, user, None)
    db.commit()
    return _login_response(user, token)

"""Auth helpers mirroring ailt_api security patterns for Child Care."""

from __future__ import annotations

import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db.models import Q
from django.utils import timezone

from childcare import models
from childcare.email_service import send_otp_email

PASSWORD_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,}$")


def hash_password(password: str) -> str:
    return make_password(password)


def verify_password(plain: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    return check_password(plain, hashed)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def new_otp_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def otp_expires_at():
    minutes = int(getattr(settings, "OTP_TTL_MINUTES", 15) or 15)
    return timezone.now() + timedelta(minutes=minutes)


def session_expires_at():
    days = int(getattr(settings, "CHILDCARE_SESSION_TTL_DAYS", 30) or 30)
    return timezone.now() + timedelta(days=days)


def validate_password(password: str) -> str | None:
    if not PASSWORD_RE.match(password or ""):
        return "Password must be at least 8 characters with 1 letter and 1 number"
    return None


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def find_parent(identifier: str) -> models.ParentAccount | None:
    needle = (identifier or "").strip()
    if not needle:
        return None
    email_needle = needle.lower() if "@" in needle else needle
    return (
        models.ParentAccount.objects.using("childcare")
        .filter(Q(email=email_needle) | Q(username=needle) | Q(mobile_number=needle))
        .first()
    )


def store_and_send_otp(*, email: str, channel: str, purpose: str) -> str:
    target = normalize_email(email)
    code = new_otp_code()
    models.OtpCode.objects.using("childcare").create(
        target=target,
        channel=channel,
        code=code,
        expires_at=otp_expires_at(),
        used=False,
    )
    send_otp_email(to=target, purpose=purpose, code=code)
    return code


def verify_otp(*, email: str, channel: str, code: str) -> bool:
    target = normalize_email(email)
    row = (
        models.OtpCode.objects.using("childcare")
        .filter(target=target, channel=channel, used=False)
        .order_by("-id")
        .first()
    )
    if not row or row.code != (code or "").strip():
        return False
    if row.expires_at < timezone.now():
        return False
    row.used = True
    row.save(using="childcare", update_fields=["used"])
    return True


def issue_session(parent: models.ParentAccount, device_id: str | None) -> models.DeviceSession:
    token = new_session_token()
    device = (device_id or "").strip()
    if device and not parent.registered_device_id:
        parent.registered_device_id = device
        parent.save(using="childcare", update_fields=["registered_device_id", "updated_at"])
    session = models.DeviceSession.objects.using("childcare").create(
        parent=parent,
        token=token,
        device_id=device,
        is_active=True,
        expires_at=session_expires_at(),
        last_active_at=timezone.now(),
    )
    return session


def primary_child(parent: models.ParentAccount) -> models.ChildProfile | None:
    return (
        models.ChildProfile.objects.using("childcare")
        .filter(parent_id=parent.id)
        .order_by("id")
        .first()
    )


def auth_payload(parent: models.ParentAccount, session: models.DeviceSession) -> dict:
    child = primary_child(parent)
    child_data = None
    if child:
        child_data = {
            "id": child.id,
            "full_name": child.full_name,
            "birth_day": child.birth_day,
            "birth_month": child.birth_month,
            "birth_year": child.birth_year,
            "address": child.address,
        }
    return {
        "ok": True,
        "sessionToken": session.token,
        "email": parent.email,
        "username": parent.username,
        "fullName": parent.full_name,
        "emailVerified": parent.email_verified,
        "role": parent.role or "user",
        "child": child_data,
    }

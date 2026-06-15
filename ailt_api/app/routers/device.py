from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import DeviceTrial
from app.schemas import (
    DeviceRegisterRequest,
    DeviceRegisterResponse,
    GuestAiRecordRequest,
    GuestAiSyncRequest,
    GuestAiUsageResponse,
)
from app.security import ms_in_days, ms_now

router = APIRouter(prefix="/device", tags=["device"])


def _guest_ai_response(row: DeviceTrial) -> GuestAiUsageResponse:
    limit = settings.guest_ai_limit
    count = row.guest_ai_count or 0
    return GuestAiUsageResponse(
        count=count,
        limit=limit,
        requiresLogin=count >= limit,
    )


def _get_or_create_trial(db: Session, body: DeviceRegisterRequest) -> DeviceTrial:
    row = db.scalar(select(DeviceTrial).where(DeviceTrial.device_id == body.deviceId))
    if row:
        return row
    ends = ms_in_days(settings.trial_days)
    row = DeviceTrial(
        device_id=body.deviceId,
        model=body.model,
        os_version=body.osVersion,
        trial_ends_at_ms=ends,
        guest_ai_count=0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _get_or_create_by_device_id(db: Session, device_id: str) -> DeviceTrial:
    return _get_or_create_trial(
        db,
        DeviceRegisterRequest(deviceId=device_id, model="", osVersion=""),
    )


@router.post("/register", response_model=DeviceRegisterResponse)
def register_device(body: DeviceRegisterRequest, db: Session = Depends(get_db)) -> DeviceRegisterResponse:
    row = _get_or_create_trial(db, body)
    remaining_ms = max(0, row.trial_ends_at_ms - ms_now())
    days = max(0, int(remaining_ms / 86400000) + (1 if remaining_ms % 86400000 else 0))
    if remaining_ms == 0:
        days = 0
    return DeviceRegisterResponse(trialEndsAt=row.trial_ends_at_ms, trialDaysRemaining=min(days, settings.trial_days))


@router.post("/guest-ai-usage/sync", response_model=GuestAiUsageResponse)
def sync_guest_ai_usage(body: GuestAiSyncRequest, db: Session = Depends(get_db)) -> GuestAiUsageResponse:
    row = _get_or_create_by_device_id(db, body.deviceId)
    row.guest_ai_count = max(row.guest_ai_count or 0, body.localCount)
    db.commit()
    db.refresh(row)
    return _guest_ai_response(row)


@router.post("/guest-ai-usage/record", response_model=GuestAiUsageResponse)
def record_guest_ai_usage(body: GuestAiRecordRequest, db: Session = Depends(get_db)) -> GuestAiUsageResponse:
    row = _get_or_create_by_device_id(db, body.deviceId)
    limit = settings.guest_ai_limit
    if (row.guest_ai_count or 0) < limit:
        row.guest_ai_count = (row.guest_ai_count or 0) + 1
    db.commit()
    db.refresh(row)
    return _guest_ai_response(row)

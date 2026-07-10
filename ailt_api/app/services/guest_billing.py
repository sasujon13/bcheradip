"""Machine-keyed guest usage for the Cheradip extension (no login required)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ExtDeviceTrial, ExtUser
from app.services.plans import get_plan, ms_now
from app.services.quota_engine import can_start_new_request, evaluate_after_usage


def _guest_plan():
    return get_plan("free")


def get_or_create_device_trial(db: Session, device_id: str) -> ExtDeviceTrial:
    row = db.scalar(select(ExtDeviceTrial).where(ExtDeviceTrial.device_id == device_id).limit(1))
    if row:
        return row
    now = ms_now()
    row = ExtDeviceTrial(
        device_id=device_id,
        guest_requests=0,
        guest_line_edits=0,
        first_seen_at_ms=now,
        updated_at_ms=now,
    )
    db.add(row)
    db.flush()
    return row


def _guest_state(requests: int, line_edits: int) -> dict:
    plan = _guest_plan()
    state = can_start_new_request(
        plan_id="free",
        payg_enabled=False,
        team_requests=requests,
        team_lines=line_edits,
    )
    state["requests"] = requests
    state["lineEdits"] = line_edits
    state["quota"] = plan.request_quota
    state["lineQuota"] = plan.line_quota
    state["mode"] = "guest"
    state["allowed"] = True
    state["requiresLogin"] = not state.get("canStart", True)
    return state


def guest_status(db: Session, device_id: str) -> dict:
    row = get_or_create_device_trial(db, device_id)
    return _guest_state(int(row.guest_requests or 0), int(row.guest_line_edits or 0))


def record_guest_usage(db: Session, device_id: str, requests: int, line_edits: int) -> dict:
    row = get_or_create_device_trial(db, device_id)
    before = _guest_state(int(row.guest_requests or 0), int(row.guest_line_edits or 0))
    row.guest_requests = int(row.guest_requests or 0) + max(0, requests)
    row.guest_line_edits = int(row.guest_line_edits or 0) + max(0, line_edits)
    row.updated_at_ms = ms_now()
    db.commit()
    db.refresh(row)
    after = _guest_state(int(row.guest_requests or 0), int(row.guest_line_edits or 0))
    out = evaluate_after_usage(before, after)
    out.update(after)
    out["requiresLogin"] = not after.get("canStart", True)
    out["needsPayment"] = out.get("needsPayment", False)
    return out


def merge_device_on_login(db: Session, device_id: str | None, user: ExtUser) -> None:
    """Attach guest usage to the user's team so reinstall/login cannot reset quota."""
    if not device_id or not device_id.strip():
        return
    from app.services.plans import current_period_bounds
    from app.services.team_billing import _period_record, get_or_create_team

    device_id = device_id.strip()
    row = get_or_create_device_trial(db, device_id)
    row.linked_user_id = user.id
    guest_req = int(row.guest_requests or 0)
    guest_lines = int(row.guest_line_edits or 0)
    if guest_req == 0 and guest_lines == 0:
        row.updated_at_ms = ms_now()
        db.commit()
        return

    team = get_or_create_team(db, user)
    start_ms, _ = current_period_bounds()
    rec = _period_record(db, team.id, user.id, start_ms)
    rec.requests = int(rec.requests or 0) + guest_req
    rec.line_edits = int(rec.line_edits or 0) + guest_lines
    rec.updated_at_ms = ms_now()
    row.updated_at_ms = ms_now()
    db.commit()

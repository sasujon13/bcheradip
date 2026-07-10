"""One-time post-login bonus pool for Free plan users."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import ExtUser
from app.services.plans import get_plan


def free_extension_summary(user: ExtUser) -> dict:
    plan = get_plan("free")
    used_req = int(user.free_extension_requests or 0)
    used_lines = int(user.free_extension_line_edits or 0)
    claimed = bool(user.free_extension_claimed)
    exhausted = claimed and (
        used_req >= plan.request_quota or used_lines >= plan.line_quota
    )
    return {
        "freeExtensionClaimed": claimed,
        "freeExtensionAvailable": claimed and not exhausted,
        "freeExtensionRequests": used_req,
        "freeExtensionLines": used_lines,
        "freeExtensionQuota": plan.request_quota,
        "freeExtensionLineQuota": plan.line_quota,
        "freeExtensionExhausted": exhausted,
    }


def claim_free_extension(db: Session, user: ExtUser) -> dict:
    plan = get_plan("free")
    if user.free_extension_claimed:
        return {
            "ok": False,
            "message": "Free extension access was already claimed on this account.",
            **free_extension_summary(user),
        }
    user.free_extension_claimed = True
    user.free_extension_requests = 0
    user.free_extension_line_edits = 0
    db.commit()
    db.refresh(user)
    return {
        "ok": True,
        "message": f"Added {plan.request_quota} requests and {plan.line_quota} line edits to test Cheradip.",
        **free_extension_summary(user),
    }

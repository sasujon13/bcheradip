"""Quota preflight, post-usage evaluation, and PAYG payment thresholds."""

from __future__ import annotations

from app.services.plans import (
    PAYG_BUSINESS_FIRST_REMINDER_USD,
    PAYG_BUSINESS_HARD_CAP_USD,
    PAYG_BUSINESS_REMINDER_STEP_USD,
    get_plan,
    payg_gap_usd,
)


def quota_limit_message(
    *,
    limit_reason: str | None,
    used_requests: int,
    used_lines: int,
    request_quota: int,
    line_quota: int,
) -> str:
    if limit_reason == "line":
        return (
            f"You have reached your quota limit ({used_lines} line edits of "
            f"{line_quota} allowed)."
        )
    if limit_reason == "request":
        return (
            f"You have reached your quota limit ({used_requests} requests of "
            f"{request_quota} allowed)."
        )
    return "You have reached your quota limit."


def payg_payment_threshold_usd(plan_id: str) -> float | None:
    """Display hint for PAYG thresholds (Pro/Plus gap; Business hard cap)."""
    plan_id = (plan_id or "free").lower()
    if plan_id == "business":
        return PAYG_BUSINESS_HARD_CAP_USD
    return payg_gap_usd(plan_id)


def business_payg_reminder_tier(uncovered_usd: float) -> int | None:
    """0 at $100, 1 at $120, … None when under $100."""
    if uncovered_usd < PAYG_BUSINESS_FIRST_REMINDER_USD:
        return None
    return int((uncovered_usd - PAYG_BUSINESS_FIRST_REMINDER_USD) // PAYG_BUSINESS_REMINDER_STEP_USD)


def _payg_prepaid_hint(uncovered_usd: float) -> str:
    return (
        f"Pay-as-you-go usage: ${uncovered_usd:.2f}. "
        "Pay now or choose Prepaid for uninterrupted service."
    )


def evaluate_payg_status(plan_id: str, uncovered_usd: float) -> dict:
    """PAYG gating after included quota is exhausted."""
    plan_id = (plan_id or "free").lower()
    uncovered = round(max(0.0, uncovered_usd), 2)

    if plan_id == "business":
        if uncovered >= PAYG_BUSINESS_HARD_CAP_USD:
            return {
                "canStart": False,
                "blockNextRequest": True,
                "needsPayment": True,
                "reason": "payg_hard_cap",
                "paygUncoveredUsd": uncovered,
                "paygHardCapUsd": PAYG_BUSINESS_HARD_CAP_USD,
                "quotaMessage": (
                    f"Pay-as-you-go usage reached ${PAYG_BUSINESS_HARD_CAP_USD:.0f}. "
                    "Pay now or add prepaid credit to continue."
                ),
            }
        tier = business_payg_reminder_tier(uncovered)
        if tier is not None:
            return {
                "canStart": True,
                "blockNextRequest": False,
                "needsPayment": True,
                "reason": "payg_reminder",
                "paygReminderTier": tier,
                "paygUncoveredUsd": uncovered,
                "paygHardCapUsd": PAYG_BUSINESS_HARD_CAP_USD,
                "quotaMessage": _payg_prepaid_hint(uncovered),
            }
        return {
            "canStart": True,
            "blockNextRequest": False,
            "needsPayment": False,
            "reason": "payg",
            "paygUncoveredUsd": uncovered,
        }

    threshold = payg_gap_usd(plan_id)
    if threshold is not None and uncovered >= threshold:
        return {
            "canStart": False,
            "blockNextRequest": True,
            "needsPayment": True,
            "reason": "payg_threshold",
            "paygUncoveredUsd": uncovered,
            "paygThresholdUsd": threshold,
            "quotaMessage": _payg_prepaid_hint(uncovered),
        }
    return {
        "canStart": True,
        "blockNextRequest": False,
        "needsPayment": uncovered > 0,
        "reason": "payg",
        "paygUncoveredUsd": uncovered,
        "paygThresholdUsd": threshold,
        "quotaMessage": _payg_prepaid_hint(uncovered) if uncovered > 0 else None,
    }


def _limit_reason(team_requests: int, team_lines: int, req_quota: int, line_quota: int) -> str | None:
    if team_lines >= line_quota:
        return "line"
    if team_requests >= req_quota:
        return "request"
    return None


def can_start_new_request(
    *,
    plan_id: str,
    payg_enabled: bool,
    team_requests: int,
    team_lines: int,
    credit_balance_usd: float = 0.0,
    free_extension_claimed: bool = False,
    bonus_requests: int = 0,
    bonus_lines: int = 0,
) -> dict:
    """Whether a *new* chat request may begin (current request always finishes)."""
    plan = get_plan(plan_id)
    req_q = plan.request_quota
    line_q = plan.line_quota
    limit_reason = _limit_reason(team_requests, team_lines, req_q, line_q)

    base = {
        "canStart": True,
        "blockNextRequest": False,
        "needsPayment": False,
        "requiresLogin": False,
        "reason": "ok",
        "limitReason": None,
        "quotaMessage": None,
        "teamRequests": team_requests,
        "teamLines": team_lines,
        "quota": req_q,
        "lineQuota": line_q,
        "paygThresholdUsd": payg_payment_threshold_usd(plan_id),
    }

    if limit_reason is None:
        return base

    base["limitReason"] = limit_reason

    if plan.payg_allowed and payg_enabled:
        from app.services.team_billing import _overage_billing

        bill = _overage_billing(plan_id, team_requests, team_lines)["billUsd"]
        uncovered = round(max(0.0, bill - credit_balance_usd), 2)
        base["overageUsd"] = bill
        payg = evaluate_payg_status(plan_id, uncovered)
        base.update(payg)
        return base

    if free_extension_claimed:
        bonus_limit = _limit_reason(bonus_requests, bonus_lines, req_q, line_q)
        if bonus_limit is None:
            base["reason"] = "free_extension"
            return base

    msg = quota_limit_message(
        limit_reason=limit_reason,
        used_requests=team_requests,
        used_lines=team_lines,
        request_quota=req_q,
        line_quota=line_q,
    )
    base.update(
        {
            "canStart": False,
            "blockNextRequest": True,
            "needsPayment": plan_id == "free",
            "reason": "quota_exceeded",
            "quotaMessage": msg,
        }
    )
    if plan_id == "free" and not free_extension_claimed:
        base["requiresLogin"] = False
    return base


def evaluate_after_usage(
    before: dict,
    after: dict,
) -> dict:
    """Merge post-record state; flag when quota was crossed during this batch."""
    out = dict(after)
    out["allowed"] = True
    out["blockNextRequest"] = not after.get("canStart", True)
    before_ok = before.get("canStart", True)
    after_ok = after.get("canStart", True)
    out["quotaJustExceeded"] = before_ok and not after_ok

    before_tier = before.get("paygReminderTier")
    after_tier = after.get("paygReminderTier")
    if after_tier is not None and (before_tier is None or after_tier > before_tier):
        out["showPaygReminder"] = True
        if after.get("quotaMessage"):
            out["showQuotaMessage"] = after["quotaMessage"]
    elif out["quotaJustExceeded"] and after.get("quotaMessage"):
        out["showQuotaMessage"] = after["quotaMessage"]

    return out

"""Cheradip extension plan catalog + pay-as-you-go (PAYG) logic.

Cursor-style tiers:
  free      — no cost, small monthly request quota, no PAYG
  pro       — base unit (X requests / month)
  plus      — 3x Pro quota and price
  business  — 10x Pro quota and price

PAYG is an add-on that requires an active paid plan (pro/plus/business).
When accumulated overage reaches the *price gap to the next tier* the client is
asked to either pay the outstanding PAYG amount now, or subscribe to the next
tier (also a payment) — so charges are not deferred to the end of the month.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class PlanDef:
    id: str
    name: str
    price_usd: float
    request_quota: int  # included fast requests per month
    payg_allowed: bool
    stripe_price_env: str  # settings attribute holding the Stripe price id
    paddle_price_env: str = ""  # settings attribute holding the Paddle price id


# Base unit = Pro. Price: Plus = 3x, Business = 10x of Pro.
# Pricing is half of Cursor for the same request quota (2x requests per dollar):
#   Pro $10 (Cursor $20 quota), Plus $30 (Cursor $60), Business $100 (Cursor $200).
# Bonus requests on top of the price multiple make the quotas more generous:
#   Plus  = 3x price but 4x requests  (1500 + 500 bonus  = 2000)
#   Business = 10x price but 15x requests (5000 + 2500 bonus = 7500)
_PRO_QUOTA = 500
_PRO_PRICE = 10.0

PLANS: dict[str, PlanDef] = {
    "free": PlanDef("free", "Free", 0.0, 50, False, "", ""),
    "pro": PlanDef("pro", "Pro", _PRO_PRICE, _PRO_QUOTA, True, "stripe_price_pro", "paddle_price_pro"),
    "plus": PlanDef(
        "plus", "Plus", _PRO_PRICE * 3, _PRO_QUOTA * 4, True, "stripe_price_plus", "paddle_price_plus"
    ),
    "business": PlanDef(
        "business",
        "Business",
        _PRO_PRICE * 10,
        _PRO_QUOTA * 15,
        True,
        "stripe_price_business",
        "paddle_price_business",
    ),
}

# Order used for "next label" upgrade prompts.
PLAN_ORDER = ["free", "pro", "plus", "business"]

# Price per extra request beyond the monthly quota (PAYG).
# Same effective rate as a paid plan: $10 / 500 requests = $0.02 per request.
PAYG_UNIT_USD = 0.02


def get_plan(plan_id: str | None) -> PlanDef:
    return PLANS.get((plan_id or "free").lower(), PLANS["free"])


def next_plan(plan_id: str) -> PlanDef | None:
    plan_id = (plan_id or "free").lower()
    if plan_id not in PLAN_ORDER:
        return None
    idx = PLAN_ORDER.index(plan_id)
    if idx + 1 >= len(PLAN_ORDER):
        return None
    return PLANS[PLAN_ORDER[idx + 1]]


def payg_gap_usd(plan_id: str) -> float | None:
    """USD of overage that equals the cost of upgrading to the next tier.

    Once accumulated PAYG >= this gap, prompt the user to pay now or upgrade.
    Returns None for the top tier (no next label — just settle PAYG).
    """
    cur = get_plan(plan_id)
    nxt = next_plan(plan_id)
    if nxt is None:
        return None
    return round(max(0.0, nxt.price_usd - cur.price_usd), 2)


def ms_now() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def current_period_bounds() -> tuple[int, int]:
    """UTC calendar-month period [start_ms, end_ms)."""
    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_day = monthrange(now.year, now.month)[1]
    end = start.replace(day=last_day, hour=23, minute=59, second=59)
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000) + 1000
    return start_ms, end_ms


def public_catalog() -> list[dict]:
    """Plan list for GET /subscription/plans (client pricing UI)."""
    out: list[dict] = []
    for pid in PLAN_ORDER:
        p = PLANS[pid]
        out.append(
            {
                "id": p.id,
                "name": p.name,
                "priceUsd": p.price_usd,
                "requestQuota": p.request_quota,
                "paygAllowed": p.payg_allowed,
                "multiplierOfPro": round(p.request_quota / _PRO_QUOTA, 2) if _PRO_QUOTA else 1,
            }
        )
    return out

"""Provider-agnostic billing event, produced by each gateway's webhook parser.

Both the Paddle and Stripe gateways normalize their webhooks into this shape so
the subscription router does not care which processor is active.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BillingEvent:
    # "checkout_completed" | "subscription_updated" | "subscription_canceled" | "ignored"
    type: str
    product: str = "ext"  # "ext" (coding extension) | "ailt" (language tutor app)
    kind: str | None = None  # "subscription" | "payg"
    team_id: int | None = None  # ext product
    user_id: int | None = None  # ailt product (main-DB User id)
    plan: str | None = None
    charge_id: int | None = None
    amount_usd: float = 0.0
    currency: str = "USD"
    customer_id: str | None = None
    subscription_id: str | None = None
    transaction_id: str | None = None  # provider transaction/session/invoice id
    payment_intent: str | None = None
    status: str | None = None  # for subscription_updated (active/past_due/canceled)

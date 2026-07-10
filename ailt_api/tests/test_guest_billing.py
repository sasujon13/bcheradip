"""Tests for machine-keyed guest billing and PAYG tiers."""

from app.services.guest_billing import _guest_state
from app.services.quota_engine import (
    business_payg_reminder_tier,
    can_start_new_request,
    evaluate_payg_status,
    payg_payment_threshold_usd,
)


def test_guest_within_quota():
    d = _guest_state(10, 100)
    assert d["canStart"] is True
    assert d["blockNextRequest"] is False


def test_guest_request_exhausted_blocks_next():
    d = _guest_state(50, 100)
    assert d["canStart"] is False
    assert d["blockNextRequest"] is True
    assert "50 requests" in (d.get("quotaMessage") or "")


def test_guest_line_exhausted_blocks_next():
    d = _guest_state(10, 500)
    assert d["canStart"] is False
    assert d["limitReason"] == "line"
    assert "500" in (d.get("quotaMessage") or "")


def test_payg_pro_threshold_is_upgrade_gap():
    assert payg_payment_threshold_usd("pro") == 20.0


def test_payg_business_hard_cap_is_200():
    assert payg_payment_threshold_usd("business") == 200.0


def test_business_reminder_tier_at_100():
    assert business_payg_reminder_tier(100.0) == 0
    assert business_payg_reminder_tier(119.99) == 0
    assert business_payg_reminder_tier(120.0) == 1


def test_business_payg_reminder_allows_continue():
    d = evaluate_payg_status("business", 120.0)
    assert d["canStart"] is True
    assert d["reason"] == "payg_reminder"
    assert d["paygReminderTier"] == 1
    assert "Prepaid" in d["quotaMessage"]


def test_business_payg_hard_block_at_200():
    d = evaluate_payg_status("business", 200.0)
    assert d["canStart"] is False
    assert d["reason"] == "payg_hard_cap"


def test_payg_pro_allows_next_request_under_threshold():
    d = can_start_new_request(
        plan_id="pro",
        payg_enabled=True,
        team_requests=600,
        team_lines=6000,
        credit_balance_usd=0.0,
    )
    assert d["canStart"] is True
    assert d["reason"] == "payg"

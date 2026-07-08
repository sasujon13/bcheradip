"""Unit tests for line-edit vs request metering and PAYG max-billing."""

from __future__ import annotations

from app.services.plans import PAYG_LINE_UNIT_USD, PAYG_UNIT_USD, PLANS
from app.services.team_billing import _overage_billing


def test_within_both_quotas_is_not_exhausted():
    b = _overage_billing("pro", team_requests=100, team_lines=1000)
    assert b["reqOver"] == 0 and b["lineOver"] == 0
    assert b["lineExhausted"] is False and b["reqExhausted"] is False
    assert b["billUsd"] == 0.0


def test_line_edits_are_first_priority_limit():
    # Lines over quota, requests still within quota → line-limited.
    pro = PLANS["pro"]
    b = _overage_billing("pro", team_requests=pro.request_quota - 1, team_lines=pro.line_quota + 200)
    assert b["lineExhausted"] is True
    assert b["reqExhausted"] is False
    assert b["lineOver"] == 200
    assert b["billUsd"] == round(200 * PAYG_LINE_UNIT_USD, 2)


def test_requests_are_fallback_limit():
    pro = PLANS["pro"]
    b = _overage_billing("pro", team_requests=pro.request_quota + 10, team_lines=pro.line_quota - 5)
    assert b["reqExhausted"] is True
    assert b["lineExhausted"] is False
    assert b["reqOver"] == 10
    assert b["billUsd"] == round(10 * PAYG_UNIT_USD, 2)


def test_payg_bill_is_the_larger_of_the_two():
    # Example from the spec: request bill $5.20 vs line bill $5.80 → charge $5.80.
    pro = PLANS["pro"]
    req_over = int(round(5.20 / PAYG_UNIT_USD))  # 260 requests -> $5.20
    line_over = int(round(5.80 / PAYG_LINE_UNIT_USD))  # 2900 lines -> $5.80
    b = _overage_billing(
        "pro",
        team_requests=pro.request_quota + req_over,
        team_lines=pro.line_quota + line_over,
    )
    assert b["reqBillUsd"] == 5.20
    assert b["lineBillUsd"] == 5.80
    assert b["billUsd"] == 5.80  # max, never the sum

"""Unit tests for Cheradip extension plan catalog + PAYG gap logic."""

from __future__ import annotations

from app.services.plans import (
    PAYG_LINE_UNIT_USD,
    PAYG_UNIT_USD,
    PLANS,
    get_plan,
    next_plan,
    payg_gap_usd,
    public_catalog,
)


def test_multipliers_pro_plus_business():
    # Price stays 3x / 10x of Pro, but bonus requests make quotas 4x / 15x.
    assert PLANS["plus"].request_quota == PLANS["pro"].request_quota * 4
    assert PLANS["business"].request_quota == PLANS["pro"].request_quota * 15
    assert PLANS["plus"].price_usd == PLANS["pro"].price_usd * 3
    assert PLANS["business"].price_usd == PLANS["pro"].price_usd * 10


def test_line_quotas():
    # Line-edit quota is 10x the request quota per plan.
    assert PLANS["free"].line_quota == 500
    assert PLANS["pro"].line_quota == 5000
    assert PLANS["plus"].line_quota == 20000
    assert PLANS["business"].line_quota == 75000
    for p in PLANS.values():
        assert p.line_quota == p.request_quota * 10


def test_payg_line_unit_is_tenth_of_request_unit():
    # 1 request or 10 line edits, each $0.02 → $0.002 per line.
    assert PAYG_UNIT_USD == 0.02
    assert PAYG_LINE_UNIT_USD == 0.002


def test_free_has_no_payg():
    assert get_plan("free").payg_allowed is False
    assert get_plan("pro").payg_allowed is True


def test_next_plan_order():
    assert next_plan("free").id == "pro"
    assert next_plan("pro").id == "plus"
    assert next_plan("plus").id == "business"
    assert next_plan("business") is None


def test_payg_gap_equals_upgrade_delta():
    # Reaching this overage costs the same as upgrading to the next tier.
    assert payg_gap_usd("pro") == PLANS["plus"].price_usd - PLANS["pro"].price_usd
    assert payg_gap_usd("plus") == PLANS["business"].price_usd - PLANS["plus"].price_usd
    assert payg_gap_usd("business") is None


def test_unknown_plan_defaults_to_free():
    assert get_plan("bogus").id == "free"
    assert get_plan(None).id == "free"


def test_public_catalog_shape():
    cat = public_catalog()
    ids = [p["id"] for p in cat]
    assert ids == ["free", "pro", "plus", "business"]
    assert all("priceUsd" in p and "requestQuota" in p and "lineQuota" in p for p in cat)

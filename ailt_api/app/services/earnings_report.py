"""Admin earnings report aggregation by period."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ReferralEarning, Subscription
from app.services.referral_earnings import mature_pending_earnings, now_ms

PERIOD_DAILY = "daily"
PERIOD_MONTHLY = "monthly"
PERIOD_QUARTERLY = "quarterly"
PERIOD_HALF_YEARLY = "half_yearly"
PERIOD_YEARLY = "yearly"
PERIOD_BI_ANNUALLY = "bi_annually"
PERIOD_LIFETIME = "lifetime"
PERIOD_CUSTOM = "custom"
PERIOD_LIFETIME_BUCKET = "lifetime_bucket"

VALID_PERIODS = frozenset(
    {
        PERIOD_DAILY,
        PERIOD_MONTHLY,
        PERIOD_QUARTERLY,
        PERIOD_HALF_YEARLY,
        PERIOD_YEARLY,
        PERIOD_BI_ANNUALLY,
        PERIOD_LIFETIME,
        PERIOD_CUSTOM,
    }
)


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    return datetime.strptime(raw.strip()[:10], "%Y-%m-%d").date()


def _bucket_key(period: str, d: date) -> str:
    if period == PERIOD_LIFETIME_BUCKET:
        return "Lifetime"
    if period == PERIOD_DAILY:
        return d.isoformat()
    if period == PERIOD_MONTHLY:
        return f"{d.year:04d}-{d.month:02d}"
    if period == PERIOD_QUARTERLY:
        q = (d.month - 1) // 3 + 1
        return f"{d.year:04d}-Q{q}"
    if period == PERIOD_HALF_YEARLY:
        h = 1 if d.month <= 6 else 2
        return f"{d.year:04d}-H{h}"
    if period == PERIOD_YEARLY:
        return f"{d.year:04d}"
    if period == PERIOD_BI_ANNUALLY:
        start_year = d.year - (d.year % 2)
        return f"{start_year:04d}-{start_year + 1:04d}"
    return "lifetime"


def _bucket_label(key: str) -> str:
    return key


def _date_range(period: str, from_date: date | None, to_date: date | None) -> tuple[date, date]:
    today = datetime.utcnow().date()
    end = to_date or today
    if period == PERIOD_LIFETIME:
        start = from_date or date(2020, 1, 1)
        return start, end
    if period == PERIOD_DAILY:
        start = from_date or (end - timedelta(days=29))
        return start, end
    if period == PERIOD_MONTHLY:
        start = from_date or date(end.year, end.month, 1) - timedelta(days=365)
        return start, end
    if period == PERIOD_QUARTERLY:
        start = from_date or (end - timedelta(days=365))
        return start, end
    if period == PERIOD_HALF_YEARLY:
        start = from_date or (end - timedelta(days=730))
        return start, end
    if period == PERIOD_YEARLY:
        start = from_date or date(end.year - 4, 1, 1)
        return start, end
    if period == PERIOD_BI_ANNUALLY:
        start = from_date or date(end.year - 5, 1, 1)
        return start, end
    if period == PERIOD_CUSTOM:
        if not from_date or not to_date:
            raise ValueError("Custom period requires from and to dates (YYYY-MM-DD)")
        if from_date > to_date:
            raise ValueError("from date must be on or before to date")
        return from_date, to_date
    raise ValueError(f"Unsupported period: {period}")


def _custom_bucket_period(start: date, end: date) -> str:
    span = (end - start).days + 1
    if span <= 31:
        return PERIOD_DAILY
    if span <= 366:
        return PERIOD_MONTHLY
    return PERIOD_QUARTERLY


def _empty_metrics() -> dict[str, float]:
    return {
        "pending": 0.0,
        "available": 0.0,
        "net_pending": 0.0,
        "net_available": 0.0,
        "total_referral": 0.0,
    }


def _finalize(metrics: dict[str, float]) -> dict[str, float]:
    metrics["net_pending"] = round(metrics["pending"] - metrics.get("_ref_pending", 0.0), 2)
    metrics["net_available"] = round(metrics["available"] - metrics.get("_ref_available", 0.0), 2)
    metrics["total_referral"] = round(
        metrics.get("_ref_pending", 0.0) + metrics.get("_ref_available", 0.0),
        2,
    )
    for key in ("pending", "available", "net_pending", "net_available", "total_referral"):
        metrics[key] = round(metrics[key], 2)
    metrics.pop("_ref_pending", None)
    metrics.pop("_ref_available", None)
    return metrics


def build_earnings_report(
    db: Session,
    *,
    period: str,
    from_raw: str | None = None,
    to_raw: str | None = None,
) -> dict[str, Any]:
    mature_pending_earnings(db)
    db.flush()

    period_key = (period or PERIOD_MONTHLY).strip().lower()
    if period_key not in VALID_PERIODS:
        raise ValueError(
            "period must be one of: daily, monthly, quarterly, half_yearly, yearly, bi_annually, lifetime, custom"
        )

    from_date = _parse_date(from_raw)
    to_date = _parse_date(to_raw)
    start, end = _date_range(period_key, from_date, to_date)

    bucket_period = period_key
    if period_key == PERIOD_CUSTOM:
        bucket_period = _custom_bucket_period(start, end)
    elif period_key == PERIOD_LIFETIME:
        bucket_period = PERIOD_LIFETIME_BUCKET

    start_ms = int(datetime.combine(start, datetime.min.time()).timestamp() * 1000)
    end_ms = int(datetime.combine(end, datetime.max.time()).timestamp() * 1000)
    current_ms = now_ms()

    subs = db.scalars(
        select(Subscription).where(
            Subscription.paid_at_ms.is_not(None),
            Subscription.paid_at_ms >= start_ms,
            Subscription.paid_at_ms <= end_ms,
        )
    ).all()

    earnings = db.scalars(
        select(ReferralEarning).where(
            ReferralEarning.created_at >= datetime.combine(start, datetime.min.time()),
            ReferralEarning.created_at <= datetime.combine(end, datetime.max.time()),
        )
    ).all()

    buckets: dict[str, dict[str, float]] = defaultdict(_empty_metrics)

    for sub in subs:
        paid_ms = sub.paid_at_ms or 0
        paid_day = datetime.utcfromtimestamp(paid_ms / 1000).date()
        key = _bucket_key(bucket_period, paid_day)
        revenue = float(
            sub.play_amount_usd or sub.net_amount_usd or sub.gross_amount_usd or 0.0
        )
        if sub.expires_at_ms and sub.expires_at_ms > current_ms:
            buckets[key]["pending"] += revenue
        else:
            buckets[key]["available"] += revenue

    for earning in earnings:
        created_day = earning.created_at.date() if earning.created_at else start
        key = _bucket_key(bucket_period, created_day)
        amount = float(earning.amount_usd)
        # Use live pending/available split (respects maturation), not only DB status at query time.
        if earning.status == "pending" and earning.clears_at_ms > current_ms:
            buckets[key]["_ref_pending"] += amount
        else:
            buckets[key]["_ref_available"] += amount

    rows = []
    totals_raw = _empty_metrics()
    for key in sorted(buckets.keys()):
        metrics = _finalize(dict(buckets[key]))
        rows.append({"label": _bucket_label(key), **metrics})
        totals_raw["pending"] += buckets[key]["pending"]
        totals_raw["available"] += buckets[key]["available"]
        totals_raw["_ref_pending"] = totals_raw.get("_ref_pending", 0.0) + buckets[key].get(
            "_ref_pending", 0.0
        )
        totals_raw["_ref_available"] = totals_raw.get("_ref_available", 0.0) + buckets[key].get(
            "_ref_available", 0.0
        )

    if period_key == PERIOD_LIFETIME and not rows:
        rows.append({"label": "Lifetime", **_finalize(_empty_metrics())})

    totals = _finalize(totals_raw)

    return {
        "period": period_key,
        "bucket_period": bucket_period,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "generated_at_ms": current_ms,
        "totals": totals,
        "rows": rows,
    }

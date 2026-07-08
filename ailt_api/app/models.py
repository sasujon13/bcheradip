from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.ext_database import ExtBase


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    whatsapp: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="user")
    full_name: Mapped[str | None] = mapped_column(String(80))
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    whatsapp_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    login_with: Mapped[str | None] = mapped_column(String(16))
    registered_device_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    sessions: Mapped[list[SessionToken]] = relationship(back_populates="user")
    referral_balance: Mapped[ReferralBalance | None] = relationship(back_populates="user")


class SessionToken(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    device_id: Mapped[str | None] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped[User] = relationship(back_populates="sessions")


class OtpCode(Base):
    __tablename__ = "otp_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target: Mapped[str] = mapped_column(String(255), index=True)
    channel: Mapped[str] = mapped_column(String(16))
    code: Mapped[str] = mapped_column(String(8))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DeviceTrial(Base):
    __tablename__ = "device_trials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    model: Mapped[str] = mapped_column(String(128), default="")
    os_version: Mapped[str] = mapped_column(String(64), default="")
    trial_ends_at_ms: Mapped[int] = mapped_column(BigInteger)
    guest_ai_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    buyer_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    referrer_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    device_id: Mapped[str | None] = mapped_column(String(128), index=True)
    product_id: Mapped[str] = mapped_column(String(64))
    purchase_token: Mapped[str] = mapped_column(String(512))
    tier: Mapped[str] = mapped_column(String(16), default="pro")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at_ms: Mapped[int | None] = mapped_column(BigInteger)
    gross_amount_usd: Mapped[float] = mapped_column(Float, default=0.0)
    net_amount_usd: Mapped[float] = mapped_column(Float, default=0.0)
    play_amount_usd: Mapped[float] = mapped_column(Float, default=0.0)
    referral_balance_used_usd: Mapped[float] = mapped_column(Float, default=0.0)
    referral_commission_usd: Mapped[float] = mapped_column(Float, default=0.0)
    paid_at_ms: Mapped[int | None] = mapped_column(BigInteger, index=True)
    slot1_code: Mapped[str | None] = mapped_column(String(64))
    slot2_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ExtUser(ExtBase):
    """Cheradip VS Code extension account — separate user space from the AILT app."""

    __tablename__ = "ext_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="user")  # user|admin
    full_name: Mapped[str | None] = mapped_column(String(80))
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)  # admin can suspend
    last_login_at_ms: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ExtSession(ExtBase):
    """Session token for a Cheradip extension user (session-based auth)."""

    __tablename__ = "ext_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("ext_users.id"), index=True)
    token: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    device_id: Mapped[str | None] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ExtOtpCode(ExtBase):
    """OTP codes for extension account recovery (separate from the app OTP table)."""

    __tablename__ = "ext_otp_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target: Mapped[str] = mapped_column(String(255), index=True)
    channel: Mapped[str] = mapped_column(String(16))
    code: Mapped[str] = mapped_column(String(8))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AppSetting(ExtBase):
    """Runtime, admin-editable settings (e.g. Paddle keys) — DB overrides .env.

    Stored in the extension database so the Paddle payment credentials can be
    set from the admin page without a redeploy. Secret values live only here.
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)
    updated_at_ms: Mapped[int | None] = mapped_column(BigInteger)


class BillingTeam(ExtBase):
    """Cursor-style team billing account for the Cheradip VS Code extension.

    One team = one Stripe subscription. All member usage bills together.
    """

    __tablename__ = "billing_teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), default="My Team")
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("ext_users.id"), index=True)
    plan: Mapped[str] = mapped_column(String(16), default="free")  # free|pro|plus|business
    payg_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|past_due|canceled
    seats: Mapped[int] = mapped_column(Integer, default=1)
    license_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64), index=True)
    current_period_start_ms: Mapped[int | None] = mapped_column(BigInteger)
    current_period_end_ms: Mapped[int | None] = mapped_column(BigInteger)
    payg_due_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TeamMember(ExtBase):
    __tablename__ = "team_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("billing_teams.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("ext_users.id"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="member")  # owner|admin|member
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class UsageRecord(ExtBase):
    """Per team+user usage within a billing period (month)."""

    __tablename__ = "usage_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("billing_teams.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("ext_users.id"), index=True)
    period_start_ms: Mapped[int] = mapped_column(BigInteger, index=True)
    requests: Mapped[int] = mapped_column(Integer, default=0)
    line_edits: Mapped[int] = mapped_column(BigInteger, default=0)  # replacements + insertions
    tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    overage_units: Mapped[int] = mapped_column(Integer, default=0)
    overage_usd: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at_ms: Mapped[int] = mapped_column(BigInteger, default=0)


class PaygCharge(ExtBase):
    __tablename__ = "payg_charges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("billing_teams.id"), index=True)
    units: Mapped[int] = mapped_column(Integer, default=0)  # request overage units
    line_units: Mapped[int] = mapped_column(Integer, default=0)  # line-edit overage units
    amount_usd: Mapped[float] = mapped_column(Float, default=0.0)  # max(request bill, line bill)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|paid
    stripe_payment_intent: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ExtPayment(ExtBase):
    """Payment history for the Cheradip extension (subscriptions, PAYG, credits, refunds)."""

    __tablename__ = "ext_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("billing_teams.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("ext_users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(24), default="subscription")
    # subscription | payg | credit_topup | refund | adjustment
    plan: Mapped[str | None] = mapped_column(String(16))
    amount_usd: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(8), default="usd")
    status: Mapped[str] = mapped_column(String(16), default="paid")  # paid|pending|failed|refunded
    description: Mapped[str | None] = mapped_column(String(255))
    stripe_payment_intent: Mapped[str | None] = mapped_column(String(64), index=True)
    stripe_invoice_id: Mapped[str | None] = mapped_column(String(64), index=True)
    stripe_session_id: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at_ms: Mapped[int] = mapped_column(BigInteger, index=True, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CreditBalance(ExtBase):
    """Prepaid credit wallet per team — offsets PAYG / subscription; admin can grant."""

    __tablename__ = "credit_balances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("billing_teams.id"), unique=True, index=True)
    balance_usd: Mapped[float] = mapped_column(Float, default=0.0)
    lifetime_added_usd: Mapped[float] = mapped_column(Float, default=0.0)
    lifetime_spent_usd: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at_ms: Mapped[int] = mapped_column(BigInteger, default=0)


class CreditTransaction(ExtBase):
    """Ledger of every credit change (grant, spend, refund, adjustment)."""

    __tablename__ = "credit_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("billing_teams.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("ext_users.id"), index=True)
    # actor: admin who granted, or the user who spent
    delta_usd: Mapped[float] = mapped_column(Float, default=0.0)  # +grant / -spend
    reason: Mapped[str] = mapped_column(String(64), default="adjustment")
    balance_after_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at_ms: Mapped[int] = mapped_column(BigInteger, index=True, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    discount_percent: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_apply: Mapped[bool] = mapped_column(Boolean, default=False)
    paywall_slot: Mapped[int] = mapped_column(Integer, default=2)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ReferralPolicy(Base):
    __tablename__ = "referral_policy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    buyer_discount_percent: Mapped[int] = mapped_column(Integer, default=20)
    commission_percent: Mapped[int] = mapped_column(Integer, default=20)
    notice_text: Mapped[str] = mapped_column(Text, default="")


class ReferralBalance(Base):
    __tablename__ = "referral_balances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    balance_usd: Mapped[float] = mapped_column(Float, default=0.0)
    pending_usd: Mapped[float] = mapped_column(Float, default=0.0)
    available_usd: Mapped[float] = mapped_column(Float, default=0.0)
    lifetime_earned_usd: Mapped[float] = mapped_column(Float, default=0.0)

    user: Mapped[User] = relationship(back_populates="referral_balance")


class ReferralEarning(Base):
    __tablename__ = "referral_earnings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"), index=True)
    referrer_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount_usd: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    clears_at_ms: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ReferralBalanceUsage(Base):
    __tablename__ = "referral_balance_usages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    usage_type: Mapped[str] = mapped_column(String(16))
    amount_usd: Mapped[float] = mapped_column(Float)
    recipient_email: Mapped[str | None] = mapped_column(String(255))
    subscription_id: Mapped[int | None] = mapped_column(ForeignKey("subscriptions.id"), index=True)
    withdrawal_id: Mapped[int | None] = mapped_column(ForeignKey("referral_withdrawals.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ReferralWithdrawal(Base):
    __tablename__ = "referral_withdrawals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount_usd: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(32))
    payout_details: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class LanguagePack(Base):
    __tablename__ = "language_packs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    download_url: Mapped[str | None] = mapped_column(String(512))
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AiProvider(Base):
    __tablename__ = "ai_providers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128))
    tier: Mapped[str] = mapped_column(String(16), default="free")
    health: Mapped[str] = mapped_column(String(16), default="healthy")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    quota_daily_limit: Mapped[int | None] = mapped_column(Integer)
    requests_today: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    last_used_at_ms: Mapped[int | None] = mapped_column(BigInteger)


class AiRoutingPolicy(Base):
    __tablename__ = "ai_routing_policy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mode: Mapped[str] = mapped_column(String(32), default="random_free")
    prefer_paid_when_free_exhausted: Mapped[bool] = mapped_column(Boolean, default=True)
    quota_reset_day_utc: Mapped[str | None] = mapped_column(String(10))


class AdminReportSettings(Base):
    """Per-service toggles for admin report generation (single-row config)."""

    __tablename__ = "admin_report_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cloud_reports_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    home_ai_reports_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    debug_reports_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class UserLearningActivity(Base):
    __tablename__ = "user_learning_activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    client_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text)
    activity_type: Mapped[str] = mapped_column(String(32))
    language_code: Mapped[str] = mapped_column(String(16))
    output_language_code: Mapped[str | None] = mapped_column(String(16))
    input_text: Mapped[str | None] = mapped_column(Text)
    output_text: Mapped[str | None] = mapped_column(Text)
    tags_json: Mapped[str | None] = mapped_column(Text)
    is_saved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at_ms: Mapped[int] = mapped_column(BigInteger)
    updated_at_ms: Mapped[int] = mapped_column(BigInteger)

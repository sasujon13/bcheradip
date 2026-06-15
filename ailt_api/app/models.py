from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


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
    last_error: Mapped[str | None] = mapped_column(Text)
    last_used_at_ms: Mapped[int | None] = mapped_column(BigInteger)


class AiRoutingPolicy(Base):
    __tablename__ = "ai_routing_policy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mode: Mapped[str] = mapped_column(String(32), default="random_free")
    prefer_paid_when_free_exhausted: Mapped[bool] = mapped_column(Boolean, default=True)


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

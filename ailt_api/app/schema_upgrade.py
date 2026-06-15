"""Add missing columns on existing MySQL tables (create_all does not alter tables)."""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# (table, column, ALTER TABLE ... ADD COLUMN fragment)
_COLUMN_PATCHES: list[tuple[str, str, str]] = [
    ("users", "full_name", "full_name VARCHAR(80) NULL"),
    ("users", "email_verified", "email_verified TINYINT(1) NOT NULL DEFAULT 0"),
    ("users", "whatsapp_verified", "whatsapp_verified TINYINT(1) NOT NULL DEFAULT 0"),
    ("users", "login_with", "login_with VARCHAR(16) NULL"),
    ("users", "registered_device_id", "registered_device_id VARCHAR(128) NULL"),
    ("promo_codes", "auto_apply", "auto_apply TINYINT(1) NOT NULL DEFAULT 0"),
    ("promo_codes", "paywall_slot", "paywall_slot INT NOT NULL DEFAULT 2"),
    ("device_trials", "guest_ai_count", "guest_ai_count INT NOT NULL DEFAULT 0"),
    ("subscriptions", "buyer_user_id", "buyer_user_id INT NULL"),
    ("subscriptions", "referrer_user_id", "referrer_user_id INT NULL"),
    ("subscriptions", "gross_amount_usd", "gross_amount_usd DOUBLE NOT NULL DEFAULT 0"),
    ("subscriptions", "net_amount_usd", "net_amount_usd DOUBLE NOT NULL DEFAULT 0"),
    ("subscriptions", "play_amount_usd", "play_amount_usd DOUBLE NOT NULL DEFAULT 0"),
    ("subscriptions", "referral_balance_used_usd", "referral_balance_used_usd DOUBLE NOT NULL DEFAULT 0"),
    ("subscriptions", "referral_commission_usd", "referral_commission_usd DOUBLE NOT NULL DEFAULT 0"),
    ("subscriptions", "paid_at_ms", "paid_at_ms BIGINT NULL"),
    ("subscriptions", "slot1_code", "slot1_code VARCHAR(64) NULL"),
    ("subscriptions", "slot2_code", "slot2_code VARCHAR(64) NULL"),
    ("referral_balances", "pending_usd", "pending_usd DOUBLE NOT NULL DEFAULT 0"),
    ("referral_balances", "available_usd", "available_usd DOUBLE NOT NULL DEFAULT 0"),
]


def _table_exists(engine: Engine, table: str) -> bool:
    return inspect(engine).has_table(table)


def _column_exists(engine: Engine, table: str, column: str) -> bool:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT COUNT(*) AS n
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = :table_name
                  AND COLUMN_NAME = :column_name
                """
            ),
            {"table_name": table, "column_name": column},
        ).one()
        return int(row.n) > 0


def upgrade_schema(engine: Engine) -> None:
    """Apply idempotent ALTER TABLE patches for columns added after first deploy."""
    with engine.begin() as conn:
        for table, column, ddl in _COLUMN_PATCHES:
            if not _table_exists(engine, table):
                continue
            if _column_exists(engine, table, column):
                continue
            conn.execute(text(f"ALTER TABLE `{table}` ADD COLUMN {ddl}"))
            logger.info("Added column %s.%s", table, column)

        # Existing admins created before signup columns — treat as verified.
        if _table_exists(engine, "users") and _column_exists(engine, "users", "email_verified"):
            conn.execute(
                text(
                    """
                    UPDATE users
                    SET email_verified = 1, whatsapp_verified = 1
                    WHERE role = 'admin'
                      AND (email_verified = 0 OR whatsapp_verified = 0)
                    """
                )
            )

        if _table_exists(engine, "referral_balances") and _column_exists(engine, "referral_balances", "available_usd"):
            conn.execute(
                text(
                    """
                    UPDATE referral_balances
                    SET available_usd = balance_usd
                    WHERE available_usd = 0 AND balance_usd > 0
                    """
                )
            )

        if _table_exists(engine, "subscriptions") and _column_exists(engine, "subscriptions", "paid_at_ms"):
            conn.execute(
                text(
                    """
                    UPDATE subscriptions
                    SET paid_at_ms = UNIX_TIMESTAMP(created_at) * 1000
                    WHERE paid_at_ms IS NULL AND created_at IS NOT NULL
                    """
                )
            )

        if _table_exists(engine, "subscriptions") and _column_exists(engine, "subscriptions", "purchase_token"):
            idx_row = conn.execute(
                text(
                    """
                    SELECT COUNT(*) AS n
                    FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'subscriptions'
                      AND INDEX_NAME = 'ix_subscriptions_purchase_token'
                    """
                )
            ).one()
            if int(idx_row.n) == 0:
                conn.execute(
                    text("CREATE INDEX ix_subscriptions_purchase_token ON subscriptions (purchase_token(191))")
                )
                logger.info("Added index subscriptions.purchase_token")

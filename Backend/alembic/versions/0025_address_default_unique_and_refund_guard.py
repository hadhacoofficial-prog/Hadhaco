"""Two data-integrity fixes (schema audit M10, M8):

1. user_addresses: the existing idx_user_addresses_is_default index is a
   plain (non-unique) index, so a race between two concurrent "set as
   default" requests can leave two default addresses for the same
   (user_id, type). Before making it unique we deduplicate any existing
   violations, keeping the most-recently-updated default per
   (user_id, type) and clearing the rest.

2. refunds: no cross-row invariant prevented SUM(refunds.amount) from
   exceeding payments.amount for a given payment (a double-refund race
   had zero DB-level backstop). Adds a trigger that raises on any
   INSERT/UPDATE that would push the total past the payment amount.

Revision ID: 0025_address_default_unique_and_refund_guard
Revises: 0024_coupon_usages_order_fk
Create Date: 2026-07-03
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0025_address_default_unique_and_refund_guard"
down_revision: str | None = "0024_coupon_usages_order_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. Deduplicate then enforce one default address per (user, type) ──
    op.execute("""
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY user_id, type
                       ORDER BY updated_at DESC, created_at DESC
                   ) AS rn
            FROM user_addresses
            WHERE is_default = true AND deleted_at IS NULL
        )
        UPDATE user_addresses
        SET is_default = false
        WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
    """)

    op.execute("DROP INDEX IF EXISTS idx_user_addresses_is_default")
    op.create_index(
        "idx_user_addresses_is_default",
        "user_addresses",
        ["user_id", "type"],
        unique=True,
        postgresql_where="is_default = true AND deleted_at IS NULL",
    )

    # ── 2. Refund-overpayment guard ─────────────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION check_refund_total()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        DECLARE
            payment_amount NUMERIC(12, 2);
            other_refunds  NUMERIC(12, 2);
        BEGIN
            SELECT amount INTO payment_amount
            FROM payments WHERE id = NEW.payment_id;

            SELECT COALESCE(SUM(amount), 0) INTO other_refunds
            FROM refunds
            WHERE payment_id = NEW.payment_id
              AND id != NEW.id;

            IF other_refunds + NEW.amount > payment_amount THEN
                RAISE EXCEPTION
                    'refund total (%) would exceed payment amount (%) for payment %',
                    other_refunds + NEW.amount, payment_amount, NEW.payment_id;
            END IF;

            RETURN NEW;
        END;
        $$;
    """)
    op.execute("DROP TRIGGER IF EXISTS trg_check_refund_total ON refunds")
    op.execute("""
        CREATE TRIGGER trg_check_refund_total
            BEFORE INSERT OR UPDATE ON refunds
            FOR EACH ROW EXECUTE FUNCTION check_refund_total()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_check_refund_total ON refunds")
    op.execute("DROP FUNCTION IF EXISTS check_refund_total()")

    op.execute("DROP INDEX IF EXISTS idx_user_addresses_is_default")
    op.create_index(
        "idx_user_addresses_is_default",
        "user_addresses",
        ["user_id", "is_default"],
        postgresql_where="is_default = true",
    )

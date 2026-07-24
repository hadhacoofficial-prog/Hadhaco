"""Partial unique index: at most one pending order per user.

Adds a safety-net database constraint that prevents duplicate pending orders
even when application-level guards are bypassed by race conditions.  The index
covers orders in 'stock_reserved' or 'payment_pending' status — the two
transient states that a checkout order occupies between creation and
payment completion/expiry.

Revision ID: 0055_one_pending_order_per_user_guard
Revises: 0054_performance_indexes_phase6
Create Date: 2026-07-24
"""

from alembic import op

revision: str = "0055_one_pending_order_per_user_guard"
down_revision: str | None = "0054_performance_indexes_phase6"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("""
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY user_id
                       ORDER BY
                           CASE WHEN razorpay_order_id IS NOT NULL THEN 0 ELSE 1 END,
                           id DESC
                   ) AS rn
            FROM orders
            WHERE status IN ('stock_reserved', 'payment_pending')
        )
        UPDATE orders
        SET status = 'payment_failed',
            payment_status = 'failed',
            updated_at = NOW()
        WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
        """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS
        idx_one_pending_order_per_user
        ON orders (user_id)
        WHERE status IN ('stock_reserved', 'payment_pending')
        """)


def downgrade() -> None:
    op.drop_index("idx_one_pending_order_per_user", if_exists=True)

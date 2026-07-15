"""Financial integrity constraints for payments, refunds, and webhooks.

1. UNIQUE(refunds.razorpay_refund_id) — prevents duplicate refund rows from
   the admin-initiate_refund / refund.created webhook race.  The column is
   nullable (rows start as 'pending' before Razorpay assigns an id), and
   Postgres unique indexes allow unlimited NULLs, so this only rejects a
   genuine duplicate once a real razorpay_refund_id is set.

2. CHECK(payments.status) — restricts to the finite set of valid states:
   created, captured, failed, refunded, partially_refunded.

3. CHECK(refunds.status) — restricts to: pending, processed, failed.

4. CHECK(refunds.amount >= 0) is already enforced by migration 0021; this
   migration adds a complementary CHECK on payments.currency to prevent
   blank/null currency values on captured payments.

Revision ID: 0050_financial_integrity_constraints
Revises: 0049_admin_session_activity_tracking
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0050_financial_integrity_constraints"
down_revision: str | None = "0049_admin_session_activity_tracking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. UNIQUE on refunds.razorpay_refund_id (nullable-safe: multiple NULLs allowed)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS "
        "idx_refunds_razorpay_refund_id_unique "
        "ON refunds (razorpay_refund_id) "
        "WHERE razorpay_refund_id IS NOT NULL"
    )

    # 2. CHECK: payments.status must be a known value
    op.execute(
        "ALTER TABLE payments ADD CONSTRAINT payments_status_check "
        "CHECK (status IN ('created','captured','failed','refunded','partially_refunded')) "
        "NOT VALID"
    )
    op.execute("ALTER TABLE payments VALIDATE CONSTRAINT payments_status_check")

    # 3. CHECK: refunds.status must be a known value
    op.execute(
        "ALTER TABLE refunds ADD CONSTRAINT refunds_status_check "
        "CHECK (status IN ('pending','processed','failed')) "
        "NOT VALID"
    )
    op.execute("ALTER TABLE refunds VALIDATE CONSTRAINT refunds_status_check")

    # 4. CHECK: payments.currency must not be empty (defensive)
    op.execute(
        "ALTER TABLE payments ADD CONSTRAINT payments_currency_check "
        "CHECK (currency IS NOT NULL AND length(currency) > 0) "
        "NOT VALID"
    )
    op.execute("ALTER TABLE payments VALIDATE CONSTRAINT payments_currency_check")


def downgrade() -> None:
    op.execute("ALTER TABLE payments DROP CONSTRAINT IF EXISTS payments_currency_check")
    op.execute("ALTER TABLE refunds DROP CONSTRAINT IF EXISTS refunds_status_check")
    op.execute("ALTER TABLE payments DROP CONSTRAINT IF EXISTS payments_status_check")
    op.execute("DROP INDEX IF EXISTS idx_refunds_razorpay_refund_id_unique")

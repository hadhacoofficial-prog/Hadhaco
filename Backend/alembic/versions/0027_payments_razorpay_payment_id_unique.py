"""Add a unique index on payments.razorpay_payment_id (schema audit T6).

Closes the double-submit/webhook race: verify_and_fulfill's payment insert
had no idempotency guard, so a frontend retry racing the Razorpay webhook
could insert two payment rows for one captured payment. The column is
nullable (rows start as 'created' before capture), and Postgres unique
indexes allow unlimited NULLs, so this only rejects a genuine duplicate
once a real razorpay_payment_id is set — never blocks distinct legitimate
retries (each has its own razorpay_payment_id).

Revision ID: 0027_payments_razorpay_payment_id_unique
Revises: 0026_sequence_counters
Create Date: 2026-07-03
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0027_payments_razorpay_payment_id_unique"
down_revision: str | None = "0026_sequence_counters"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_payments_razorpay_payment_id")
    op.create_index(
        "idx_payments_razorpay_payment_id_unique",
        "payments",
        ["razorpay_payment_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("idx_payments_razorpay_payment_id_unique", table_name="payments")
    op.create_index(
        "idx_payments_razorpay_payment_id", "payments", ["razorpay_payment_id"]
    )

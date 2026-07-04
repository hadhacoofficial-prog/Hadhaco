"""Expand webhook_events for full audit/debug traceability, and add
Refund.failure_reason (parity with Payment.failure_reason) to support the
refund.failed webhook path.

webhook_events already exists (provider, event_type, event_id, payload,
status, error_message, processed_at, created_at) with a unique constraint
on (provider, event_id) for idempotency. This adds:
  - razorpay_payment_id / razorpay_order_id: external Razorpay ids, captured
    directly from the payload even before we've resolved a local Payment row.
  - order_id: resolved internal order reference, once known.
  - headers: relevant request headers (signature, content-type, timestamp)
    for debugging delivery issues.
  - processing_attempts: incremented on every processing attempt, so
    repeated Razorpay retries of a failing event are visible.

Revision ID: 0029_webhook_events_expansion
Revises: 0028_trigram_search_indexes
Create Date: 2026-07-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "0029_webhook_events_expansion"
down_revision: str | None = "0028_trigram_search_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "webhook_events",
        sa.Column("razorpay_payment_id", sa.String(100), nullable=True),
    )
    op.add_column(
        "webhook_events",
        sa.Column("razorpay_order_id", sa.String(100), nullable=True),
    )
    op.add_column(
        "webhook_events",
        sa.Column(
            "order_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "webhook_events",
        sa.Column("headers", JSONB(), nullable=True),
    )
    op.add_column(
        "webhook_events",
        sa.Column(
            "processing_attempts", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.create_index("idx_webhook_events_order_id", "webhook_events", ["order_id"])
    op.create_index(
        "idx_webhook_events_razorpay_payment_id",
        "webhook_events",
        ["razorpay_payment_id"],
    )

    op.add_column(
        "refunds",
        sa.Column("failure_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("refunds", "failure_reason")

    op.drop_index("idx_webhook_events_razorpay_payment_id", table_name="webhook_events")
    op.drop_index("idx_webhook_events_order_id", table_name="webhook_events")
    op.drop_column("webhook_events", "processing_attempts")
    op.drop_column("webhook_events", "headers")
    op.drop_column("webhook_events", "order_id")
    op.drop_column("webhook_events", "razorpay_order_id")
    op.drop_column("webhook_events", "razorpay_payment_id")

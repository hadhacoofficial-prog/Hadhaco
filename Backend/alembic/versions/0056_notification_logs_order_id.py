"""Add order_id to notification_logs for email idempotency.

Links notification logs to specific orders so the application can check
whether an order-related email (order_created, payment_captured) has
already been sent before dispatching a duplicate.  Prevents double
emails when Razorpay webhooks and frontend verification race.

Revision ID: 0056_notification_logs_order_id
Revises: 0055_one_pending_order_per_user_guard
Create Date: 2026-07-24
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0056_notification_logs_order_id"
down_revision: str | None = "0055_one_pending_order_per_user_guard"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "notification_logs",
        sa.Column("order_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "idx_notification_logs_order_event",
        "notification_logs",
        ["order_id", "event_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_notification_logs_order_event", if_exists=True)
    op.drop_column("notification_logs", "order_id")

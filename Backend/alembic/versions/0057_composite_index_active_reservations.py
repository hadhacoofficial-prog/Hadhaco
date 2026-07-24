"""Composite indexes for notification retry worker and active-reservations.

1. idx_inv_res_user_status_expires — covers the storefront
   GET /orders/active-reservations query (user_id + status + expires_at).

2. idx_notification_logs_retry_pending — covers the notification retry
   worker's polling query (status + next_retry_at).

Revision ID: 0057_composite_index_active_reservations
Revises: 0056_notification_logs_order_id
Create Date: 2026-07-24
"""

from alembic import op

revision: str = "0057_composite_index_active_reservations"
down_revision: str | None = "0056_notification_logs_order_id"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Covers: WHERE user_id = :uid AND status = 'ACTIVE' AND expires_at > now()
    op.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_inv_res_user_status_expires
        ON inventory_reservations (user_id, status, expires_at)
        WHERE status = 'ACTIVE'
    """)
    # Covers: WHERE status = 'retrying' AND next_retry_at <= now()
    # (notification retry worker polling query)
    op.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_notification_logs_retry_pending
        ON notification_logs (status, next_retry_at)
        WHERE status = 'retrying'
    """)


def downgrade() -> None:
    op.drop_index("idx_notification_logs_retry_pending", if_exists=True)
    op.drop_index("idx_inv_res_user_status_expires", if_exists=True)

"""Add stock_reserved to orders_status_check constraint.

The reservation system creates orders with status='stock_reserved' before
payment intent is opened. The original constraint only allowed the legacy
set of statuses, causing CheckViolationError on order creation.

Revision ID: 0006_order_status_fix
Revises: 0005_reservation_system
Create Date: 2026-06-23
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006_order_status_fix"
down_revision: str | None = "0005_reservation_system"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ALLOWED_STATUSES = (
    "pending",
    "stock_reserved",
    "confirmed",
    "processing",
    "shipped",
    "delivered",
    "cancelled",
    "refunded",
)


def upgrade() -> None:
    op.execute("ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_status_check")
    values = ", ".join(f"'{s}'" for s in _ALLOWED_STATUSES)
    op.execute(
        f"ALTER TABLE orders ADD CONSTRAINT orders_status_check "
        f"CHECK (status IN ({values}))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_status_check")
    legacy = "'pending','confirmed','processing','shipped','delivered','cancelled','refunded'"
    op.execute(
        f"ALTER TABLE orders ADD CONSTRAINT orders_status_check "
        f"CHECK (status IN ({legacy}))"
    )

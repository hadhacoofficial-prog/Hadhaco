"""Expand orders_status_check to cover all statuses used by the reservation system.

The original constraint only had 7 legacy statuses.  Migration 0006 added
stock_reserved.  The service also uses payment_pending, payment_expired,
payment_failed, packed, return_requested, and returned — all defined in
UpdateOrderStatusRequest and/or set directly by service code.

Revision ID: 0007_order_status_full
Revises: 0006_order_status_fix
Create Date: 2026-06-23
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007_order_status_full"
down_revision: str | None = "0006_order_status_fix"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ALLOWED_STATUSES = (
    "pending",
    "stock_reserved",
    "payment_pending",
    "confirmed",
    "processing",
    "packed",
    "shipped",
    "delivered",
    "cancelled",
    "payment_failed",
    "payment_expired",
    "return_requested",
    "returned",
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
    v006 = (
        "pending",
        "stock_reserved",
        "confirmed",
        "processing",
        "shipped",
        "delivered",
        "cancelled",
        "refunded",
    )
    values = ", ".join(f"'{s}'" for s in v006)
    op.execute(
        f"ALTER TABLE orders ADD CONSTRAINT orders_status_check "
        f"CHECK (status IN ({values}))"
    )

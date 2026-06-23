"""Add max_order_quantity to products table.

Revision ID: 0009_add_max_order_quantity
Revises: 0008_add_tracking_url_to_shipments
Create Date: 2026-06-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_add_max_order_quantity"
down_revision: str | None = "0008_add_tracking_url_to_shipments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "max_order_quantity",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("products", "max_order_quantity")

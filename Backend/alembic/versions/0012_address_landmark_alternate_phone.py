"""Add landmark and alternate_phone to addresses and order snapshots.

Revision ID: 0012_address_landmark_alternate_phone
Revises: 0011_order_item_image_url
Create Date: 2026-06-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_address_landmark_alternate_phone"
down_revision: str | None = "0011_order_item_image_url"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Saved address table
    op.add_column(
        "user_addresses", sa.Column("landmark", sa.String(255), nullable=True)
    )
    op.add_column(
        "user_addresses", sa.Column("alternate_phone", sa.String(20), nullable=True)
    )

    # Order address snapshot — shipping side
    op.add_column(
        "orders", sa.Column("shipping_landmark", sa.String(255), nullable=True)
    )
    op.add_column(
        "orders", sa.Column("shipping_alternate_phone", sa.String(20), nullable=True)
    )

    # Order address snapshot — billing side
    op.add_column(
        "orders", sa.Column("billing_landmark", sa.String(255), nullable=True)
    )
    op.add_column(
        "orders", sa.Column("billing_alternate_phone", sa.String(20), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("orders", "billing_alternate_phone")
    op.drop_column("orders", "billing_landmark")
    op.drop_column("orders", "shipping_alternate_phone")
    op.drop_column("orders", "shipping_landmark")
    op.drop_column("user_addresses", "alternate_phone")
    op.drop_column("user_addresses", "landmark")

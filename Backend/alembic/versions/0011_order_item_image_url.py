"""Add image_url snapshot to order_items.

Revision ID: 0011_order_item_image_url
Revises: 0010_fulfillment_workflow
Create Date: 2026-06-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_order_item_image_url"
down_revision: str | None = "0010_fulfillment_workflow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "order_items",
        sa.Column("image_url", sa.String(1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("order_items", "image_url")

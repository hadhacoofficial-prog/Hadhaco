"""Add tracking_url to shipments table.

Revision ID: 0008_add_tracking_url_to_shipments
Revises: 0007_order_status_full
Create Date: 2026-06-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_add_tracking_url_to_shipments"
down_revision: str | None = "0007_order_status_full"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Widen alembic_version.version_num so long revision IDs fit (default is VARCHAR(32))
    op.execute(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)"
    )
    op.add_column(
        "shipments",
        sa.Column("tracking_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("shipments", "tracking_url")

"""Add crop metadata columns to product_images.

Admin can crop each product image individually via react-easy-crop. The crop
box is stored in pixel coordinates of the untouched original image so the
editor can be reopened later and restored exactly. All columns are nullable
and additive only — existing rows keep crop_x IS NULL, meaning "use the
already-generated thumbnail/medium/large as-is" (see MediaService, which only
regenerates variants when a crop is explicitly saved).

Revision ID: 0031_product_image_crop_metadata
Revises: 0030_webhook_email_templates
Create Date: 2026-07-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0031_product_image_crop_metadata"
down_revision: str | None = "0030_webhook_email_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "product_images", sa.Column("crop_x", sa.Numeric(10, 2), nullable=True)
    )
    op.add_column(
        "product_images", sa.Column("crop_y", sa.Numeric(10, 2), nullable=True)
    )
    op.add_column(
        "product_images", sa.Column("crop_width", sa.Numeric(10, 2), nullable=True)
    )
    op.add_column(
        "product_images", sa.Column("crop_height", sa.Numeric(10, 2), nullable=True)
    )
    op.add_column(
        "product_images", sa.Column("crop_zoom", sa.Numeric(5, 2), nullable=True)
    )
    op.add_column(
        "product_images", sa.Column("crop_rotation", sa.Numeric(6, 2), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("product_images", "crop_rotation")
    op.drop_column("product_images", "crop_zoom")
    op.drop_column("product_images", "crop_height")
    op.drop_column("product_images", "crop_width")
    op.drop_column("product_images", "crop_y")
    op.drop_column("product_images", "crop_x")

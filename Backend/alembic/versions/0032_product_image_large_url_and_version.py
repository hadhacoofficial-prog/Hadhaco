"""Add large_url and updated_at to product_images.

`large_url` was already being generated and uploaded to R2 by
MediaService (the "large" 1200x1200 WebP variant) but was never
persisted on the row or returned by the API, so the product detail
gallery zoom had nothing to reference and silently fell back to the
untouched original image.

`updated_at` is a plain per-row timestamp (server_default + onupdate)
used purely to cache-bust the thumbnail/medium/large URLs: since crop
and replace overwrite the same R2 object key in place, the URL string
never changes even though the bytes do, so browsers/CDNs will happily
keep serving stale cached bytes for that URL forever. Appending
`?v=<updated_at>` when serializing the response forces a fresh fetch
whenever the underlying image actually changes, with zero impact on
the R2 storage layout itself.

Revision ID: 0032_product_image_large_url_and_version
Revises: 0031_product_image_crop_metadata
Create Date: 2026-07-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0032_product_image_large_url_and_version"
down_revision: str | None = "0031_product_image_crop_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "product_images", sa.Column("large_url", sa.String(1024), nullable=True)
    )
    op.add_column(
        "product_images",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_column("product_images", "updated_at")
    op.drop_column("product_images", "large_url")

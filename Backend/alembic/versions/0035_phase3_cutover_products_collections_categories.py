"""Phase 3 cutover (scoped): products, collections, categories, avatars, reviews.

Drops the legacy per-module image storage now that every row has been
backfilled into images/image_variants (see the standalone backfill script
run against this database prior to this migration — not part of the
migration itself, since it needs PIL/boto3/HTTP calls Alembic isn't set up
to run). This is the scoped half of the architecture doc's Phase 3
("Cutover") — CMS/hero/banner images are deliberately NOT touched here;
that migration entangles with landing_sections.config JSONB in ways that
need dedicated attention, tracked separately.

What this migration does:
- Adds `primary_image_id` FK columns to collections/categories/profiles,
  backfilled from the already-populated `images` table (owner_type/owner_id
  match, is_primary=true).
- Drops `product_images` and `review_images` tables entirely (fully
  replaced by images/image_variants with owner_type='product'/'review').
- Drops `collections.image_url`, `categories.image_url`,
  `profiles.avatar_url` — replaced by `primary_image_id`.

No backward-compatibility shim, no soft-retirement — per the architecture
doc's explicit "no dual-running" replacement philosophy. A pre-migration
snapshot was taken (see Docs/audits and the session record) before running
this.

Revision ID: 0035_phase3_cutover_products_collections_categories
Revises: 0034_universal_images_schema
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "0035_phase3_cutover_products_collections_categories"
down_revision: str | None = "0034_universal_images_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column("primary_image_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_collections_primary_image_id",
        "collections",
        "images",
        ["primary_image_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "categories",
        sa.Column("primary_image_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_categories_primary_image_id",
        "categories",
        "images",
        ["primary_image_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "profiles",
        sa.Column("primary_image_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_profiles_primary_image_id",
        "profiles",
        "images",
        ["primary_image_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute("""
        UPDATE collections c
        SET primary_image_id = i.id
        FROM images i
        WHERE i.owner_type = 'collection'
          AND i.owner_id = c.id
          AND i.is_primary = true
          AND i.deleted_at IS NULL
        """)
    op.execute("""
        UPDATE categories c
        SET primary_image_id = i.id
        FROM images i
        WHERE i.owner_type = 'category'
          AND i.owner_id = c.id
          AND i.is_primary = true
          AND i.deleted_at IS NULL
        """)
    op.execute("""
        UPDATE profiles p
        SET primary_image_id = i.id
        FROM images i
        WHERE i.owner_type = 'user'
          AND i.owner_id = p.id
          AND i.is_primary = true
          AND i.deleted_at IS NULL
        """)

    op.drop_table("product_images")
    op.drop_table("review_images")
    op.drop_column("collections", "image_url")
    op.drop_column("categories", "image_url")
    op.drop_column("profiles", "avatar_url")


def downgrade() -> None:
    """
    Structural downgrade only — recreates the dropped tables/columns empty.
    Does NOT restore data (the whole point of Phase 3 is that the old
    tables/columns are gone; use the pre-migration DB snapshot to restore
    data if this migration needs to be rolled back for real).
    """
    op.add_column("profiles", sa.Column("avatar_url", sa.Text(), nullable=True))
    op.add_column("categories", sa.Column("image_url", sa.Text(), nullable=True))
    op.add_column("collections", sa.Column("image_url", sa.Text(), nullable=True))

    op.create_table(
        "review_images",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "review_id",
            UUID(as_uuid=True),
            sa.ForeignKey("reviews.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("r2_key", sa.String(512), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "product_images",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "product_id",
            UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.String(1024), nullable=False),
        sa.Column("thumbnail_url", sa.String(1024), nullable=True),
        sa.Column("medium_url", sa.String(1024), nullable=True),
        sa.Column("large_url", sa.String(1024), nullable=True),
        sa.Column("alt_text", sa.String(255), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("crop_x", sa.Numeric(10, 2), nullable=True),
        sa.Column("crop_y", sa.Numeric(10, 2), nullable=True),
        sa.Column("crop_width", sa.Numeric(10, 2), nullable=True),
        sa.Column("crop_height", sa.Numeric(10, 2), nullable=True),
        sa.Column("crop_zoom", sa.Numeric(5, 2), nullable=True),
        sa.Column("crop_rotation", sa.Numeric(6, 2), nullable=True),
    )

    op.drop_constraint("fk_profiles_primary_image_id", "profiles", type_="foreignkey")
    op.drop_column("profiles", "primary_image_id")
    op.drop_constraint(
        "fk_categories_primary_image_id", "categories", type_="foreignkey"
    )
    op.drop_column("categories", "primary_image_id")
    op.drop_constraint(
        "fk_collections_primary_image_id", "collections", type_="foreignkey"
    )
    op.drop_column("collections", "primary_image_id")

"""Create images and image_variants tables (Universal Image System, Phase 0).

Foundation migration for the Universal Responsive Image Management System
(see docs/architecture/Universal_Responsive_Image_System_Design.md). This is
additive-only: `product_images`, `cms_media`, and every legacy image column
are left untouched here. They are dropped in the single Phase 3 cutover
migration once the new pipeline is fully built and proven (§17 of the
design doc) — there is deliberately no dual-running/compat period, so this
migration does not touch any existing table.

`images` is the canonical asset row (one per uploaded original + its full
crop/variant lineage); `image_variants` is one row per generated derived
file (thumbnail/medium/large/hero-desktop@2x/...). Both are polymorphic via
`owner_type`/`owner_id` so every module (product, collection, category,
hero, banner, cms_section_item, user, review, company_config, seo_page)
shares the same two tables instead of each having its own.

Revision ID: 0034_universal_images_schema
Revises: 0033_backfill_sequence_counters
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "0034_universal_images_schema"
down_revision: str | None = "0033_backfill_sequence_counters"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "images",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("module", sa.String(40), nullable=False),
        sa.Column("preset_id", sa.String(60), nullable=False),
        sa.Column("owner_type", sa.String(40), nullable=False),
        sa.Column("owner_id", UUID(as_uuid=True), nullable=True),
        sa.Column("original_key", sa.Text(), nullable=False),
        sa.Column("original_ext", sa.String(10), nullable=False),
        sa.Column("original_width", sa.Integer(), nullable=False),
        sa.Column("original_height", sa.Integer(), nullable=False),
        sa.Column("original_size_bytes", sa.Integer(), nullable=False),
        sa.Column("mime_type", sa.String(80), nullable=False),
        sa.Column("alt_text", sa.Text(), nullable=True),
        sa.Column(
            "metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="ready"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "uploaded_by",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
            onupdate=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_images_owner",
        "images",
        ["owner_type", "owner_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_images_owner_sort",
        "images",
        ["owner_type", "owner_id", "sort_order"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_images_status",
        "images",
        ["status"],
        postgresql_where=sa.text("status <> 'ready'"),
    )

    op.create_table(
        "image_variants",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "image_id",
            UUID(as_uuid=True),
            sa.ForeignKey("images.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("breakpoint", sa.String(20), nullable=False),
        sa.Column("variant_name", sa.String(40), nullable=False),
        sa.Column("dpr", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("format", sa.String(10), nullable=False, server_default="webp"),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ready"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "image_id",
            "breakpoint",
            "variant_name",
            "dpr",
            name="uq_image_variants_image_breakpoint_variant_dpr",
        ),
    )
    op.create_index("ix_image_variants_image", "image_variants", ["image_id"])


def downgrade() -> None:
    op.drop_index("ix_image_variants_image", table_name="image_variants")
    op.drop_table("image_variants")
    op.drop_index("ix_images_status", table_name="images")
    op.drop_index("ix_images_owner_sort", table_name="images")
    op.drop_index("ix_images_owner", table_name="images")
    op.drop_table("images")

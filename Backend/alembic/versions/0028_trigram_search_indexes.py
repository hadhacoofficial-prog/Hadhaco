"""Add trigram (gin_trgm_ops) indexes for ILIKE '%term%' search paths that
can't use search_vector (schema audit F5): products.sku (excluded from the
tsvector — see update_product_search_vector()), products.name (used by
search::autocomplete and the full_text_search ILIKE fallback), and the
admin name/slug search columns on categories and collections. pg_trgm is
already enabled (supabase/sql/000_extensions.sql).

Indexes are created CONCURRENTLY on products (the hottest table) to avoid
a write-blocking lock; categories/collections are low-traffic enough for a
plain CREATE INDEX.

Revision ID: 0028_trigram_search_indexes
Revises: 0027_payments_razorpay_payment_id_unique
Create Date: 2026-07-03
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0028_trigram_search_indexes"
down_revision: str | None = "0027_payments_razorpay_payment_id_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_products_name_trgm "
            "ON products USING GIN (name gin_trgm_ops)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_products_sku_trgm "
            "ON products USING GIN (sku gin_trgm_ops)"
        )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_categories_name_trgm "
        "ON categories USING GIN (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_categories_slug_trgm "
        "ON categories USING GIN (slug gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_collections_name_trgm "
        "ON collections USING GIN (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_collections_slug_trgm "
        "ON collections USING GIN (slug gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_collections_slug_trgm")
    op.execute("DROP INDEX IF EXISTS idx_collections_name_trgm")
    op.execute("DROP INDEX IF EXISTS idx_categories_slug_trgm")
    op.execute("DROP INDEX IF EXISTS idx_categories_name_trgm")

    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_products_sku_trgm")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_products_name_trgm")

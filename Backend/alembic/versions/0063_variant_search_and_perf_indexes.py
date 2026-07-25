"""Variant search + perf indexes for the new admin inventory page.

Adds:
  - Trigram GIN indexes on product_variants.sku / .name, mirroring the
    existing idx_products_name_trgm / idx_products_sku_trgm, so the new
    variant-level admin search (GET /admin/product-variants) can ILIKE-match
    variant SKU/name without a sequential scan.
  - A plain btree index on product_variants.updated_at, for the "Last
    Updated" sort and "Recently Updated" filter on that same endpoint.
  - A plain btree index on order_items.variant_id (previously unindexed
    despite the column existing), for the admin inventory page's per-variant
    "recent orders" drill-down.

Note: 0059_runtime_validated_index_cleanup dropped idx_product_variants_sku
(confirmed 0 scans at the time) — this migration does not recreate it; the
new trigram index covers both exact and fuzzy sku lookups going forward, and
the sku UNIQUE constraint already provides an implicit btree for equality.

Revision ID: 0063_variant_search_and_perf_indexes
Revises: 0062_variant_aware_low_stock_view
Create Date: 2026-07-25
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0063_variant_search_and_perf_indexes"
down_revision: str | None = "0062_variant_aware_low_stock_view"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "idx_product_variants_sku_trgm "
            "ON product_variants USING gin (sku gin_trgm_ops)"
        )
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "idx_product_variants_name_trgm "
            "ON product_variants USING gin (name gin_trgm_ops)"
        )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_product_variants_updated_at "
        "ON product_variants (updated_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_order_items_variant_id "
        "ON order_items (variant_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_order_items_variant_id")
    op.execute("DROP INDEX IF EXISTS idx_product_variants_updated_at")
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_product_variants_name_trgm")
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_product_variants_sku_trgm")

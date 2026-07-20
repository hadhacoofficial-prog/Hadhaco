"""Phase 6 — Additional performance indexes for remaining hot query paths.

Targets:
  1. Product list sort by created_at (covering index eliminates sort step)
  2. Product list sort by base_price (covering index eliminates sort step)
  3. Search history trending aggregation (covers the 7-day window query)
  4. Product collection reverse lookup (used by collection detail pages)

These are safe, additive-only changes.  No existing indexes are modified or
removed.

Revision ID: 0054_performance_indexes_phase6
Revises: 0053_final_audit_cta_and_status_templates
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0054_performance_indexes_phase6"
down_revision: str | None = "0053_final_audit_cta_and_status_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Products: covering indexes for list sort ──────────────────────────────
    # The existing idx_products_status_deleted covers WHERE but not ORDER BY.
    # A covering index that includes the sort column lets PG do an
    # index-only scan (no separate Sort step in EXPLAIN).
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "idx_products_active_created_covering "
            "ON products (deleted_at, status, created_at DESC) "
            "WHERE deleted_at IS NULL AND status = 'active'"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "idx_products_active_price_covering "
            "ON products (deleted_at, status, base_price) "
            "WHERE deleted_at IS NULL AND status = 'active'"
        )

    # ── Search history: trending aggregation ───────────────────────────────────
    # The trending query does:
    #   WHERE created_at >= NOW() - INTERVAL '7 days'
    #   GROUP BY query ORDER BY search_count DESC LIMIT :limit
    # A composite index on (created_at, query) lets PG scan only recent rows.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_search_history_created_query "
        "ON search_history (created_at, query)"
    )

    # ── Product collections: reverse lookup for collection detail pages ────────
    # The existing idx_product_collections_col covers (collection_id).
    # This reverse index covers (product_id) for get_collections_for_product.
    # Note: the PK already covers product_id lookups, but this explicit index
    # is slightly more efficient (no sort_order column in the index).
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_product_collections_product "
        "ON product_collections (product_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_product_collections_product")
    op.execute("DROP INDEX IF EXISTS idx_search_history_created_query")
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_products_active_price_covering"
        )
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_products_active_created_covering"
        )

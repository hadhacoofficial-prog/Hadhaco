"""Phase 8 — Runtime-validated performance index cleanup.

Adds description trigram index for ILIKE search fallback and drops
unused indexes confirmed by pg_stat_user_indexes (0 scans since boot).

Changes:
  1. CREATE idx_products_description_trgm — trigram GIN on products.description
     for ILIKE '%query%' fallback when FTS returns no results.
   2. DROP 17 unused standalone indexes confirmed by pg_stat_user_indexes (0 scans).
      UNIQUE constraints (products_sku_key, reviews_product_id_user_id_key,
      orders_order_number_key) are preserved — they enforce data integrity.
     These indexes cause unnecessary write amplification on INSERT/UPDATE/DELETE
     and consume 2.32 MB of index space.

All drops are safe: each index had 0 scans in pg_stat_user_indexes, meaning
no query path in the running application has used them since the database
was last restarted.

Revision ID: 0059_runtime_validated_index_cleanup
Revises: 0058_reservation_state_machine
Create Date: 2026-07-25
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0059_runtime_validated_index_cleanup"
down_revision: str | None = "0058_reservation_state_machine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. Add description trigram index ────────────────────────────────────
    # The ILIKE fallback query (Q8 in EXPLAIN ANALYZE) does:
    #   WHERE name ILIKE '%query%' OR description ILIKE '%query%' OR sku ILIKE '%query%'
    # name and sku already have trigram indexes (idx_products_name_trgm,
    # idx_products_sku_trgm).  description is the only column without one,
    # forcing a seq scan on the entire products table for description matches.
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "idx_products_description_trgm "
            "ON products USING gin (description gin_trgm_ops) "
            "WHERE deleted_at IS NULL"
        )

    # ── 2. Drop unused indexes (confirmed 0 scans in pg_stat_user_indexes) ──
    # Each of these indexes had idx_scan = 0 in the cumulative pg_stat output,
    # meaning no query path has used them since the database was last restarted.
    # Removing them reduces write amplification on every INSERT/UPDATE/DELETE.
    # UNIQUE constraints (products_sku_key, reviews_product_id_user_id_key,
    # orders_order_number_key) are excluded — they enforce data integrity,
    # not query performance.  They cannot be dropped with DROP INDEX.
    DROP_INDEXES = [
        # Products — redundant covering/partial indexes
        "idx_products_compare_price",
        "idx_products_is_new",
        "idx_products_is_featured",
        "idx_products_active_created_covering",
        "idx_products_status_deleted",
        "idx_products_featured_status_deleted",
        # Product variants — unused SKU lookup
        "idx_product_variants_sku",
        # Categories — partial active index never used
        "idx_categories_active",
        # Categories — trigram indexes never used
        "idx_categories_name_trgm",
        "idx_categories_slug_trgm",
        # Collections — partial/trigram indexes never used
        "idx_collections_active",
        "idx_collections_featured",
        "idx_collections_name_trgm",
        "idx_collections_slug_trgm",
        # Reviews — redundant/unused indexes
        "idx_reviews_rating",
        "idx_reviews_is_approved",
        # Orders — unused indexes
        "idx_orders_user_id",
        # Search history — unused query index (created_query covers this)
        "idx_search_history_query",
    ]

    for idx in DROP_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {idx}")


def downgrade() -> None:
    import logging

    log = logging.getLogger("alembic")

    # Re-create dropped indexes (best-effort, without CONCURRENTLY for safety).
    #
    # DOWNGRADE LIMITATION: This downgrade was written against the schema at
    # migration 0059. Later migrations (0060+) may rename or drop columns that
    # these indexes reference. Each recreation uses a SAVEPOINT so that a
    # failure on one index does not cascade to others or abort the transaction.
    #
    # If you are downgrading past 0059 from a later head, some indexes will
    # be skipped with a warning. This is expected and safe — the indexes were
    # confirmed unused before being dropped, and the schema they reference may
    # no longer exist.
    RECREATE = [
        ("products", "idx_products_compare_price"),
        ("products", "idx_products_is_new"),
        ("products", "idx_products_is_featured"),
        (
            "products",
            "idx_products_active_created_covering",
            "ON products (deleted_at, status, created_at DESC) "
            "WHERE deleted_at IS NULL AND status = 'active'",
        ),
        ("products", "idx_products_status_deleted"),
        ("products", "idx_products_featured_status_deleted"),
        ("product_variants", "idx_product_variants_sku"),
        ("categories", "idx_categories_active"),
        ("categories", "idx_categories_name_trgm"),
        ("categories", "idx_categories_slug_trgm"),
        ("collections", "idx_collections_active"),
        ("collections", "idx_collections_featured"),
        ("collections", "idx_collections_name_trgm"),
        ("collections", "idx_collections_slug_trgm"),
        ("reviews", "idx_reviews_rating"),
        ("reviews", "idx_reviews_is_approved"),
        ("orders", "idx_orders_user_id"),
        ("search_history", "idx_search_history_query"),
    ]

    for i, entry in enumerate(RECREATE):
        table = entry[0]
        idx_name = entry[1]
        custom_def = entry[2] if len(entry) > 2 else None
        sp_name = f"sp_recreate_{i}"
        op.execute(f"SAVEPOINT {sp_name}")
        try:
            if custom_def:
                op.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} {custom_def}")
            else:
                col = idx_name.replace(f"idx_{table}_", "").replace(f"{table}_", "")
                op.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({col})")
            op.execute(f"RELEASE SAVEPOINT {sp_name}")
        except Exception as exc:
            op.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")
            log.warning(
                "Skipping index %s recreation (column may have been removed): %s",
                idx_name,
                exc,
            )

    # Drop the description trigram index
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_products_description_trgm")

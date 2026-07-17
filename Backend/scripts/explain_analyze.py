"""
Phase 7: EXPLAIN ANALYZE Audit Script
======================================
Runs EXPLAIN ANALYZE on critical query patterns to measure real execution
plans and timings.  Connects via the async DATABASE_URL from .env.

Usage:
    cd Backend
    python scripts/explain_analyze.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# ---------------------------------------------------------------------------
# 1. Load DATABASE_URL from .env
# ---------------------------------------------------------------------------
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not found in .env or environment")
    sys.exit(1)

if "asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql+psycopg://", "postgresql+asyncpg://")
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")


# ---------------------------------------------------------------------------
# 2. Critical queries (each is a complete EXPLAIN ANALYZE statement)
# ---------------------------------------------------------------------------
QUERIES: dict[str, str] = {
    "A_product_list_with_window_count": """EXPLAIN (ANALYZE, BUFFERS, COSTS, FORMAT TEXT)
SELECT p.*, COUNT(*) OVER() AS _total_count
FROM products p
WHERE p.deleted_at IS NULL
  AND p.status = 'active'
ORDER BY p.created_at DESC
LIMIT 20 OFFSET 0""",

    "B_product_list_with_variants_selectinload": """EXPLAIN (ANALYZE, BUFFERS, COSTS, FORMAT TEXT)
SELECT p.*
FROM products p
LEFT JOIN product_variants pv ON pv.product_id = p.id
WHERE p.deleted_at IS NULL
  AND p.status = 'active'
ORDER BY p.created_at DESC
LIMIT 20 OFFSET 0""",

    "C_category_tree_active": """EXPLAIN (ANALYZE, BUFFERS, COSTS, FORMAT TEXT)
SELECT c.id, c.parent_id, c.name, c.slug, c.sort_order, c.is_active
FROM categories c
WHERE c.is_active = TRUE
  AND c.deleted_at IS NULL
ORDER BY c.sort_order ASC, c.name ASC""",

    "D_collection_list_admin_with_product_count": """EXPLAIN (ANALYZE, BUFFERS, COSTS, FORMAT TEXT)
SELECT
    c.id, c.name, c.slug, c.is_active, c.is_featured, c.sort_order, c.updated_at,
    COALESCE(pc.cnt, 0) AS product_count
FROM collections c
LEFT JOIN (
    SELECT collection_id, COUNT(product_id) AS cnt
    FROM product_collections
    GROUP BY collection_id
) pc ON pc.collection_id = c.id
WHERE c.deleted_at IS NULL
ORDER BY c.sort_order ASC, c.name ASC
LIMIT 20 OFFSET 0""",

    "E_search_fts_tsvector": """EXPLAIN (ANALYZE, BUFFERS, COSTS, FORMAT TEXT)
SELECT p.id, p.name, p.slug, p.base_price, p.compare_at_price,
       p.stock_quantity, p.metal_type, p.is_featured,
       ts_rank(p.search_vector, plainto_tsquery('english', 'gold ring')) AS rank
FROM products p
WHERE p.deleted_at IS NULL
  AND p.status = 'active'
  AND p.search_vector @@ plainto_tsquery('english', 'gold ring')
ORDER BY rank DESC
LIMIT 20 OFFSET 0""",

    "F_search_ilike_fallback": """EXPLAIN (ANALYZE, BUFFERS, COSTS, FORMAT TEXT)
SELECT p.id, p.name, p.slug, p.base_price, p.compare_at_price,
       p.stock_quantity, p.metal_type, p.is_featured
FROM products p
WHERE p.deleted_at IS NULL
  AND p.status = 'active'
  AND (p.name ILIKE '%gold ring%' OR p.description ILIKE '%gold ring%' OR p.sku ILIKE '%gold ring%')
ORDER BY p.created_at DESC
LIMIT 20 OFFSET 0""",

    "G_order_history_with_item_count": """EXPLAIN (ANALYZE, BUFFERS, COSTS, FORMAT TEXT)
SELECT o.*,
       (SELECT COUNT(*) FROM order_items oi WHERE oi.order_id = o.id) AS _item_count
FROM orders o
WHERE o.user_id = (SELECT id FROM profiles LIMIT 1)
ORDER BY o.created_at DESC
LIMIT 10 OFFSET 0""",

    "H_product_detail_by_slug": """EXPLAIN (ANALYZE, BUFFERS, COSTS, FORMAT TEXT)
SELECT p.*
FROM products p
WHERE p.slug = (SELECT slug FROM products WHERE deleted_at IS NULL AND status = 'active' LIMIT 1)
  AND p.deleted_at IS NULL""",

    "I_product_variants_by_product_id": """EXPLAIN (ANALYZE, BUFFERS, COSTS, FORMAT TEXT)
SELECT pv.*
FROM product_variants pv
WHERE pv.product_id = (
    SELECT id FROM products WHERE deleted_at IS NULL AND status = 'active' LIMIT 1
)""",

    "J_product_images_by_owner": """EXPLAIN (ANALYZE, BUFFERS, COSTS, FORMAT TEXT)
SELECT i.*
FROM images i
WHERE i.owner_type = 'product'
  AND i.owner_id = (
      SELECT id FROM products WHERE deleted_at IS NULL AND status = 'active' LIMIT 1
  )
  AND i.deleted_at IS NULL
ORDER BY i.sort_order""",

    "K_image_variants_by_image_ids": """EXPLAIN (ANALYZE, BUFFERS, COSTS, FORMAT TEXT)
SELECT iv.*
FROM image_variants iv
WHERE iv.image_id IN (
    SELECT i.id FROM images i
    WHERE i.owner_type = 'product'
      AND i.owner_id IN (
          SELECT id FROM products WHERE deleted_at IS NULL AND status = 'active'
          ORDER BY created_at DESC LIMIT 20
      )
      AND i.deleted_at IS NULL
)""",

    "L_review_listing_by_product": """EXPLAIN (ANALYZE, BUFFERS, COSTS, FORMAT TEXT)
SELECT r.*
FROM reviews r
WHERE r.product_id = (
    SELECT id FROM products WHERE deleted_at IS NULL AND status = 'active' LIMIT 1
)
  AND r.deleted_at IS NULL
  AND r.is_approved = TRUE
ORDER BY r.created_at DESC
LIMIT 20 OFFSET 0""",

    "M_autocomplete_prefix_ilike": """EXPLAIN (ANALYZE, BUFFERS, COSTS, FORMAT TEXT)
SELECT DISTINCT name
FROM products
WHERE deleted_at IS NULL
  AND status = 'active'
  AND name ILIKE 'gold%'
ORDER BY name
LIMIT 8""",

    "N_category_admin_with_subqueries": """EXPLAIN (ANALYZE, BUFFERS, COSTS, FORMAT TEXT)
SELECT
    c.id, c.parent_id, c.name, c.slug, c.primary_image_id,
    c.sort_order, c.is_active, c.updated_at,
    COALESCE(pc.product_count, 0) AS product_count,
    COALESCE(cc.children_count, 0) AS children_count
FROM categories c
LEFT JOIN (
    SELECT category_id, COUNT(*) AS product_count
    FROM products
    WHERE deleted_at IS NULL
    GROUP BY category_id
) pc ON pc.category_id = c.id
LEFT JOIN (
    SELECT parent_id, COUNT(*) AS children_count
    FROM categories
    WHERE deleted_at IS NULL
    GROUP BY parent_id
) cc ON cc.parent_id = c.id
WHERE c.deleted_at IS NULL
ORDER BY c.sort_order ASC, c.name ASC
LIMIT 50 OFFSET 0""",
}


# ---------------------------------------------------------------------------
# 3. Run
# ---------------------------------------------------------------------------
async def run() -> None:
    engine = create_async_engine(DATABASE_URL, pool_size=2, max_overflow=1)

    print("=" * 90)
    print("  PHASE 7: EXPLAIN ANALYZE — Hadha.co Database Audit")
    print("=" * 90)
    print()

    async with engine.connect() as conn:
        # First: table stats
        print(">> Table row counts:")
        for tbl in ["products", "product_variants", "images", "image_variants",
                     "categories", "collections", "product_collections",
                     "orders", "order_items", "reviews", "review_votes"]:
            try:
                r = await conn.execute(text(f"SELECT COUNT(*) FROM {tbl}"))
                cnt = r.scalar_one()
                print(f"   {tbl:30s}  {cnt:>8,} rows")
            except Exception as e:
                print(f"   {tbl:30s}  ERROR: {e}")
        print()

        for name, sql in QUERIES.items():
            print("=" * 90)
            print(f"  {name}")
            print("=" * 90)
            t0 = time.perf_counter()
            try:
                result = await conn.execute(text(sql))
                rows = result.fetchall()
                elapsed = (time.perf_counter() - t0) * 1000
                for row in rows:
                    print(f"  {row[0]}")
                print(f"\n  >> Client-side elapsed: {elapsed:.1f}ms")
            except Exception as e:
                print(f"  ERROR: {e}")
            print()

    await engine.dispose()
    print("=" * 90)
    print("  DONE")
    print("=" * 90)


if __name__ == "__main__":
    asyncio.run(run())

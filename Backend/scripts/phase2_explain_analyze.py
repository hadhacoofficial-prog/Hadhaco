"""Phase 2 – EXPLAIN ANALYZE baseline for product list queries.

Runs against live Supabase DB via the sync Alembic URL (EXPLAIN ANALYZE
requires a non-async connection in psycopg2).
"""

import os
import sys

os.chdir(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, ".")

from dotenv import load_dotenv  # noqa: E402

load_dotenv()
from sqlalchemy import create_engine, text  # noqa: E402

DATABASE_URL = os.getenv("ALEMBIC_DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = os.getenv("DATABASE_URL", "")
    # Convert async URL to sync for EXPLAIN ANALYZE
    DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def run(label: str, sql: str, params: dict | None = None):
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}")
    with engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        for row in result:
            print(row[0])


# ---------- 1. Count query (BEFORE optimization) ----------
run(
    "QUERY 1: Count (BEFORE — separate count)",
    """
    EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
    SELECT count(products.id)
    FROM products
    WHERE products.deleted_at IS NULL
      AND products.status = :status
    """,
    {"status": "active"},
)

# ---------- 2. Data query with selectinload (BEFORE optimization) ----------
run(
    "QUERY 2: Data + selectinload images/variants (BEFORE)",
    """
    EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
    SELECT products.id, products.sku, products.name, products.slug,
           products.short_description, products.category_id,
           products.metal_type, products.base_price, products.compare_at_price,
           products.stock_quantity, products.reserved_quantity,
           products.sold_quantity, products.status,
           products.is_featured, products.is_new_arrival, products.is_best_seller,
           products.created_at, products.updated_at
    FROM products
    WHERE products.deleted_at IS NULL
      AND products.status = :status
    ORDER BY products.created_at DESC
    LIMIT :limit OFFSET :offset
    """,
    {"status": "active", "limit": 20, "offset": 0},
)

# ---------- 3. selectinload for images ----------
run(
    "QUERY 3: selectinload images (BEFORE)",
    """
    EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
    SELECT images.id, images.module, images.preset_id,
           images.owner_type, images.owner_id,
           images.original_key, images.original_ext,
           images.original_width, images.original_height,
           images.original_size_bytes, images.mime_type,
           images.alt_text, images.metadata,
           images.status, images.version, images.uploaded_by,
           images.sort_order, images.is_primary,
           images.deleted_at, images.created_at, images.updated_at
    FROM images
    WHERE images.owner_type = 'product'
      AND images.deleted_at IS NULL
      AND images.owner_id IN (
          SELECT products.id FROM products
          WHERE products.deleted_at IS NULL AND products.status = :status
          ORDER BY products.created_at DESC
          LIMIT :limit OFFSET :offset
      )
    ORDER BY images.sort_order
    """,
    {"status": "active", "limit": 20, "offset": 0},
)

# ---------- 4. selectinload for image_variants ----------
run(
    "QUERY 4: selectinload image_variants (BEFORE)",
    """
    EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
    SELECT image_variants.id, image_variants.image_id,
           image_variants.breakpoint, image_variants.variant_name,
           image_variants.dpr, image_variants.format,
           image_variants.url, image_variants.width,
           image_variants.height, image_variants.size_bytes,
           image_variants.status, image_variants.error_message,
           image_variants.created_at
    FROM image_variants
    WHERE image_variants.image_id IN (
        SELECT images.id FROM images
        WHERE images.owner_type = 'product'
          AND images.deleted_at IS NULL
          AND images.owner_id IN (
              SELECT products.id FROM products
              WHERE products.deleted_at IS NULL AND products.status = :status
              ORDER BY products.created_at DESC
              LIMIT :limit OFFSET :offset
          )
    )
    """,
    {"status": "active", "limit": 20, "offset": 0},
)

# ---------- 5. selectinload for product_variants ----------
run(
    "QUERY 5: selectinload product_variants (BEFORE)",
    """
    EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
    SELECT product_variants.id, product_variants.product_id,
           product_variants.sku, product_variants.name,
           product_variants.price_adjustment,
           product_variants.stock_quantity, product_variants.reserved_quantity,
           product_variants.sold_quantity, product_variants.weight_grams,
           product_variants.is_active, product_variants.sort_order,
           product_variants.created_at, product_variants.updated_at
    FROM product_variants
    WHERE product_variants.product_id IN (
        SELECT products.id FROM products
        WHERE products.deleted_at IS NULL AND products.status = :status
        ORDER BY products.created_at DESC
        LIMIT :limit OFFSET :offset
    )
    """,
    {"status": "active", "limit": 20, "offset": 0},
)

# ---------- 6. Collections batch query ----------
run(
    "QUERY 6: Collections batch (BEFORE)",
    """
    EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
    SELECT product_collections.product_id, collections.id, collections.name,
           collections.slug
    FROM product_collections
    JOIN collections ON product_collections.collection_id = collections.id
    WHERE product_collections.product_id IN (
        SELECT products.id FROM products
        WHERE products.deleted_at IS NULL AND products.status = :status
        ORDER BY products.created_at DESC
        LIMIT :limit OFFSET :offset
    )
    AND collections.deleted_at IS NULL
    ORDER BY product_collections.product_id, product_collections.sort_order
    """,
    {"status": "active", "limit": 20, "offset": 0},
)

# ---------- 7. OPTIMIZED: Window function (count+data merged) ----------
run(
    "QUERY 7: Window function merge (AFTER — count+data in 1 query)",
    """
    EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
    SELECT products.id, products.sku, products.name, products.slug,
           products.short_description, products.category_id,
           products.metal_type, products.base_price, products.compare_at_price,
           products.stock_quantity, products.reserved_quantity,
           products.sold_quantity, products.status,
           products.is_featured, products.is_new_arrival, products.is_best_seller,
           products.created_at, products.updated_at,
           COUNT(*) OVER() AS total_count
    FROM products
    WHERE products.deleted_at IS NULL
      AND products.status = :status
    ORDER BY products.created_at DESC
    LIMIT :limit OFFSET :offset
    """,
    {"status": "active", "limit": 20, "offset": 0},
)

# ---------- 8. OPTIMIZED: Batch primary+secondary image per product ----------
run(
    "QUERY 8: Batch primary+secondary image (AFTER — only 2 imgs per product)",
    """
    EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
    WITH ranked AS (
        SELECT images.*,
               ROW_NUMBER() OVER (
                   PARTITION BY images.owner_id
                   ORDER BY images.is_primary DESC, images.sort_order ASC, images.created_at ASC
               ) AS rn
        FROM images
        WHERE images.owner_type = 'product'
          AND images.deleted_at IS NULL
          AND images.owner_id IN (
              SELECT products.id FROM products
              WHERE products.deleted_at IS NULL AND products.status = :status
              ORDER BY products.created_at DESC
              LIMIT :limit OFFSET :offset
          )
    )
    SELECT ranked.*
    FROM ranked
    WHERE ranked.rn <= 2
    ORDER BY ranked.owner_id, ranked.rn
    """,
    {"status": "active", "limit": 20, "offset": 0},
)

# ---------- 9. OPTIMIZED: image_variants for ONLY the primary images ----------
run(
    "QUERY 9: image_variants for primary images only (AFTER)",
    """
    EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
    WITH ranked AS (
        SELECT images.id AS image_id, images.owner_id,
               ROW_NUMBER() OVER (
                   PARTITION BY images.owner_id
                   ORDER BY images.is_primary DESC, images.sort_order ASC, images.created_at ASC
               ) AS rn
        FROM images
        WHERE images.owner_type = 'product'
          AND images.deleted_at IS NULL
          AND images.owner_id IN (
              SELECT products.id FROM products
              WHERE products.deleted_at IS NULL AND products.status = :status
              ORDER BY products.created_at DESC
              LIMIT :limit OFFSET :offset
          )
    )
    SELECT image_variants.*
    FROM image_variants
    JOIN ranked ON image_variants.image_id = ranked.image_id
    WHERE ranked.rn = 1
    """,
    {"status": "active", "limit": 20, "offset": 0},
)

print("\n\nDone. Compare BEFORE (queries 1-6) vs AFTER (queries 7-9).")

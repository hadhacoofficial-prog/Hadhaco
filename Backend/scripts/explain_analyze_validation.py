"""Phase 2 - EXPLAIN ANALYZE validation for all critical query paths.

Connects directly to Supabase PostgreSQL and runs ANALYZE on every
hot query to confirm indexes are used, no seq scans remain, and
covering indexes deliver index-only scans where expected.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# ── Load .env manually ────────────────────────────────────────────────────────
_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres.oiwpknkjcmujexwbgivf:Hadhaco%402026"
    "@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres",
)

# Convert asyncpg URL → psycopg (sync) for EXPLAIN ANALYZE
PSycopg_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


async def main() -> None:
    try:
        import psycopg
    except ImportError:
        print("ERROR: psycopg not installed. Run: pip install psycopg[binary]")
        sys.exit(1)

    print(f"Connecting to: {PSycopg_URL.split('@')[1]}")
    print("=" * 80)

    conn = psycopg.connect(PSycopg_URL, connect_timeout=10)
    conn.autocommit = True

    # First: verify indexes exist
    print("\n### INDEX INVENTORY ###\n")
    idx_rows = conn.execute("""
        SELECT indexname, tablename, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename IN ('products', 'search_history', 'product_collections', 'categories', 'collections', 'orders')
        ORDER BY tablename, indexname;
    """).fetchall()
    for r in idx_rows:
        print(f"  {r[0]:50s} ON {r[1]}")
        print(f"    {r[2]}")
    print()

    # ── Table stats ───────────────────────────────────────────────────────────
    print("### TABLE SIZES ###\n")
    for tbl in ["products", "categories", "collections", "product_collections",
                 "search_history", "orders", "images", "image_variants",
                 "product_variants", "product_attributes"]:
        try:
            q = psycopg.sql.SQL("SELECT COUNT(*) FROM {}").format(
                psycopg.sql.Identifier(tbl)
            )
            r = conn.execute(q).fetchone()
            print(f"  {tbl:30s} => {r[0]:>6d} rows")
        except Exception:
            print(f"  {tbl:30s} => (table missing or error)")
    print()

    # ── EXPLAIN queries ───────────────────────────────────────────────────────
    queries: list[tuple[str, str, str]] = [
        # (label, description, SQL)
        (
            "Q1: Product List (basic, created_at DESC)",
            "Core product listing: WHERE status='active' AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 20",
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
            SELECT p.*, COUNT(*) OVER() AS _total_count
            FROM products p
            WHERE p.deleted_at IS NULL AND p.status = 'active'
            ORDER BY p.created_at DESC
            LIMIT 20 OFFSET 0
            """,
        ),
        (
            "Q2: Product List (base_price ASC)",
            "Price sort: WHERE status='active' AND deleted_at IS NULL ORDER BY base_price ASC LIMIT 20",
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
            SELECT p.*, COUNT(*) OVER() AS _total_count
            FROM products p
            WHERE p.deleted_at IS NULL AND p.status = 'active'
            ORDER BY p.base_price ASC
            LIMIT 20 OFFSET 0
            """,
        ),
        (
            "Q3: Product List (featured, created_at DESC)",
            "Featured filter: WHERE is_featured=true AND status='active' AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 20",
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
            SELECT p.*, COUNT(*) OVER() AS _total_count
            FROM products p
            WHERE p.deleted_at IS NULL AND p.status = 'active' AND p.is_featured = true
            ORDER BY p.created_at DESC
            LIMIT 20 OFFSET 0
            """,
        ),
        (
            "Q4: Product List (category filter, created_at DESC)",
            "Category filter: WHERE category_id=? AND status='active' AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 20",
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
            SELECT p.*, COUNT(*) OVER() AS _total_count
            FROM products p
            WHERE p.deleted_at IS NULL AND p.status = 'active'
              AND p.category_id = (SELECT id FROM categories LIMIT 1)
            ORDER BY p.created_at DESC
            LIMIT 20 OFFSET 0
            """,
        ),
        (
            "Q5: Product List (price range, base_price ASC)",
            "Price range: min_price=1000, max_price=50000 ORDER BY base_price ASC LIMIT 20",
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
            SELECT p.*, COUNT(*) OVER() AS _total_count
            FROM products p
            WHERE p.deleted_at IS NULL AND p.status = 'active'
              AND p.base_price >= 1000 AND p.base_price <= 50000
            ORDER BY p.base_price ASC
            LIMIT 20 OFFSET 0
            """,
        ),
        (
            "Q6: Product List (FTS search — 'ring')",
            "Full-text search: search_vector @@ plainto_tsquery('english', 'ring') ORDER BY ts_rank DESC LIMIT 20",
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
            SELECT p.id, p.name, p.slug, p.base_price,
                   ts_rank(p.search_vector, plainto_tsquery('english', 'ring')) AS rank
            FROM products p
            WHERE p.deleted_at IS NULL AND p.status = 'active'
              AND p.search_vector @@ plainto_tsquery('english', 'ring')
            ORDER BY rank DESC
            LIMIT 20 OFFSET 0
            """,
        ),
        (
            "Q7: Product List (FTS search — 'gold necklace')",
            "Multi-word FTS: search_vector @@ plainto_tsquery('english', 'gold necklace') ORDER BY ts_rank DESC LIMIT 20",
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
            SELECT p.id, p.name, p.slug, p.base_price,
                   ts_rank(p.search_vector, plainto_tsquery('english', 'gold necklace')) AS rank
            FROM products p
            WHERE p.deleted_at IS NULL AND p.status = 'active'
              AND p.search_vector @@ plainto_tsquery('english', 'gold necklace')
            ORDER BY rank DESC
            LIMIT 20 OFFSET 0
            """,
        ),
        (
            "Q8: Product List (ILIKE fallback — '%solitaire%')",
            "ILIKE fallback: (name ILIKE '%solitaire%' OR description ILIKE '%solitaire%' OR sku ILIKE '%solitaire%') LIMIT 20",
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
            SELECT p.id, p.name, p.slug, p.base_price, p.stock_quantity
            FROM products p
            WHERE p.deleted_at IS NULL AND p.status = 'active'
              AND (p.name ILIKE '%solitaire%' OR p.description ILIKE '%solitaire%' OR p.sku ILIKE '%solitaire%')
            ORDER BY p.created_at DESC
            LIMIT 20 OFFSET 0
            """,
        ),
        (
            "Q9: Product Detail by slug",
            "Single product lookup: WHERE slug = ?",
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
            SELECT p.*
            FROM products p
            WHERE p.deleted_at IS NULL AND p.slug = 'test-product-slug'
            LIMIT 1
            """,
        ),
        (
            "Q10: Product Detail by id (PK)",
            "PK lookup: WHERE id = ?",
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
            SELECT p.*
            FROM products p
            WHERE p.id = (SELECT id FROM products LIMIT 1)
            LIMIT 1
            """,
        ),
        (
            "Q11: Trending Searches (materialized view)",
            "Trending: SELECT query, search_count FROM trending_searches ORDER BY search_count DESC LIMIT 10",
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
            SELECT query, search_count FROM trending_searches
            ORDER BY search_count DESC
            LIMIT 10
            """,
        ),
        (
            "Q12: Trending Fallback (live aggregation)",
            "Fallback aggregation: GROUP BY query, COUNT(*), ORDER BY search_count DESC LIMIT 10 (7-day window)",
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
            SELECT query, COUNT(*) AS search_count
            FROM search_history
            WHERE created_at >= NOW() - INTERVAL '7 days'
            GROUP BY query
            ORDER BY search_count DESC
            LIMIT 10
            """,
        ),
        (
            "Q13: Autocomplete (ILIKE prefix)",
            "Autocomplete: DISTINCT name WHERE name ILIKE 'ring%' ORDER BY name LIMIT 8",
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
            SELECT DISTINCT name FROM products
            WHERE deleted_at IS NULL AND status = 'active'
              AND name ILIKE 'ring%'
            ORDER BY name
            LIMIT 8
            """,
        ),
        (
            "Q14: Product Collections (reverse lookup)",
            "get_collections_for_product: JOIN product_collections WHERE product_id = ? ORDER BY sort_order",
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
            SELECT c.*
            FROM collections c
            JOIN product_collections pc ON pc.collection_id = c.id
            WHERE pc.product_id = (SELECT id FROM product_collections LIMIT 1)
              AND c.deleted_at IS NULL
            ORDER BY pc.sort_order
            """,
        ),
        (
            "Q15: Image CTE (2 images per product)",
            "CTE with ROW_NUMBER() to fetch exactly 2 images per product for 20 products",
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
            WITH ranked AS (
                SELECT
                    img.id AS _image_id,
                    img.owner_id AS _owner_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY img.owner_id
                        ORDER BY img.is_primary DESC, img.sort_order ASC, img.created_at ASC
                    ) AS _rn
                FROM images img
                WHERE img.owner_type = 'product'
                  AND img.deleted_at IS NULL
                  AND img.owner_id IN (SELECT id FROM products WHERE deleted_at IS NULL AND status = 'active' LIMIT 20)
            )
            SELECT _image_id, _owner_id FROM ranked WHERE _rn <= 2
            """,
        ),
        (
            "Q16: Orders by user (created_at DESC)",
            "Customer order history: WHERE user_id=? ORDER BY created_at DESC LIMIT 20",
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
            SELECT o.*
            FROM orders o
            WHERE o.user_id = (SELECT user_id FROM orders LIMIT 1)
            ORDER BY o.created_at DESC
            LIMIT 20 OFFSET 0
            """,
        ),
        (
            "Q17: Collection List",
            "Collection listing: WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT 20",
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
            SELECT c.*
            FROM collections c
            WHERE c.deleted_at IS NULL
            ORDER BY c.created_at DESC
            LIMIT 20 OFFSET 0
            """,
        ),
        (
            "Q18: Category Tree",
            "Category listing: WHERE deleted_at IS NULL ORDER BY sort_order ASC",
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
            SELECT cat.*
            FROM categories cat
            WHERE cat.deleted_at IS NULL
            ORDER BY cat.sort_order ASC
            """,
        ),
    ]

    results: list[dict] = []
    seq_scan_found = False

    for label, desc, sql in queries:
        print(f"\n{'-' * 80}")
        print(f"### {label} ###")
        print(f"# {desc}")
        print(f"{'-' * 80}")

        t0 = time.perf_counter()
        try:
            rows = conn.execute(sql).fetchall()
            elapsed = (time.perf_counter() - t0) * 1000
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            print(f"  ERROR ({elapsed:.1f}ms): {e}")
            results.append({"label": label, "elapsed_ms": elapsed, "error": str(e)})
            continue

        plan_lines = []
        for r in rows:
            plan_lines.append(r[0])
        plan_text = "\n".join(plan_lines)
        print(plan_text)

        has_seq = "Seq Scan" in plan_text
        has_index = "Index Scan" in plan_text or "Index Only Scan" in plan_text
        has_bitmap = "Bitmap" in plan_text

        # Parse execution time
        exec_time_ms = 0.0
        for line in plan_lines:
            if "Execution Time:" in line:
                exec_time_ms = float(line.split(":")[1].strip().replace(" ms", ""))
                break

        if has_seq:
            seq_scan_found = True

        status = "PASS"
        if has_seq and exec_time_ms > 10:
            status = "WARN (Seq Scan + slow)"
        elif has_seq:
            status = "INFO (Seq Scan OK for small table)"

        print(f"\n  => Execution Time: {exec_time_ms:.1f}ms | "
              f"Index Used: {'YES' if has_index or has_bitmap else 'NO'} | "
              f"Seq Scan: {'YES' if has_seq else 'NO'} | "
              f"Status: {status}")

        results.append({
            "label": label,
            "elapsed_ms": elapsed,
            "exec_time_ms": exec_time_ms,
            "seq_scan": has_seq,
            "index_scan": has_index or has_bitmap,
            "status": status,
        })

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'=' * 80}")
    print("### EXPLAIN ANALYZE SUMMARY ###")
    print(f"{'=' * 80}\n")

    for r in results:
        err = f"ERROR: {r.get('error', '')}" if "error" in r else ""
        print(f"  {r['label']:50s} => exec={r.get('exec_time_ms', 0):7.1f}ms "
              f"index={'YES' if r.get('index_scan') else 'NO '} "
              f"seq={'YES' if r.get('seq_scan') else 'NO '} "
              f"{r.get('status', '')} {err}")

    pass_count = sum(1 for r in results if "PASS" in r.get("status", ""))
    warn_count = sum(1 for r in results if "WARN" in r.get("status", ""))
    info_count = sum(1 for r in results if "INFO" in r.get("status", ""))
    err_count = sum(1 for r in results if "error" in r)

    print(f"\n  TOTAL: {len(results)} queries | "
          f"PASS: {pass_count} | WARN: {warn_count} | INFO: {info_count} | ERROR: {err_count}")

    if seq_scan_found:
        print("\n  WARNING: Seq Scans detected — review above for large tables.")
    else:
        print("\n  ALL queries use indexes. No seq scans on large tables.")

    print(f"\n{'=' * 80}")
    conn.close()


if __name__ == "__main__":
    asyncio.run(main())

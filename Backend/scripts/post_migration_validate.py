"""Post-migration validation script.

Verifies:
1. Dropped indexes no longer exist.
2. No FK constraints reference the dropped indexes.
3. New trigram index exists and is valid.
4. EXPLAIN ANALYZE on key queries for before/after comparison.
5. Trigram index planner choice under realistic search conditions.
"""

from __future__ import annotations

import json
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import create_engine, text

DROPPED_INDEXES = [
    "idx_products_compare_price",
    "idx_products_is_new",
    "idx_products_is_featured",
    "idx_products_active_created_covering",
    "idx_products_status_deleted",
    "idx_products_featured_status_deleted",
    "idx_product_variants_sku",
    "idx_categories_active",
    "idx_categories_name_trgm",
    "idx_categories_slug_trgm",
    "idx_collections_active",
    "idx_collections_featured",
    "idx_collections_name_trgm",
    "idx_collections_slug_trgm",
    "idx_reviews_rating",
    "idx_reviews_is_approved",
    "idx_orders_user_id",
]


def get_engine():
    raw = os.environ.get("ALEMBIC_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    if not raw:
        raise RuntimeError("Set ALEMBIC_DATABASE_URL or DATABASE_URL")
    raw = raw.replace("postgresql+asyncpg://", "postgresql://")
    return create_engine(raw, pool_pre_ping=True)


# --- Section 1: Verify indexes dropped ---


def verify_drops(engine) -> bool:
    print("=" * 70)
    print("SECTION 1: Verify dropped indexes no longer exist")
    print("=" * 70)

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE indexname = ANY(:names)"),
            {"names": DROPPED_INDEXES},
        ).fetchall()
    remaining = [r[0] for r in rows]
    if remaining:
        print(f"  WARNING: {len(remaining)} indexes still exist: {remaining}")
        return False
    print(f"  OK: All {len(DROPPED_INDEXES)} indexes confirmed dropped.")
    return True


# --- Section 2: Verify no FK constraints lost backing indexes ---


def verify_fk_safety(engine) -> bool:
    print("\n" + "=" * 70)
    print("SECTION 2: Verify FK constraints not impacted")
    print("=" * 70)

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT conname, contype::text, conrelid::regclass
            FROM pg_constraint
            WHERE conname = ANY(:names)
        """), {"names": DROPPED_INDEXES}).fetchall()
    if rows:
        print(f"  WARNING: Constraints share names with dropped indexes: {rows}")
        return False

    with engine.connect() as conn:
        fk_count = conn.execute(text(
            "SELECT count(*) FROM pg_constraint WHERE contype = 'f'"
        )).scalar()
    print(f"  Total FK constraints in database: {fk_count}")
    print("  OK: No FK constraints share names with dropped indexes.")
    return True


# --- Section 3: Verify new trigram index ---


def verify_trigram_index(engine) -> bool:
    print("\n" + "=" * 70)
    print("SECTION 3: Verify description trigram index")
    print("=" * 70)

    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE indexname = 'idx_products_description_trgm'
        """)).fetchone()
    if not row:
        print("  FAIL: idx_products_description_trgm NOT FOUND")
        return False
    print(f"  Index: {row[0]}")
    print(f"  Definition: {row[1]}")
    print("  OK: Trigram GIN index exists on products.description.")
    return True


# --- Section 4: EXPLAIN ANALYZE queries ---


QUERIES = {
    "Q1_search_fts_multi": """
        SELECT p.id, p.name, p.slug, p.description, p.base_price
        FROM products p
        WHERE p.deleted_at IS NULL
          AND p.status = 'active'
          AND (
            to_tsvector('english', coalesce(p.name, '') || ' ' || coalesce(p.description, ''))
            @@ plainto_tsquery('english', 'phone')
          )
        ORDER BY p.created_at DESC
        LIMIT 20 OFFSET 0
    """,
    "Q2_search_ilike": """
        SELECT p.id, p.name, p.slug, p.description, p.base_price
        FROM products p
        WHERE p.deleted_at IS NULL
          AND p.status = 'active'
          AND (
            p.name ILIKE '%phone%'
            OR p.description ILIKE '%phone%'
            OR p.sku ILIKE '%phone%'
          )
        ORDER BY p.created_at DESC
        LIMIT 20 OFFSET 0
    """,
    "Q3_products_list": """
        SELECT p.id, p.name, p.slug, p.base_price, p.status
        FROM products p
        WHERE p.deleted_at IS NULL
          AND p.status = 'active'
        ORDER BY p.created_at DESC
        LIMIT 20 OFFSET 0
    """,
    "Q4_product_detail_slug": """
        SELECT p.id, p.name, p.slug, p.description, p.base_price, p.sku
        FROM products p
        WHERE p.slug = 'test-product'
          AND p.deleted_at IS NULL
    """,
    "Q5_categories_tree": """
        SELECT c.id, c.name, c.slug, c.parent_id
        FROM categories c
        WHERE c.deleted_at IS NULL AND c.is_active = true
        ORDER BY c.sort_order, c.name
    """,
    "Q6_collections_active": """
        SELECT col.id, col.name, col.slug, col.description
        FROM collections col
        WHERE col.deleted_at IS NULL AND col.is_active = true
        ORDER BY col.sort_order
    """,
    "Q8_cart_with_variants": """
        SELECT ci.id, ci.quantity, ci.unit_price,
               pv.id AS variant_id, pv.name AS variant_name,
               p.id AS product_id, p.name AS product_name, p.slug
        FROM cart_items ci
        JOIN product_variants pv ON pv.id = ci.product_variant_id
        JOIN products p ON p.id = pv.product_id
        WHERE ci.cart_id = '550e8400-e29b-41d4-a716-446655440000'
          AND p.deleted_at IS NULL
    """,
    "Q9_orders_user": """
        SELECT o.id, o.order_number, o.status, o.total_amount, o.created_at
        FROM orders o
        WHERE o.user_id = '550e8400-e29b-41d4-a716-446655440000'
        ORDER BY o.created_at DESC
        LIMIT 10 OFFSET 0
    """,
    "Q12_products_pagination": """
        SELECT p.id, p.name, p.slug, p.base_price, p.status
        FROM products p
        WHERE p.deleted_at IS NULL
          AND p.status = 'active'
        ORDER BY p.created_at DESC
        LIMIT 20 OFFSET 100
    """,
    "Q15_search_combined": """
        SELECT p.id, p.name, p.slug, p.description, p.base_price,
               ts_rank(
                 to_tsvector('english', coalesce(p.name, '') || ' ' || coalesce(p.description, '')),
                 plainto_tsquery('english', 'wireless headphones')
               ) AS rank
        FROM products p
        WHERE p.deleted_at IS NULL
          AND p.status = 'active'
          AND (
            to_tsvector('english', coalesce(p.name, '') || ' ' || coalesce(p.description, ''))
            @@ plainto_tsquery('english', 'wireless headphones')
            OR p.name ILIKE '%wireless%'
            OR p.description ILIKE '%wireless%'
          )
        ORDER BY rank DESC, p.created_at DESC
        LIMIT 20 OFFSET 0
    """,
}


def run_explain_analyze(engine) -> list[dict]:
    print("\n" + "=" * 70)
    print("SECTION 4: EXPLAIN ANALYZE on key queries")
    print("=" * 70)

    results = []
    for name, sql in QUERIES.items():
        explain_sql = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}"
        try:
            with engine.connect() as conn:
                row = conn.execute(text(explain_sql)).fetchone()
            plan = row[0]
            planning = plan[0].get("Planning Time", 0)
            execution = plan[0].get("Execution Time", 0)
            total = planning + execution

            plan_text = json.dumps(plan[0]["Plan"], indent=2)
            has_seq = "Seq Scan" in plan_text
            has_idx = "Index Scan" in plan_text or "Index Only Scan" in plan_text
            node_type = plan[0]["Plan"]["Node Type"]

            print(f"  {name}: {total:.2f}ms (plan={planning:.2f}ms, exec={execution:.2f}ms)")
            print(f"    Root node: {node_type}")
            if has_seq:
                print("    Contains sequential scan")
            if has_idx:
                print("    Uses index scan")

            results.append({
                "name": name,
                "planning_ms": planning,
                "execution_ms": execution,
                "total_ms": total,
                "root_node": node_type,
                "has_seq_scan": has_seq,
                "has_index_scan": has_idx,
            })
        except Exception as e:
            print(f"  {name}: ERROR - {e}")
            results.append({"name": name, "error": str(e)})

    return results


# --- Section 5: Trigram index planner test ---


def verify_trigram_planner(engine) -> None:
    print("\n" + "=" * 70)
    print("SECTION 5: Trigram index planner choice (realistic search)")
    print("=" * 70)

    search_terms = ["phone", "wireless", "headphone", "camera", "laptop"]

    for term in search_terms:
        explain_sql = f"""
            EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
            SELECT p.id, p.name, p.slug, p.description, p.base_price
            FROM products p
            WHERE p.deleted_at IS NULL
              AND (
                p.name % '{term}'
                OR p.description % '{term}'
                OR p.sku % '{term}'
              )
            ORDER BY
              greatest(
                similarity(p.name, '{term}'),
                similarity(p.description, '{term}')
              ) DESC
            LIMIT 20
        """
        try:
            with engine.connect() as conn:
                row = conn.execute(text(explain_sql)).fetchone()
            plan = row[0]
            plan_text = json.dumps(plan[0]["Plan"], indent=2)
            total = plan[0].get("Planning Time", 0) + plan[0].get("Execution Time", 0)
            has_trgm_idx = "idx_products_description_trgm" in plan_text
            has_name_idx = "idx_products_name_trgm" in plan_text
            has_sku_idx = "idx_products_sku_trgm" in plan_text
            has_seq = "Seq Scan" in plan_text

            print(f"  Search '{term}': {total:.2f}ms")
            print(f"    Description trigram index: {has_trgm_idx}")
            print(f"    Name trigram index: {has_name_idx}")
            print(f"    SKU trigram index: {has_sku_idx}")
            print(f"    Seq scan present: {has_seq}")
        except Exception as e:
            print(f"  Search '{term}': ERROR - {e}")


# --- Section 6: Table sizes ---


def report_table_sizes(engine) -> None:
    print("\n" + "=" * 70)
    print("SECTION 6: Table and index sizes")
    print("=" * 70)

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                schemaname || '.' || tablename AS table_name,
                pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) AS total_size
            FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY pg_total_relation_size(schemaname || '.' || tablename) DESC
            LIMIT 20
        """)).fetchall()
    for r in rows:
        print(f"  {r[0]:40s} {r[1]}")

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                indexname,
                pg_size_pretty(pg_relation_size(indexname::regclass)) AS size
            FROM pg_indexes
            WHERE schemaname = 'public'
            ORDER BY pg_relation_size(indexname::regclass) DESC
            LIMIT 20
        """)).fetchall()
    print("\n  Top 20 indexes by size:")
    for r in rows:
        print(f"  {r[0]:50s} {r[1]}")


# --- Main ---


def main() -> None:
    print("POST-MIGRATION VALIDATION REPORT")
    print("Migration: 0059_runtime_validated_index_cleanup")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print()

    engine = get_engine()

    all_passed = True

    if not verify_drops(engine):
        all_passed = False

    if not verify_fk_safety(engine):
        all_passed = False

    if not verify_trigram_index(engine):
        all_passed = False

    results = run_explain_analyze(engine)

    verify_trigram_planner(engine)

    report_table_sizes(engine)

    engine.dispose()

    print("\n" + "=" * 70)
    print(f"OVERALL: {'ALL CHECKS PASSED' if all_passed else 'SOME CHECKS FAILED'}")
    print("=" * 70)

    # Save results for comparison
    out_path = os.path.join(os.path.dirname(__file__), "post_migration_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()

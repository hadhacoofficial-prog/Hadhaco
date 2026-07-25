"""Phase 3: pg_stat_user_indexes and pg_stat_user_tables audit.

Connects directly to Supabase PostgreSQL and reads cumulative index
and table statistics to find unused indexes, missing indexes, and
tables with heavy sequential scan pressure.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

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
PSycopg_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


def main() -> None:
    import psycopg

    conn = psycopg.connect(PSycopg_URL, connect_timeout=10)
    conn.autocommit = True

    # ── Table-level scan stats ────────────────────────────────────────────
    print("=" * 100)
    print("  TABLE SCAN STATISTICS (pg_stat_user_tables)")
    print("=" * 100)
    rows = conn.execute("""
        SELECT relname, seq_scan, idx_scan,
               seq_tup_read, idx_tup_fetch, n_live_tup,
               n_tup_ins, n_tup_upd, n_tup_del
        FROM pg_stat_user_tables
        WHERE schemaname = 'public' AND n_live_tup > 0
        ORDER BY seq_scan DESC
    """).fetchall()

    print(
        f"\n  {'Table':<28} {'Seq Scan':>10} {'Idx Scan':>10} "
        f"{'Seq Tup Read':>14} {'Idx Tup Fetch':>14} {'Live Tups':>10}"
    )
    print("  " + "-" * 96)
    for r in rows:
        seq = r[1] or 0
        idx = r[2] or 0
        total = seq + idx
        seq_pct = (seq / total * 100) if total else 0
        flag = " *** HIGH SEQ" if seq_pct > 80 and total > 10 else ""
        print(
            f"  {r[0]:<28} {seq:>10} {idx:>10} "
            f"{r[3] or 0:>14} {r[4] or 0:>14} {r[5] or 0:>10}"
            f"  ({seq_pct:.0f}% seq){flag}"
        )

    # ── Index-level stats ─────────────────────────────────────────────────
    print(f"\n{'=' * 100}")
    print("  INDEX USAGE STATISTICS (pg_stat_user_indexes)")
    print("=" * 100)

    TARGET_TABLES = (
        "products",
        "product_variants",
        "images",
        "image_variants",
        "categories",
        "collections",
        "orders",
        "order_items",
        "reviews",
        "review_votes",
        "product_collections",
        "search_history",
    )

    rows = conn.execute(
        """
        SELECT
            relname as tablename, indexrelname as indexname,
            idx_scan, idx_tup_read, idx_tup_fetch,
            pg_size_pretty(pg_relation_size(indexrelid)) as index_size
        FROM pg_stat_user_indexes
        WHERE schemaname = 'public'
          AND relname = ANY(%s)
        ORDER BY relname, idx_scan DESC
    """,
        (list(TARGET_TABLES),),
    ).fetchall()

    print(f"\n  {'Table':<24} {'Index':<55} {'Scans':>8} {'Size':>8}")
    print("  " + "-" * 99)
    current_table = None
    for r in rows:
        if r[0] != current_table:
            if current_table is not None:
                print()
            current_table = r[0]
        scans = r[2] or 0
        flag = " (UNUSED)" if scans == 0 else ""
        print(f"  {r[0]:<24} {r[1]:<55} {scans:>8} {r[5]:>8}{flag}")

    # ── Unused indexes (total bloat cost) ─────────────────────────────────
    print(f"\n{'=' * 100}")
    print("  UNUSED INDEXES — CANDIDATES FOR REMOVAL")
    print("=" * 100)

    rows = conn.execute("""
        SELECT
            relname as tablename, indexrelname as indexname,
            pg_size_pretty(pg_relation_size(indexrelid)) as index_size,
            pg_relation_size(indexrelid) as size_bytes
        FROM pg_stat_user_indexes
        WHERE schemaname = 'public'
          AND idx_scan = 0
          AND indexrelname NOT LIKE '%_pkey'
        ORDER BY pg_relation_size(indexrelid) DESC
    """).fetchall()

    total_waste = 0
    for r in rows:
        waste = r[3] or 0
        total_waste += waste
        print(f"  {r[0]:<24} {r[1]:<55} {r[2]:>8}")

    if rows:
        print(f"\n  Total wasted index space: {total_waste / 1024 / 1024:.2f} MB")
    else:
        print("  None found.")

    # ── FTS index stats specifically ──────────────────────────────────────
    print(f"\n{'=' * 100}")
    print("  FULL-TEXT SEARCH INDEX HEALTH")
    print("=" * 100)

    rows = conn.execute("""
        SELECT
            i.indexrelname as indexname,
            i.relname as tablename,
            pg_size_pretty(pg_relation_size(i.indexrelid)) as index_size
        FROM pg_stat_user_indexes i
        JOIN pg_indexes ix ON ix.indexname = i.indexrelname AND ix.schemaname = i.schemaname
        WHERE i.schemaname = 'public'
          AND ix.indexdef LIKE '%gin%'
        ORDER BY i.relname
    """).fetchall()
    for r in rows:
        print(f"  {r[1]:<24} {r[0]:<55} {r[2]:>8}")

    # Check if search_vector trigger is active
    rows = conn.execute("""
        SELECT trigger_name, event_manipulation, action_statement
        FROM information_schema.triggers
        WHERE event_object_table = 'products'
          AND trigger_schema = 'public'
    """).fetchall()
    print("\n  Product triggers:")
    for r in rows:
        print(f"    {r[0]:<40} ON {r[1]:<10} => {r[2]}")

    # Check search_vector column definition
    rows = conn.execute("""
        SELECT column_name, udt_name, collation_name
        FROM information_schema.columns
        WHERE table_name = 'products'
          AND column_name = 'search_vector'
    """).fetchall()
    if rows:
        print(f"\n  search_vector column: type={rows[0][1]}, collation={rows[0][2]}")
    else:
        print("\n  WARNING: search_vector column not found on products table!")

    # ── Table bloat estimate ──────────────────────────────────────────────
    print(f"\n{'=' * 100}")
    print("  TABLE SIZES")
    print("=" * 100)
    rows = conn.execute(
        """
        SELECT
            relname,
            pg_size_pretty(pg_total_relation_size(c.oid)) as total_size,
            pg_size_pretty(pg_relation_size(c.oid)) as table_size,
            pg_size_pretty(pg_indexes_size(c.oid)) as index_size,
            (SELECT reltuples::bigint FROM pg_class WHERE oid = c.oid) as est_rows
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind = 'r'
          AND relname = ANY(%s)
        ORDER BY pg_total_relation_size(c.oid) DESC
    """,
        (list(TARGET_TABLES),),
    ).fetchall()

    print(
        f"\n  {'Table':<24} {'Total':>12} {'Table':>12} {'Indexes':>12} {'Est Rows':>10}"
    )
    print("  " + "-" * 74)
    for r in rows:
        print(f"  {r[0]:<24} {r[1]:>12} {r[2]:>12} {r[3]:>12} {r[4] or 0:>10}")

    conn.close()

    print(f"\n{'=' * 100}")
    print("  DONE")
    print("=" * 100)


if __name__ == "__main__":
    main()

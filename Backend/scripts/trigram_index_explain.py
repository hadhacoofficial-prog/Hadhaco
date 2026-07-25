"""Detailed EXPLAIN output for the description trigram index."""

from __future__ import annotations

import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import create_engine, text  # noqa: E402


def get_engine():
    raw = os.environ.get("ALEMBIC_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    raw = raw.replace("postgresql+asyncpg://", "postgresql://")
    return create_engine(raw, pool_pre_ping=True)


def summarize_plan(node, depth=0):
    prefix = "  " * (depth + 1)
    node_type = node.get("Node Type", "?")
    relation = node.get("Relation Name", "")
    rows = node.get("Actual Rows", "?")
    cost = node.get("Total Cost", "?")
    shared_hit = node.get("Shared Hit Blocks", 0)
    shared_read = node.get("Shared Read Blocks", 0)
    filter_info = ""
    if "Filter" in node:
        filter_info += f" filter={node['Filter'][:100]}"
    if "Index Cond" in node:
        filter_info += f" idx_cond={node['Index Cond'][:100]}"
    print(
        f"{prefix}{node_type} on {relation} "
        f"(rows={rows}, cost={cost}, hit={shared_hit}, read={shared_read})"
        f"{filter_info}"
    )
    for child in node.get("Plans", []):
        summarize_plan(child, depth + 1)


def main():
    engine = get_engine()

    searches = [
        ("phone", "single word"),
        ("wireless", "single word"),
        ("headphone", "single word"),
        ("wireless headphones", "two words"),
    ]

    for term, label in searches:
        explain_sql = f"""
            EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT JSON)
            SELECT p.id, p.name, p.slug, p.description, p.base_price,
                   greatest(
                     similarity(p.name, '{term}'),
                     similarity(p.description, '{term}')
                   ) AS sim_score
            FROM products p
            WHERE p.deleted_at IS NULL
              AND (
                p.name % '{term}'
                OR p.description % '{term}'
              )
            ORDER BY sim_score DESC
            LIMIT 20
        """
        with engine.connect() as conn:
            row = conn.execute(text(explain_sql)).fetchone()
        plan = row[0][0]
        plan_text = json.dumps(plan, indent=2)

        exec_plan = plan["Plan"]
        total_cost = exec_plan.get("Total Cost", "N/A")
        actual_rows = exec_plan.get("Actual Rows", "N/A")
        planning = plan.get("Planning Time", 0)
        execution = plan.get("Execution Time", 0)

        print(f'=== Search: "{term}" ({label}) ===')
        print(f"  Total Cost: {total_cost}")
        print(f"  Actual Rows Returned: {actual_rows}")
        print(f"  Planning Time: {planning:.2f}ms")
        print(f"  Execution Time: {execution:.2f}ms")

        has_desc_trgm = "idx_products_description_trgm" in plan_text
        has_name_trgm = "idx_products_name_trgm" in plan_text
        has_sku_trgm = "idx_products_sku_trgm" in plan_text
        has_seq = "Seq Scan" in plan_text

        if has_desc_trgm:
            print("  Trigram Index: idx_products_description_trgm (NEW - GIN)")
        elif has_name_trgm:
            print("  Trigram Index: idx_products_name_trgm")
        elif has_sku_trgm:
            print("  Trigram Index: idx_products_sku_trgm")
        else:
            print("  Trigram Index: NOT USED")

        print(f"  Sequential Scan Present: {has_seq}")
        print("  Plan Structure:")
        summarize_plan(exec_plan)
        print()

    engine.dispose()


if __name__ == "__main__":
    main()

"""Generate Backend/supabase/recovery_sql/02_categories.sql from the recovered
`categories:tree:v1:all` cache (decoded to
`.../Json data/categories_tree.json`).

Scope: `categories` table ONLY. Cross-checked against `categories_navbar.json`
and `navigation_categories.json` (same ids/names/slugs/sort_order — see the
recovery report) to confirm they're three different projections of the same
underlying rows, so `categories_tree.json` alone (the richest/most complete
projection: it's the only one carrying `parent_id` explicitly) is sufficient
as the single source of truth.

Every row's `id` IS the real, known production UUID (unlike the homepage
sections, category ids survive directly in every cached projection — they
are not hidden behind a child-item indirection), so every INSERT here targets
`ON CONFLICT (id) DO UPDATE`, not `(slug)` — id is the primary key and the
value we actually recovered.

NOT restored (and why): `categories.image_url` is not a real column at all —
`CategoryService._image_urls()` (app/modules/categories/service.py:106-119)
resolves it at read time via a polymorphic join to the `images`/`image_variants`
tables (owner_type='category', owner_id=category.id). Only the final resolved
CDN URL string survived in the cache; the `images` row's required NOT NULL
fields (original_width/height/size_bytes, mime_type, original_key, preset_id)
and the `image_variants` row's required fields (width/height/size_bytes, url
per breakpoint) did not survive anywhere in the cache. Fabricating those
would violate the "never invent data" rule, so image restoration is left
unresolved here (documented in the recovery report), exactly as `cms_media`
was left unresolved in the homepage phase.
"""

from __future__ import annotations

import json
from pathlib import Path

CACHE_JSON = Path(
    r"F:\Work\Hadha.co\data\hadha-redis-recovery-20260725-191619\recovery-backup\Json data\categories_tree.json"
)
OUT_SQL = Path(
    r"F:\Work\Hadha.co\Project\Backend\supabase\recovery_sql\02_categories.sql"
)


def sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def flatten(nodes: list[dict], out: list[dict]) -> None:
    """Pre-order traversal: a parent is always appended before its children,
    so sequential INSERTs never hit the self-referencing FK before the
    parent row exists."""
    for n in nodes:
        out.append(n)
        flatten(n.get("children") or [], out)


def main() -> None:
    doc = json.loads(CACHE_JSON.read_text(encoding="utf-8"))
    tree = doc["d"]
    cache_written_at = doc.get("t")

    flat: list[dict] = []
    flatten(tree, flat)

    lines: list[str] = []
    lines.append("-- ============================================================")
    lines.append("-- 02_categories.sql")
    lines.append("-- Category tree restoration, recovered from the Redis cache key")
    lines.append("-- `categories:tree:v1:all` (decoded payload:")
    lines.append("-- recovery-backup/Json data/categories_tree.json).")
    lines.append(f"-- Cache write timestamp (epoch): {cache_written_at}")
    lines.append("--")
    lines.append("-- SCOPE: `categories` table ONLY. Navigation/navbar caches are just")
    lines.append("-- alternate projections of these same rows (cross-verified in the")
    lines.append("-- recovery report) and need no separate restoration.")
    lines.append("--")
    lines.append(
        "-- Every id below is a REAL recovered production UUID (category ids survive"
    )
    lines.append(
        "-- directly in the cache, unlike homepage section ids) - ON CONFLICT (id) is"
    )
    lines.append("-- the correct, non-fabricated upsert target throughout.")
    lines.append("--")
    lines.append(
        "-- NOT restored: image_url (not a categories column - resolved via a"
    )
    lines.append(
        "-- polymorphic join to images/image_variants at read time; those tables'"
    )
    lines.append(
        "-- required NOT NULL fields did not survive in the cache - see the"
    )
    lines.append("-- recovery report). product_count is also not a column (computed live).")
    lines.append("--")
    lines.append("-- Idempotent: INSERT ... ON CONFLICT DO UPDATE only. No DELETE/TRUNCATE.")
    lines.append("-- Rows are ordered parent-before-child so the self-referencing")
    lines.append("-- categories.parent_id FK never fails mid-script.")
    lines.append("-- ============================================================")
    lines.append("")
    lines.append("BEGIN;")
    lines.append("")

    for node in flat:
        cid = node["id"]
        parent_id = node.get("parent_id")
        name = node["name"]
        slug = node["slug"]
        sort_order = node["sort_order"]
        parent_sql = sql_str(parent_id) if parent_id else "NULL"

        lines.append(f"-- {slug}  (id = {cid}{', parent = ' + parent_id if parent_id else ' - top-level'})")
        lines.append("INSERT INTO categories")
        lines.append(
            "    (id, parent_id, name, slug, sort_order, is_active, created_at, updated_at)"
        )
        lines.append("VALUES")
        lines.append(
            f"    ({sql_str(cid)}, {parent_sql}, {sql_str(name)}, {sql_str(slug)}, {sort_order}, TRUE, NOW(), NOW())"
        )
        lines.append("ON CONFLICT (id) DO UPDATE SET")
        lines.append("    parent_id = EXCLUDED.parent_id,")
        lines.append("    name = EXCLUDED.name,")
        lines.append("    slug = EXCLUDED.slug,")
        lines.append("    sort_order = EXCLUDED.sort_order,")
        lines.append("    is_active = EXCLUDED.is_active,")
        lines.append("    updated_at = NOW();")
        lines.append("")

    lines.append("-- ── Validation ───────────────────────────────────────────────────────────")
    lines.append("DO $$")
    lines.append("DECLARE")
    lines.append("    cat_count INTEGER;")
    lines.append("BEGIN")
    lines.append("    SELECT COUNT(*) INTO cat_count FROM categories WHERE id IN (")
    lines.append(
        "        " + ", ".join(sql_str(n["id"]) for n in flat) + ");"
    )
    lines.append(f"    IF cat_count <> {len(flat)} THEN")
    lines.append(
        f"        RAISE EXCEPTION 'category restore validation failed: expected {len(flat)} rows, found %', cat_count;"
    )
    lines.append("    END IF;")
    lines.append(
        f"    RAISE NOTICE 'Category tree restore validated: % of {len(flat)} recovered categories present', cat_count;"
    )
    lines.append("END $$;")
    lines.append("")
    lines.append("COMMIT;")
    lines.append("")

    OUT_SQL.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT_SQL} ({len(flat)} categories)")


if __name__ == "__main__":
    main()

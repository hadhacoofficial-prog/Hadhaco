"""Generate Backend/supabase/recovery_sql/01_homepage.sql from the recovered
Redis cache payload (`cms:homepage`, decoded to
`F:\\Work\\Hadha.co\\data\\hadha-redis-recovery-20260725-191619\\recovery-backup\\Json data\\cms_homepage.json`).

Scope: Homepage CMS ONLY -> `landing_sections` + `cms_section_items`.
Categories / Products / Collections / Navigation / Company Config are
intentionally out of scope for this phase and are not touched.

Design decisions (see recovery_reports/01_homepage_recovery.md for full
rationale):
  - 4 of the 16 sections have a recovered UUID, because their id survived as
    the `section_id` FK on their recovered `cms_section_items` rows:
    announcement_bar, hero_carousel, featured_collection, why_choose_us.
    For these, `id` is forced via `DO UPDATE SET id = EXCLUDED.id` since the
    child item rows below must reference this exact id.
  - The other 12 sections have no recovered items, so no UUID for them
    survived in the cache. We do NOT invent one: `id` is omitted from the
    INSERT column list entirely, so Postgres assigns it via the column's own
    `DEFAULT gen_random_uuid()` only on first insert; because `id` is never
    referenced in the ON CONFLICT SET clause, a pre-existing row's id is left
    untouched on every re-run.
  - `draft_config` is seeded equal to `config` (mirrors the original
    `0004_cms_homepage_extension` migration's seeding pattern) since the cache
    only ever reflects the *published* config - there is no recoverable draft
    state.
  - `status='published'`, since this payload was actively served from the
    live public cache at capture time.
  - Section-level `published_at` and `version_number` are NOT present
    anywhere in the recovered cache (only cms_section_items carry
    created_at/updated_at) - left as NULL / default 1 respectively, and
    flagged as unresolved in the report rather than guessed.
"""

from __future__ import annotations

import json
from pathlib import Path

CACHE_JSON = Path(
    r"F:\Work\Hadha.co\data\hadha-redis-recovery-20260725-191619\recovery-backup\Json data\cms_homepage.json"
)
OUT_SQL = Path(
    r"F:\Work\Hadha.co\Project\Backend\supabase\recovery_sql\01_homepage.sql"
)

# section_key -> known landing_sections.id, recovered from the `section_id`
# FK embedded in that section's cms_section_items entries in the cache.
KNOWN_SECTION_IDS: dict[str, str] = {
    "announcement_bar": "bc6c2286-9194-416f-9a35-5e9a98b1482d",
    "hero_carousel": "294bf305-3b09-48ca-b979-ded8449712b8",
    "featured_collection": "5f104219-6fdd-44fb-b379-4545021e3a80",
    "why_choose_us": "f1235bc5-3ebc-4cae-8a2e-3cbdc2a29c88",
}

_TAG = "hpj"  # dollar-quote tag for embedded JSONB literals


def jsonb_literal(obj) -> str:
    text = json.dumps(obj, ensure_ascii=False, sort_keys=False)
    return f"${_TAG}${text}${_TAG}$::jsonb"


def sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def main() -> None:
    doc = json.loads(CACHE_JSON.read_text(encoding="utf-8"))
    data = doc["d"]["data"]
    cache_written_at = doc["d"].get("t") or doc.get("t")
    layout = data["layout"]
    sections = data["sections"]

    assert len(layout) == 16, f"expected 16 layout entries, found {len(layout)}"

    lines: list[str] = []
    lines.append("-- ============================================================")
    lines.append("-- 01_homepage.sql")
    lines.append("-- Homepage CMS restoration, recovered from the Redis cache key")
    lines.append(
        "-- `cms:homepage` (decoded payload: recovery-backup/Json data/cms_homepage.json)."
    )
    lines.append(
        f'-- Cache write timestamp (epoch, from the cache_swr wrapper\'s "t" field): {cache_written_at}'
    )
    lines.append("--")
    lines.append("-- SCOPE: Homepage CMS only -> landing_sections + cms_section_items.")
    lines.append(
        "-- Categories, Products, Collections, Navigation and Company Config are"
    )
    lines.append("-- OUT OF SCOPE for this script and are not touched.")
    lines.append("--")
    lines.append("-- Idempotent: every statement is INSERT ... ON CONFLICT DO UPDATE.")
    lines.append("-- No DELETE, no TRUNCATE. Safe to run multiple times.")
    lines.append(
        "-- See Backend/supabase/recovery_reports/01_homepage_recovery.md for the"
    )
    lines.append(
        "-- full schema mapping, per-section confidence levels and unresolved fields."
    )
    lines.append("-- ============================================================")
    lines.append("")
    lines.append("BEGIN;")
    lines.append("")
    lines.append(
        "-- ── 1. landing_sections (16 rows = full homepage layout) ──────────────────"
    )
    lines.append("")

    for entry in layout:
        key = entry["section_key"]
        section_type = entry["section_type"]
        title = entry["title"]
        sort_order = entry["sort_order"]
        is_active = entry["is_active"]
        config = sections[key]["config"]
        known_id = KNOWN_SECTION_IDS.get(key)

        lines.append(f"-- section_key = {key}  (section_type = {section_type})")
        if known_id:
            lines.append(
                f"-- id recovered from cms_section_items.section_id ({len(sections[key]['items'])} item(s) below reference it)"
            )
            lines.append("INSERT INTO landing_sections")
            lines.append(
                "    (id, section_key, section_type, title, config, draft_config, is_active, sort_order, status, version_number, created_at, updated_at)"
            )
            lines.append("VALUES")
            lines.append(
                f"    ({sql_str(known_id)}, {sql_str(key)}, {sql_str(section_type)}, {sql_str(title)},"
            )
            lines.append(f"     {jsonb_literal(config)},")
            lines.append(f"     {jsonb_literal(config)},")
            lines.append(
                f"     {str(is_active).upper()}, {sort_order}, 'published', 1, NOW(), NOW())"
            )
            lines.append("ON CONFLICT (section_key) DO UPDATE SET")
            lines.append("    id = EXCLUDED.id,")
        else:
            lines.append(
                "-- no id recoverable (section has zero items in the cache) -> DEFAULT gen_random_uuid(), id never overwritten on conflict"
            )
            lines.append("INSERT INTO landing_sections")
            lines.append(
                "    (section_key, section_type, title, config, draft_config, is_active, sort_order, status, version_number, created_at, updated_at)"
            )
            lines.append("VALUES")
            lines.append(
                f"    ({sql_str(key)}, {sql_str(section_type)}, {sql_str(title)},"
            )
            lines.append(f"     {jsonb_literal(config)},")
            lines.append(f"     {jsonb_literal(config)},")
            lines.append(
                f"     {str(is_active).upper()}, {sort_order}, 'published', 1, NOW(), NOW())"
            )
            lines.append("ON CONFLICT (section_key) DO UPDATE SET")
        lines.append("    section_type = EXCLUDED.section_type,")
        lines.append("    title = EXCLUDED.title,")
        lines.append("    config = EXCLUDED.config,")
        lines.append("    is_active = EXCLUDED.is_active,")
        lines.append("    sort_order = EXCLUDED.sort_order,")
        lines.append("    status = EXCLUDED.status,")
        lines.append("    updated_at = NOW();")
        lines.append("")

    lines.append(
        "-- ── 2. cms_section_items (recovered items for the 4 sections that had any) ─"
    )
    lines.append("--")
    lines.append(
        "-- NOTE (why_choose_us anomaly, preserved verbatim, not deduplicated):"
    )
    lines.append(
        "-- the cache contains 8 items for 4 distinct cards - each card appears twice"
    )
    lines.append(
        "-- under two different UUIDs with two different created_at/updated_at pairs"
    )
    lines.append(
        "-- but otherwise byte-identical config. This looks like a duplicate-publish"
    )
    lines.append(
        "-- artifact in the source system, not a decoding error. Per the 'never invent,"
    )
    lines.append(
        "-- never silently alter recovered data' rule, all 8 rows are restored exactly"
    )
    lines.append("-- as cached. See the recovery report for the flagged anomaly.")
    lines.append("")

    item_count = 0
    for entry in layout:
        key = entry["section_key"]
        items = sections[key]["items"]
        if not items:
            continue
        section_id = KNOWN_SECTION_IDS[key]
        lines.append(f"-- items for section_key = {key}  (section_id = {section_id})")
        for item in items:
            item_count += 1
            lines.append("INSERT INTO cms_section_items")
            lines.append(
                "    (id, section_id, sort_order, is_enabled, config, created_at, updated_at)"
            )
            lines.append("VALUES")
            lines.append(
                f"    ({sql_str(item['id'])}, {sql_str(section_id)}, {item['sort_order']}, {str(item['is_enabled']).upper()},"
            )
            lines.append(f"     {jsonb_literal(item['config'])},")
            lines.append(
                f"     {sql_str(item['created_at'])}::timestamptz, {sql_str(item['updated_at'])}::timestamptz)"
            )
            lines.append("ON CONFLICT (id) DO UPDATE SET")
            lines.append("    section_id = EXCLUDED.section_id,")
            lines.append("    sort_order = EXCLUDED.sort_order,")
            lines.append("    is_enabled = EXCLUDED.is_enabled,")
            lines.append("    config = EXCLUDED.config,")
            lines.append("    updated_at = EXCLUDED.updated_at;")
            lines.append("")

    lines.append(
        "-- ── 3. In-transaction validation ─────────────────────────────────────────"
    )
    lines.append(
        "-- Aborts the whole restore (ROLLBACK) if the row counts don't match what was"
    )
    lines.append(
        "-- recovered from the cache, instead of committing a partial/mismatched state."
    )
    lines.append("DO $$")
    lines.append("DECLARE")
    lines.append("    section_count INTEGER;")
    lines.append("    item_count INTEGER;")
    lines.append("BEGIN")
    lines.append(
        "    SELECT COUNT(*) INTO section_count FROM landing_sections WHERE section_key IN ("
    )
    lines.append(
        "        " + ", ".join(sql_str(entry["section_key"]) for entry in layout) + ");"
    )
    lines.append("    IF section_count <> 16 THEN")
    lines.append(
        "        RAISE EXCEPTION 'homepage restore validation failed: expected 16 landing_sections rows, found %', section_count;"
    )
    lines.append("    END IF;")
    lines.append("")
    lines.append(
        "    SELECT COUNT(*) INTO item_count FROM cms_section_items WHERE section_id IN ("
    )
    lines.append(
        "        " + ", ".join(sql_str(v) for v in KNOWN_SECTION_IDS.values()) + ");"
    )
    lines.append(f"    IF item_count < {item_count} THEN")
    lines.append(
        f"        RAISE EXCEPTION 'homepage restore validation failed: expected at least {item_count} cms_section_items rows across recovered sections, found %', item_count;"
    )
    lines.append("    END IF;")
    lines.append(
        "    -- Uses >= rather than = : admins may legitimately add more items to"
    )
    lines.append(
        "    -- these sections after this restore runs once; re-running the script"
    )
    lines.append(
        "    -- later must not fail just because the count grew past the recovered"
    )
    lines.append("    -- baseline.")
    lines.append("")
    lines.append(
        "    RAISE NOTICE 'Homepage CMS restore validated: % landing_sections, % cms_section_items', section_count, item_count;"
    )
    lines.append("END $$;")
    lines.append("")
    lines.append("COMMIT;")
    lines.append("")

    OUT_SQL.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT_SQL} ({len(lines)} lines, {item_count} section_items)")


if __name__ == "__main__":
    main()

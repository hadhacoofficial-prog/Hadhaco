"""Generate Backend/supabase/recovery_sql/03_company_config.sql from the
recovered `company:config` cache (decoded to
`.../Json data/company_config.json`).

`company_config` is a singleton table (id fixed at 1, seeded once by
alembic/versions/0013_company_config.py). All 30 public fields returned by
GET /company/config (app/modules/company/router.py) are present in the
recovered cache and are restored verbatim via a single
INSERT ... ON CONFLICT (id) DO UPDATE. Fields the model has but the public
API response schema doesn't expose (e.g. `logo_r2_key`) are not present in
the cache and are left untouched (not overwritten) on conflict - see the
recovery report.
"""

from __future__ import annotations

import json
from pathlib import Path

CACHE_JSON = Path(
    r"F:\Work\Hadha.co\data\hadha-redis-recovery-20260725-191619\recovery-backup\Json data\company_config.json"
)
OUT_SQL = Path(
    r"F:\Work\Hadha.co\Project\Backend\supabase\recovery_sql\03_company_config.sql"
)

# Recovered field -> column (identical names for every field in this cache).
FIELDS = [
    "name", "legal_name", "brand_name", "tagline", "description", "website", "domain",
    "logo_url", "favicon_url", "packing_slip_logo_url", "shipping_label_logo_url",
    "phone", "alternate_phone", "whatsapp", "support_email", "sales_email",
    "address_line_1", "address_line_2", "city", "state", "postal_code", "country",
    "google_maps_url", "latitude", "longitude",
    "gstin", "cin", "business_hours",
    "instagram_url", "facebook_url", "youtube_url", "twitter_x_url", "linkedin_url",
    "pinterest_url",
    "default_meta_title", "default_meta_description", "organization_description",
    "theme_color",
]


def sql_value(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return repr(v)
    return "'" + str(v).replace("'", "''") + "'"


def main() -> None:
    doc = json.loads(CACHE_JSON.read_text(encoding="utf-8"))
    payload = doc["d"]
    cache_written_at = doc.get("t")
    data = payload["data"]

    missing = [f for f in FIELDS if f not in data]
    if missing:
        raise SystemExit(f"cache is missing expected fields: {missing}")

    lines: list[str] = []
    lines.append("-- ============================================================")
    lines.append("-- 03_company_config.sql")
    lines.append("-- Company config restoration, recovered from the Redis cache key")
    lines.append("-- `company:config` (decoded payload:")
    lines.append("-- recovery-backup/Json data/company_config.json).")
    lines.append(f"-- Cache write timestamp (epoch): {cache_written_at}")
    lines.append("--")
    lines.append("-- SCOPE: `company_config` table ONLY - a singleton row (id = 1,")
    lines.append("-- seeded once by alembic/versions/0013_company_config.py).")
    lines.append("--")
    lines.append(
        f"-- All {len(FIELDS)} fields the public GET /company/config endpoint returns are"
    )
    lines.append(
        "-- present in the cache and restored verbatim. Model-only fields the public"
    )
    lines.append(
        "-- API never serializes (e.g. logo_r2_key) are absent from the cache and are"
    )
    lines.append(
        "-- NOT included in this statement's SET clause, so an existing value (if any)"
    )
    lines.append("-- is left untouched rather than being wiped to NULL.")
    lines.append("--")
    lines.append("-- Idempotent: INSERT ... ON CONFLICT (id) DO UPDATE. No DELETE/TRUNCATE.")
    lines.append("-- ============================================================")
    lines.append("")
    lines.append("BEGIN;")
    lines.append("")
    lines.append("INSERT INTO company_config")
    lines.append("    (id, " + ", ".join(FIELDS) + ")")
    lines.append("VALUES")
    lines.append("    (1,")
    for i, f in enumerate(FIELDS):
        comma = "," if i < len(FIELDS) - 1 else ""
        lines.append(f"     {sql_value(data[f])}{comma}  -- {f}")
    lines.append("    )")
    lines.append("ON CONFLICT (id) DO UPDATE SET")
    for i, f in enumerate(FIELDS):
        comma = "," if i < len(FIELDS) - 1 else ""
        lines.append(f"    {f} = EXCLUDED.{f}{comma}")
    lines.append(";")
    lines.append("")
    lines.append("-- ── Validation ───────────────────────────────────────────────────────────")
    lines.append("DO $$")
    lines.append("DECLARE")
    lines.append("    cfg_name TEXT;")
    lines.append("BEGIN")
    lines.append("    SELECT name INTO cfg_name FROM company_config WHERE id = 1;")
    lines.append("    IF cfg_name IS NULL THEN")
    lines.append(
        "        RAISE EXCEPTION 'company_config restore validation failed: no row with id=1 after restore';"
    )
    lines.append("    END IF;")
    lines.append(
        f"    IF cfg_name <> {sql_value(data['name'])} THEN"
    )
    lines.append(
        f"        RAISE EXCEPTION 'company_config restore validation failed: expected name %, found %', {sql_value(data['name'])}, cfg_name;"
    )
    lines.append("    END IF;")
    lines.append(
        "    RAISE NOTICE 'company_config restore validated: name = %', cfg_name;"
    )
    lines.append("END $$;")
    lines.append("")
    lines.append("COMMIT;")
    lines.append("")

    OUT_SQL.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT_SQL} ({len(FIELDS)} fields)")


if __name__ == "__main__":
    main()

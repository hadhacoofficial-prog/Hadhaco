# Categories, Navigation, Company Config Recovery Report — Phase 3

Continuation of the homepage restoration ([`01_homepage_recovery.md`](01_homepage_recovery.md)). This phase covers everything explicitly excluded from Phase 2: **Categories, Navigation, Products, Collections, Company Config**.

Generated SQL:
- [`Backend/supabase/recovery_sql/02_categories.sql`](../recovery_sql/02_categories.sql) — from `generate_02_categories.py`
- [`Backend/supabase/recovery_sql/03_company_config.sql`](../recovery_sql/03_company_config.sql) — from `generate_03_company_config.py`

No SQL was generated for Products or Collections — see Section 4.

---

## 1. Tables discovered

| Table | Model | Role |
|---|---|---|
| `categories` | `app/modules/categories/models.py:11` | Self-referencing tree (`parent_id -> categories.id`), backs `/categories`, `/categories/navbar`, `/categories/navigation`. |
| `images` / `image_variants` | `app/modules/media/models.py` | Polymorphic (`owner_type`/`owner_id`) image storage shared across every module. Referenced by categories for `image_url`, but not restorable here (see Section 3). |
| `company_config` | `app/modules/company/models.py:9` | Singleton row (`id` fixed at 1), backs `/company/config`. |
| `products` | `app/modules/catalog/models.py:28` | Not touched — cache was empty (Section 4). |
| `collections` | `app/modules/collections/models.py:11` | Not touched — cache was empty (Section 4). |

---

## 2. Redis → DB mapping: `categories`

Source: `categories:tree:v1:all` (decoded to `categories_tree.json`) — the recovered top-level array plus nested `children`, produced by `CategoryService.get_tree()` → `_build_tree()` (`app/modules/categories/service.py:42-45, 266-285`), itself backed by `CategoryRepository.list_all_active(db)` — i.e. **only active, non-deleted categories** were ever in this cache.

Cross-verified against the other two category caches decoded in Phase 1:
- `categories:navbar:v1` (`categories_navbar.json`) — same 24 categories, grouped by gender bucket (women/men/unisex/kids), each entry carrying the same `id`/`name`/`slug`/`sort_order`/`image_url` as the tree cache's matching node. Confirmed by direct comparison: every id in the navbar cache appears in the tree cache with identical field values.
- `navigation:categories:v2` (`navigation_categories.json`) — same data again, plus a `gender_meta` map whose 4 entries (`women`/`men`/`unisex`/`kids`) have ids `2bde3046-...`, `020c8125-...`, `8f6fce03-...`, `1de28621-...` — these are exactly the 4 top-level (`parent_id: null`) nodes in the tree cache. This confirms all three caches are different read-time *projections* of the same 24 `categories` rows, not three separate datasets — restoring from `categories_tree.json` alone fully covers all three.

| Redis field | Column | Notes |
|---|---|---|
| `id` | `id` (PK) | **Real recovered UUID for every one of the 24 rows** — unlike the homepage phase, category ids are never hidden behind an indirection; they appear directly in the cache. `ON CONFLICT (id) DO UPDATE` is used throughout — the correct, non-fabricated upsert target. |
| `parent_id` | `parent_id` (self-FK, `ON DELETE RESTRICT`) | Preserved exactly; `NULL` for the 4 top-level gender categories. |
| `name` | `name` | Preserved exactly (including the recovered typo "Eliphant Ring" and inconsistent casing "ear studs" vs "Rings" — not corrected, per "never alter recovered data"). |
| `slug` | `slug` (UNIQUE) | Preserved exactly. |
| `sort_order` | `sort_order` | Preserved exactly. |
| *(implied by cache source)* | `is_active` | Set to `TRUE` for every row — a recovered fact, not a guess: `list_all_active()` only ever returns active rows, so every category present in this cache is, by construction, active. |
| `image_url` | *(no such column)* | **Not restored** — see Section 3. |
| *(not cached)* | `product_count` | Not a column at all — computed live per-request via `CategoryRepository.get_product_count()`. Nothing to restore. |
| *(not cached)* | `description`, `seo_title`, `seo_description`, `primary_image_id` | None of these are exposed by any of the 3 cached endpoints (they're admin-only fields). Left unset (`NULL`/column default). **Unresolved** — flagged, not guessed. |
| *(not cached)* | `created_at`, `updated_at` | No timestamp survives at the category level in any of the three caches. Set to `NOW()` at restore time; `created_at` is not overwritten on conflict (only set on first insert). |

**Row count recovered: 24** (4 top-level gender categories + 10 women + 4 men + 4 unisex + 2 kids subcategories).

**Insertion order**: the script performs a pre-order traversal of the recovered tree so every parent row is inserted before its children — required because `categories.parent_id` is a same-table foreign key checked immediately (not deferred).

---

## 3. Unresolved: category `image_url` / the `images` table

`CategoryService._image_urls()` (`app/modules/categories/service.py:106-119`) resolves each category's `image_url` at **read time**, not from a column on `categories` — it's a polymorphic join: `ImageRepository.get_primary_variant_urls(db, "category", category_ids)` against the shared `images` (`app/modules/media/models.py:21`) and `image_variants` (`:91`) tables, keyed by `owner_type='category'`, `owner_id=<category.id>`.

Both tables have multiple `NOT NULL` columns with **no corresponding data anywhere in the recovered cache**:

- `images`: `original_key`, `original_ext`, `original_width`, `original_height`, `original_size_bytes`, `mime_type`, `module`, `preset_id` — none of these survive; only the final CDN URL string does.
- `image_variants`: `width`, `height`, `size_bytes`, `format`, `breakpoint`, `variant_name`, `dpr`, `url` — same problem; the cache has one resolved URL per category, not a breakdown per breakpoint/variant/dpr.

Per the "never fabricate data" rule, **no rows were inserted into `images` or `image_variants` in this phase**. This means: after running `02_categories.sql`, every category will exist with correct name/slug/hierarchy/ordering, but the storefront's category images will not render until the images are either re-uploaded through the admin Media Library or a separate, explicitly-authorized backfill decides what (if anything) can be safely inferred about the file metadata from the CDN URL path itself (e.g. the filename suggests `desktop/large@1x.webp`, which hints at `breakpoint='desktop'`, `variant_name='large'`, `dpr=1`, `format='webp'` — but `width`/`height`/`size_bytes` genuinely cannot be inferred from a URL and are NOT NULL, so even a partial restore isn't possible without either fetching the live image over HTTP to measure it, or leaving it out entirely as done here). This mirrors exactly how `cms_media` was left unresolved in the homepage phase.

The 24 recovered CDN URLs (for reference, not for insertion) are preserved verbatim in `categories_tree.json`/`categories_navbar.json`/`navigation_categories.json` from Phase 1, so they are not lost — they're simply not written to the DB by this phase's SQL.

---

## 4. Products and Collections: nothing to restore

Both recovered caches were checked and are genuinely empty at capture time — not truncated, not corrupted:

- `products:list:v1:bb7272dca763` → `{"items": [], "total": 0, "page": 1, "page_size": 24, "total_pages": 0}`
- `collections:list:v1` → `[]`

The `products` table (`app/modules/catalog/models.py:28`) has numerous `NOT NULL` columns (`sku`, `name`, `slug`, `base_price`, ...) and `collections` (`app/modules/collections/models.py:11`) has its own required fields — with zero cached rows to source values from, generating any INSERT would mean inventing every single field. **No SQL was generated for either table.** This is not a gap in this recovery effort; it reflects what was actually in Redis at capture time. If products/collections data needs to be restored, it must come from a different source (a database backup, not this Redis cache) — flagged here rather than silently worked around.

---

## 5. Redis → DB mapping: `company_config`

Source: `company:config` (decoded to `company_config.json`), produced by the company config service backing `GET /company/config` (`app/modules/company/router.py`). Singleton row, `id` fixed at `1` (seeded once by `alembic/versions/0013_company_config.py`).

All **38** fields the public endpoint returns are present in the cache and restored verbatim (`name`, `tagline`, `phone`, `whatsapp`, `support_email`, `city`, `state`, `postal_code`, `country`, `gstin`, plus 28 further fields that are legitimately `NULL` in the cache — e.g. `legal_name`, `description`, `logo_url`, all social-media URLs except none set, `latitude`/`longitude`, SEO defaults). Every `NULL` here is a recovered fact (the config genuinely has no value set for that field), not a gap.

One model column, `logo_r2_key` (`app/modules/company/models.py:27`), is never serialized by the public API response and therefore never appears in this cache. It is **excluded from the `ON CONFLICT ... SET` clause** (not merely set to NULL) so that if a value already exists in the live DB, this restore does not silently wipe it — a deliberate "don't touch what we can't verify" choice.

---

## 6. Validation

- ✔ Categories: 24/24 recovered rows present after restore (in-SQL `DO $$` block raises if not).
- ✔ Cross-checked all 24 ids/names/slugs/sort_orders against 2 independent cache projections (navbar, navigation) — all three agree exactly.
- ✔ Parent/child relationships preserved: every subcategory's `parent_id` matches one of the 4 recovered top-level ids.
- ✔ `company_config`: single row present with `id=1`, `name` matches recovered value (in-SQL validation).
- ✔ Static structural checks: `INSERT INTO categories` appears 24 times; `DO $$...$$` balanced in both scripts; both wrapped in `BEGIN;`/`COMMIT;`; no `DELETE`/`TRUNCATE`/`DROP` anywhere.
- ⚠️ **Not performed: live execution against a real Postgres/Supabase instance** — same limitation as Phase 2 (no local Postgres available: Docker Desktop's engine was not running, `psql` not installed). Recommend a staging dry run before production, in the order `01_homepage.sql` → `02_categories.sql` → `03_company_config.sql` (no cross-dependencies between the three, but this preserves a clean audit trail matching the phase numbering).
- N/A Products/Collections: nothing generated, nothing to validate (Section 4).

---

## 7. Confidence levels

| Dataset | Confidence | Basis |
|---|---|---|
| `categories` (24 rows: id/parent_id/name/slug/sort_order/is_active) | **High** | Real UUIDs for every row, cross-verified against 2 independent cache projections, exact field-for-field agreement. |
| `categories.image_url` / `images` / `image_variants` | **Unresolved — not attempted** | Required NOT NULL fields for both tables have zero recoverable data in any cache; restoring would require fabrication. Correctly left out. |
| `company_config` (38 fields) | **High** | Singleton row, all public-API fields present and internally consistent (e.g. `country: "IN"` matches `postal_code`/`state`/`city` all being Indian values). |
| `company_config.logo_r2_key` | **Unresolved** | Not exposed by the cached endpoint; deliberately excluded from the upsert's SET clause rather than guessed or nulled. |
| Products / Collections | **N/A — no data existed to recover** | Cache was empty at capture time; not a recovery failure, a fact about what was cached. |
| Overall SQL correctness | **High** (structural/static) / **Untested** (live execution) | Same caveat as Phase 2 — no local Postgres available to execute against. |

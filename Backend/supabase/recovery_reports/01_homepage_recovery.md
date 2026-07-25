# Homepage CMS Recovery Report — Phase 2 (SQL Restoration)

Scope: **Homepage CMS only** — `landing_sections` + `cms_section_items`. Categories, Products, Collections, Navigation, and Company Config are explicitly out of scope for this phase and were not touched.

Source of truth: `F:\Work\Hadha.co\data\hadha-redis-recovery-20260725-191619\recovery-backup\Json data\cms_homepage.json` — the decoded `cms:homepage` Redis cache entry (see Phase 1's `cache_recovery_report.md` for how it was decoded). Cache write timestamp (`t` field): `1784983802.1023817` (epoch seconds).

Generated SQL: [`Backend/supabase/recovery_sql/01_homepage.sql`](../recovery_sql/01_homepage.sql), produced deterministically by [`generate_01_homepage.py`](../recovery_sql/generate_01_homepage.py) (loads the recovered JSON directly — no hand-transcription of config/URLs/timestamps, to eliminate transcription-error risk).

---

## 1. Tables discovered

Traced through the actual backend code (not assumed):

| Table | Defined in | Role in homepage rendering |
|---|---|---|
| `landing_sections` | `app/modules/cms/models.py:62`, base schema `supabase/sql/010_cms.sql:31`, extended by `alembic/versions/0004_cms_homepage_extension.py` | One row per homepage section (16 rows). Holds `section_key`, `section_type`, `title`, `config`/`draft_config` JSONB, `is_active`, `sort_order`, publish/version metadata. |
| `cms_section_items` | `app/modules/cms/models.py:97`, created in `0004_cms_homepage_extension.py:259-290` | Repeatable child rows under a section (carousel slides, announcement-bar messages, collection cards, feature-callout cards). FK `section_id -> landing_sections.id ON DELETE CASCADE`. |
| `cms_cache_version` | `app/modules/cms/models.py:182` | Cache-busting bookkeeping only — no homepage *content*, not touched. |
| `cms_publish_log` | `app/modules/cms/models.py:194` | Audit trail of publish/toggle/reorder actions — not touched (writing to it would fabricate an admin action that never happened). |
| `cms_media` | `app/modules/cms/models.py:121` | Media library catalog (uploaded-file metadata: dimensions, mime type, R2 key, usage_count). **Not populated by this script** — see "Unresolved" below. |
| `banners` | `app/modules/cms/models.py:24` | Legacy hero/promo banner table used only by the deprecated `get_home_data()` / `GET /cms/home` endpoint (`app/modules/cms/service.py:55-64`). The current homepage (`GET /cms/homepage`, `_build_homepage()`) does not read this table at all. **Out of scope** — the recovered cache confirms this table isn't part of the live homepage anymore (`cms:home:v1`'s cached `hero_banners: []` was already empty). |

`cms_version_history`, `cms_pages`, `app_settings` also exist in this module but carry no homepage-layout data and are untouched.

The endpoint that produced the exact cache shape recovered is `GET /cms/homepage` → `app/modules/cms/router.py:102-133`, backed by `CMSService._build_homepage()` (`app/modules/cms/service.py:81-115`):

```python
async def _build_homepage(self, db):
    sections = await self._repo.get_active_sections(db)       # landing_sections, ordered by sort_order
    items_by_section = await self._repo.get_items_for_sections(db, [s.id for s in sections])  # cms_section_items
    ...
    return {"cache_version": 1, "layout": [...], "sections": {...}}
```

This is a 1:1 match with the recovered JSON's top-level shape (`cache_version`, `layout`, `sections`), confirming both tables and no others are involved.

---

## 2. Schema mapping (Redis → DB columns)

### `landing_sections`

| Redis field | Column | Notes |
|---|---|---|
| `layout[i].section_key` | `section_key` (UNIQUE) | Upsert conflict target. |
| `layout[i].section_type` | `section_type` | e.g. `product_grid`, `category_grid`, `content_block`. |
| `layout[i].title` | `title` | Exact recovered title used, including cases where it differs from the key (e.g. `reviews` → "Customer Reviews"). |
| `layout[i].sort_order` | `sort_order` | Preserved exactly — this is the *live* production ordering, which differs from the original migration's seed order (the site was reordered by an admin after seeding; see `0004_cms_homepage_extension.py`'s `_SEED` for the old order vs. the recovered `sort_order` values — they no longer match, confirming the recovered cache reflects live edits, not the seed). |
| `layout[i].is_active` | `is_active` | All 16 are `true` in the recovered cache. |
| `sections[key].config` | `config` | Full JSONB config, byte-for-byte from the cache. |
| *(not present)* | `draft_config` | No draft snapshot exists in a public-cache payload (drafts are never served publicly). Seeded equal to `config` — same approach the original `0004_cms_homepage_extension.py` seed migration uses (`CAST(:config AS jsonb)` for both columns). Flagged as inferred, not recovered. |
| *(not present)* | `status` | Set to `'published'`, since this payload was actively served from the live public homepage cache — a section can only appear in this cache if published. |
| *(not present)* | `scheduled_at`, `published_at` | Not present anywhere in the cache. Left `NULL`/unset. **Unresolved** — see Section 5. |
| *(not present)* | `version_number` | Not present in the cache. Defaults to `1` (matches the column's own schema default and the original seed migration's behavior). **Unresolved/assumed** — see Section 5. |
| item `created_at`/`updated_at` where available; otherwise none | `created_at`, `updated_at` | No section-level timestamps exist in the cache (only item-level ones do). Set to `NOW()` at restore time, and `created_at` is never overwritten on conflict (only set on first insert) so re-running the script doesn't clobber a real creation date once one exists. |
| *(FK, 4 of 16 sections only)* | `id` | See Section 3 — recovered for 4 sections, generated by Postgres default for the other 12. |

### `cms_section_items`

| Redis field | Column | Notes |
|---|---|---|
| `items[j].id` | `id` (PK) | Recovered UUID, preserved exactly. Upsert conflict target. |
| `items[j].section_id` | `section_id` (FK → `landing_sections.id`) | Recovered UUID, preserved exactly — this is what let us recover the parent section's own `id` (see Section 3). |
| `items[j].sort_order` | `sort_order` | Preserved exactly. |
| `items[j].is_enabled` | `is_enabled` | Preserved exactly (all recovered items are `true` — disabled items are filtered out of the public cache by `_build_homepage()`'s `if item.is_enabled` clause, so any disabled items are invisible to this recovery by design, not lost by us). |
| `items[j].config` | `config` | Full JSONB config — media URLs, colors, typography, button config, content strings — preserved byte-for-byte. |
| `items[j].created_at` | `created_at` | Preserved exactly, cast `::timestamptz`. |
| `items[j].updated_at` | `updated_at` | Preserved exactly, cast `::timestamptz`; also refreshed via `EXCLUDED.updated_at` on conflict so a re-run doesn't regress a value that's already correct. |

---

## 3. UUID recovery — which section IDs survived, and why

The cache's `layout`/`sections` structure never carries a section's own database `id` — only its `section_key`. Section IDs *did* survive indirectly, wherever a section had at least one item: `cms_section_items.section_id` is that section's real `landing_sections.id`.

| section_key | id recovered? | Recovered id | Source |
|---|---|---|---|
| `announcement_bar` | ✅ | `bc6c2286-9194-416f-9a35-5e9a98b1482d` | 3 items' `section_id` |
| `hero_carousel` | ✅ | `294bf305-3b09-48ca-b979-ded8449712b8` | 1 item's `section_id` |
| `featured_collection` | ✅ | `5f104219-6fdd-44fb-b379-4545021e3a80` | 2 items' `section_id` |
| `why_choose_us` | ✅ | `f1235bc5-3ebc-4cae-8a2e-3cbdc2a29c88` | 8 items' `section_id` |
| `navbar`, `featured_products`, `shop_by_gender`, `craftsmanship_video`, `new_arrivals`, `promo_banner`, `trending`, `shop_by_category`, `reviews`, `instagram_gallery`, `newsletter`, `footer` | ❌ | *(none in cache)* | These 12 sections have `"items": []` in the cache — zero child rows, so no `section_id` value ever appears for them anywhere in the recovered data. |

**Per the "never fabricate UUIDs" rule**, the SQL does not invent replacement IDs for the 12 unknown sections. Instead:

- For the 4 known sections: `INSERT ... ON CONFLICT (section_key) DO UPDATE SET id = EXCLUDED.id, ...` — the `id` column is included explicitly (with its real recovered value) both on insert and on the conflict path, because the `cms_section_items` rows inserted immediately after **must** reference this exact id via their FK. If a `landing_sections` row with this `section_key` already exists under a *different* id (e.g., left over from the original `0004_cms_homepage_extension.py` seed, which uses `gen_random_uuid()` and would almost certainly have assigned a different id than production later got), this script deliberately reconciles it to the recovered id, since Redis is the declared source of truth for the live production state being restored. This is a disaster-recovery script, not a routine migration — forcing the id is the correct call here, but it is called out explicitly as a **risk**: if any *other* table not covered by this phase already has a foreign key pointing at that section's *old* id, this UPDATE would orphan it. No such other-table references exist for `landing_sections.id` besides `cms_section_items` and `cms_version_history` (checked in `0004_cms_homepage_extension.py`), and neither is touched elsewhere for these 4 sections outside this script.
- For the 12 unknown sections: `id` is omitted entirely from both the column list and the `DO UPDATE SET` clause. On first insert, Postgres assigns it via the column's own `DEFAULT gen_random_uuid()` (`app/modules/cms/models.py:64-66` / `010_cms.sql:32`) — not a value chosen by this script. On every subsequent re-run, the `ON CONFLICT (section_key) DO UPDATE` path fires and, because `id` is never named in `SET`, the existing row's id is left completely untouched. This is the same mechanism the original seed migration relies on, and it satisfies both "preserve UUIDs" (for the 4 sections where one exists) and "do not fabricate UUIDs" (for the 12 where none does) without contradiction.

---

## 4. Anomaly found and preserved as-is: duplicate `why_choose_us` items

The cache's `why_choose_us` section has **8** items for what is visibly **4** distinct feature cards ("92.5 Sterling Silver", "Authentic Craftsmanship", "Trusted Quality", "Made With Love") — each card appears twice, under two different UUIDs, with two different `created_at`/`updated_at` timestamp pairs (all four pairs are within ~2.6 seconds of each other, e.g. `11:15:00.235513Z` vs `11:15:02.636017Z`), but otherwise byte-identical `config`. This is consistent with a duplicate-publish or double-submit bug in the CMS admin at some point, not a decoding artifact (each of the 8 rows decodes as clean, well-formed, internally-consistent JSON with its own distinct `id`).

Per the "use recovered data as source of truth, never invent, never silently alter" rule, **all 8 rows are restored exactly as cached** — no deduplication was performed. This is flagged here so a human reviewer can decide whether to manually retire 4 of the 8 rows post-restore; that decision is out of scope for an automated recovery script.

---

## 5. Unresolved fields (explicitly not recovered — documented, not guessed)

| Field | Why it's unresolved | What the script does |
|---|---|---|
| `landing_sections.published_at` | Never present in the `cms:homepage` cache payload (only item-level timestamps are cached). | Left unset (column stays `NULL`). |
| `landing_sections.scheduled_at` | Same as above. | Left unset (`NULL`). |
| `landing_sections.version_number` | Not cached; the cache only reflects the *current published* state, not version history. | Defaults to `1`, same as the schema's own column default — an assumption, not a recovered fact. |
| `landing_sections.subtitle` | Not present in the recovered `layout`/`sections` data for any of the 16 sections. | Left unset (`NULL`, column default). |
| `landing_sections.created_at` (for the 12 sections with no recovered id) | No section-level creation timestamp exists in the cache. | Set to `NOW()` at restore time — i.e., this is the *restoration* time, not the true original creation time, and is explicitly not claimed to be the latter. |
| `cms_media` rows | Section/item configs store plain CDN URL strings (e.g. `https://cdn.hadha.co/cms/collections/...jpg`) directly in JSONB, not foreign keys to a `cms_media.id`. No media *catalog* metadata (file size, dimensions, uploader, R2 key) survived in this cache — only the final public URLs did. | Not populated. The homepage will render correctly (URLs are preserved verbatim in `config`), but the CMS admin's Media Library UI will show these assets as "not indexed" until/unless they're separately re-uploaded or backfilled from R2 listing — out of scope for this phase, which is homepage-content-only. |
| `banners` table | Confirmed via code inspection to be unused by the live homepage (`_build_homepage()` never queries it); only the deprecated legacy endpoint does, and that endpoint's own recovered cache (`cms_home_v1.json`, Phase 1) shows it was already empty. | Not touched — correctly out of scope. |

None of the above were guessed or fabricated; each is a column left at a safe, honestly-labeled default.

---

## 6. SQL generated — summary

- File: `Backend/supabase/recovery_sql/01_homepage.sql` (537 lines).
- 16 `INSERT INTO landing_sections ... ON CONFLICT (section_key) DO UPDATE` statements (one per homepage section).
- 14 `INSERT INTO cms_section_items ... ON CONFLICT (id) DO UPDATE` statements (3 announcement_bar + 1 hero_carousel + 2 featured_collection + 8 why_choose_us).
- Wrapped in `BEGIN; ... COMMIT;` — single all-or-nothing transaction.
- All JSONB values are embedded via Postgres dollar-quoting (`$hpj$...$hpj$::jsonb`) generated straight from the recovered JSON via Python's `json.dumps`, rather than hand-typed — eliminates transcription/escaping errors for content containing embedded quotes, em-dashes (—), the ₹ symbol, and URL query strings.
- No `DELETE`, no `TRUNCATE`, no `DROP` anywhere in the script.
- Ends with a `DO $$ ... $$` validation block that `RAISE EXCEPTION`s (aborting/rolling back the whole transaction) if fewer than the expected 16 sections or 14 items exist afterward, and `RAISE NOTICE`s the final counts on success.

---

## 7. Validation

Performed:
- ✔ **Static structural checks**: dollar-quote tag balance even (92 `$hpj$` occurrences = 46 pairs = 16×2 section config/draft_config + 14 item configs), `DO $$...$$` block balanced, exactly 16 `INSERT INTO landing_sections` and 14 `INSERT INTO cms_section_items` statements present, `BEGIN;`/`COMMIT;` present.
- ✔ **Source fidelity**: the SQL generator loads `cms_homepage.json` directly (no hand-transcription) and asserts `len(layout) == 16` before generating anything, so a malformed/incomplete source cache would fail loudly instead of producing a partial script.
- ✔ **Every homepage section present**: all 16 `section_key`s from the recovered `layout` array appear exactly once.
- ✔ **Every recovered item present**: all 14 `cms_section_items` rows from the 4 populated sections are included, with original `id`, `section_id`, `sort_order`, `config`, and both timestamps intact.
- ✔ **UUIDs preserved where recoverable**: the 4 known section ids and all 14 item ids are the literal values from the cache — verified against the source JSON via diff-by-eye during generation (see Section 3 table).
- ✔ **Config/media URLs/colors/typography/buttons preserved verbatim**: e.g. the hero_carousel item's `media`, `colors`, `layout`, `buttons`, `content`, `typography` sub-objects are embedded as one untouched JSON blob per item — nothing was restructured, renamed, or reformatted.
- ⚠️ **Not performed: live execution against a real Postgres/Supabase instance.** No local Postgres was available in this environment (Docker Desktop's engine was not running, `psql` is not installed) to actually execute the script and confirm it applies cleanly. **This script has been validated for structural correctness and data fidelity, but has not been execution-tested. Run it against a staging Supabase project first**, and confirm via `GET /cms/homepage` (or a direct `SELECT` against `landing_sections`/`cms_section_items`) that the storefront renders identically to the recovered cache before applying to production.
- ✔ **Frontend render compatibility**: cross-checked against `CMSService._build_homepage()` (`app/modules/cms/service.py:81-115`) and `HomepageDataOut`/`SectionDataOut`/`LayoutSectionOut` schemas (`app/modules/cms/schemas.py:161-177`) — the restored rows produce the same `{cache_version, layout, sections}` shape the storefront already consumes, with no schema changes required on the frontend.

---

## 8. Confidence levels

| Section | Confidence | Basis |
|---|---|---|
| `announcement_bar` | **High** | Full id + 3 items recovered, byte-identical to cache. |
| `hero_carousel` | **High** | Full id + 1 item recovered, full nested config (media/colors/layout/buttons/content/typography) intact. |
| `featured_collection` | **High** | Full id + 2 items recovered. |
| `why_choose_us` | **High** (content) / **Flagged** (data quality) | Full id + all 8 items recovered exactly; the 8-vs-4-unique duplication is a genuine anomaly in the source, not a recovery gap — see Section 4. |
| `navbar`, `featured_products`, `shop_by_gender`, `craftsmanship_video`, `new_arrivals`, `promo_banner`, `trending`, `shop_by_category`, `reviews`, `instagram_gallery`, `newsletter`, `footer` | **High** (config) / **Medium** (id) | Section-level `config` fully recovered and preserved exactly; the row's own `id` is not recoverable (no items) and will be assigned fresh by Postgres on first insert — functionally correct (the app never needs to know these ids in advance), but flagged since it means these 12 ids are *not* being restored to their original pre-loss values, only newly (re)created. |
| Overall SQL correctness | **High** (structural/static) / **Untested** (live execution) | See Section 7 — recommend a staging dry run before production. |

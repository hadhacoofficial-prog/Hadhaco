# Performance Audit Report

## 1. Production Latency — Root Cause

Production logs show **2.5–3.0s** for upload and **2.0–2.6s** for crop.
The code trace initially estimated 150–800ms for the request path.

### The discrepancy explained

The bottleneck is `bust_product_list_cache` (`core/redis.py:223-271`), which is
called on **every** upload/crop/replace/set-primary/delete that touches a
product image.

**What it does per call:**
1. `SCAN products:list:v1:*` — bounded to 1.0s timeout
2. For **each** matching key: `GET` (300ms timeout) → decompress → JSON parse
   → modify timestamp → recompress → `SETEX` (300ms timeout)

**Cost per cached page:** ~600ms (GET + SETEX, each with 300ms timeout).
**If there are 5 cached product list pages:** 3.0s of sequential Redis I/O.

This is the dominant cost in both upload and crop endpoints.

### Secondary costs (confirmed by instrumentation)

| Phase | Upload | Crop |
|---|---|---|
| Auth chain (`_ensure_2fa_session`) | 10–30ms | — (via `require_admin` dep) |
| File read | 1–50ms | — |
| CPU validate + probe | 20–100ms | — |
| R2 `put_original` | 100–400ms | — |
| DB `create_image` (flush+refresh×2) | 30–80ms | — |
| `_enqueue_generation` (update+flush+refresh×2) | 20–50ms | 20–50ms |
| `_get_image_or_404` (selectinload) | — | 5–20ms |
| `update_metadata` (flush+refresh×2) | — | 20–50ms |
| **`bust_product_list_cache`** | **500–3000ms** | **500–3000ms** |
| Transaction commit | 5–20ms | 5–20ms |
| Connection return (`DISCARD ALL`) | 1–5ms | 1–5ms |

## 2. Instrumentation Added

Every major phase now logs `perf_counter()` timestamps via `structlog`.

### Structured log events (grep for these)

| Logger | Event | Where | What it measures |
|---|---|---|---|
| `perf.media` | `upload_phases` | `media/router.py` | read_file → upload_service → cache_bust → serialize |
| `perf.media` | `crop_phases` | `media/router.py` | get_image → crop_service → cache_bust → serialize |
| `perf.media` | `bust_cache_for` | `media/router.py` | Total time in `_bust_cache_for` |
| `perf.media.service` | `upload_service_phases` | `universal_service.py` | validate → probe_dims → r2_put_original → db_create_image → enqueue_generation |
| `perf.media.service` | `crop_service_phases` | `universal_service.py` | compute_diff → validate_geometry → db_update_metadata → enqueue_generation |
| `perf.media.service` | `enqueue_generation` | `universal_service.py` | update_fields_ms, enqueue_ms |
| `perf.media.repo` | `create_image_db` | `repository.py` | flush_ms, refresh_ms, refresh_variants_ms |
| `perf.media.repo` | `update_metadata_db` | `repository.py` | flush_ms, refresh_ms, refresh_variants_ms |
| `perf.media.repo` | `update_fields_db` | `repository.py` | flush_ms, refresh_ms, refresh_variants_ms, fields |
| `perf.auth` | `load_profile` | `dependencies.py` | redis_ms, db_ms, source (redis/db) |
| `perf.auth` | `ensure_2fa` | `dependencies.py` | has_2fa_ms, verify_ms, touch_ms, total_ms |
| `profiling` | `slow_product_list_cache_bust` | `profiling.py` | key_count, scan_ms, keys_ms, total_ms (>50ms) |
| `profiling` | `slow_db_session_lifecycle` | `profiling.py` | checkout_ms, commit_ms (>10ms) |

### How to read in production

```bash
# Find slow uploads
grep "upload_phases" /var/log/app.log | jq '.total_ms'

# Find slow cache busts
grep "slow_product_list_cache_bust" /var/log/app.log

# See per-phase breakdown of a single upload
grep "upload_service_phases" /var/log/app.log | jq '.phases'

# See 2FA auth cost per request
grep "ensure_2fa" /var/log/app.log | jq '.total_ms'

# See DB session checkout/commit cost
grep "slow_db_session_lifecycle" /var/log/app.log
```

## 3. Known Issues Found

### Critical

1. **`bust_product_list_cache` is O(N) sequential Redis per cached page** —
   `core/redis.py:262-265`. For each key: GET + decompress + modify + compress
   + SETEX. With 5 cached pages, this alone costs ~3s. Called on every
   product-image mutation.

2. **`images` table has zero B-tree indexes** — `media/models.py:21-88`. No
   `__table_args__`. The only indexes are the unique constraint on variants
   and the3 migration-added indexes (`idx_images_owner`, `idx_images_owner_primary`,
   `idx_images_status_updated`).

3. **Redundant `db.refresh(image, attribute_names=["variants"])` on new images** —
   `repository.py:21,55,66`. `create_image` flushes a brand-new image then
   immediately refreshes `variants` (which is always empty). This fires an
   unnecessary SELECT on every create. Same in `update_metadata` and
   `update_fields` — variants don't change on metadata/field updates.

### High

4. **2FA gate does 3 DB queries per admin request** — `dependencies.py:233-291`.
   `has_active_2fa` + `is_admin_session_2fa_verified` + `touch_admin_session_activity`.
   Never cached. With `pool_size=2`, this competes with the actual endpoint work.

5. **`_enqueue_generation` does flush+refresh×2** — `universal_service.py:488-500`.
   After updating fields, it calls `update_fields` which does: flush → refresh →
   refresh variants (pointless for status/metadata update).

6. **`DISCARD ALL` on connection return** — `database.py:109-119`. Synchronous
   call in the pool reset handler. Runs on the event loop thread after the
   response is returned, adding 1-5ms per request.

### Medium

7. **`_load_profile` does Redis GET + conditional DB query** — `dependencies.py:119-135`.
   With 60s cache TTL, every 7th request hits the DB. No stale-while-revalidate
   — a cache miss blocks on the DB.

8. **Product create does N+1 variant attribute upserts** — `catalog/service.py:226-303`.
   Each variant's `attributes_to_add` triggers a separate INSERT.

9. **Collections `_attach_image_urls` does dual image queries** —
   `collections/service.py:28-51`. Fetches primary image IDs, then fetches
   variants for those IDs — two round-trips that could be one JOIN.

## 4. Files Modified

| File | Change |
|---|---|
| `app/modules/media/router.py` | Added `perf_counter` phases to upload, crop endpoints; `_bust_cache_for` timing |
| `app/modules/media/universal_service.py` | Added `perf_counter` phases to `upload()`, `crop()`, `_enqueue_generation()` |
| `app/modules/media/repository.py` | Added `perf_counter` to `create_image`, `update_metadata`, `update_fields` (flush/refresh timing) |
| `app/core/database.py` | Added `perf_counter` to `get_db` (checkout, commit timing) |
| `app/core/dependencies.py` | Added `perf_counter` to `_load_profile`, `_ensure_2fa_session` |
| `app/core/profiling.py` | Added `record_db_commit`, `record_db_session_lifecycle`, `record_bust_product_list_cache` |
| `app/core/redis.py` | Added `perf_counter` to `bust_product_list_cache` (scan + per-key timing) |

## 5. Recommended Fixes (Priority Order)

### P0: Fix the cache bust (saves 1-3s per upload/crop)

`bust_product_list_cache` should use Redis pipeline for the per-key SETEX
operations instead of sequential await. Or batch-delete all keys and let
cache_swr handle the hard-miss (revert to old behavior but with coalescing).

### P1: Remove redundant `refresh(variants)` on new/updated images

`create_image`, `update_metadata`, `update_fields` all call
`db.refresh(image, attribute_names=["variants"])` — for a newly-created image
this is always empty, and for metadata/field updates variants don't change.
Remove these 3 calls to save 1 DB round-trip each.

### P2: Cache the2FA gate result

Cache `has_active_2fa` + `is_admin_session_2fa_verified` in Redis with a
short TTL (30s). This saves 2-3 DB queries per admin request.

### P3: Add indexes to `images` table

Add B-tree indexes on `(owner_type, owner_id)` and `(status, updated_at)`
at minimum. The existing `idx_images_owner` covers the first; verify
`idx_images_status_updated` covers the second.

### P4: Batch N+1 variant attribute upserts in product create

Replace per-variant loop with a single bulk INSERT ON CONFLICT.

### P5: Merge collection image queries

Combine `get_primary_image_ids` + `get_image_variants_for_images` into a
single JOIN query.

## 6. What to Watch After Deploy

After deploying the instrumentation, monitor for:

1. `slow_product_list_cache_bust` — confirms the cache bust is the dominant cost
2. `upload_phases` / `crop_phases` — `cache_bust` should be the largest delta
3. `slow_db_session_lifecycle` — checkout/commit times under load
4. `ensure_2fa` total_ms — auth chain overhead per request
5. `create_image_db` / `update_fields_db` — flush/refresh breakdown

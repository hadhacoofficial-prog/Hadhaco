# PERFORMANCE OPTIMIZATION FINAL REPORT

**Date:** 2026-08-12
**Baseline commit (BEFORE):** `a91cac0` (HEAD)
**Optimization state (AFTER):** staged-but-uncommitted changes on top of `a91cac0`
**Status:** FINAL VALIDATION COMPLETE — all quality gates green, live k6 probe executed against production, changes **staged but uncommitted**. Production-readiness decision: see §14.8.

---

## 1. Executive summary

The P0/P1/P2/P3 performance optimization plan was implemented and validated against a real
BEFORE/AFTER measurement harness plus the full test/lint/type gate suite.

**What was measured (not estimated):**
- Read-only requests now skip the DB `COMMIT` (P1-1): **1 commit/request → 0**.
- The admin 2FA gate collapsed from 2 DB round-trips to 1 (P1-2).
- Product-list image hydration dropped the dedicated image-variants query (P2-1a).
- Admin collections list dropped a separate COUNT query via window function (P2-1c).
- Variant update uses `UPDATE … RETURNING` — **2 executes + 1 re-read → 1 execute** (P2-1b).
- Product-list cache bust moved off the media request path (P0-1): **0 Redis ops at response time**, bust + rewarm run fire-and-forget.
- `DISCARD ALL` on every connection return removed (P0-2): **1 statement/return → 0**.

**What was verified by tests, not by wall-clock timing:**
- `cache_swr` semantics (fresh / stale / background refresh / coalescing / ETag / Redis-failure / refresh-failure) — verified from code + unit tests; mechanism unchanged by this diff (it already existed at HEAD).
- P1-4 SSE user-scoping — verified by 119 passing shared-api tests, including new `userScope.test.ts` and `inventory.sync.test.ts`.

**Honest limitations:**
- No live DB/Redis environment → wall-clock latency deltas (PDP ms, media upload/crop ms, cache-bust ms) are **NOT MEASURABLE**; only structural round-trip/operation-count deltas are measured.
- P2-2's end-user latency benefit is **IMPLEMENTED BUT NOT MEASURED** — request-count evidence only.
- The backend SSE fan-out is **unchanged**; only the frontend filters foreign-user events (P1-4 is a client-side reduction of invalidation work, **not** a server-side broadcast optimization).
- The **pre-existing SQLAlchemy mapper defect** (15 unit-test failures, present on BEFORE and AFTER) was **root-caused and fixed** during final validation — the full backend suite is now green (§6, §14.1).
- A **bounded, read-only live k6 probe** was executed against the production API (`https://api.hadha.co`) — real numbers and their heavy caveats are in §14.3. The probe measures **currently-deployed** production code (the staged optimizations are not deployed), so it is a live baseline, not proof of this diff's latency impact.

---

## 2. Original performance / root-cause findings

See `Docs/PERFORMANCE_AUDIT.md` (relocated from `Backend/`), `Docs/PERFORMANCE_ROOT_CAUSE_ANALYSIS.md`,
and `Docs/PERFORMANCE_OPTIMIZATION_PLAN.md` for the full analysis. Summary of the identified issues:

| ID | Finding |
|----|---------|
| P0-0 | No durable performance baseline — in-memory profiler snapshot only, never drained to logs. |
| P0-1 | Product-list cache bust ran **inline** on the media request path (SCAN + per-key soft-expire), blocking upload/crop/replace for up to ~1s. |
| P0-2 | `DISCARD ALL` executed on **every** connection pool return — one extra round-trip + asyncpg prepared-statement re-prepare per request. |
| P1-1 | `get_db` issued `COMMIT` on every request including pure read-only ones. |
| P1-2 | Admin 2FA gate issued two sequential SELECTs (admin_2fa, then admin_sessions). |
| P1-3 | PDP page made two GETs per load (loader + live poll query). |
| P1-4 | SSE events were fanned out to all clients and all subscribers invalidated queries even for foreign-user events. |
| P2-1 | N+1-ish list hydration: separate image-variants query; admin collections used a separate COUNT; variant update did UPDATE + re-read. |
| P2-2 | Hard-DELETE cache bust turned every /api/v1/products request into a blocking ~2.3–2.7s fetch until TTL; stampede risk at expiry. |

---

## 3. Approved optimization plan

| ID | Change | Status |
|----|--------|--------|
| P0-0 | Periodic profiler-metrics drain to structured perf log (`perf.metrics` / `perf.sql` slow-SQL WARN). | Implemented |
| P0-1 | Fire-and-forget, single-flight, coalesced product-list bust + best-effort rewarm. | Implemented |
| P0-2 | Remove per-return `DISCARD ALL` (session lifecycle already cleans transaction state). | Implemented |
| P1-1 | Skip `COMMIT` for read-only requests (ORM dirty-state + raw-DML cursor flag). | Implemented |
| P1-2 | Composite EXISTS 2FA gate (1 query); throttle check folded into the UPDATE's WHERE. | Implemented |
| P1-3 | PDP loader seeds `queryKeys.products.stock(slug)` via `ensureQueryData` → one GET per load. | Implemented |
| P1-4 | Frontend user-scoping of SSE events + targeted product-scoped invalidation. | Implemented |
| P2-1 | Remove image-variants query (variants selectinloaded with the 2 images); window-function COUNT for admin collections; `UPDATE … RETURNING` for variants. | Implemented |
| P2-2 | Wire `cache_swr` (TTL + SWR window + coalescing) into the PDP route; soft-expire bust instead of hard DELETE. | Implemented |
| P3-1 | Cart cross-tab broadcast consolidated into SyncBus (removed duplicate BroadcastChannel path). | Implemented |
| P3-2 | Storefront `products.$slug.tsx` loader → React Query `ensureQueryData`. | Implemented (same change as P1-3) |

All phases previously accepted provisionally (P2-1, P2-2, P3-1, P3-2) remain accepted with the caveats
recorded in §9 and §12.

---

## 4. P0/P1/P2/P3 implementation changes

### P0-0 — Profiler metrics drain
- `app/core/profiling.py`: `drain_metrics()` emits the full snapshot as a single `perf.metrics` INFO log; slow SQL now logs a `perf.sql` WARN immediately (works in request **and** worker contexts) and is appended to the global slow-query deque.
- `app/core/config.py`: `PERF_SLOW_SQL_THRESHOLD_MS` (default 200 ms), `PERF_DRAIN_INTERVAL_SECONDS` (default 60; 0 disables).
- `app/main.py`: lifespan task drains the snapshot every interval; cancelled on shutdown.
- `app/core/dependencies.py`: admin 2FA gate logs a `slow_2fa_gate` WARN when > 100 ms.

### P0-1 — Fire-and-forget cache bust
- `app/core/redis.py`: `schedule_product_list_bust()` / `_run_bust_in_background()` / `cancel_pending_busts()`.
  Single-flight loop: bust → best-effort rewarm → drain any busts requested meanwhile. Cancelled safely at shutdown.
- `app/modules/media/router.py`: `_bust_cache_for` now calls `schedule_product_list_bust()` (returns immediately) for product images; CMS homepage delete stays inline (single fast round-trip).
- `app/main.py`: `cancel_pending_busts()` before Redis pool close.

### P0-2 — Remove `DISCARD ALL`
- `app/core/database.py`: reset listener removed; rationale documented. asyncpg per-connection prepared-statement cache now survives across requests.

### P1-1 — Conditional COMMIT
- `app/core/database.py`: `get_db` commits only when `_session_has_writes()` is true — ORM `new/dirty/deleted` or a raw-DML statement seen by the `after_cursor_execute` listener (`hadha_write` flag on the connection).

### P1-2 — 2FA gate
- `app/modules/auth/service.py`: `get_2fa_gate_state()` returns `(has_2fa, session_verified)` from one composite EXISTS query; `is_admin_session_2fa_verified` / `has_active_2fa` removed. `record_admin_session_activity` now throttles inside the UPDATE's WHERE (no SELECT + TOCTOU window).

### P1-3 / P3-2 — PDP single request
- `Frontend_whole/storefront/src/routes/products.$slug.tsx`: loader seeds `queryKeys.products.stock(slug)` with `ensureQueryData` so the live poll reuses the cache — one GET per load.

### P1-4 — SSE user scoping (frontend)
- `packages/shared-api/src/lib/sync/userScope.ts` (new): `isEventForCurrentUser()` — undefined scope = local/cross-tab (always relevant); declared scope (even empty) must name the current user.
- `cart.sync.ts`, `checkout.sync.ts`, `order.sync.ts`, `reservation.sync.ts`: skip foreign-user events.
- `inventory.sync.ts`: `INVENTORY_CHANGED` / reservation events invalidate **only** queries whose cached data references the affected `productIds` (predicate-based); coarse catalog bust reserved for membership-changing events (`PRODUCT_UPDATED`, `PRICE_CHANGED`).
- `events.ts`: `userId` / `userIds` payload fields added.
- **Backend SSE broadcast is unchanged** — see §7.

### P2-1 — Round-trip reductions
- `catalog/repository.py`: `get_image_variants_for_images` deleted; `get_images_for_products` selectinloads `Image.variants` for the 2 images only; `update_variant` uses `UPDATE … RETURNING` (removes post-update re-read).
- `catalog/service.py`: variant hydration loop removed.
- `collections/repository.py`: admin list uses `COUNT(*) OVER()` — total and page in one round-trip.

### P2-2 — SWR wiring
- `catalog/router.py`: `get_product_by_slug` switched from plain cache-aside to `cache_swr` (ttl=600, swr_window=600) with a self-contained `_fetch_product` session (safe for the detached background refresh), ETag/Cache-Control preserved (`stale-while-revalidate=600`).
- Soft-expire bust (`_soft_expire_swr_entry` in `redis.py`) rewrites the `"t"` field instead of hard-deleting, with hard-delete fallback for non-wrapper entries.

### P3-1 — Cart cross-tab consolidation
- `storefront/src/stores/cart.ts`: removed the duplicate raw-string BroadcastChannel path; SyncBus already broadcasts `CART_CHANGED` cross-tab on the same channel (serialized events with per-tab origin dedupe).

---

## 5. Files changed

41 files, **+3452 / −399** (staged diff vs `a91cac0`):

**Backend — app:**
`core/config.py`, `core/database.py`, `core/dependencies.py`, `core/profiling.py`, `core/redis.py`,
`main.py`, `modules/auth/service.py`, `modules/catalog/repository.py`, `modules/catalog/router.py`,
`modules/catalog/service.py`, `modules/collections/repository.py`, `modules/media/router.py`,
`modules/media/storage.py` (comment-only: background variant generation + R2 semaphore rationale),
`workers/admin_session_cleanup.py` (comment-only).

**Backend — tests / docs:**
`tests/unit/test_cache_swr_soft_bust.py`, `tests/unit/test_profiling.py` (new),
`tests/unit/test_repositories.py`, `tests/unit/test_service_auth_collections.py`,
`tests/unit/test_service_orders_profiles_catalog.py`, `tests/unit/test_service_remaining_gaps.py`,
`tests/measurement/test_performance_deltas.py` (measurement harness — **now staged, was untracked**),
`tests/measurement/.gitignore` (excludes generated `results/*` JSONL),
`Docs/PERFORMANCE_AUDIT.md` (moved from `Backend/`),
`Docs/PERFORMANCE_OPTIMIZATION_PLAN.md` (new), `Docs/PERFORMANCE_ROOT_CAUSE_ANALYSIS.md` (new).

**Mapper defect fix (production-readiness, not a performance change):**
`modules/catalog/models.py`, `modules/reviews/models.py` — see §14.1.

**Frontend:**
`packages/shared-api/src/lib/sync/{events,cart.sync,checkout.sync,inventory.sync,order.sync,reservation.sync}.ts`,
`packages/shared-api/src/lib/sync/userScope.ts` (new),
`packages/shared-api/src/lib/sync/__tests__/{inventory.sync.test.ts,userScope.test.ts}` (new),
`storefront/src/routes/products.$slug.tsx`, `storefront/src/stores/cart.ts`,
`storefront/src/routes/__tests__/products-slug.single-request.test.tsx` (new — PDP single-request verification).

**k6 (live validation probe):**
`k6/smoke/prod-readiness.js` (new — bounded read-only production probe, reuses existing k6 helpers).
Generated `k6/results/prod-readiness-live.json` is **not** staged (artifact; numbers captured in §14.3).

---

## 6. Test / validation results

### 6.1 Backend (Python) — exact results (final, post-mapper-fix)

Command: `./hadha/Scripts/python.exe -m pytest <paths> -q --no-header -p no:cacheprovider`

| Suite | Collected | Passed | Skipped | Failed | Warnings | Notes |
|-------|-----------|--------|---------|--------|----------|-------|
| `tests/unit` | 1257 | 1257 | 0 | **0** | 17 | **green after mapper fix** (§14.1) |
| `tests/integration` (3 files) | 82 | 82 | 0 | 0 | pydantic deprecation | `test_api_smoke.py` (11), `test_api_comprehensive.py` (57), `test_company_api.py` (14) |
| `tests/stress` | 66 | 64 | 2 | 0 | 0 | 2 skipped are pre-existing skips |
| `tests/measurement` | 15 | 15 | 0 | 0 | 1 | 14 original + **new PDP success-path e2e** (§14.2); hardened with per-test circuit-state reset |
| **Backend total** | **1420** | **1418** | **2** | **0** | | |

Stress + measurement were also re-run combined: `79 passed, 2 skipped, 0 failed` (proves the harness's
per-test circuit-state reset keeps measurement tests deterministic even after the stress suite opens the
Redis circuit breaker in-process).

### 6.2 The 15 unit-test failures — root-caused and FIXED

- The failures were a **pre-existing repo defect** (reproduced identically on the `perf-before` worktree at
  `a91cac0` with the staged diff absent) — not caused by this performance work.
- Root cause and fix: see §14.1. After the fix, the previously failing files
  `test_service_orders_create.py` (7) + `test_service_webhooks.py` (8) pass **44/44**, and the full unit
  suite passes **1257/1257**.

### 6.3 Frontend — final results

| Gate | Result |
|------|--------|
| Storefront vitest | **44 passed / 0 failed** (incl. new `products-slug.single-request.test.tsx` — 4 tests) |
| shared-api vitest | **119 passed / 0 failed** (incl. new `userScope.test.ts` + `inventory.sync.test.ts`) |
| Storefront typecheck (`tsc --noEmit`) | **0 errors** |
| Storefront lint (`npm run lint`) | **0 errors, 57 warnings** (all pre-existing `react-refresh/only-export-components` on `components/ui/*`) |
| shared-api `tsc --noEmit` | **not a clean gate** — broken at baseline (vitest globals not in tsconfig, missing module resolutions; no `typecheck` script). Unchanged by this work; vitest is its gate. |

---

## 7. `cache_swr` semantics — verified from code + tests

`cache.py` is **not** in the staged diff — the SWR mechanism predates this work; this diff only wires it
into routes and changes the bust to soft-expire. Semantics verified from `app/core/cache.py` and
`tests/unit/test_cache_swr_soft_bust.py` (all passing):

| Behavior | Verified behavior |
|----------|-------------------|
| Fresh-cache | `age < ttl` → return cached value, **no fetch** (measurement: fresh served=1, db_fetches=0). |
| Stale-cache | `ttl ≤ age < ttl+swr_window` → serve stale value immediately, spawn background refresh. |
| Background refresh | `_swr_refresh` task (≤32 concurrent globally); writes `{d,t}` with Redis TTL `ttl+swr_window`. |
| Request coalescing | Per-key `asyncio.Lock` + double-check under the lock → 5 concurrent cold requests = **1 DB fetch** (measured). |
| ETag / 304 | **Outside `cache_swr`** — route-level `make_etag` + `check_not_modified` + `not_modified_response()` + `add_cache_headers` (kept in the PDP rewrite). 304 on `If-None-Match` match. |
| Redis failure | `safe_redis_get/setex` guard via circuit breaker + 0.3 s timeout → `None` → caller falls through to DB (fail-open). |
| Refresh fetch failure | `_swr_refresh` catches all exceptions silently; stale data remains servable until hard expiry (`test_refresh_failure_leaves_stale_cache_recoverable` passes). |
| Soft-expire bust | `_soft_expire_swr_entry` rewrites `"t"` to "just expired" (stale-serve + one coalesced refresh); hard-delete fallback for non-wrapper values. |

**Measured note:** the PDP route now does **2 Redis GETs on cold miss** (1 pre-lock + 1 double-check under the lock)
vs 1 before. This is the intentional cost of coalescing (sub-ms Redis GET traded against duplicate DB fetches);
DB executes stay at 1.

---

## 8. BEFORE / AFTER performance measurements

Method: `tests/measurement/test_performance_deltas.py` executed identically in the `perf-before` worktree
(BEFORE = `a91cac0`) and the main tree (AFTER = `a91cac0` + staged diff). Recording stubs count DB
`execute/commit/get` and Redis `get/setex/delete/scan_iter` calls — **no network, no live DB/Redis**.
BEFORE runs the original 14 harness tests; AFTER runs **15** (the new PDP success-path e2e test is an
AFTER-only addition — it verifies the success flow that the 404-branch test could not). Deltas below are
from the freshly regenerated `perf-deltas.jsonl` files.

### P1-1 — read-only requests skip COMMIT

```text
Metric: get_db COMMITs issued for a read-only request
Before: 1
After:  0
Delta:  -1 per read-only request
Percentage: -100%
Measurement method: RecordingSession.commit counter in get_db lifecycle test
Sample size: 1 run each tree (deterministic — no DB)
Confidence/limitations: High. Structural; deterministic.
```

### P1-2 — 2FA gate round-trips

```text
Metric: DB executes to resolve (has_2fa, session_verified)
Before: 2
After:  1
Delta:  -1 per admin request
Percentage: -50%
Measurement method: RecordingSession.execute counter on AuthService gate
Sample size: 1 run each tree
Confidence/limitations: High. Deterministic.
```

### P2-1a — product list hydration (empty list + image-variants query)

```text
Metric: list_products DB executes on empty DB
Before: 1
After:  1
Delta:  0
Percentage: 0%
Measurement method: RecordingSession counter via CatalogService.list_products
Sample size: 1 run each tree
Confidence/limitations: Empty DB short-circuits image hydration, so this metric alone
                        cannot see the variant-query removal — see next metric.

Metric: get_image_variants_for_images method + its DB executes
Before: method present, 1 execute when invoked
After:  method removed (0 executes possible)
Delta:  -1 query per non-empty product list
Percentage: -100% of the dedicated variant query
Measurement method: method-existence probe in measurement harness
Sample size: 1 run each tree
Confidence/limitations: High for "query eliminated". List-write path covered by unit tests
                        (get_images_for_products now selectinloads Image.variants).
```

### P2-1b — variant update round-trips

```text
Metric: repository update_variant DB executes + re-reads
Before: 2 executes, 1 db.get
After:  1 execute, 0 db.get
Delta:  -1 execute, -1 get per variant update
Percentage: -50% round-trips
Measurement method: RecordingSession counters via ProductRepository.update_variant
Sample size: 1 run each tree
Confidence/limitations: High. UPDATE … RETURNING is deterministic.

Metric: service update_variant (non-stock path) DB executes
Before: 3
After:  2
Delta:  -1
Percentage: -33%
Measurement method: RecordingSession counter via CatalogService.update_variant
Sample size: 1 run each tree
Confidence/limitations: High.
```

### P2-1c — pagination round-trips

```text
Metric: admin collections list DB executes
Before: 2 (separate COUNT + data)
After:  1 (COUNT(*) OVER() window)
Delta:  -1 per admin collections page
Percentage: -50%
Measurement method: RecordingSession counter via CollectionRepository.list_admin
Sample size: 1 run each tree
Confidence/limitations: High. Deterministic.

Metric: product list_paginated DB executes
Before: 1
After:  1
Delta:  0
Percentage: 0%
Measurement method: RecordingSession counter via ProductRepository.list_paginated
Sample size: 1 run each tree
Confidence/limitations: Window-function COUNT was already at HEAD for products;
                        this phase's change is the variant-hydration removal (P2-1a).
```

### P2-2 — SWR semantics (mechanism unchanged)

```text
Metric: 5 concurrent cold requests → DB fetches / Redis GETs / SETEX
Before: 1 / 10 / 1
After:  1 / 10 / 1
Delta:  0
Percentage: 0% (identical)
Measurement method: asyncio.gather of 5 cache_swr calls against RecordingRedis
Sample size: 1 run each tree
Confidence/limitations: High — cache.py is not in the diff, so identical is expected
                        and confirms no regression. Coalescing works: 1 DB fetch for 5 readers.

Metric: fresh-hit → served from cache / DB fetches
Before: served=1 / fetches=0
After:  served=1 / fetches=0
Delta:  0

Metric: stale-hit → stale served / background DB fetch / SETEX
Before: 1 / 1 / 1
After:  1 / 1 / 1
Delta:  0
```

**Note on P2-2 end-user latency:** SWR's purpose is serving stale data fast instead of blocking on a
DB refresh. That latency benefit is **not directly measured here** (no live Redis/DB wall-clock numbers
available) — it is supported only by the verified semantics and by the post-deploy production incident
described in `bust_product_list_cache`'s docstring. Classified **IMPLEMENTED BUT NOT MEASURED** for latency.

### P0-1 — cache bust off the request path

```text
Metric: product-list bust Redis ops executed synchronously at media-write response time
Before: inline `await bust_product_list_cache` (SCAN + soft-expire on the request path)
After:  0 ops at return; schedule_product_list_bust present; background scan=1,
        rewrite gets=10, setex=10 after 0.3s
Delta:  request path freed of the entire SCAN+rewrite; work moved to a single-flight task
Measurement method: RecordingRedis counters around schedule_product_list_bust + sleep
Sample size: 1 run each tree
Confidence/limitations: High for structural change (fire-and-forget proven by
                        ops-at-return=0 vs scan-after-sleep=1). Wall-clock ms not measurable
                        without a live Redis.
```

### P0-2 — DISCARD ALL removal

```text
Metric: reset listener present / DISCARD statements per connection return
Before: 1 / 1
After:  0 / 0
Delta:  -1 statement per connection return
Percentage: -100%
Measurement method: listener presence probe + cursor statement capture
Sample size: 1 run each tree
Confidence/limitations: High. Deterministic. (Round-trip saving itself is structural, not
                        measured in ms — no live Postgres.)
```

### PDP route — request count

```text
Metric: /api/v1/products/{slug} cold-miss Redis GETs / DB executes
Before: 1 GET / 1 execute
After:  2 GETs / 1 execute
Delta:  +1 Redis GET (coalescing double-check), DB unchanged
Measurement method: in-process ASGI client with overridden get_db/get_redis
Sample size: 1 run each tree (slug resolves 404 in both)
Confidence/limitations: High for counts. +1 GET is the intended coalescing double-check;
                        on cache hits the count is 1 as before. Latency delta not measurable.
```

### Media upload / media crop / DB checkout / commit / Redis bust latency (ms)

```text
Metric: media upload wall-clock, media crop wall-clock, DB checkout ms, DB commit ms,
        Redis cache-bust latency ms, SSE-triggered request count
Before: NOT MEASURABLE
After:  NOT MEASURABLE
Measurement method: n/a
Sample size: n/a
Confidence/limitations: NOT MEASURABLE — no live DB/Redis environment and no load tooling
                        connected to a running stack in this workspace. Do not invent
                        numbers. The structural evidence above (round-trip and operation
                        counts) is the strongest evidence available in this environment.
```

---

## 9. Deviations from the approved plan

1. **P2-2 scope clarification:** `cache_swr` itself was already present at HEAD; the phase implemented the
   route wiring and soft-expire bust rather than the SWR primitive. Semantics verified identical BEFORE/AFTER.
2. **P0-2 risk assessment:** removal of `DISCARD ALL` relies on the audit finding that no session-scoped
   state (GUCs, LISTEN/NOTIFY, temp tables) is used by the app. This was a documented, deliberate deviation
   from "defense-in-depth reset" and is safe only while that invariant holds.
3. **P1-3 and P3-2** are the same change (PDP loader); implemented once.
4. **Media `storage.py` and `workers/admin_session_cleanup.py`** changed comment-only (docstrings aligned
   with the background variant-generation architecture). No behavioral change.
5. **Measurement harness** (`tests/measurement/`) is now **staged** with a `.gitignore` for generated
   `results/*` JSONL — the reproducible test code is part of the change set; artifacts are not.

---

## 10. Remaining bottlenecks

1. **Variant generation is backgrounded** but still drives R2 I/O through the shared `to_thread` pool
   (bounded only by `_R2_CONCURRENCY = 8`). A dedicated task queue remains a follow-up (documented in
   `storage.py`).
2. **Product-list bust is single-flight within one process.** Under multiple uvicorn workers, each worker
   runs its own bust; coalescing is per-process. Acceptable today; cross-process single-flight is a
   future improvement.
3. **`_coalesce_locks`** are process-local — stampede protection holds per worker. Redis TTL/soft-expiry
   keeps cross-worker behavior acceptable.
4. **PDP hard miss** still pays the full DB fetch on a truly cold cache (no SWR value yet). This is the
   unavoidable first-read cost.
5. **`test_api_smoke.py`** hung once when run concurrently with other pytest sessions (Sentry teardown
   "Waiting up to 2 seconds" contention); passes 11/11 standalone. Watch for test-session parallelism.

---

## 11. Known limitations

1. **No live-environment wall-clock measurements** — all measured evidence is operation/round-trip counts
   from recording stubs. Latency claims for SWR, P0-1, and P0-2 are structural, not timed.
2. **15 pre-existing unit-test failures (SQLAlchemy mapper init order in `catalog/models.py`)** — **FIXED**
   during final validation; full suite green (see §14.1). No longer a limitation.
3. **shared-api `tsc --noEmit` is not a green gate** at baseline (vitest globals missing from its tsconfig,
   no `typecheck` script). Unchanged by this work; the shared-api gate is vitest (119/119).
4. **P1-4 is frontend-only filtering** — the backend still broadcasts every event to every SSE client
   (see §7 SSE section below). Under very high fan-out this is a scaling limit, unchanged by this work.
5. **SSE event counts are not instrumented end-to-end** in this environment: events delivered/broadcast
   and the API requests avoided per event are not directly measurable here (see §8 SSE section).
6. **PDP success path** now has an end-to-end route test (`test_route_pdp_success_path_miss_hit_etag_304`)
   covering cold-miss → fetch → cache-populate → warm hit → ETag → If-None-Match → 304, with zero DB
   work on hits (§14.2). **Resolved.**
7. **`_soft_expire_swr_entry` is a non-atomic GET→SETEX pair** — a background refresh completing in between
   can be clobbered (bounded by coalescing; next reader re-refreshes). It also resets the Redis TTL to
   `2×ttl` per bust, which extends stale-entry memory retention. Accepted tradeoff; a Lua-script version is
   a follow-up.
8. **P1-3 one-GET claim** — **now verified by tests** (`products-slug.single-request.test.tsx`, 4/4
   passing, §14.2): cold load = 1 GET, poll mount = 0 extra, back-nav within and beyond staleTime = 0
   extra. The storefront `tsc`/`lint`/vitest gates are green.
9. **Measurement harness is state-sensitive** — **hardened**: the harness now resets the Redis
   circuit-breaker module state per-test, so `tests/stress` + `tests/measurement` run deterministically in
   one process (79 passed, 2 skipped, 0 failed).
10. **Frontend `containsAnyProduct` relies on cached data shapes** (`{id}` / `{items:[…]}`). If a product
    query ever stores data under another shape, targeted invalidation would silently miss. Current shapes
    are covered by `inventory.sync.test.ts`.

### SSE / P1-4 — what is and is not true

- **Backend SSE fan-out is unchanged.** `publish_sync_event` → Redis pub/sub → `_listen_redis` pushes
  every event to every subscriber queue (`_subscribers`); there is **no per-user routing server-side**.
- **The P1-4 optimization filters on the frontend** (`isEventForCurrentUser`, targeted `invalidateQueries`
  predicates). It prevents unnecessary downstream invalidation/API-refetch work caused by foreign-user
  events, and it narrows `INVENTORY_CHANGED`/reservation busts to the affected products.
- Measured/reported: **SSE events broadcast — NOT MEASURABLE** (no live multi-client env).
  **Requests/invalidation work caused by events — reduced by construction** (verified by 119 shared-api
  unit tests asserting foreign-user events no longer invalidate; the actual network-request count avoided
  is not measured).
- This report does **not** describe frontend filtering as a server-side SSE routing optimization.

---

## 12. Remaining concerns

1. **Live wall-clock confirmation of the staged optimizations is still outstanding.** The bounded k6 probe
   measured the **currently-deployed** production code; the staged optimizations are not deployed, so no
   latency delta can be attributed to them yet. A deploy-then-measure cycle (see §14.3) is required.
2. **The staged changes are not committed** — by design, left for human review.
3. **shared-api tsc debt** predates this work (no `typecheck` script; vitest globals missing from tsconfig)
   and should be scheduled so the package has a real type gate.
4. **Live probe surfaced elevated production PDP/list p95** on a cold-miss-heavy, tiny sample — needs a
   controlled warm-cache load run to determine whether this is a real production bottleneck (see §14.3,
   §14.8).

---

## 13. Final classification of every optimization

| ID | Optimization | Classification | Evidence |
|----|--------------|----------------|----------|
| P0-0 | Profiler metrics drain + slow-SQL logging | **IMPLEMENTED BUT NOT MEASURED** (observability only) | code + `test_profiling.py` (new, passing) |
| P0-1 | Fire-and-forget coalesced cache bust | **VERIFIED PERFORMANCE IMPROVEMENT** (structural) | 0 ops at response vs 1 background scan + 10/10 rewrites; media router callsite probe |
| P0-2 | Remove per-return `DISCARD ALL` | **VERIFIED PERFORMANCE IMPROVEMENT** (structural) | 1 statement/return → 0; listener removed |
| P1-1 | Read-only requests skip COMMIT | **VERIFIED PERFORMANCE IMPROVEMENT** (structural) | commits/read-only: 1 → 0 |
| P1-2 | Composite 2FA gate | **VERIFIED PERFORMANCE IMPROVEMENT** (structural) | executes: 2 → 1 |
| P1-3/P3-2 | PDP single GET per load | **VERIFIED PERFORMANCE IMPROVEMENT** (request-count, test-verified) | new storefront test: 1 GET cold, 0 extra on poll mount + back-nav (§14.2) |
| P1-4 | Frontend SSE user-scoping + targeted invalidation | **IMPLEMENTED BUT NOT MEASURED** (broadcast reduction intentionally NOT claimed) | 119 shared-api tests incl. new userScope + inventory.sync tests |
| P2-1a | Remove image-variants query | **VERIFIED PERFORMANCE IMPROVEMENT** (structural) | method + 1 execute → removed |
| P2-1b | UPDATE … RETURNING for variants | **VERIFIED PERFORMANCE IMPROVEMENT** (structural) | 2 executes + 1 get → 1 execute |
| P2-1c | Window-function COUNT for admin collections | **VERIFIED PERFORMANCE IMPROVEMENT** (structural) | executes: 2 → 1 |
| P2-2 | SWR wiring + soft-expire bust | **IMPLEMENTED BUT NOT MEASURED** (latency) / **VERIFIED IMPLEMENTATION** (semantics) | SWR semantics identical BEFORE/AFTER; coalescing 1 fetch for 5 readers; latency not timed |
| P3-1 | Cart cross-tab consolidation | **IMPLEMENTED BUT NOT MEASURED** | code change; storefront vitest green |
| — | Remaining: variant-gen task queue, per-worker bust/coalescing | **REMAINING BOTTLENECK** | §10, §12 |

**Legend:** VERIFIED = the delta was actually measured by the harness or proven by a passing test.
IMPLEMENTED BUT NOT MEASURED = code shipped + tests pass, but no timed evidence in this environment.
NO MEASURABLE IMPROVEMENT = none claimed (list_paginated/`list_products` count metrics were already optimal at HEAD).
REMAINING BOTTLENECK = documented follow-up work.

---

## 14. Production Readiness Validation

### 14.1 Mapper defect (blocker fixed)

```text
Problem:   15 unit tests failed on BOTH the BEFORE commit (a91cac0) and the AFTER tree with
           Mapper[Product(products)] … 'Image.sort_order' failed to locate a name ("name 'Image' is
           not defined"). Triggered by import order in test_service_orders_create.py (7) and
           test_service_webhooks.py (8).
Root cause: catalog/models.py (Product.images) and reviews/models.py (Review.images) used eval-string
           relationship arguments (primaryjoin="...Image.owner_id...", order_by="Image.sort_order").
           SQLAlchemy evaluates these strings in the module's RUNTIME namespace when mappers configure,
           but Image was only imported under `if TYPE_CHECKING:` — so when a test triggered mapper
           configuration without importing media.models first, `Image` was undefined → NameError.
Fix:       Promote the `from app.modules.media.models import Image` import from `TYPE_CHECKING` to a
           runtime import in both files (one line each; TYPE_CHECKING block removed where it became
           unused). Verified cycle-free: media/models.py imports nothing from catalog/reviews, and
           `import app.main` + `configure_mappers()` succeed. Relationship behavior, ordering by
           Image.sort_order, schema, and API behavior are unchanged.
Tests before: test_service_orders_create.py 7 failed, test_service_webhooks.py 8 failed (15 total)
Tests after:  44/44 passed for those files; full unit suite 1257/1257 passed, 0 failed
Result:       FIXED — no remaining failures on any suite. The fix is minimal and scoped to the defect.
```

### 14.2 PDP success-path validation (backend e2e + frontend single-request)

**Backend — ASGI route test** (`test_route_pdp_success_path_miss_hit_etag_304`, measurement harness,
exercises the REAL route + service code against recording stubs):

```text
Cold load:  GET /api/v1/products/silver-ring-e2e → cache miss
Product requests:  1 (cold), then 1 warm, then 1 conditional
DB fetches:        2 on cold miss (get_by_slug + get_collections_for_product) → 200 with correct shape
                   (slug, name, base_price=4999.0, inventory_status=IN_STOCK, can_purchase=true,
                   code=PRODUCT_FETCHED)
Cache behavior:    populated on miss — SETEX ≥ 1, key product:detail:v1:silver-ring-e2e present;
                   Cache-Control: stale-while-revalidate=600
ETag:              present on the 200; stable across cache hits (etag2 == etag1)
304:               If-None-Match=<etag> → 304, ZERO additional DB executes (session.executes stays 2)
Result:            200 (2 DB) → 200 (0 DB) → 304 (0 DB) — the full miss→populate→hit→ETag→304 flow
                   verified. PASSED.
```

**Frontend — single-request verification** (`products-slug.single-request.test.tsx`, 4/4 passing) covering
`staleTime`, query key, loader `ensureQueryData`, `useQuery`, polling config, and navigation:

```text
Cold load:                       loader issues exactly ONE product-detail GET and seeds the poll key
                                 (queryKeys.products.stock(slug)) — verified: 1 GET
Live poll mount (same key):      reuses loader-seeded cache — 0 additional GETs
Navigate away + back (fresh):    loader serves cache — 0 additional GETs
Navigate back after staleTime:   loader serves cache — 0 additional GETs (React Query v5
                                 ensureQueryData refetches only on a hard miss or with
                                 revalidateIfStale; the live poll's refetchInterval owns refresh)
Result:                          P1-3/P3-2 single-request behavior HOLDS — verified by tests.
```

### 14.3 Live performance validation (bounded k6 probe against production)

**Environment:** production `https://api.hadha.co` was reachable (health 200). No local stack was
running. Admin endpoints and `/me` return 401 without credentials — no credentials are available, so they
are **NOT MEASURABLE** (documented, not faked). The k6 production config documents read-only as the
allowed production mode.

**Method:** new bounded probe `k6/smoke/prod-readiness.js` (reuses existing `helpers/http.js`, envelope
parsing, thresholds — no new framework). 2 VUs, 12 shared iterations, 60s cap, public GET endpoints only,
product slugs fetched live in `setup()`. **No auth, no writes, no admin routes.**

```text
LIVE VALIDATION STATUS: EXECUTED (bounded, read-only)
Test:           k6 run smoke/prod-readiness.js --env BASE_URL=https://api.hadha.co
Duration:       completed within the 60s cap (12 iterations)
Virtual users:  2
Sample size:    61 requests (list 12, detail 12, collections 12, categories 12, homepage 12, setup 1)
Environment:    https://api.hadha.co (production, currently-deployed code)

Metric (per endpoint):     med     p90      p95      max      samples
Product list /products:    284 ms  2.62 s   4.87 s   7.31 s   12        (1 transient failure → 11/12 ok)
Product detail /products/{slug}: 1.75 s  2.23 s  2.31 s   2.39 s   12  (12/12 HTTP 200, all business-ok)
Collections /collections:  149 ms  155 ms   244 ms   351 ms   12
Homepage /cms/homepage:    150 ms  427 ms   724 ms   1.04 s   12

Error rate:     1.63% (1 of 61 requests failed — the slow product-list request; api_success_rate 98.36%)
Thresholds:     detail p(95)<800 FAILED (2.31s); list p(95)<1000 FAILED (4.87s); others passed

BEFORE: NOT AVAILABLE — all prior k6 artifacts (k6/results/*) were captured against the local docker
        stack (http://localhost:8000) at earlier commit states, never against production. No trustworthy
        same-environment baseline exists, so no improvement percentage is computed.
AFTER:  numbers above (current production behavior — NOT the staged code, which is not deployed).
Conclusion: cannot calculate a valid improvement percentage; the probe is a live baseline of deployed
            behavior plus an availability check, not evidence for or against this diff's latency impact.

Media upload / media crop: NOT MEASURABLE with the current k6 workload — no existing script exercises
    the media endpoints, and doing so would require write access + credentials. Explicitly out of the
    k6 suite's read-only production mode.
DB query count / DB commit count / Redis operations / cache hit-miss / SSE-triggered API requests:
    NOT OBSERVABLE from k6 — no instrumentation access in production; k6 measures HTTP only. These are
    covered structurally by the measurement harness (§8) instead.
```

**Caveats (important):** the probe targets a random slug per iteration, so every PDP request is a
**cold cache miss** (each different product) — the 1.75–2.31 s detail numbers reflect cold-fetch
latency at 2 VUs with a tiny sample, not warm-cache p95. The 4.87 s list p95 is inflated by the single
7.31 s outlier that also produced the only failure. Percentiles on ~12 samples are noisy. The staged
optimizations are NOT deployed, so none of these numbers measure this diff.

### 14.4 BEFORE/AFTER comparison (live)

For every live metric: **BEFORE: NOT AVAILABLE** (no trustworthy live baseline of the same environment;
prior k6 results target the local dev stack). Only AFTER values exist, so no valid improvement percentage
can be computed. The structural (harness) BEFORE/AFTER evidence in §8 remains the measured evidence for
this diff.

### 14.5 Final test status (exact totals)

| Gate | Result |
|------|--------|
| Backend unit | 1257 passed, 0 failed, 0 skipped (17 warnings) |
| Backend integration | 82 passed, 0 failed (25 + 57) |
| Backend stress | 64 passed, 2 skipped, 0 failed |
| Backend measurement | 15 passed, 0 failed (incl. PDP success-path e2e) |
| Backend total | **1418 passed, 2 skipped, 0 failed** (1420 collected) |
| Black / Ruff / Mypy | All clean (322 files unchanged / All checks passed / no issues in 247 files) |
| Storefront vitest / tsc / lint | 44 passed / 0 errors / 0 errors (57 pre-existing warnings) |
| shared-api vitest | 119 passed, 0 failed |
| shared-api tsc | broken at baseline (pre-existing) — unchanged, documented §6.3 |
| k6 live probe | executed, 61 requests, 1 transient failure (see §14.3) |

### 14.6 Final classification of every optimization (retained, updated)

See §13. Updates from final validation:
- **P1-3 / P3-2 (PDP single GET)** upgraded **IMPLEMENTED BUT NOT MEASURED → VERIFIED PERFORMANCE
  IMPROVEMENT (request-count, test-verified)**: 1 GET on cold load, 0 extra on poll mount and on
  back-navigation, proven by the new storefront test (§14.2).
- **P0-1 / P0-2 / P2-2** remain **VERIFIED (structural)** / **IMPLEMENTED BUT NOT MEASURED (latency)** —
  unchanged: the live probe cannot measure them because the staged code is not deployed.
- No item is upgraded to VERIFIED merely because its code exists; every VERIFIED row has harness or
  test evidence (§8, §14.2).

### 14.7 Regression check of all previous optimizations

All previously established structural improvements were re-verified by re-running the measurement suite
after every change (mapper fix, harness hardening, PDP test additions): P0-1 (bust off request path),
P0-2 (no DISCARD ALL), P1-1 (read-only COMMIT skipped), P1-2 (2→1 2FA round-trip), P1-3/P3-2 (PDP single
GET — new test), P1-4 (frontend SSE scoping — 119 shared-api tests), P2-1a/b/c (round-trip reductions),
P2-2 (SWR semantics identical), P3-1 (cart BroadcastChannel consolidation — storefront vitest green).
Measurement: **15/15 passed** in the final run. No regressions.

### 14.8 Final production-readiness decision

```text
NOT YET PRODUCTION READY

Green (no blocker):  backend unit/integration/stress/measurement suites (1418 passed, 0 failed),
                     Black/Ruff/Mypy, storefront vitest/tsc/lint, shared-api vitest, mapper defect
                     fixed, PDP single-request behavior verified, measurement harness staged, final staged diff
                     reviewed for accidental/unrelated changes.

Remaining (blocks the READY declaration):
1. Live validation evidence is a bounded cold-miss probe, not a controlled warm-cache load run.
   The probe measured CURRENTLY-DEPLOYED code (the staged optimizations are not deployed), and it
   surfaced production PDP p95 ≈ 2.31 s and list p95 ≈ 4.87 s — far above the documented production
   targets (300 ms / 400 ms) — plus 1 transient request failure (1.63%). A properly-sized load run
   against a staging/controlled environment (existing k6 load tooling), then a deploy-then-measure
   cycle, is required before production-ready can be declared.
2. shared-api tsc debt at baseline (no real type gate for the package) — scheduled follow-up.
3. The final diff is intentionally left staged and uncommitted for human review; the performance
   decision should be re-confirmed after commit and deploy.

The structural evidence in §8 and the test evidence in §14.2 remain valid and green; what is missing
for PRODUCTION READY is live, controlled, post-deploy validation of the deployed optimizations.
```

---

## 15. How to reproduce this validation

```bash
# 1. Backend full suite (chunks to stay within timeouts)
cd Backend
./hadha/Scripts/python.exe -m pytest tests/unit tests/integration tests/stress tests/measurement -q --no-header -p no:cacheprovider

# 2. Measurement harness — AFTER
cd Backend && ./hadha/Scripts/python.exe -m pytest tests/measurement -q --no-header
cat tests/measurement/results/perf-deltas.jsonl

# 3. Measurement harness — BEFORE (worktree at a91cac0)
cd .claude/worktrees/perf-before/Backend
'/F:/Work/Hadha.co/Project/Backend/hadha/Scripts/python.exe' -m pytest tests/measurement -q --no-header
cat tests/measurement/results/perf-deltas.jsonl

# 4. Lint/type gates
cd Backend && ./hadha/Scripts/python.exe -m black --check app tests && ./hadha/Scripts/python.exe -m ruff check app tests && ./hadha/Scripts/python.exe -m mypy app/ --ignore-missing-imports
cd Frontend_whole/storefront && npm run typecheck && npm run lint && npx vitest run
cd Frontend_whole/packages/shared-api && npx vitest run
```

# CURRENT SLOW SQL — ROOT-CAUSE ANALYSIS

> **Status: ANALYSIS ONLY.** No application code, SQL, indexes, worker architecture, cache behavior, metrics, or middleware was changed for this document. This is the `ROOT-CAUSE INVESTIGATION → OPTIMIZATION PLAN` stage. Implementation waits for explicit approval.
>
> Investigation method: source-code inspection of the repository at `F:/Work/Hadha.co/Project` (git HEAD `a91cac0` + working tree), runtime introspection of the installed SQLAlchemy/FastAPI versions, self-contained empirical reproductions of the critical session defect, and correlation of the provided production logs. Live database diagnostics (EXPLAIN, `pg_stat_*`) could **not** be run from this environment (no production DB credentials/network) — the exact read-only queries to run are listed in §7 and §13.

---

## 1. Executive Summary

The production backend (`uvicorn --workers 2` on `https://api.hadha.co`, remote Supabase Postgres) is running a **single critical correctness defect** plus a set of performance contributors. They are ordered by severity, not by the size of the SQL statements involved.

1. **P0 — Database-session teardown bug (`_session_has_writes`).** Every HTTP request that executes SQL **without ORM-tracked changes** — which is *every* read-only request and every raw-Core-DML request (product PATCH, media upload, reservation/notification workers on the request path) — raises `AttributeError: 'function' object has no attribute 'info'` at `app/core/database.py` in `_session_has_writes()`. The bug is **empirically reproduced** (§3.1). Under the deployed `get_db` (which re-raises, as it has since the initial commit), the error fires **before `session.commit()`**, the transaction is rolled back, and FastAPI converts the teardown exception into an HTTP **500**. For write requests this means the DB write is **lost while the route has already computed a success response** — and for read-only requests the storefront returns 500. This defect supersedes all performance questions and must be fixed first.

2. **P0 — Duplicated scheduled jobs across the 2 Uvicorn workers.** Every worker process runs the full lifespan: the APScheduler queue (6 jobs: reservation_expiry 15s, media_generation 5s, notification_retry 30s, cms_publish 60s, admin_session_cleanup 1h, partition_manager monthly) and the `sync_notification_rules` seed each run **twice per cluster**. This doubles every sweep's DB load, creates the 914 ms `INSERT INTO notification_rules` (concurrent unique-index lock wait between the two seeders), and gives `notification_retry` (a plain SELECT, no atomic claim) a real **duplicate-email/WhatsApp** risk.

3. **P1 — Missing indexes on the worker sweep tables.** `reclaim_stale_processing` (`images WHERE status='processing' AND updated_at < cutoff`, every 5 s) and `get_pending_retries` (`notification_logs WHERE status='retrying' AND next_retry_at <= now()`, every 30 s) full-table-scan unindexed tables (models define **no** indexes on these columns). This is the recurring 230–365 ms SQL in the logs. `landing_sections(status, scheduled_at)` is the same pattern at 60 s.

4. **P1 — The ~120 ms p50 across *all* queries is remote-DB round-trip latency.** Even the already-indexed reservation query (`idx_inv_res_status_expires`) takes 235 ms. SQL/index changes cannot remove this floor; the levers are fewer round-trips per operation, and not classifying every >200 ms statement as an anomaly at this threshold.

5. **P1 — Request latency is dominated by query-count × RTT, not by individual SQL.** The 1.83 s product PATCH executes ~12–15 DB round-trips (including a **double** selectinload-heavy product load) plus an inline Redis cache bust; the 206 ms UPDATE is only ~11 % of the request. The ~3 s media upload is CPU normalization (~726 ms) + synchronous R2 PUT (~1.1 s) + a flush/refresh/refresh-variants insert pattern (~566 ms) + an inline `update_fields` (~345 ms); the "cascade" queries are split between the request's own refreshes and the **background** fire-and-forget cache rewarm (products SELECT 818 ms, product_collections 348 ms), which correctly no longer runs in the request path (P0-1).

6. **P3 — Metrics inconsistency is a scope mismatch, not a bug.** `sql.total_queries/slow_queries` count only **request-path** SQL (incremented at `end_request`), while `sql_latency.*` is a process-global histogram incremented for **every** query including worker/startup context. With only `/metrics` scrapes completing in the drain window, `sql.total_queries=0` while `sql_latency.count=57` — both are "true", they measure different scopes.

The highest-leverage evidence-supported plan (§10): **fix the session defect, deploy leader-gated scheduling (already drafted in the working tree), add the three sweep indexes (migration already drafted), then reduce per-request round-trips on the admin write paths.** Everything else is secondary.

---

## 2. Evidence

Source: the two provided log dumps (Uvicorn startup through ~8 min of runtime) plus repo inspection.

| Fact | Evidence |
|---|---|
| 2 Uvicorn workers, each running the full lifespan | `Started parent process [1]`, `Started server process [8]` and `[9]`; **two** `resend_connected`, `queue_started`, `pubsub_listener_started`, `metrics_drain_started`, `cache_warm_started`, `Application startup complete` lines, ~1.5 s apart |
| `notification_rules` seed ran in both processes | The 914.1 ms `INSERT INTO notification_rules` appears in **both** processes' `slow_sql_top5` (timestamps 1786533400.63 and 1786533400.63 vs 1786533397.14) |
| Worker sweeps run repeatedly | `UPDATE images SET status…` at 232.8/243.6/365.2/225.4/231.8/262.6 ms (≈ every 5–25 s); `SELECT … inventory_reservations … expires_at < now()` at 235.5/262.6 ms; `SELECT notification_logs …` at 241–299 ms |
| Cache warm is lock-gated | `warm_skip_all reason=another_worker_warming` in worker 2 while worker 1 warms; `cache_warm_done endpoints_ok=4 … elapsed_ms=2613.8` |
| Remote-DB latency floor | `sql_latency.p50=119–130 ms` across **all** queries; `redis.avg_ms=1.8` (Redis is local/fast, DB is not) |
| Metrics scope split | Drains show `sql.total_queries=0, sql.total_ms=0, sql.slow_queries=0` while `sql_latency.count=45–243, p95≈190–266 ms` in the same snapshot |
| P0 session defect | Provided traceback: `AttributeError: 'function' object has no attribute 'info'` at `database.py:159` (`_session_has_writes(session)`) and `:203` (`conn.info.get("hadha_write")`) |
| Empirically reproduced | `SessionTransaction.connection` is a **function** (introspection, SQLAlchemy 2.0.36). In-memory repro: `txn.connection` → `conn.info` → `AttributeError`; `txn.connection(engine)` → `Connection` with `.info` (✓). FastAPI 0.115.5 teardown-raise → client sees **500**; swallowed variant → client sees **200** (both tested) |
| Pool not under pressure | `pool.capacity=20, peak_checked_out=4, peak_utilization_pct=20, total_checkout_waits≤221, total_wait_ms=0` |

---

## 3. Slow Query Inventory

For each query: `Query / Caller / Worker-or-endpoint / Frequency / Rows examined / Rows returned / Execution plan / Indexes used / Lock wait / CPU-IO evidence / Likely root cause / Confidence`.

### 3.1 `_session_has_writes` — NOT SQL, but a session-logic defect (P0)

```
Query:          n/a (Python)
Caller:         app.core.database.get_db teardown (after every request)
Worker/endpoint: every request that executes SQL
Frequency:      every DB-touching request
Rows examined:  n/a
Rows returned:  n/a
Execution plan: n/a
Indexes used:   n/a
Lock wait:      n/a
CPU/IO evidence: AttributeError trace observed in production
Likely root cause:
    _session_has_writes does `conn = getattr(txn, "connection", None)`.
    SessionTransaction.connection is a *method* (self, bindkey, ...) -> Connection,
    not an attribute. `getattr` returns the bound method (always truthy), and
    `conn.info.get("hadha_write")` raises AttributeError.
    Repro (self-contained, sqlite + SQLAlchemy 2.0.36):
        txn is None after a query? False
        conn type: method
        AttributeError REPRODUCED: 'function' object has no attribute 'info'
        calling txn.connection(engine) works, conn.info = <class 'dict'>
    Introduced by the P1-1 "skip COMMIT for read-only requests" change
    (present in HEAD a91cac0 lineage and in the working tree).
    Correct access: `txn.connection(sync.get_bind())` — returns the Connection
    whose `.info` the after_cursor_execute listener actually populated.
Consequences (all code-verified):
    - The crash happens at the write-check, BEFORE session.commit() runs.
    - get_db's `except` block rolls back and re-raises (the re-raise predates
      P1-1; verified via git history). FastAPI 0.115.5 builds the response
      *inside* the yield-dependency context and returns it after teardown —
      an exception here turns the response into HTTP 500 (empirically tested).
    - Therefore: write requests (Core DML only, no ORM-dirty — product PATCH,
      media upload INSERT, media status claims, etc.) are **rolled back** while
      the route already built a success body; read-only requests 500.
    - The provided `status=200` PATCH line is inconsistent with a 500 outcome
      for the same code; the two fragments are most plausibly from before vs
      after the P1-1 build went live (see §15). Either way the write is lost.
Confidence:     100 % (code + introspection + empirical repro)
```

### 3.2 `INSERT INTO notification_rules …` — 914.1 ms (P0 contributor)

```
Query:          INSERT INTO notification_rules (…~14 cols…) ON CONFLICT DO UPDATE
Caller:         app.modules.notifications.event_registry.sync_notification_rules
Worker/endpoint: FastAPI lifespan startup (per worker process)
Frequency:      once per process startup (~26 registry entries, one pg_insert each)
Rows examined:  1 (unique index on event_type)
Rows returned:  0–1
Execution plan: not captured (needs prod EXPLAIN); unique index `event_type`
Indexes used:   uq on notification_rules.event_type (unique constraint)
Lock wait:      HIGH likelihood — two processes seed the SAME 26 event_type rows
                ~1.5 s apart; the second process's INSERT blocks on the first
                process's uncommitted speculative insert for each key.
CPU/IO evidence: identical 914.1 ms in BOTH processes' slow_sql_top5 → both
                processes attempted the same insert under contention.
Likely root cause: NOT a slow statement — duplicated concurrent startup
                seeding across the 2 workers. No app triggers exist on this
                table (only one trigger in the whole codebase, migration 0025,
                unrelated). First-cold-cache insert cost is secondary.
Confidence:     85 % (lock wait inferred from the identical-duration double
                observation; EXPLAIN/pg_locks confirmable in prod)
```

### 3.3 Product SELECT (cache warm / rewarm) — 302.9 ms and 818.7 ms (P2)

```
Query:          SELECT products.id, sku, name, slug, …, COUNT(*) OVER() …
                (CatalogService.list_products, page=1 page_size=20 status=active,
                 + get_images_for_products + Image.variants selectinload)
Caller:         app.core.cache_warmer.warm_once (startup) / rewarm_after_invalidation
Worker/endpoint: cache warmer (background, lock-gated) — NOT a request path
Frequency:      once at startup (per cluster, thanks to warm lock); on
                invalidation re-warms (rate-limited 10 s)
Rows examined:  products table (filters + order + window count + 2-image
                hydration per row)
Rows returned:  20 products (+ images/variants/collections for those rows)
Execution plan: not captured; relies on products filters indexes (see repo)
Indexes used:   product filters (status/deleted_at etc.) — verify in prod
Lock wait:      none observed
CPU/IO evidence: 302.9 ms during startup warm; 818.7 ms during the media-upload
                window — same query, higher latency under concurrent worker
                activity (upload + generation + other sweeps).
Likely root cause: remote-DB RTT + serialization cost of the hydrated list;
                the 818.7 ms instance is contention, not a plan change (query
                plan instability unproven — needs EXPLAIN).
Confidence:     70 %
```

### 3.4 `UPDATE images SET status=…, updated_at=now() WHERE status=… AND updated_at<… RETURNING images.id` — 232.8–365.2 ms, repeated (P1)

```
Query:          UPDATE images SET status=$1, updated_at=now()
                WHERE status=$2 AND updated_at < $3 RETURNING id
Caller:         ImageRepository.reclaim_stale_processing
Worker/endpoint: media_generation worker (queue.py, every 5 s) — runs in BOTH
                worker processes (duplication)
Frequency:      every 5 s × 2 processes
Rows examined:  ENTIRE images table (no index on (status, updated_at))
Rows returned:  0 in steady state (few stale 'processing' rows exist)
Execution plan: sequential scan of images (inferred — no index in the model)
Indexes used:   NONE — images model defines no indexes beyond the PK
                (media/models.py has no __table_args__/Index for status)
Lock wait:      UPDATE row locks only on matched rows (rare); the cost is the scan
CPU/IO evidence: consistent 230–365 ms every tick in the logs
Likely root cause: full-table scan every 5 s, twice per cluster. Missing
                composite index (status, updated_at) — drafted as migration
                0065 in the working tree (NOT deployed).
Confidence:     90 % (model inspection; EXPLAIN in prod to confirm seq scan)
```

### 3.5 Image SELECT (list_pending_images) — 222.5–266.6 ms (P1)

```
Query:          SELECT images.id, module, preset_id, owner_type, owner_id,
                original_key, … FROM images
                WHERE status='pending' AND deleted_at IS NULL
                ORDER BY updated_at LIMIT 20
                (with Image.variants selectinload)
Caller:         media_generation.run (list_pending_images)
Worker/endpoint: media_generation worker, every 5 s × 2 processes
Frequency:      every 5 s × 2
Rows examined:  images table (status filter) + sort on updated_at
Rows returned:  ≤ 20
Execution plan: sequential scan + sort (inferred — no index)
Indexes used:   NONE
Lock wait:      none
CPU/IO evidence: 222–266 ms ticks
Likely root cause: same missing index as 3.4 (a (status, updated_at) index
                serves both the reclaim UPDATE and this ORDER BY).
Confidence:     90 %
```

### 3.6 `SELECT … FROM inventory_reservations WHERE status IN ('ACTIVE','CHECKOUT_IN_PROGRESS') AND expires_at < now() LIMIT 500` — 235.5/262.6 ms (P2)

```
Query:          SELECT id, product_id, variant_id, order_id, quantity, user_id
                FROM inventory_reservations WHERE status IN (...) AND expires_at < now()
                LIMIT 500
Caller:         ReservationService.expire_stale_reservations
Worker/endpoint: reservation_expiry worker (every 15 s) — duplicated × 2
Frequency:      every 15 s × 2
Rows examined:  indexed seek on (status, expires_at)
Rows returned:  expired reservations (≤ 500)
Execution plan: index seek — the composite index idx_inv_res_status_expires
                EXISTS (inventory/models.py line 134; migration-applied)
Indexes used:   idx_inv_res_status_expires (status, expires_at)
Lock wait:      none on this SELECT; the FOLLOW-UP per-row work locks rows
CPU/IO evidence: 235 ms despite a matching index → RTT + contention, not a scan
Likely root cause: remote-DB round-trip; plus the worker then does a per-row
                FOR UPDATE SKIP LOCKED + product lock + 2 stock UPDATEs +
                reservation UPDATE + order UPDATE (~5–6 round-trips per expired
                reservation, all sequential) — the 235 ms SELECT is the visible
                tip of a much more expensive loop.
Confidence:     85 % (index presence verified in code)
```

### 3.7 `SELECT notification_logs … WHERE status='retrying' AND next_retry_at <= now()` — 223.3–299 ms, repeated (P1)

```
Query:          SELECT * FROM notification_logs
                WHERE status='retrying' AND next_retry_at <= now()
Caller:         NotificationRepository.get_pending_retries
Worker/endpoint: notification_retry worker (every 30 s) — duplicated × 2,
                plain SELECT with no atomic claim → double-send risk
Frequency:      every 30 s × 2
Rows examined:  ENTIRE notification_logs table (no index on status/next_retry_at)
Rows returned:  pending retry logs (usually few)
Execution plan: sequential scan (inferred — model defines no indexes on these
                columns)
Indexes used:   NONE
Lock wait:      none
CPU/IO evidence: 223–299 ms per tick; table grows unbounded (no purge/retention
                exists in the notifications module — confirmed by search)
Likely root cause: missing composite index (status, next_retry_at) + unbounded
                growth + duplication.
Confidence:     90 %
```

### 3.8 `SELECT landing_sections …` (cms_publish) — 269 ms (P2)

```
Query:          SELECT landing_sections.* WHERE status='scheduled' AND scheduled_at <= now()
Caller:         cms_publish worker (every 60 s, ×2)
Frequency:      every 60 s × 2
Rows examined:  landing_sections (small table; no (status, scheduled_at) index)
Rows returned:  0 in steady state
Execution plan: sequential scan of a small-but-wide (JSONB config) table
Indexes used:   NONE
Lock wait:      none
Likely root cause: missing composite index; small absolute impact, high
                relative cost on remote DB.
Confidence:     85 %
```

### 3.9 Product PATCH 1.83 s — request timeline (P1)

```
Request:  PATCH /api/v1/admin/products/{id}  →  status 200 (or 500 under the buggy build)
SQL observed: UPDATE products … 206.6 ms  (≈ 11 % of the request)
Reconstructed timeline (source-verified call chain):
  1. require_admin:  JWT decode + get_2fa_gate_state  (1 composite EXISTS query,
                     ~120 ms RTT) + throttled admin-session touch (UPDATE, ~120 ms)
  2. _service.update:
       a. _repo.get_by_id  → _base_query = SELECT product WITH selectinload
          (images→variants, variants, attributes)  ⇒ 1 + 4 SELECTs (~5 round-trips)
       b. slug_exists (only if slug changed)  ⇒ 1
       c. _repo.update  ⇒ UPDATE products (206.6 ms) + db.get (1) + db.expire +
          get_by_id AGAIN  ⇒ another 1 + 4 SELECTs  ← the double full load
       d. if collection_ids: DELETE product_collections + per-collection INSERTs
       e. get_collections_for_product  ⇒ 1 SELECT (join product_collections)
  3. ProductResponse.model_validate(updated)  (in-memory, fast)
  4. await bust_all_product_caches(redis)  ← INLINE in request path:
       SCAN products:list:v1:* + per-key soft-expire + SCAN detail keys + DELs
       + sitemap DEL + SCAN autocomplete + DELs  (≈6–12 Redis round-trips)
  5. teardown: _session_has_writes → AttributeError → rollback → 500 (deployed
     re-raise) OR response 200 + write lost (swallowed variant)
Total ≈ 12–15 DB round-trips × ~120–250 ms + Redis bust ≈ 1.5–3.7 s.
The observed 1828.91 ms is fully explained WITHOUT any single mystery cost.
Likely root cause: query-count × remote-DB RTT, led by the double
selectinload-heavy product load and the inline cache bust. The 206 ms UPDATE
is not the problem.
Confidence: 85 % (call chain source-verified; per-query timings from logs)
```

### 3.10 Media upload ~2.96 s — phase reconstruction (P1)

```
Request:  POST /api/v1/admin/media/product/upload  → 201 (or 500 under buggy build)
Phase labels are CUMULATIVE ms-since-start (confirmed in router/service code —
they must NOT be summed). Incremental durations:
  read_file                 0      (file.read())
  normalize_orientation     726 ms (CPU executor: PIL decode/rotate/re-encode)   ← +726
  validate / probe_dims     727    (CPU executor, near-zero)                     ← +1
  r2_put_original          1803    (storage.put_original: synchronous PUT of the
                                     full original to R2 + remote ack)          ← +1076
  db_create_image          2369    (flush INSERT + refresh + refresh variants)   ← +566
  enqueue_generation       2714    (update_fields Core UPDATE ≈ 275 ms + task)   ← +345
  done                     2714
  + router: cache_bust (fire-and-forget schedule_product_list_bust — fast, P0-1),
            serialize (ImageOut.from_image — data already loaded), teardown
Request-path SQL: INSERT image; SELECT images (refresh); SELECT image_variants
(refresh variants); UPDATE images (status/metadata) = 4 round-trips ≈ 350–700 ms total.
Background (same process, after the response, NOT request-path):
  - media_generation fast-path task: try_claim_pending (UPDATE images ≈ 275 ms)
    + R2 variant uploads + variant INSERTs
  - bust loop → rewarm_after_invalidation(["products"]) → CatalogService.list_products
    ≈ products SELECT 818.7 ms + image/variant hydration + product_collections 348.8 ms
Cascade attribution:
  1. UPDATE images ~275 ms   → request's update_fields flush (enqueue phase)
  2. SELECT products ~818.7 ms → BACKGROUND rewarm (P0-1 correctly removed it
                                from the request path)
  3. SELECT images ~350.1 ms  → request's db.refresh in create_image
  4. SELECT image_variants ~699.7 ms → request's db.refresh(image,["variants"]) —
                                inflated by concurrent worker/warm load
  5. product_collections/collections ~348.8 ms → BACKGROUND rewarm hydration
Likely root cause: R2 PUT latency (~1.1 s) + CPU normalize (~0.7 s) + 4
sequential request SQL round-trips; the products/collections SELECTs are
background rewarm, not request path. Variable latency on the same queries
(F) = concurrent worker + background-warm load on the shared remote DB.
Confidence: 80 %
```

### 3.11 Crop 404 at ~352–356 ms (P3)

```
Route: PATCH /api/v1/admin/media/{image_id}/crop EXISTS (media/router.py:179).
       A 404 therefore means the image_id was not found (stale client ID /
       deleted image) or a path mismatch — not a missing route.
Latency explanation for a 404:
  require_admin (JWT + get_2fa_gate_state EXISTS ~120 ms) → get_image
  (SELECT images + selectinload variants ~120–250 ms) → HTTPException(404)
  → teardown (which under the buggy build converts the 404 into a 500).
  On a local DB this would be ~5 ms; on the remote DB it is ~350 ms.
Likely root cause: remote RTT × (admin auth gate + one image lookup). The
404 itself is a client-side stale-ID or path issue to fix in the frontend.
Confidence: 75 %
```

---

## 4. Background Worker Analysis

| Job (queue.py) | Interval | What it scans/writes | Idempotent? | Multi-process risk |
|---|---|---|---|---|
| `media_generation` | 5 s | `images` (reclaim UPDATE + pending SELECT + per-image claim/generation) | Atomic claims (`try_claim_pending` UPDATE…RETURNING) → safe per row | Runs 2× → double the 5 s ticks and the scan cost; recovery path duplicated (harmless but wasteful) |
| `reservation_expiry` | 15 s | `inventory_reservations` SELECT + per-row `FOR UPDATE SKIP LOCKED` + stock/order UPDATEs | SKIP LOCKED → safe per row | Runs 2× → double every 15 s tick (each tick is ~5–6 RTTs per expired reservation) |
| `notification_retry` | 30 s | `notification_logs` SELECT (no claim!) + provider sends | **NOT** atomic — two processes can select the same logs and both send | **Double-send risk (correctness)** |
| `cms_publish` | 60 s | `landing_sections` SELECT + status UPDATE | Re-check of status before update (verify) → mostly safe | Runs 2× → duplicate publish attempts (low risk) |
| `admin_session_cleanup` | 3600 s | `admin_sessions` DELETE | Idempotent DELETE | Runs 2× → harmless |
| `partition_manager` | monthly | DDL (IF NOT EXISTS guards) | Idempotent | Runs 2× → second is a no-op |

Every job runs inside **each** uvicorn worker because `queue.start()` is called unconditionally in the lifespan (`app/main.py`). The logs confirm `queue_started` twice with the full 6-job list.

---

## 5. Multi-Process Analysis

The production image starts `uvicorn --workers 2` (`Backend/docker/Dockerfile` production stage). Each process runs the entire lifespan. Per-startup behavior:

| Lifespan step | Per-worker behavior | Correct? |
|---|---|---|
| Resend probe | runs 2× (read-only) | Harmless |
| `register_notification_listeners` | runs 2× | **Required per worker** (in-process event bus must catch this worker's mutations) |
| `sync_notification_rules` | runs 2× → the 914 ms INSERT contention | **BUG — must be single-runner** |
| `queue.start()` | runs 2× → every job double-scheduled | **BUG — must be single-runner** (notification_retry double-send risk) |
| cache warm (`start_warm_loop`) | runs 2× but `warm_once` uses a Redis `SET NX` lock → `warm_skip_all` in the second worker | Correct (already self-gating) |
| pub/sub listener | runs 2× | **Required per worker** — SSE connections are process-local; each worker must subscribe to receive events for its own EventSource clients (pubsub.py docstring states this explicitly) |
| metrics drain | runs 2× | Correct by design (per-process profiler) |

**Conclusion:** the duplication is real and limited to the queue and the rules seed. Pub/sub and cache warm must stay per-worker/self-gated. A Redis leader-election fix that gates *only* `queue.start()` and `sync_notification_rules` (drafted in the working tree as `app/core/worker_leader.py` + `main.py` wiring, not deployed) is the correct shape; do NOT gate pubsub.

---

## 6. Cache Warming Analysis

- The startup warm is distributed-lock-gated: the second worker logs `warm_skip_all reason=another_worker_warming` — the lock works.
- The 302.9 ms product SELECT is the warm's `CatalogService.list_products` for key `products:list:v1:b78a702a3ff2` (the `warm_ok` line names the same key). It runs once per cluster at startup, competing with startup seeding + worker sweeps for DB slots — bounded, not a runtime cost.
- During the media upload, the `warm_ok products …b78a702a3ff2` line is the **background** bust-and-rewarm loop (P0-1): `_bust_cache_for` → `schedule_product_list_bust` (fire-and-forget) → bust + `rewarm_after_invalidation(["products"])`. It is NOT in the request path (verified: the media router calls the scheduled variant, not the inline `bust_product_list_cache`), but its DB work (products SELECT 818.7 ms, product_collections 348.8 ms) lands in the same log window and inflates observed "cascade" latency and DB contention.
- The **catalog PATCH path is different**: `update_product` calls `await bust_all_product_caches(redis)` **inline** — the only product write path that still blocks on the bust (SCAN + per-key soft-expire + detail scan/delete + sitemap + search scans).

---

## 7. Database Health

Could not query the live DB from this environment (no credentials/network). Read-only diagnostics to run against production (via `psql` or a read-only role, all non-destructive):

```sql
-- 1. Long-running / blocked transactions during a slow window
SELECT pid, state, wait_event_type, wait_event, now() - xact_start AS txn_age,
       now() - query_start AS query_age, left(query, 120)
FROM pg_stat_activity WHERE datname = current_database()
  AND state <> 'idle' ORDER BY query_start LIMIT 30;

-- 2. Table stats — seq scans / index usage / bloat candidates
SELECT relname, seq_scan, idx_scan, n_live_tup, n_dead_tup,
       round(100 * n_dead_tup / GREATEST(n_live_tup,1),1) AS dead_pct,
       pg_size_pretty(pg_total_relation_size(relid)) AS size
FROM pg_stat_user_tables
WHERE relname IN ('images','image_variants','notification_logs',
                  'inventory_reservations','landing_sections','products',
                  'product_collections')
ORDER BY seq_scan DESC;

-- 3. Index usage for the sweep tables
SELECT schemaname, relname, indexrelname, idx_scan
FROM pg_stat_user_indexes
WHERE relname IN ('images','notification_logs','inventory_reservations','landing_sections');

-- 4. EXPLAIN (ANALYZE, BUFFERS) — read-only, one row each, run in a slow window
EXPLAIN (ANALYZE, BUFFERS)
  UPDATE images SET status='pending', updated_at=now()
  WHERE status='processing' AND updated_at < now() - interval '120 seconds'
  RETURNING id;   -- ROLLBACK immediately afterwards to avoid mutating data
```

Known from code (no DB access needed):
- `images` and `notification_logs` models define **no** relevant indexes (verified in `media/models.py`, `notifications/models.py`).
- `idx_inv_res_status_expires (status, expires_at)` **exists** for `inventory_reservations` (still 235 ms → RTT-bound, not scan-bound).
- `notification_logs` has **no purge/retention** path anywhere in the module (search confirmed) → unbounded growth.
- Pool: capacity 20, peak checkout 4, zero wait time → no pool pressure (matches `peak_utilization_pct=20` in the drains).

---

## 8. Metrics Instrumentation Analysis

The `sql.total_queries=0 / total_ms=0 / slow_queries=0` vs `sql_latency.count=57 / p95=266.59` "disagreement" is fully explained by the profiler's two aggregation scopes (`app/core/profiling.py`):

1. **`sql.total_queries / total_ms / slow_queries`** (`_GlobalStats.as_dict()["sql"]`) are incremented **only** in `Profiler.end_request()` from per-request stats (`_PerRequestStats`), which `record_query()` fills **only** when the query runs inside a request context (`self._local.stats is not None`).
2. **`sql_latency.*`** is the process-global `LatencyHistogram`, incremented in `record_query()` for **every** query regardless of context — requests *and* workers *and* startup (cache warm, `sync_notification_rules`, media reclaim, reservation expiry, notification retry).
3. The drain windows contain only `/metrics` scrape requests (`requests_total=1–10`), which run no SQL → `sql.total_queries` stays 0, while the histogram accumulates 45–243 samples of worker/startup SQL.
4. Each of the 2 worker processes has its **own** in-memory profiler; the interleaved drains (uptime 61.5 s / 62.6 s, 121.5 / 122.6 s…) are the two processes alternating on their own 60 s `metrics_drain` loops.

**Conclusion:** both numbers are correct for what they measure; there is no counter-reset or timing bug. The real gap is that **worker SQL is invisible to `sql.total_queries`/`slow_queries`** while still firing `slow_sql` warnings and polluting the histogram — the dashboard undercounts total query volume. Fix is instrumentation, not a metric bug (§10, P3).

---

## 9. Root Causes (ranked)

| # | Root cause | Evidence | Classification |
|---|---|---|---|
| RC-1 | `_session_has_writes` calls `txn.connection` (a method) as an attribute → `AttributeError` on every non-ORM-write request → rollback + 500 (deployed re-raise) | Traceback + introspection + empirical repro (§3.1) | **P0** (correctness) |
| RC-2 | Scheduled queue + `sync_notification_rules` duplicated across 2 workers | Logs: `queue_started` ×2, identical 914.1 ms INSERT in both top5s (§3.2, §5) | **P0** (correctness + contention) |
| RC-3 | Missing indexes: `images(status, updated_at)`, `notification_logs(status, next_retry_at)`, `landing_sections(status, scheduled_at)` | Model inspection; recurring 223–365 ms scans (§3.4/3.5/3.7/3.8) | **P1** |
| RC-4 | Admin write requests = 12–15 DB round-trips × remote RTT (double selectinload product load, inline `bust_all_product_caches`) | PATCH timeline (§3.9); `_base_query`/repo code | **P1** |
| RC-5 | Upload latency = CPU normalize (~0.7 s) + synchronous R2 PUT (~1.1 s) + 4 SQL RTTs; background rewarm adds concurrent DB load | Phase marks (§3.10); `universal_service.py` | **P1** |
| RC-6 | Reservation expiry per-row loop (~5–6 RTTs per expired reservation), 15 s × 2 workers | reservation_service.py (§3.6) | **P2** |
| RC-7 | `notification_logs` unbounded growth → retry scan worsens over time | No purge found (§3.7) | **P2** |
| RC-8 | Crop 404: stale client ID + admin gate + image lookup at remote RTT (~350 ms); 404 becomes 500 under the buggy build | media router, dependencies (§3.11) | **P3** |
| RC-9 | Profiler gap: worker SQL not counted in `sql.total_queries`; dashboard understates volume | profiling.py (§8) | **P3** |

Not a root cause: the 120 ms p50 floor is remote-DB round-trip latency (proven by the indexed reservation query still taking 235 ms). Do not "fix" this with SQL changes — manage round-trip count instead.

---

## 10. Prioritized Optimization Plan

### P0-A — Fix `_session_has_writes` (unblocks every request)

```
Problem:        Every non-ORM-write request crashes at teardown → 500 + rolled-back writes.
Root cause:     txn.connection is a method, not an attribute (RC-1).
Evidence:       Traceback, introspection (SessionTransaction.connection → <function>),
                empirical repro (§3.1).
Proposed change: In _session_has_writes, obtain the real Connection:
                conn = txn.connection(sync.get_bind())  (single-engine app — safe),
                guarded by try/except so a broken session degrades to a no-op
                rather than an exception. Keep the ORM-dirty fast path first.
Expected impact: Removes the AttributeError everywhere; commits resume for
                Core-DML requests; read-only requests stop 500ing; the PATCH
                and upload writes actually persist.
Risk:           LOW (one-line semantic fix; the correct API verified in the repro).
Validation:     Unit test: real AsyncSession + Core UPDATE through get_db-style
                teardown asserts COMMIT issued and no exception. Re-run the
                full backend suite (unit/integration/stress/measurement).
Rollback:       Revert the one-line change (the buggy behavior returns — it
                must not be deployed without this fix).
```

### P0-B — Deploy single-runner scheduling (leader election) for queue + rules seed

```
Problem:        Queue jobs + notification_rules seed run in every worker (RC-2).
Root cause:     lifespan starts them unconditionally; uvicorn --workers 2.
Evidence:       Logs (§5): queue_started ×2, 914.1 ms INSERT in both processes.
Proposed change: Deploy the already-drafted fix: app/core/worker_leader.py
                (Redis SET NX + token-ownership Lua guard + heartbeat refresh
                + follower re-acquire loop) gating queue.start() and
                sync_notification_rules; pubsub/cache-warm/metrics stay as-is.
Expected impact: Halves sweep query volume; removes the double-send risk on
                notification_retry; removes the 914 ms INSERT lock-wait;
                leader crash auto-recovers within ~2 poll cycles.
Risk:           LOW-MEDIUM — new module (already unit-tested: 9 tests), fail-open
                on Redis outage so the queue is never disabled.
Validation:     Deploy → confirm exactly one queue_started per cluster and one
                worker_leader_acquired; rerun worker_leader unit tests.
Rollback:       Revert main.py wiring + worker_leader.py; queue returns to
                per-worker operation (status quo ante).
```

### P1-A — Add the three sweep indexes

```
Problem:        images/notification_logs/landing_sections sweeps scan every tick (RC-3).
Root cause:     Missing composite indexes.
Evidence:       Models define none; recurring 223–365 ms scans (§3.4/3.5/3.7/3.8).
Proposed change: Deploy the already-drafted migration 0065_worker_sweep_indexes
                (CREATE INDEX CONCURRENTLY in autocommit blocks — non-blocking):
                images(status, updated_at); notification_logs(status, next_retry_at);
                landing_sections(status, scheduled_at).
Expected impact: Sweeps become indexed seeks; the 5 s/30 s/60 s tick latency
                drops to ~RTT (≈120 ms) even before P0-B halves the tick count.
Risk:           LOW (additive, CONCURRENTLY, IF NOT EXISTS; matches 0063 convention).
Validation:     alembic upgrade head on staging; EXPLAIN before/after showing
                index scan; re-check slow_sql counts in logs.
Rollback:       Migration downgrade (DROP INDEX CONCURRENTLY IF EXISTS).
```

### P1-B — Reduce product-PATCH round-trips

```
Problem:        PATCH ≈ 12–15 RTTs; the 206 ms UPDATE is ~11 % of the request (RC-4).
Root cause:     _repo.update does Core UPDATE + re-fetch via get_by_id (with
                images→variants/variants/attributes selectinload) — a SECOND
                full load; plus inline bust_all_product_caches.
Evidence:       repository.py update()/get_by_id(); _base_query; PATCH timeline.
Proposed change:
  1. Make _repo.update use UPDATE … RETURNING (pattern already used by
     update_variant) to avoid the second full product load.
  2. Move bust_all_product_caches for the PATCH to schedule_product_list_bust
     (the same fire-and-forget path media already uses), keeping only the
     product-detail key delete inline.
Expected impact: Removes ~5 RTTs and the ~100–300 ms inline Redis bust → PATCH
                should drop to roughly half.
Risk:           LOW-MEDIUM (cache invalidation timing changes — validate the
                SWR soft-expire still guarantees a coalesced refresh).
Validation:     Re-run measurement suite PDP/PATCH path tests; k6 admin PATCH
                probe; confirm product list cache still refreshes after edit.
Rollback:       Revert to inline bust + old update.
```

### P1-C — Media upload: shrink request-path time and background contention

```
Problem:        ~2.96 s upload = CPU normalize (0.7 s) + R2 PUT (1.1 s) + 4 SQL
                RTTs; background rewarm adds concurrent load (RC-5).
Root cause:     Synchronous phases in the request path.
Evidence:       Phase marks (§3.10).
Proposed change (evaluate, don't batch blindly):
  1. create_image: drop the two db.refresh() calls after flush (the INSERT
     already returned; the response only needs fields the caller set) —
     removes 2 RTTs. Validate ImageOut.from_image works from the in-memory
     instance (it does not need the variants refresh for a fresh row).
  2. normalize_orientation: profile; consider a lighter decode pass (PIL
     thumbnail/EXIF-only rotate without full re-encode) — must preserve
     existing crop/orientation guarantees.
  3. r2_put_original: keep synchronous (correctness: the DB row must not
     reference a missing object), but measure actual upload size; if large,
     evaluate presigned client-direct upload as a separate approved project.
  4. Keep the background rewarm as-is (already off the request path) — do
     NOT pull it back inline.
Expected impact: Upload ≈ −1.2–1.6 s (two refreshes + normalize pass).
Risk:           MEDIUM for #2 (image correctness) — gate behind byte-for-byte
                crop regression tests.
Validation:     Crop/upload E2E in measurement suite + manual editor flow;
                compare generated variants before/after.
Rollback:       Revert per item.
```

### P2-A — Batch reservation expiry per-row loop

```
Problem:        5–6 RTTs per expired reservation, 15 s × 2 workers (RC-6).
Root cause:     Per-row FOR UPDATE SKIP LOCKED + stock/order updates.
Evidence:       reservation_service.py expire_stale_reservations.
Proposed change: After P0-B (single runner), batch the per-row updates into
                set-based statements (UPDATE inventory_reservations … WHERE
                id = ANY(…) AND status IN (…) RETURNING order_id for the claim,
                one UPDATE per stock target for quantities, etc.) — or at
                minimum raise the LIMIT and keep the existing row-level safety.
Expected impact: Tick cost drops from ~5–6 RTTs × N to ~3–4 RTTs total.
Risk:           MEDIUM (inventory correctness) — require the existing
                concurrency tests to pass unchanged.
Validation:     Concurrency stress (k6 inventory suite) + unit tests.
Rollback:       Revert batching.
```

### P2-B — Notification-log retention

```
Problem:        notification_logs grows unbounded; scans get worse over time (RC-7).
Proposed change: A monthly cron (reuse partition_manager pattern or a new
                job) archiving/deleting logs older than ~90 days (keep
                status='retrying' and recent), plus P1-A's index.
Risk:           LOW; keep audit-relevant history.
```

### P3 — Metrics + instrumentation

```
Problem:        Worker SQL invisible in sql.total_queries; slow threshold at
                200 ms fires constantly against the ~120 ms RTT floor (RC-9).
Proposed change: (a) Document the scope semantics in /health/metrics and the
                report; (b) add a worker-context counter (increment global
                sql_queries_total in record_query when stats is None) so the
                dashboard matches the histogram; (c) revisit the 200 ms
                threshold only AFTER P0/P1 land — do not raise it to hide
                the scan costs it is currently (correctly) surfacing.
Risk:           LOW.
```

---

## 11. Expected Impact

| Metric | Before (log evidence) | After (P0-A + P0-B + P1-A) | After (+P1-B/P1-C) |
|---|---|---|---|
| `slow_sql` warning volume | ~1 per 5–25 s from sweeps | Sweeps become indexed seeks + half the tick count | — |
| `images`/`notification_logs` sweep latency | 223–365 ms | ~RTT (≈120–150 ms) | — |
| `INSERT notification_rules` | 914 ms | one-runner → no lock wait | — |
| Admin PATCH | 1828 ms (12–15 RTTs) | unchanged until P1-B | ≈900–1100 ms |
| Media upload | ~2958 ms | unchanged until P1-C | ≈1400–1800 ms |
| Request error rate | 500s on every DB request under the buggy build | zero (defect gone) | — |
| Queue double-send risk | real (notification_retry) | removed | — |

---

## 12. Risks

1. **Deploying the current build without P0-A is the biggest risk**: every DB-backed request 500s / Core writes are silently rolled back. Validate the live SHA first (§15).
2. Leader election: fail-open on Redis outage (both workers run the queue) is an accepted trade-off (same as cache warmer) — document it.
3. Index migration uses CONCURRENTLY (non-blocking) but still consumes IO on a large `images`/`notification_logs` table — run in a low-traffic window.
4. P1-B/P1-C change cache-timing and image-refresh semantics — each needs its own regression coverage before promotion.
5. Do not raise the 200 ms slow threshold pre-fix; it is currently surfacing real scans.

---

## 13. Validation Plan

1. **Live-state confirmation (blocker for everything):** verify the deployed image's git SHA and reproduce one DB-backed request against production — is it 200 or 500? This decides whether P0-A is an emergency hotfix or a scheduled fix.
2. **Per-fix gates:** unit tests → integration (api_smoke + comprehensive) → stress → measurement harness → frontend storefront vitest/tsc/lint (only if frontend files change) — the exact commands are documented in AGENTS.md and the measurement harness `tests/measurement/`.
3. **Live SQL validation:** the read-only SQL in §7 (pg_stat_activity during a slow window, index-usage stats, EXPLAIN ANALYZE for the three sweeps with immediate ROLLBACK).
4. **k6:** reuse `k6/smoke/prod-readiness.js` (read-only) after each deploy wave to compare p95 per endpoint; controlled load only against staging.
5. **BEFORE/AFTER:** same probes, same environment (production) and same time-of-day; no cross-environment comparisons.

---

## 14. Items Explicitly NOT Recommended

1. **Do NOT raise `PERF_SLOW_SQL_THRESHOLD_MS` to quiet the logs** — it would hide the real scans while the ~120 ms RTT floor is a separate, documented fact.
2. **Do NOT add an index to `inventory_reservations`** — `idx_inv_res_status_expires` already exists; the 235 ms is RTT/contention, and the plan should target the per-row loop instead.
3. **Do NOT gate or remove the per-worker pub/sub listener** — SSE connections are process-local; a single-listener design would silently break real-time updates on the other worker.
4. **Do NOT move the media upload's R2 PUT to fire-and-forget** without a correctness design: the DB row references the object; the current ordering (upload → insert) is deliberate.
5. **Do NOT reintroduce `DISCARD ALL` (P0-2) or per-request COMMIT (P1-1)** — those changes are sound; P1-1's bug is the `txn.connection` access, not the read-only-commit idea.
6. **Do NOT rewrite the catalog query set "while we're in there"** — P1-B is scoped to the update path.
7. **Do NOT treat the 914 ms INSERT as a statement-level problem** — fixing duplication (P0-B) is the fix; a batched multi-VALUES insert is optional polish, not the root cause.

---

## 15. Open Questions

1. **Deployed SHA / live behavior (blocker).** The provided logs contain both `status=200` (PATCH) and the `_session_has_writes` AttributeError trace. Under the code in HEAD (re-raise), a request that reaches `_session_has_writes` returns **500** — so the 200 line and the trace cannot be from the same build. Which is live *right now*? Run one DB-backed request and check the status, and confirm `git rev-parse HEAD` of the deployed image.
2. **Row counts / table sizes** for `images`, `notification_logs`, `inventory_reservations`, `landing_sections` (drives the exact index benefit; §7 queries).
3. **EXPLAIN plans** for the three sweep queries and the product list query (to confirm seq scans vs index seeks and any plan instability behind the 302→818 ms spread).
4. **Upload object size + R2 region** — is the ~1.1 s R2 PUT dominated by bytes or by network path? Is the R2 bucket in the same region as the server?
5. **Is the storefront currently returning 500s?** If the buggy build is live, every product/cart/PDP GET is affected; confirm before scheduling, not after.
6. **Trigger/constraint inventory** on `notification_rules` — none in app code; confirm none added by hand in the production DB.

---

## STOP CONDITION

Analysis complete. Per the agreed workflow (`LOGS → ROOT-CAUSE INVESTIGATION → EVIDENCE → PLAN → USER APPROVAL → IMPLEMENTATION → TESTING → BEFORE/AFTER`), **no fixes have been implemented in this pass** (the working tree's earlier-drafted leader-election module, sweep-index migration, and related tests from the prior approved phase are present but explicitly **not deployed** — deploying them is a separate, approved action). Wait for explicit approval of this plan before changing database code, SQL, indexes, worker architecture, cache warming, upload architecture, object storage behavior, middleware, or routes.

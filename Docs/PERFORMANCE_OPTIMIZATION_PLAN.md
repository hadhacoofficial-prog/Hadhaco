# Performance Optimization Plan — Hadha.co

Companion to `PERFORMANCE_ROOT_CAUSE_ANALYSIS.md`. **No code was changed.**
This is the proposal awaiting approval. Every item carries the full required
template. Expected improvements are estimates — Phase 0 measures before/after.

---

## Priority matrix

| ID | Area | Severity | Effort | Risk | Est. win |
|----|------|----------|--------|------|----------|
| P0-0 | Measurement — expose profiler + add perf log file | P0 | S | None | Enables everything below |
| P0-1 | Cache bust → fire-and-forget + pipelined soft-expire | P0 | S | Low | Removes 10–1000ms from every media op response |
| P0-2 | Drop per-request `DISCARD ALL` | P0 | S | Med | Removes 1 round-trip + re-prepare per request |
| P1-1 | Commit only when dirty in `get_db` | P1 | S | Med | Removes 1 round-trip per read-only request |
| P1-2 | Coalesce admin auth gate queries | P1 | M | Low | −2 DB round-trips per admin request |
| P1-3 | PDP loader → `ensureQueryData` hydration | P1 | S | Low | −1 blocking request per PDP view (~half product traffic) |
| P1-4 | Scope SSE invalidation per event/user | P1 | M | Med | Stops catalog stampedes on others' actions |
| P2-1 | Redundant admin queries (variant re-read, double image_variants) | P2 | S | Low | −1–2 queries on admin list/variant endpoints |
| P2-2 | SWR for product detail | P2 | S | Low | Cold-miss detail stops blocking |
| P3-1 | Remove legacy cart BroadcastChannel double-post | P3 | S | Low | −1 duplicate invalidation per cross-tab mutation |
| P3-2 | Fix stale storage.py docstring | P3 | S | None | Docs only |

Phases: **0** measurement → **1** P0 items → **2** P1 items → **3** P2/P3 + docs.
Each phase ends with re-run of full linter suite + affected tests + a
measured before/after on the target endpoint.

---

## P0-0 — Measurement first (Phase 0)

- **Problem:** No perf logs on disk; profiler is in-memory only. Root causes
  F1–F3 cannot be confirmed with real numbers, only code evidence.
- **Root cause:** `app/core/profiling.py` records to memory; nothing
  serializes it; `GET /health/metrics` is the only window.
- **Current:** In-memory pool/SQL/Redis/cache/bust/endpoint profiler;
  `main.py:344`.
- **Proposed:**
  1. Add a structured perf log (JSON-lines via structlog) at WARN level for
     slow operations (SQL ≥ 200ms, busts, auth gate, R2) — reusing the
     existing `perf.*` loggers (`router.py:34`).
  2. Expose `/health/metrics` without auth to a monitor, or add
     `log.drain_metrics()` that flushes the profiler snapshots to the log
     every N seconds.
  3. Capture 24–48h baseline: p50/p95/p99 for `/products`, PDP, admin media
     upload/crop/replace, and the auth gate.
- **Files:** `app/core/profiling.py`, `app/core/database.py`, `app/main.py`,
  `app/modules/media/router.py`.
- **Functions:** `profiler.record_*`, `get_db`, `start_warm_loop`.
- **DB:** none. **Backend:** logging + config only. **Frontend:** none.
- **Migration:** none. **Risk:** none. **Rollback:** remove the log drains.
- **Expected improvement:** enables accurate before/after for P0-1..P2-2.
- **Validation:** perf log lines present with p95 latency per endpoint.

---

## P0-1 — Cache bust: fire-and-forget + pipelined soft-expire

- **Problem:** Every media upload/crop/replace/reorder/set-primary/delete
  waits synchronously on `SCAN` + N sequential GET→rewrite→SETEX round-trips
  (up to 1.0s scan budget) before responding (`analysis F1`).
- **Root cause:** `app/core/redis.py:223-271` runs `bust_product_list_cache`
  inline; `app/modules/media/router.py:52` `await`s it in the request.
- **Current:** soft-expire (reader herd fixed); bust still blocks the writer.
  `cache_warmer.rewarm_after_invalidation` exists but is not wired in.
- **Proposed (choose one):**
  - **A — background task (recommended):** wrap the bust in
    `asyncio.create_task` (guard against GC + keep a set of in-flight tasks).
    Response returns immediately; the soft-expired entries guarantee the next
    reader still gets stale-serve + one coalesced refresh.
  - **B — Redis PIPELINE:** rewrite keys in a single `redis.pipeline()` round
    trip (still need GET first for decompress; use a Lua script to do
    get+rewrite+setex atomically in one round-trip per key or via
    `eval`). Keeps sync timing but cuts round-trips to ~1.
  - **C — rewarm hook:** call `rewarm_after_invalidation(["products"])`
    fire-and-forget after soft-expire so the next visitor finds a fully fresh
    entry (complements A).
  - Recommend **A + C**.
- **Files:** `app/core/redis.py`, `app/modules/media/router.py`,
  `app/core/cache_warmer.py`.
- **Functions:** `bust_product_list_cache`, `_soft_expire_swr_entry`,
  `_bust_cache_for`, `rewarm_after_invalidation`.
- **DB:** none. **Backend:** async task util + wiring. **Frontend:** none.
- **Migration:** none. **Risk (A):** task killed on shutdown → worst case the
  entries stay soft-expired and SWR refreshes lazily (graceful). Use
  `asyncio.shield`/task registry and cancel-on-shutdown.
- **Rollback:** revert to inline await (previous behavior).
- **Expected improvement:** media op response drops by (bust time), typically
  10–1000ms depending on keyspace.
- **Validation:** `profiler.record_bust_product_list_cache` shows bust no
  longer on the request path; media upload p95 improves; storefront list
  still fresh after a bust.

---

## P0-2 — Stop issuing `DISCARD ALL` per request

- **Problem:** one server round-trip + prepared-statement re-prepare on every
  connection return to pool (`analysis F2`).
- **Root cause:** pool reset handler unconditionally runs `DISCARD ALL`
  (`app/core/database.py`).
- **Current:** runs on every checkout/return; pool `pre_ping` off (deliberate
  for Supabase session-mode PgBouncer).
- **Proposed:**
  1. Remove `DISCARD ALL` from the per-return path (transactions are already
     rolled back/closed by session lifecycle; connection state is reset on
     COMMIT/ROLLBACK anyway).
  2. If any leak concern remains, scope it to error paths only (run
     `ROLLBACK`/`DISCARD` when an exception escapes `get_db`), not on success.
- **Files:** `app/core/database.py`.
- **Functions:** `get_db`, pool reset event handler.
- **DB:** connection-state policy only, no schema change. **Backend:** 1 file.
  **Frontend:** none.
- **Migration:** none.
- **Risk:** if the app ever issues session-scoped GUCs/`SET`s that must not
  leak to the next user, they could survive. Audit: grep for `SET `,
  `LISTEN`, `NOTIFY` outside of dedicated code. If found, scope DISCARD to
  only those paths.
- **Rollback:** restore the reset handler.
- **Expected improvement:** −1 round-trip + re-prepare cost per request.
- **Validation:** DB session checkouts per request drop by 1 (profiler pool
  counters); p95 on read-only endpoints improves.

---

## P1-1 — Commit only when dirty

- **Problem:** `COMMIT` after every request including read-only GETs
  (`analysis F3`).
- **Root cause:** `get_db` unconditional commit (`app/core/database.py`).
- **Current:** commit-on-success regardless of writes; `autoflush=False`,
  `expire_on_commit=False`.
- **Proposed:** track dirty/used-session; `await db.commit()` only if the
  session made writes (SQLAlchemy `Session.dirty`/`new`/`deleted` or a
  `transaction.attached` flag). Rollback on exception as today.
- **Files:** `app/core/database.py`.
- **Functions:** `get_db`.
- **DB:** none. **Backend:** 1 file. **Frontend:** none.
- **Migration:** none. **Risk:** a write that previously relied on the
  unconditional commit being "free" now must call `db.commit()` explicitly —
  audit any handler that mutates then returns without committing. **Rollback:**
  unconditional commit.
- **Expected improvement:** −1 round-trip per read-only request; removes
  transaction-open overhead on the storefront path.
- **Validation:** p95 on `/products` and PDP backend latency improves;
  existing write endpoints still commit (regression tests).

---

## P1-2 — Coalesce admin auth gate

- **Problem:** 3–4 sequential DB round-trips before every admin handler
  (`analysis F4`).
- **Root cause:** separate SELECTs for profile/2FA/2FA-verified + throttled
  UPDATE in `dependencies.py` → `service.py:120,328,506`.
- **Current:** JWKS cached (good); the auth DB chain is the admin overhead.
- **Proposed:**
  1. Combine 2FA + session-verified checks into one SQL query (single
     `WHERE id=%s AND admin_2fa_enabled AND session_2fa_verified`).
  2. Cache `is_admin_session_2fa_verified` in Redis with a short TTL
     (mirrors `ADMIN_SESSION_ACTIVITY_THROTTLE`) so repeated calls skip DB.
- **Files:** `app/core/dependencies.py`, `app/modules/auth/service.py`,
  `app/core/redis.py`.
- **Functions:** `has_active_2fa`, `is_admin_session_2fa_verified`,
  `touch_admin_session_activity`, `require_admin`.
- **DB:** one new composite query (read-only). **Backend:** 2 files.
  **Frontend:** none.
- **Migration:** none. **Risk:** cache poisoning of 2FA state → use short TTL
  + bust on 2FA enable/disable. **Rollback:** revert to sequential checks.
- **Expected improvement:** −2 DB round-trips per admin request (~10–30ms).
- **Validation:** admin endpoint latency measured; 2FA disable still takes
  effect immediately.

---

## P1-3 — PDP: hydrate query cache from loader

- **Problem:** duplicate `GET /products/{slug}` per PDP load (`analysis F5`).
- **Root cause:** loader fetches raw, never seeds the key the `useQuery`
  polls (`products.$slug.tsx:55-78` vs `:136-146`); both `cache:"no-cache"`.
- **Current:** 2 identical requests; no `setQueryData`/`dehydrate`/`ensureQueryData`
  anywhere in the storefront.
- **Proposed:** follow the established idiom from `products.index.tsx:54-61`:
  in the loader, `queryClient.ensureQueryData({ queryKey: queryKeys.products.stock(slug), queryFn: () => api.get(...), staleTime: 30_000 })`, then reuse the result for the rendered product. The `useQuery` then resolves from cache for `staleTime` and only refetches on the 60s poll or confidence drop.
- **Files:** `storefront/src/routes/products.$slug.tsx`.
- **Functions:** route `loader`, `ProductPage`.
- **DB:** none. **Backend:** none. **Frontend:** 1 file (+ possibly
  `router.tsx` to expose `queryClient` in route context — verify it already
  is; `products.index.tsx` uses `context: { queryClient }` so it exists).
- **Migration:** none. **Risk:** low — behavior identical, one fewer request.
- **Rollback:** restore raw loader fetch.
- **Expected improvement:** −1 blocking request per PDP view; halves product-
  detail API/DB load from storefront.
- **Validation:** network tab shows 1 (not 2) `/products/{slug}` on load;
  poll still fires at 60s.

---

## P1-4 — Scope SSE invalidation

- **Problem:** one shopper's reservation/stock event refetches every list +
  stock query on every connected client (`analysis F6`).
- **Root cause:** unfiltered fan-out (`pubsub.py:179-188`); bare-prefix
  invalidations (`["products"]` etc.); `productIds` param unused
  (`inventory.sync.ts:25-45`).
- **Current:** blast radius = all `products.*`, `collections`, `search`,
  `cms.homepage`, `categories`, plus `orders`/`cart` on reservation_expired.
- **Proposed (staged):**
  1. **Targeted keys:** invalidate `queryKeys.products.stock(slug)` and
     `queryKeys.products.detail(slug)` for the event's `productIds` when the
     event carries them, instead of `products.all`. Keep a coarse list bust
     only for events that actually change list membership (price/status/featured).
  2. **Per-user routing:** route `reservation_created/expired` only to the
     owning user (compare `userId`/`userIds` in payload) for `orders`/`cart`
     invalidation; keep stock events broadcast but targeted per product.
  3. **Use `productIds`:** thread the payload's product ids through
     `invalidateServerLists`.
- **Files:** `packages/shared-api/src/lib/sync/{inventory.sync,reservation.sync,cart.sync,checkout.sync}.ts`; `app/core/pubsub.py`; `app/core/events.py`.
- **Functions:** `invalidateServerLists`, sync module handlers, `_listen_redis`,
  `_event_to_sse_payload`.
- **DB:** none. **Backend:** pubsub routing. **Frontend:** sync modules.
- **Migration:** none.
- **Risk (2):** per-user routing must not break multi-tab sessions (same user,
  multiple tabs — route by user, not by tab). Keep cart/orders invalidation
  per-user, stock per-product broadcast.
- **Rollback:** restore bare-prefix invalidations.
- **Expected improvement:** catalog refetch traffic on foreign reservation
  events → near zero; PDP stock queries only refetch when *their* product
  changes.
- **Validation:** open 2 clients; A reserves stock; B sees NO product-list
  refetch, only targeted stock for that slug (or none if not viewing it).

---

## P2-1 — Redundant admin queries

- **Problem/Current:** admin products list fetches `image_variants` twice;
  `update_variant` re-reads the same row 2–3×; admin collections does
  `COUNT` + `SELECT` (`analysis F7`).
- **Proposed:** eager-load once (`selectinload`) and reuse; drop the COUNT
  and use `len()` on the already-fetched rows (or a single windowed query);
  cache row reads in the variant update path.
- **Files:** admin products/collections/variants services + repos.
- **DB:** none. **Backend:** services/repos. **Frontend:** none.
- **Migration:** none. **Risk:** low. **Rollback:** revert per-hunk.
- **Expected improvement:** −1–2 queries on those admin endpoints.
- **Validation:** profiler shows query counts drop; endpoint tests pass.

---

## P2-2 — SWR for product detail

- **Problem/Current:** detail cache is plain TTL 600 + ETag, no SWR — a cold
  miss blocks on DB and re-misses during bursts (`analysis F8`).
- **Proposed:** reuse the `cache_swr` wrapper (same as public list) for detail
  keys with a fresh-session background refresh; keep ETag for clients.
- **Files:** `app/modules/catalog/router.py` (+ `core/cache.py` helpers already exist).
- **DB:** none. **Backend:** router change. **Frontend:** none.
- **Migration:** none. **Risk:** stale-serve window at TTL (acceptable; same
  as list). **Rollback:** restore plain TTL path.
- **Expected improvement:** PDP detail never blocks on DB under burst.
- **Validation:** load test on `/products/{slug}` after expiry — no latency spike.

---

## P3-1 — Remove legacy cart BroadcastChannel double-post

- **Problem/Current:** `stores/cart.ts:31-40` posts raw `"cart-changed"` AND
  `SyncBus.emit(CART_CHANGED)` broadcasts the serialized event → remote tabs
  dispatch `CART_CHANGED` twice per mutation (`analysis F9`).
- **Proposed:** delete the legacy raw post + its re-emit listener
  (`cart.ts:173-192`); keep only SyncBus.
- **Files:** `storefront/src/stores/cart.ts`.
- **Frontend only.** **Risk:** low. **Rollback:** restore the listener.
- **Expected improvement:** −1 duplicate cross-tab invalidation.
- **Validation:** cross-tab cart change invalidates `["cart"]` exactly once
  (instrument invalidation count).

---

## P3-2 — Docs: fix stale storage.py comment

- **Problem/Current:** `app/modules/media/storage.py` docstring says variant
  generation "runs synchronously in-request"; actual architecture is the
  worker (`analysis §2`).
- **Proposed:** update docstring. **Docs only**, no behavior change.

---

## Rollback strategy (global)

All changes are code/config-level with no schema migration and no
destructive DB/Redis changes. Each item's rollback is listed above; a
phase-level revert is `git revert` of the phase's commits (kept as discrete,
reviewable commits).

## Verification workflow

1. After each phase: Black → Ruff → Mypy (backend); ESLint --fix → tsc
   (frontend); run affected tests; re-run full lint suite.
2. Measure before/after on the target endpoint via Phase-0 instrumentation.
3. Only report complete after all checks pass and numbers are captured.

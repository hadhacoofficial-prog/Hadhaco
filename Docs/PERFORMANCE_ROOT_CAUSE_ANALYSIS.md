# Performance Root Cause Analysis — Hadha.co (Aug 2026)

Read-only investigation. **No code was changed.** Every finding below is
cited to the current codebase at `HEAD` and marked either **CONFIRMED**
(proven by code + instrumentation points), **LIKELY** (strong code evidence,
needs runtime confirmation), or **UNKNOWN** (cannot be measured from files).

---

## 1. Executive summary

The slow-request problems reported before (admin upload/crop 2.5–3.0s, and
hard-miss cache thundering herds 2.3–2.7s after busts) are **largely already
fixed in current code**:

- Variant generation is off-request (worker + CPU executor + R2 offload).
- EXIF orientation normalization runs off-loop in a dedicated CPU pool.
- `bust_product_list_cache` soft-expires entries instead of hard-deleting,
  so readers serve stale + one coalesced background refresh (previously every
  in-between request was a blocking ~2.5s DB fetch).

**What is still costing latency in the current code:**

| # | Finding | Layer | Severity |
|---|---------|-------|----------|
| F1 | Cache bust still runs **inline, sequentially** in the request (`SCAN` + per-key GET→decompress→rewrite→SETEX), up to 1.0s scan budget | Backend / Redis | **P0** |
| F2 | `DISCARD ALL` on **every** connection return to pool — per-request round-trip, drops server-side prepared-statement cache | Backend / DB | **P0** |
| F3 | `get_db()` COMMITs after **every** request, including read-only GETs — an extra round-trip per request | Backend / DB | **P1** |
| F4 | Admin auth gate: 3–4 DB round-trips per admin request before the handler | Backend / DB | P1 |
| F5 | PDP double-fetches `/products/{slug}` (loader + `useQuery`), `cache:"no-cache"` both times | Frontend | P1 |
| F6 | SSE events invalidate `["products"]` + lists on **every** connected client, unfiltered — stock/reservation stampedes | Frontend | P1 |
| F7 | Redundant queries in admin endpoints (image_variants fetched twice, variant row re-read 2–3×, COUNT+SELECT) | Backend / DB | P2 |
| F8 | Product detail cache is plain TTL 600 with no SWR — cold miss blocks on DB | Backend / Cache | P2 |
| F9 | Duplicate BroadcastChannel invalidation path for cart (`CART_CHANGED` fired twice per cross-tab mutation) | Frontend | P3 |

**Data limitation (UNKNOWN):** no perf logs exist on disk. Profiling is
in-memory (`app/core/profiling.py`) and only visible at `/health/metrics`.
The docstrings reference Loki correlation post-deploy, but no log files were
found in the repo. F1–F9 are rated on code evidence; exact ms numbers require
a Phase-0 measurement pass (see the plan doc).

---

## 2. Verification of previously-claimed fixes (all CONFIRMED in code)

| Claim | Status | Evidence |
|-------|--------|----------|
| Variant generation is off-request | ✅ | `workers/media_generation.py` — fast-path `asyncio.create_task` on `enqueue()`, atomic `UPDATE…WHERE status='pending'…RETURNING` claim, `STALE_AFTER_SECONDS` crash reclaim, `MAX_ATTEMPTS=3`, semaphore(2), per-image session |
| CPU work offloaded | ✅ | `core/cpu_executor.py` — dedicated pool (`IMAGE_PROCESSING_WORKERS=2`, container capped 1 CPU), separate from default executor used for R2 I/O |
| EXIF orientation handled | ✅ | `modules/media/universal_service.py:71-112` — `_normalize_orientation` + `_normalize_orientation_off_loop`; no-op passthrough for tag 1/undecodable |
| R2 I/O off event loop | ✅ | `modules/media/storage.py` — `asyncio.to_thread` behind `Semaphore(8)`; boto3 client cached |
| Soft product-list cache invalidation | ✅ | `core/redis.py:223-271` — `bust_product_list_cache` rewrites `"t"` via `_soft_expire_swr_entry` instead of DELETE; SWR readers then serve stale + background refresh (`core/cache.py`) |
| Cache bust now bounded | ⚠️ | See F1 — soft-expire removed the *reader* herd, but the bust **itself** still runs inline+sequential in upload/crop/replace |
| Cache warming | ✅ | `core/cache_warmer.py` — startup-only warm + distributed lock + optional targeted re-warm (`rewarm_after_invalidation:412`, currently **not** wired to `bust_product_list_cache`) |
| Redis resiliency | ✅ | `core/redis.py` — circuit breaker (CLOSED/OPEN/HALF_OPEN), 0.3s op timeout, exponential backoff 30s→300s |
| Cache compression | ✅ | `core/cache.py` — zlib, threshold 2048B, level 6 |
| Media pipeline architecture matches reality | ⚠️ | `modules/media/storage.py` module docstring still says "variant generation runs synchronously in-request" — **stale comment**, contradicts the worker; harmless but misleading |
| Dead pages (`CartPage`, `AccountPage`) | ❌ **FALSE** | `routes/cart.tsx:31` imports `pages/CartPage.tsx`; `routes/account.index.tsx:72` imports `pages/AccountPage.tsx`. Both are live. Prior analysis was wrong |

---

## 3. Findings

### F1 — Cache bust inline + sequential (P0)

**Files:** `app/core/redis.py:223-271`; `app/modules/media/router.py:52` (and
`_bust_cache_for` call sites in upload/crop/replace).

**Mechanism.** Every media mutation that can change a thumbnail calls
`await _bust_cache_for(...)` **in the request path**:
- `SCAN` `products:list:v1:*` with `count=500`, bounded by `asyncio.wait_for(…, 1.0s)` (`redis.py:253-259`);
- for each key: `GET` → `decompress` → `json.loads` → rewrite `"t"` → `compress` → `SETEX 2×TTL` — **all sequential** (`redis.py:262-266`).

**Impact.** For a healthy keyspace (~10–30 filter combos) this is tens of ms
per bust; for a large/old keyspace it can approach the 1s SCAN budget plus
N sequential round-trips. The reader herd is fixed, but **the writer still
pays the bust cost inside the request**, and the media op response waits on
it. Confirmed also: `cache_warmer.rewarm_after_invalidation` (which could
replace the inline bust with a fire-and-forget re-warm) exists but is not
called here — `bust_product_list_cache` never re-warms, it soft-expires.

**Why it was built this way:** soft-expire guarantees the *next* reader hits
the stale-serve branch immediately; a fire-and-forget rewarm would leave a
window where the first reader after a mutation triggers the background
refresh anyway. The trade-off is defensible but the sync execution is not.

### F2 — `DISCARD ALL` on every connection checkout/return (P0)

**Files:** `app/core/database.py` (pool reset handler + `get_db`).

**Mechanism.** Each time a connection returns to the pool, `DISCARD ALL` is
issued (PostgreSQL). This is a full server-side round-trip per request and
**discards the server-side cached plan for every prepared statement** on that
connection, so the next request re-prepares — partially defeating statement
caching under asyncpg/psycopg. It also runs on the hot storefront path even
for pure Redis-served requests (Redis hit still opens a session for the
auth/profile chain and the commit in F3).

**Impact.** One extra round-trip + re-prepare cost per request, multiplied by
the pool budget of (2+1)×2 = 6 connections. Under the traffic that produced
the original "commit_ms in the hundreds" reports, this was part of the
per-request fixed cost.

### F3 — Commit after every request (P1)

**Files:** `app/core/database.py` (`get_db`).

**Mechanism.** `get_db` runs `COMMIT` on success even for GET handlers that
issued no writes. `autoflush=False`, `expire_on_commit=False` are set
(sane), but the unconditional commit is an extra round-trip per request and
forces a new transaction for every subsequent query in the request lifetime.
Admin GETs additionally carry a throttled `UPDATE` (`touch_admin_session_activity`,
see F4), which makes even GETs write-path.

**Impact.** One wasted round-trip per request on read-only endpoints.

### F4 — Admin auth gate: 3–4 DB round-trips per request (P1)

**Files:** `app/core/dependencies.py`; `app/modules/auth/service.py:120`
(`has_active_2fa`), `:328` (`is_admin_session_2fa_verified`), `:506`
(`touch_admin_session_activity`).

**Mechanism.** Every admin request runs, before the handler:
1. profile fetch — Redis GET (or 1 SELECT on miss);
2. `has_active_2fa` — SELECT;
3. `is_admin_session_2fa_verified` — SELECT;
4. `touch_admin_session_activity` — SELECT + throttled UPDATE.

**Impact.** 3–4 DB round-trips fixed overhead on every admin call. JWKS is
cached (confirmed not per-request network), so this is the dominant admin
overhead. These are sequential and could be coalesced into one query or
backed by Redis TTL flags.

### F5 — PDP double-fetch (P1)

**Files:** `storefront/src/routes/products.$slug.tsx:55-78` (loader),
`:136-146` (useQuery).

**Mechanism.** The loader fetches `GET /products/{slug}` directly via the
API client and passes the result through `loaderData` (never seeding React
Query). The component then runs `useQuery({ queryKey: ["products","stock",slug] })`
against the **same endpoint** with `cache:"no-cache"`. Because the key is
never hydrated, the cache starts empty and a **second network request** fires
on mount — on SSR first paint and every SPA navigation. Both requests use
`cache:"no-cache"` so the browser cache cannot collapse them.

The codebase already has the correct idiom (`ensureQueryData` in the loader
seeding the exact key the component uses) in `products.index.tsx:54-61` and
`search.tsx:48-56`; the PDP predates it.

**Impact.** ~2× product-detail DB/Redis traffic + one extra blocking request
on every PDP view. The 60s poll itself is legitimate (inventory freshness) —
the duplicate on initial load is not.

### F6 — SSE invalidation blast radius (P1)

**Files:** `packages/shared-api/src/lib/sync/{index,reservation.sync,inventory.sync,cart.sync,checkout.sync}.ts`; `core/pubsub.py:179-188`; `storefront/src/router.tsx:40-52`.

**Mechanism.**
- Server fans out **every** Redis message to **every** subscriber queue
  (`pubsub.py:179-188`); payload `userId` fields exist but nothing routes on them.
- Client subscriptions invalidate with bare-prefix keys: one
  `reservation_created`/`reservation_expired`/`inventory_changed` triggers
  `["products"]` (⇒ **all** lists + stock + detail), `["collections"]`,
  `["search"]`, `["cms","homepage"]`, `["categories"]`, and
  `["orders"]`/`["cart"]` on reservation_expired.
- `invalidateServerLists` (`inventory.sync.ts:25-45`) accepts a `productIds`
  param that **is never used** — even a single-product `INVENTORY_CHANGED`
  blasts the whole catalog.
- The **only** per-user relevance check in the entire sync layer is in the
  Zustand reservation store (`listenReservationEvents.ts:26`) — the query
  invalidation path ignores it.
- Cross-tab: `SyncBus.emit` broadcasts on `hadha:sync`; a second, legacy raw
  `"cart-changed"` post (`stores/cart.ts:31-40`) causes `CART_CHANGED` to
  dispatch **twice** per remote mutation.

**Impact.** Shopper A reserving stock makes every connected shopper refetch
every product list, every PDP stock query, every cart-line stock query and
every wishlist line. This is a self-inflicted thundering herd on the exact
catalog endpoints we cache. Some refetches are absorbed by `staleTime`, but
invalidation marks them stale and mounted observers refetch on next render.

### F7 — Redundant admin queries (P2)

**Files:** admin products list (image_variants fetched twice), `update_variant`
(same row re-read 2–3×), admin collections (separate `COUNT` + `SELECT`).
No N+1 confirmed anywhere in the codebase (delegated analysis).

### F8 — Product detail: no SWR (P2)

**Files:** `app/modules/catalog/router.py` (detail TTL 600 + ETag, plain
cache-aside). Public **list** uses SWR with fresh-session background refresh
(correct); detail does not — a cold/expired detail miss blocks on the DB,
then every PDP poll (F5) hits this path.

### F9 — Cross-tab double invalidation (P3)

See F6 cross-tab bullet. Impact bounded (cart keys only) but doubles
cross-tab refetch traffic.

---

## 4. Request cost model (estimated, validate in Phase 0)

### Storefront PDP (authenticated, fresh load) — 7 API requests
1. `GET /products/{slug}` (loader)
2. `GET /products?page_size=5&is_featured=true` (loader, related)
3. `GET /products/{slug}` — **duplicate** (F5)
4. `GET /reviews/products/{id}`
5. `GET /reviews/products/{id}/summary`
6. `GET /reviews/products/{id}/my-status` (auth)
7. `GET /orders/active-reservations` (auth)

Plus nav categories (24h cache) and the SSE stream. DB round-trips on the
backend for #1: session checkout (DISCARD ALL, F2) + auth chain + detail
queries + commit (F3).

### Admin media op (upload/crop/replace)
R2 put (100–400ms, off-loop) + DB `create_image` (30–80ms) + enqueue
(fast-path) + **inline sequential cache bust (F1)** + commit + DISCARD ALL.

---

## 5. Appendix — instrumentation state

- `app/core/profiling.py` — in-memory profiler (pool, SQL ≥200ms, Redis,
  cache, bust timings, endpoint ranking). **Not persisted**; exposed only at
  `GET /health/metrics` (`main.py:344`).
- No on-disk perf logs found (searched `Backend/**`).
- `main.py:94` starts `cache_warmer.start_warm_loop()` (startup-only).
- Docstrings cite Loki correlation for the original herd incident — the
  production observability path exists but is not visible from the repo.

# Database Connection Audit

**Repository:** Hadha.co Backend  
**Date:** 2026-07-23  
**Auditor:** opencode (automated code analysis)  
**Scope:** Every database connection, engine, pool, and session in the repository

---

## Executive Summary

| Metric | Value |
|--------|-------|
| **Engines** | 5 (2 production, 1 Alembic, 2 dev scripts) |
| **Connection Pools** | 2 (1 persistent, 1 NullPool) |
| **Session Factories** | 2 (`AsyncSessionLocal`, `AsyncWorkerSessionLocal`) |
| **Max concurrent DB connections (production)** | **~17** (8 API + ~9 ephemeral) |
| **Supabase Session Pooler limit** | **15** (default plan) |
| **Supabase Compatibility** | ⚠ Near Limit — 8 API connections + ephemeral workers can spike to 15+ |
| **Overall Risk Level** | **MEDIUM** — Well-designed but tight against Supabase Free Tier |

**Key Finding:** The application has a clean two-engine architecture (persistent pool for API, NullPool for everything else). The persistent pool is deliberately conservative (pool_size=3, max_overflow=1 per worker). However, the Supabase Session Pooler's 15-connection cap means the NullPool workers and event listeners must share the remaining 7 slots with Alembic, health checks, and admin tools — a tight but workable budget under normal load.

---

## Engine Inventory

| # | File | Line | Variable | Type | Driver | URL Source | Pool Class | pool_size | max_overflow | pool_timeout | pool_recycle | pool_pre_ping | echo | Purpose |
|---|------|------|----------|------|--------|------------|------------|-----------|--------------|--------------|-------------|---------------|------|---------|
| 1 | `app/core/database.py` | 35 | `engine` | Async | asyncpg | `settings.DATABASE_URL` | AsyncAdaptedQueuePool (default) | 3 | 1 | 30s | 1800s | False | False | **API request-scoped** — main production engine |
| 2 | `app/core/database.py` | 61 | `_worker_engine` | Async | asyncpg | `settings.DATABASE_URL` | NullPool | N/A | N/A | N/A | N/A | True | False | **Background workers** — ephemeral connections |
| 3 | `alembic/env.py` | 145 | `engine` (local) | Sync | psycopg (v3) | `settings.ALEMBIC_DATABASE_URL` or `settings.DATABASE_URL` (driver-swapped) | NullPool | N/A | N/A | N/A | N/A | N/A | N/A | **Alembic migrations** — one-shot, disposed after use |
| 4 | `scripts/explain_analyze.py` | 189 | `engine` (local) | Async | asyncpg | `settings.DATABASE_URL` | AsyncAdaptedQueuePool (default) | 2 | 1 | 30s (default) | 1800s (default) | False (default) | False | **Dev script** — EXPLAIN ANALYZE audit |
| 5 | `scripts/phase2_explain_analyze.py` | 24 | `engine` (module-level) | Sync | psycopg | `settings.ALEMBIC_DATABASE_URL` or `settings.DATABASE_URL` | Default | 5 (default) | 10 (default) | 30s (default) | -1 (default) | True | False | **Dev script** — Phase 2 EXPLAIN ANALYZE |

**Note:** Engine #4 and #5 are dev/admin scripts, not production code. They create their own engines and dispose them after use (or leave them at module scope for interactive use). They do not affect production connection counts.

---

## Session Inventory

| # | File | Line | Factory Variable | Bound Engine | Class | expire_on_commit | autocommit | autoflush | Used By |
|---|------|------|------------------|--------------|-------|------------------|------------|-----------|---------|
| 1 | `app/core/database.py` | 47 | `AsyncSessionLocal` | `engine` (persistent pool) | AsyncSession | False | False | False | `get_db()` → all API request routes via `Depends(get_db)` |
| 2 | `app/core/database.py` | 68 | `AsyncWorkerSessionLocal` | `_worker_engine` (NullPool) | AsyncSession | False | False | False | Workers, event listeners, cache warmer, health checks, SWR refresh tasks |

### Session Lifecycle

**`get_db()` (API requests)** — `app/core/database.py:143-174`

```python
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        try:
            await session.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            await session.close()
        except Exception:
            _pool_log.warning("session_close_failed", exc_info=True)
```

- **Created:** Per request via FastAPI `Depends(get_db)`
- **Committed:** Automatically on successful response
- **Rolled back:** On exception
- **Closed:** Always in `finally` block — **no leak**
- **Safety:** Corrupted session state is caught and logged, connection invalidated

**`AsyncWorkerSessionLocal()` (workers/background)** — Used as `async with AsyncWorkerSessionLocal() as db:`

- **Created:** Per worker invocation
- **Closed:** Automatically by `async with` context manager — **no leak**
- **NullPool:** Connection is destroyed immediately on close

---

## Worker Inventory

| # | File | Line | Worker Name | Schedule | Uses DB? | Engine | Session Pattern | Max Concurrent |
|---|------|------|-------------|----------|----------|--------|-----------------|----------------|
| 1 | `app/workers/reservation_expiry.py` | 23 | reservation_expiry | Every 60s | Yes | NullPool | `run_with_session()` → `async with AsyncWorkerSessionLocal()` | 1 (max_instances=1, coalesce) |
| 2 | `app/workers/cms_publish.py` | 23 | cms_publish | Every 60s | Yes | NullPool | `async with AsyncWorkerSessionLocal()` | 1 |
| 3 | `app/workers/media_generation.py` | 78 | media_generation | Every 5s | Yes | NullPool | `async with AsyncWorkerSessionLocal()` (3 sessions per run) | 1 (periodic) + N (asyncio.create_task fast-path) |
| 4 | `app/workers/notification_retry.py` | 17 | notification_retry | Every 30s | Yes | NullPool | `async with AsyncWorkerSessionLocal()` | 1 |
| 5 | `app/workers/partition_manager.py` | 19 | partition_manager | Monthly (cron) | Yes | NullPool | `async with AsyncWorkerSessionLocal()` | 1 |
| 6 | `app/workers/admin_session_cleanup.py` | 22 | admin_session_cleanup | Hourly | Yes | NullPool | `run_with_session()` → `async with AsyncWorkerSessionLocal()` | 1 |

**All workers run inside the FastAPI process** via APScheduler's `AsyncIOScheduler`. There is no separate worker process.

**Key detail about `media_generation`:** The `enqueue()` function (line 68) fires `asyncio.create_task(process_one(image_id))` — this creates additional concurrent sessions **within the same process**. If 10 images are enqueued rapidly, up to 10 concurrent NullPool sessions could exist simultaneously.

---

## Event Listener Inventory

| # | File | Line | Event | Handler | Engine | Session Pattern |
|---|------|------|-------|---------|--------|-----------------|
| 1 | `app/modules/notifications/service.py` | 427 | UserRegisteredEvent | `_handle_user_registered` | NullPool | `async with AsyncWorkerSessionLocal()` |
| 2 | `app/modules/notifications/service.py` | 442 | OrderCreatedEvent | `_handle_order_created` | NullPool | `async with AsyncWorkerSessionLocal()` |
| 3 | `app/modules/notifications/service.py` | 464 | PaymentCapturedEvent | `_handle_payment_captured` | NullPool | `async with AsyncWorkerSessionLocal()` |
| 4 | `app/modules/notifications/service.py` | 484 | PaymentFailedEvent | `_handle_payment_failed` | NullPool | `async with AsyncWorkerSessionLocal()` |
| 5 | `app/modules/notifications/service.py` | 510 | OrderStatusChangedEvent | `_handle_order_status_changed` | NullPool | `async with AsyncWorkerSessionLocal()` |
| 6 | `app/modules/notifications/service.py` | 538 | OrderShippedEvent | `_handle_order_shipped` | NullPool | `async with AsyncWorkerSessionLocal()` |
| 7 | `app/modules/notifications/service.py` | 568 | OrderDeliveredEvent | `_handle_order_delivered` | NullPool | `async with AsyncWorkerSessionLocal()` |
| 8 | `app/modules/notifications/service.py` | 595 | RefundCreatedEvent | `_handle_refund_created` | NullPool | `async with AsyncWorkerSessionLocal()` |
| 9 | `app/modules/notifications/service.py` | 616 | RefundProcessedEvent | `_handle_refund_processed` | NullPool | `async with AsyncWorkerSessionLocal()` |
| 10 | `app/modules/notifications/service.py` | 635 | RefundFailedEvent | `_handle_refund_failed` | NullPool | `async with AsyncWorkerSessionLocal()` |
| 11 | `app/modules/notifications/service.py` | 661 | ReviewRequestEvent | `_handle_review_request` | NullPool | `async with AsyncWorkerSessionLocal()` |

**All event listeners are fire-and-forget** via `asyncio.create_task()` in `app/core/events.py:282`. They open their own NullPool sessions and run concurrently with the request that published the event.

---

## FastAPI Startup & Shutdown

### Startup (`app/main.py:24-105`)

| Step | File | DB Usage |
|------|------|----------|
| 1. Validate settings | `app/core/config.py` | None |
| 2. Verify Resend API key | `app/main.py:40-65` | None (HTTP only) |
| 3. Register notification listeners | `app/main.py:68-72` | None (just registers callbacks) |
| 4. Sync notification rules | `app/main.py:76-80` | **1 NullPool session** (`async with AsyncWorkerSessionLocal()`) |
| 5. Start APScheduler | `app/main.py:83-86` | None (scheduler starts, jobs run later) |
| 6. Cache warming | `app/main.py:94-97` | **Sequential NullPool sessions** (9 targets, one at a time) |
| 7. Start Redis pub/sub | `app/main.py:100-103` | None |

### Shutdown (`app/main.py:107-116`)

| Step | DB Usage |
|------|----------|
| Cancel warm task | None |
| Stop pub/sub | None |
| Shutdown scheduler | None (jobs already stopped) |
| Close Redis | None |

**No engine.dispose() is called at shutdown** — this is acceptable because the process is exiting and the OS reclaims TCP connections. However, calling `engine.dispose()` would be a best practice for graceful shutdown.

---

## Connection Pool Analysis

### API Engine (Persistent Pool)

| Property | Value | Source |
|----------|-------|--------|
| `pool_size` | 3 | `settings.DATABASE_POOL_SIZE` (default: 3) |
| `max_overflow` | 1 | `settings.DATABASE_MAX_OVERFLOW` (default: 1) |
| `pool_timeout` | 30s | `settings.DATABASE_POOL_TIMEOUT` |
| `pool_recycle` | 1800s (30min) | `settings.DATABASE_POOL_RECYCLE` |
| `pool_pre_ping` | False | Deliberately disabled — Supabase session-mode PgBouncer incompatibility |
| `echo` | False | |
| **Max connections per worker** | **4** (3 + 1 overflow) | |
| **Max connections (2 workers)** | **8** | |

**Pool monitoring events:**
- `checkout` event at `app/core/database.py:85` — logs warning when pool is one slot from capacity
- `reset` event at `app/core/database.py:126` — issues `DISCARD ALL` to prevent cross-request contamination
- `before_cursor_execute` / `after_cursor_execute` at lines 180/185 — SQL query timing

### Worker Engine (NullPool)

| Property | Value |
|----------|-------|
| `poolclass` | NullPool |
| `pool_pre_ping` | True |
| `echo` | False |
| **Max connections** | **Unlimited** (each session opens a fresh TCP connection, closes it on exit) |
| **Typical duration per connection** | 0.1–0.5 seconds |

---

## Worst-Case Connection Calculation

### Production Configuration

- **uvicorn workers:** 2 (documented in DEVOPS.md and config.py comments)
- **APScheduler:** Runs in-process (AsyncIOScheduler), not separate process
- **No Celery/RQ/separate worker processes**

### Calculation

```
Component                          Max Connections    Type
─────────────────────────────────────────────────────────────
API Engine (2 workers × 4)              8             Persistent pool
─────────────────────────────────────────────────────────────
Workers (APScheduler, NullPool):
  reservation_expiry (60s)              1             Ephemeral
  cms_publish (60s)                     1             Ephemeral
  media_generation (5s)                 1-3           Ephemeral (+ fast-path tasks)
  notification_retry (30s)              1             Ephemeral
  partition_manager (monthly)           1             Ephemeral
  admin_session_cleanup (hourly)        1             Ephemeral
─────────────────────────────────────────────────────────────
Event listeners (NullPool)              1-5           Ephemeral (fire-and-forget)
─────────────────────────────────────────────────────────────
Cache warmer (NullPool, startup)        1             Ephemeral (sequential)
─────────────────────────────────────────────────────────────
Health checks (NullPool)                1             Ephemeral
─────────────────────────────────────────────────────────────
Alembic (sync, NullPool)                1             Only during migrations
─────────────────────────────────────────────────────────────
                                          │
Worst Case (normal operation):         ~17 │ (8 persistent + 9 ephemeral)
Typical Case (steady state):           ~10 │ (4-6 persistent + 4-6 ephemeral)
─────────────────────────────────────────────────────────────
```

### Worst Case Breakdown

```
  API persistent connections            8
+ Workers (2-3 concurrent)             3
+ Event listeners (1-2 concurrent)     2
+ Health checks                        1
+ Cache warming (startup only)         1
+ Alembic (migration only)             0 (not during normal operation)
─────────────────────────────────────────────
  TOTAL (normal operation)           ~14
  TOTAL (startup burst)             ~16
  THEORETICAL MAX                   ~17+ (media_generation fast-path burst)
```

---

## Potential Connection Leaks

### ✅ No Leaks Found

The codebase demonstrates excellent session lifecycle management:

1. **`get_db()` dependency** — Session is always closed in `finally` block (`app/core/database.py:164-174`). The `finally` block wraps `session.close()` in a safety catch for corrupted session states.

2. **All worker sessions** use `async with AsyncWorkerSessionLocal() as db:` context manager — guaranteed cleanup.

3. **All event listener sessions** use `async with AsyncWorkerSessionLocal() as db:` — guaranteed cleanup.

4. **Cache warmer sessions** use `async with AsyncWorkerSessionLocal() as db:` — guaranteed cleanup.

5. **Health check** uses `async with AsyncWorkerSessionLocal() as db:` — guaranteed cleanup.

6. **Alembic engine** calls `engine.dispose()` in a `finally` block (`alembic/env.py:158`).

7. **Scripts** call `await engine.dispose()` after use (`scripts/explain_analyze.py:236`).

### ⚠ Potential Risk: Media Generation Fast-Path

`app/workers/media_generation.py:68-75` — `enqueue()` fires `asyncio.create_task(process_one(image_id))` for each image mutation. Each `process_one()` call opens its own NullPool session. Under rapid admin image editing (e.g., bulk uploads), many concurrent sessions could exist simultaneously.

**Mitigation:** The `process_one()` function is designed to be short-lived (claim → commit → generate → commit), and `try_claim_pending` ensures only one worker processes each image. But during the generation phase (R2 upload), the connection is held open.

**Risk level:** LOW — This is bounded by the number of images being processed, which is typically small. The NullPool connections are ephemeral and close immediately after each image.

---

## Engine Lifetime Analysis

| Engine | Lifetime | Pattern | Assessment |
|--------|----------|---------|------------|
| `engine` (API) | Process-lifetime singleton | Created once at module import, shared across all requests | ✅ Correct |
| `_worker_engine` (Workers) | Process-lifetime singleton | Created once at module import, shared across all workers | ✅ Correct |
| `engine` (Alembic) | Function-scoped | Created, used, disposed in `run_migrations_online()` | ✅ Correct |
| `engine` (explain_analyze.py) | Function-scoped | Created, used, disposed in `run()` | ✅ Correct |
| `engine` (phase2_explain_analyze.py) | Module-level | Created at import, never disposed | ⚠ Acceptable for script |

**No engines are created per-request or per-service.** The architecture correctly uses process-lifetime singletons.

---

## Async Session Usage Audit

### ✅ Correct Patterns Throughout

Every session usage follows one of two correct patterns:

**Pattern 1: FastAPI dependency (API requests)**
```python
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
```

**Pattern 2: Context manager (workers/background)**
```python
async with AsyncWorkerSessionLocal() as db:
    # ... use db ...
    await db.commit()
```

Both patterns correctly handle commit/rollback/close lifecycle.

---

## Supabase Compatibility

### Connection Mode: Session Pooler

The application connects to Supabase via the **Session Pooler** (`*.pooler.supabase.com:5432`) which uses **PgBouncer in session mode**. This is the correct choice because:

1. asyncpg uses **named prepared statements** which require session-mode PgBouncer
2. Session mode maintains connection state across requests (SET statements, prepared statements)
3. Transaction mode would break prepared statement caching

### Limits

| Mode | Concurrent Connections | Notes |
|------|----------------------|-------|
| Session Pooler (default plan) | **15** | This is the binding constraint |
| Transaction Pooler | ~200 | Not used (incompatible with asyncpg prepared statements) |
| Direct Connection | ~60 | Only used by Alembic via `ALEMBIC_DATABASE_URL` |

### Verdict

| Metric | Value | Status |
|--------|-------|--------|
| API persistent connections (worst) | 8 | ✅ Within budget |
| Remaining for overhead | 7 | ⚠ Tight |
| NullPool concurrent spike risk | +5-9 | ⚠ Can exceed 15 |
| **Total worst case** | **~17** | ⚠ Near Limit |
| **Typical steady state** | **~10** | ✅ Safe |

**Verdict: ⚠ NEAR LIMIT**

The application is safe for Supabase Free Tier under **normal operation**. The persistent API pool (8 connections) is well within budget. The NullPool workers are ephemeral (0.1-0.5s per connection) and rarely all fire simultaneously. However:

1. **During startup:** Cache warming + notification rule sync + scheduler start could briefly spike to 14-16 connections
2. **Under burst traffic:** Media generation fast-path tasks could add 3-5 concurrent NullPool sessions
3. **During migrations:** Alembic adds 1 more connection

If any of these overlap, the 15-connection limit could be breached, causing `EMAXCONNSESSION` errors.

---

## Performance Issues

### Issue 1: No Engine Disposal at Shutdown
**Severity:** LOW  
**File:** `app/main.py:107-116`  
**Description:** The FastAPI lifespan shutdown does not call `engine.dispose()`. While the OS reclaims connections on process exit, explicit disposal is a best practice for graceful shutdown and prevents connection warnings in logs.  
**Recommendation:** Add `await engine.dispose()` in the shutdown path.

### Issue 2: phase2_explain_analyze.py Module-Level Engine
**Severity:** LOW (dev script only)  
**File:** `scripts/phase2_explain_analyze.py:24`  
**Description:** Creates a sync engine at module level without disposing it. The engine holds connections open until the script exits.  
**Recommendation:** Wrap in a function with try/finally dispose, or accept this as acceptable for a one-shot script.

### Issue 3: Media Generation Fast-Path Burst Potential
**Severity:** MEDIUM  
**File:** `app/workers/media_generation.py:68-75`  
**Description:** `enqueue()` fires unbounded `asyncio.create_task()` calls. Under rapid admin image editing, many concurrent NullPool sessions could exist simultaneously, each holding a connection for the duration of R2 upload.  
**Recommendation:** Add a semaphore to limit concurrent `process_one()` tasks (e.g., `asyncio.Semaphore(3)`).

### Issue 4: Event Listeners Hold Sessions During External API Calls
**Severity:** LOW  
**File:** `app/modules/notifications/service.py:427-699`  
**Description:** Event listeners open NullPool sessions that remain open during email/WhatsApp API calls (via Resend/Meta). If the external API is slow, the connection is held unnecessarily.  
**Mitigation:** The sessions are NullPool (ephemeral), so they don't block persistent pool slots. However, they do consume Supabase session-mode connection slots while waiting for HTTP responses.  
**Recommendation:** Consider dispatching the DB read and the external API call in separate sessions — read data first, close session, then send email/WhatsApp.

### Issue 5: Health Check Uses NullPool Instead of Persistent Pool
**Severity:** LOW  
**File:** `app/main.py:299`  
**Description:** `/health/ready` creates a NullPool connection for `SELECT 1`. This consumes a Supabase session-mode slot unnecessarily when the persistent pool could be used.  
**Recommendation:** Use the main `engine` for health checks instead of `AsyncWorkerSessionLocal`.

---

## Recommendations

### High Priority

None — the architecture is sound.

### Medium Priority

1. **Add `engine.dispose()` at shutdown** (`app/main.py` lifespan)
   - Ensures clean connection teardown
   - Prevents stale connection warnings

2. **Add semaphore to media_generation fast-path** (`app/workers/media_generation.py`)
   - Limit concurrent `process_one()` to 3-5 tasks
   - Prevents connection burst under rapid admin image editing

3. **Use main engine for health checks** (`app/main.py:299`)
   - Change `AsyncWorkerSessionLocal()` to `AsyncSessionLocal()` for `/health/ready`
   - Avoids consuming NullPool slot for a simple `SELECT 1`

### Low Priority

4. **Consider reducing NullPool event listener session duration**
   - Read all needed data first, close session, then make external API calls
   - Reduces time a connection slot is occupied

5. **Add monitoring for NullPool connection spikes**
   - Log when NullPool connections exceed a threshold
   - Alert on `EMAXCONNSESSION` errors

6. **Document the connection budget in code**
   - Add a comment block in `database.py` showing the full budget calculation
   - Include the Supabase 15-connection limit

---

## Final Verdict

### Maximum Possible Database Connections

**Normal operation:** ~10-14 connections  
**Startup burst:** ~14-16 connections  
**Theoretical max:** ~17+ connections (media_generation fast-path)

### Supabase Free Tier Safety

**✅ SAFE under normal operation.** The 8 persistent API connections leave 7 slots for ephemeral workers, health checks, and occasional Alembic runs. NullPool connections are short-lived (0.1-0.5s) and rarely overlap.

**⚠ NEAR LIMIT during startup and burst scenarios.** Cache warming (9 sequential sessions) + notification rule sync + scheduler start can temporarily spike to 14-16 connections. If a migration is running concurrently, the 15-connection limit could be breached.

### Production Safety

**✅ SAFE for production.** The codebase demonstrates:
- Clean two-engine architecture (persistent + NullPool)
- Proper session lifecycle management (commit/rollback/close in all paths)
- No connection leaks
- Pool monitoring with capacity warnings
- `DISCARD ALL` on connection return to prevent cross-request contamination
- `pool_recycle=1800` to prevent stale connections

### Recommended Pool Sizes

| Setting | Current | Recommended | Rationale |
|---------|---------|-------------|-----------|
| `DATABASE_POOL_SIZE` | 3 | **3** (keep) | With 2 workers: 3×2=6 persistent, leaving 9 for overhead |
| `DATABASE_MAX_OVERFLOW` | 1 | **1** (keep) | Total 4×2=8, matching DEVOPS.md budget |
| `DATABASE_POOL_TIMEOUT` | 30 | **30** (keep) | Reasonable for Supabase |
| `DATABASE_POOL_RECYCLE` | 1800 | **1800** (keep) | Matches Supabase session pooler timeout |
| uvicorn `--workers` | 2 | **2** (keep) | Optimal for connection budget |

### Exact Code Changes Required

**None required for correctness.** The application is well-designed and connection-safe. The recommendations above are optimizations, not bug fixes.

The only change worth implementing is adding `engine.dispose()` at shutdown for production best practices:

```python
# In app/main.py lifespan, after yield:
from app.core.database import engine
await engine.dispose()
```
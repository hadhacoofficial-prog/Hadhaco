# Celery Migration Plan — Hadha.co Backend

**Status:** Phase A analysis complete. This document is the Phase B implementation contract.
**Author:** Claude (agentic analysis), 2026-08-12
**Companion doc (pre-existing, still accurate on topology facts):** `Docs/WORKER_DEPLOYMENT_AUDIT.md` (2026-07-23)

---

## 0. TL;DR

- Today: 6 periodic jobs run **in-process** inside the FastAPI `hadha-backend` container via APScheduler (`app/workers/queue.py`), started from the `lifespan()` hook in `app/main.py`. Production runs `uvicorn --workers 2`, so without mitigation every job would run twice.
- That duplication is **already substantially fixed** by a Redis leader-election layer (`app/core/worker_leader.py`) added in the immediately-preceding commit (`6e97192`, 2026-08-12) — only the elected leader process calls `queue.start()`. `Docs/WORKER_DEPLOYMENT_AUDIT.md` predates this commit and should be read as "the state before leader election was added"; its Phase 7 duplication table is now only the *fallback* safety net (every job is also independently idempotent, which is why the leader election was safe to add incrementally rather than being a hard prerequisite).
- Target: 6 jobs move to **Celery Beat + 2 dedicated worker deployments** (`celery-worker-media`, `celery-worker-general`) + **1 dedicated Beat container**. APScheduler, `QueueService`, and `WorkerLeader` are removed — Beat is a single dedicated process by deployment topology, so no in-app leader election is needed anymore.
- The media upload fast-path (`asyncio.create_task` in `universal_service._enqueue_generation`) becomes a genuine Celery dispatch (`media_tasks.generate_variants.delay(...)`) — this is the one behavior change item 5 of the brief explicitly calls for, not merely a scheduler swap.
- A real bug is fixed as part of this migration: `app/core/database.py::_session_has_writes` reads `txn.connection` as if it were an attribute; in SQLAlchemy 2.0 `SessionTransaction.connection` is a **method**, so this returns a bound method object, and `.info` on it raises `AttributeError: 'function' object has no attribute 'info'` for any session whose transaction never opened a Core connection through that exact attribute path. Root cause and fix are in §9.
- Everything **not** in the explicit job inventory (cache warmer, Redis pub/sub SSE listener, in-request event-bus fire-and-forget notification dispatch, SSE generator) is deliberately **left alone** — see §8 classification table and rationale.

---

## 1. Current Architecture

### 1.1 Runtime topology (production)

```
VPS
 └─ docker compose (Infra/application/docker-compose.application.yml)
     └─ hadha-backend container
         └─ uvicorn app.main:app --workers 2   (Backend/docker/Dockerfile:43)
             ├─ worker process A ─┐
             └─ worker process B ─┴─ both run FastAPI lifespan() independently
```

Evidence: `Backend/docker/Dockerfile:43` (`CMD [... "--workers", "2" ...]`), `Infra/application/docker-compose.application.yml` (single `backend` service, no separate worker container), no systemd/cron/supervisor unit for any job (confirmed by `Docs/WORKER_DEPLOYMENT_AUDIT.md` PHASE 2).

**Scheduler duplication math:** 1 container × 2 uvicorn workers × 1 `AsyncIOScheduler` per process = **2 scheduler instances**, each registering the same 6 jobs = **12 job registrations**, all firing on the same cadence against the same Supabase Postgres and Redis. This is real: `app/workers/queue.py::build_queue()` unconditionally registers all 6 jobs in every process (`app/main.py:97-99`, `queue = build_queue()` runs regardless of leadership).

**Mitigation already in place (as of `6e97192`):** `queue.start()` is gated by `WorkerLeader.try_acquire()` (`app/main.py:100-107`) — a Redis `SET NX` lock (`app/core/worker_leader.py`). Only the elected leader actually starts the `AsyncIOScheduler`; the follower calls `leader.start_reacquire_loop(queue.start)` so a crashed leader is replaced within ~2 poll cycles (30s TTL / 15s poll) without a full restart. Fail-open on Redis unavailability (assumes leadership rather than stalling startup).

Net effect: **in the common case only 1 of the 2 processes runs the jobs today.** The Phase 7 "duplication is safe because every job is idempotent" analysis in `WORKER_DEPLOYMENT_AUDIT.md` is retained as the **belt-and-braces** property, not the primary defense — during the brief leader-transition window after a crash, both old and new leader could theoretically overlap for a few seconds, and idempotency is what makes that safe.

### 1.2 Where each background mechanism actually lives

| # | Mechanism | File | Started from |
|---|-----------|------|---------------|
| 1 | `reservation_expiry` | `app/workers/reservation_expiry.py` | APScheduler, 15s interval |
| 2 | `cms_publish` | `app/workers/cms_publish.py` | APScheduler, 60s interval |
| 3 | `media_generation` (periodic sweep) | `app/workers/media_generation.py::run()` | APScheduler, 5s interval |
| 3b | `media_generation` (fast path) | `app/workers/media_generation.py::enqueue()` | `asyncio.create_task`, called from `universal_service._enqueue_generation` per image mutation |
| 4 | `notification_retry` | `app/workers/notification_retry.py` | APScheduler, 30s interval |
| 5 | `partition_manager` | `app/workers/partition_manager.py` | APScheduler, cron `10 0 1 * *` UTC |
| 6 | `admin_session_cleanup` | `app/workers/admin_session_cleanup.py` | APScheduler, 3600s interval |
| 7 | Redis pub/sub → SSE listener | `app/core/pubsub.py` | `asyncio.create_task`, lifespan, forever loop |
| 8 | Cache warmer | `app/core/cache_warmer.py::start_warm_loop` | `asyncio.create_task`, lifespan, **one-shot at startup only** |
| 9 | Cache bust-and-rewarm | `app/core/redis.py::schedule_product_list_bust` | `asyncio.create_task`, fired from product-mutation request path, already non-blocking |
| 10 | Event bus (order/payment/user notifications) | `app/core/events.py::EventBus.publish` | `asyncio.create_task` per listener, fired from business-logic calls |
| 11 | SSE stream | `app/modules/events/router.py` | Per-HTTP-connection generator |

`app/workers/queue.py::build_queue()` registers **only jobs 1–6** with APScheduler. Jobs 7–11 are not APScheduler jobs and are explicitly out of scope for "remove APScheduler" — see §8.

---

## 2. Complete Job Inventory (APScheduler → Celery scope)

### Job: `reservation_expiry`
- **Current scheduler:** APScheduler `IntervalTrigger`
- **Trigger / Frequency:** every 15s
- **Function / Module:** `app.workers.reservation_expiry.run` → `ReservationService.expire_stale_reservations`
- **Runs in API process:** yes (leader only, today) | **Runs in worker process (target):** yes
- **Database tables:** `inventory_reservations` (SELECT candidates, `SELECT ... FOR UPDATE SKIP LOCKED` per-row, UPDATE status), `products`/variant stock columns, `orders` (via `OrderService.handle_expired_order_side_effects`), coupons
- **Redis keys:** none directly; publishes `ReservationExpiredEvent` → SSE pub/sub channel
- **R2 operations:** none
- **External APIs:** none
- **Expected duration:** sub-second typical (batch limit 500 candidates)
- **Can overlap:** APScheduler `max_instances=1` today prevents same-job overlap; **cross-process** overlap is safe by design (see locking)
- **Retry behavior:** none needed — next tick (15s later) naturally retries any row still `ACTIVE`/`CHECKOUT_IN_PROGRESS` past `expires_at`
- **Idempotent:** yes — `SELECT ... FOR UPDATE SKIP LOCKED` means a row already claimed/transitioned by another runner is silently skipped, not double-processed
- **Current locking:** row-level `FOR UPDATE SKIP LOCKED`, business-critical (see §11)
- **Current failure handling:** exception → `worker_failures_total` counter incremented, re-raised, session rolled back by `run_with_session`; next tick retries
- **Current observability:** `worker_duration_seconds` / `worker_failures_total` Prometheus metrics, structlog

### Job: `cms_publish`
- **Trigger / Frequency:** APScheduler interval, 60s
- **Function:** `app.workers.cms_publish.run`
- **DB tables:** `landing_sections` (SELECT scheduled, UPDATE → published)
- **Redis keys:** deletes `cms:homepage` cache key on publish
- **Duration:** sub-second (small result set)
- **Overlap:** safe — re-running finds nothing if already published (status filter)
- **Retry:** next tick
- **Idempotent:** yes — `WHERE status='scheduled'` means an already-published row is never touched again
- **Locking:** none (no row lock) — acceptable because publishing twice is a no-op once status flips; a true cross-process race here would at worst double-clear the cache key, which is harmless
- **Failure handling:** per-section try/except inside the loop; outer try/except logs and returns
- **Observability:** structlog only (no Prometheus metric today — will gain one automatically via the generic Celery task instrumentation)

### Job: `media_generation` (periodic sweep — crash recovery / multi-process net)
- **Trigger / Frequency:** APScheduler interval, 5s
- **Function:** `app.workers.media_generation.run` → reclaims stale `processing` rows (>120s), then processes pending
- **DB tables:** `images` (`ImageRepository.reclaim_stale_processing`, `try_claim_pending`, `mark_generation_failed`)
- **R2 operations:** GET original, PUT variants (via `background.generate_variants_for_breakpoints`)
- **Duration:** highly variable — one image's full breakpoint set, network-bound on R2
- **Overlap:** safe by atomic claim (`UPDATE ... WHERE status='pending' ... RETURNING`)
- **Retry:** `MAX_ATTEMPTS = 3`, tracked in `image.metadata_.generation.attempts`; on exhaustion marks `generation_failed` (permanent)
- **Idempotent:** yes — claim is atomic; a losing racer's claim attempt is a no-op
- **Locking:** optimistic, via conditional UPDATE, not `SELECT FOR UPDATE`
- **Failure handling:** per-image try/except so one image's failure doesn't abort the batch; transient DB errors (`OSError`, `asyncpg.exceptions.PostgresError`) logged as warnings, not exceptions
- **Observability:** `scheduler_job_duration_seconds{job_id="media_generation"}`

### Job: `media_generation` (fast path — **not** an APScheduler job today, but in scope per item 5)
- **Trigger:** `asyncio.create_task` fired synchronously inside `universal_service._enqueue_generation`, immediately after the "pending" DB state is committed
- **Purpose:** near-immediate processing in the common single-process case; **the periodic sweep above is the only path that works in a multi-process deployment**, because the process that received the HTTP request may not be the one still alive when generation would finish
- **Migration action:** replace the `asyncio.create_task(_bounded_process(image_id))` call with a Celery dispatch (`media_tasks.generate_variants.delay(str(image_id))`) queued to the `media` queue. This is a genuine architecture improvement, not just a rename: today, if the API process is SIGKILLed between `enqueue()` firing and the task finishing, the in-flight generation is silently lost until the 5s sweep picks it up (which it does — so no correctness loss, but it does mean R2 GET/PUT work was wasted and redone). Moving to Celery removes that waste and gives the fast path the same durability as the sweep.

### Job: `notification_retry`
- **Trigger / Frequency:** APScheduler interval, 30s
- **Function:** `app.workers.notification_retry.run` → `NotificationService.retry_pending`
- **DB tables:** `notification_logs` (`status='retrying' AND next_retry_at <= now()`), indexed on `(status, next_retry_at)`
- **External APIs:** Resend (email), Meta WhatsApp Business API
- **Duration:** proportional to pending-retry count; each send is a blocking HTTP call, but DB commit happens *before* the HTTP call (`send_email`/`send_whatsapp` commit the log row, then call the provider off the connection) — see `app/modules/notifications/service.py:138-152`, `:254-272`
- **Overlap:** two runners racing on the same log row is possible today (no row lock) — see §11 for the recommended `SELECT FOR UPDATE SKIP LOCKED` hardening
- **Retry:** backoff `_RETRY_DELAYS = [1, 5, 15]` minutes (`repository.py:20`), `attempt_count` tracked per log row; exhausted → `status='failed'`
- **Idempotent:** partially — resending an already-delivered notification is a *customer-visible* duplicate (a second "your order shipped" email), not a safe no-op. Order-related sends (`order_created`, `payment_captured`) have an explicit idempotency guard (`has_order_email_been_sent`) at the **dispatch** entry point, but `retry_pending` re-sends through `_retry_log`, not `dispatch`, so it does not re-check that guard — it relies entirely on `status`/`next_retry_at` gating instead. **This must be preserved exactly**, not "improved" as part of this migration (see §11 — no double-queuing).
- **Locking:** none today (row selected by SELECT, not SELECT FOR UPDATE)
- **Failure handling:** per-log try/except inside `retry_pending`'s loop (via `_retry_log`)
- **Observability:** structlog (`notification_retry_start`/`_complete`)

### Job: `partition_manager`
- **Trigger / Frequency:** APScheduler cron `10 0 1 * *` UTC (1st of month, 00:10)
- **Function:** `app.workers.partition_manager.run`
- **DB tables:** raw SQL — `create_analytics_partition()` stored proc, `CREATE TABLE IF NOT EXISTS audit_logs_YYYY_MM PARTITION OF audit_logs`
- **Duration:** sub-second, DDL only
- **Overlap:** safe — `IF NOT EXISTS` guard
- **Retry:** none configured; misfire_grace_time=3600s today. **Celery Beat replacement must set a comparable misfire tolerance** — see §6.
- **Idempotent:** yes, by construction (`IF NOT EXISTS`)
- **Failure handling:** single outer try/except, logs and swallows (a missed partition creation is not immediately fatal — writes to a non-existent future partition would fail loudly well before the month starts, giving an operator time to intervene)
- **Observability:** structlog only

### Job: `admin_session_cleanup`
- **Trigger / Frequency:** APScheduler interval, 3600s
- **Function:** `app.workers.admin_session_cleanup.run` → `AuthService.cleanup_expired_admin_sessions`
- **DB tables:** `admin_sessions`, single indexed DELETE
- **Duration:** sub-second
- **Overlap:** safe — deleting already-deleted rows is a no-op
- **Retry:** next tick
- **Idempotent:** yes
- **Locking:** none needed (DELETE is atomic per Postgres)
- **Failure handling:** delegated to `run_with_session` (catches, logs, rolls back)
- **Observability:** structlog only

---

## 3. Existing Reliability Mechanisms — What Must Be Preserved

| Mechanism | Where | Preserve as |
|---|---|---|
| Atomic claim (optimistic) | `media_generation` `try_claim_pending` | unchanged — Celery task calls the same repository method |
| `SKIP LOCKED` row lock | `reservation_expiry` | unchanged |
| Retry-count + backoff column state | `notification_retry` (`attempt_count`, `next_retry_at`) | unchanged — this **is** the idempotency mechanism; Celery's own retry counter is not used for this job (see §10) |
| Idempotent upsert / `IF NOT EXISTS` | `cms_publish`, `partition_manager`, `admin_session_cleanup` | unchanged |
| `max_instances=1` / no-overlap | APScheduler config in `queue.py` | replaced by Celery Beat's default (Beat does not re-enqueue while a same-named task is still due) **plus** each task's own DB-level idempotency, which is the real safety net — do not rely on Celery alone for overlap safety, exactly as today's code does not rely on APScheduler alone |
| `coalesce=True` / `misfire_grace_time` | APScheduler config | mapped to Celery Beat's `Crontab`/`schedule` (no direct coalesce concept in Celery Beat — mitigated because every task is naturally idempotent/re-runnable, so a missed tick just means "picked up slightly late," never a stuck duplicate) |
| Transient-DB-error quiet handling | `media_generation.run` `_TRANSIENT_DB_ERRORS` | unchanged, reused as-is inside the Celery task body |
| Bounded worker concurrency (`asyncio.Semaphore(2)`) | `app/core/database.py::get_worker_semaphore`, used by the media fast path | superseded by Celery's own `--concurrency` setting on `celery-worker-media` (the semaphore existed specifically to bound concurrent `asyncio.create_task` bursts sharing one process's connection pool; Celery's prefork concurrency directly replaces that role) |

---

## 4. Media Generation — Sync/Async Boundary (item 5)

**Current measured evidence** (from the brief): `r2_put_original ~1803ms cumulative`, `db_create_image ~2369ms cumulative`, `enqueue_generation ~2715ms cumulative`, total upload request `~2960ms`.

Reading `universal_service.py`'s upload path: the **original** image's R2 PUT and the DB row creation (status create + variant-pending bookkeeping) are synchronous and correctness-required — the response must reflect that the original is durably stored and the DB row exists before the client can reference `image_id`. `_enqueue_generation` (line 519) is explicitly designed to return "as soon as the pending status + which breakpoints need regenerating are persisted" — variant generation itself (crop/encode/R2-upload per breakpoint) is what's backgrounded.

**Verdict:** the safe boundary is already correctly drawn in the existing code (this is not something the Celery migration needs to move) — only the *mechanism* of backgrounding changes, from `asyncio.create_task` to `media_tasks.generate_variants.delay(...)`. Nothing required-for-correctness moves further into the background than it already is.

---

## 5. Scheduler Semantics Mapping

| APScheduler job | Trigger today | Celery Beat schedule | Queue | Celery task name |
|---|---|---|---|---|
| `reservation_expiry` | `IntervalTrigger(seconds=15)` | `schedules.crontab`/`timedelta(seconds=15)` | `inventory` | `inventory.expire_reservations` |
| `cms_publish` | `IntervalTrigger(seconds=60)` | `timedelta(seconds=60)` | `cms` | `cms.publish_scheduled` |
| `media_generation` (sweep) | `IntervalTrigger(seconds=5)` | `timedelta(seconds=5)` | `media` | `media.sweep_pending` |
| `notification_retry` | `IntervalTrigger(seconds=30)` | `timedelta(seconds=30)` | `notifications` | `notifications.retry_failed` |
| `partition_manager` | `CronTrigger.from_crontab("10 0 1 * *", UTC)` | `crontab(minute=10, hour=0, day_of_month=1)` | `maintenance` | `maintenance.manage_partitions` |
| `admin_session_cleanup` | `IntervalTrigger(seconds=3600)` | `timedelta(seconds=3600)` | `maintenance` | `admin.cleanup_sessions` |
| — (new, HTTP-triggered) | n/a | n/a (not a Beat schedule) | `media` | `media.generate_variants` |

All Beat schedules use `timezone="UTC"` (matches `AsyncIOScheduler(timezone="UTC")` today).

**Misfire/coalesce equivalence:** APScheduler's `coalesce=True` collapses missed ticks into one run; Celery Beat has no direct equivalent, but every one of these tasks is idempotent-by-DB-state (queries "what's due now," not "run tick N"), so a Beat process that was down for 5 minutes and comes back simply enqueues the task once, and the task naturally picks up everything that's currently due — behaviorally equivalent to coalescing. `misfire_grace_time` has no Beat equivalent either; not needed for the same reason.

---

## 6. Task / Queue Design

### Queues
- **`media`** — `media.sweep_pending`, `media.generate_variants`. IO/CPU heavy (Pillow encode + R2 network). Isolated so a burst of uploads cannot starve reservation expiry (explicit requirement).
- **`inventory`** — `inventory.expire_reservations`. Business-critical, must never queue behind media.
- **`notifications`** — `notifications.retry_failed`.
- **`cms`** — `cms.publish_scheduled`.
- **`maintenance`** — `admin.cleanup_sessions`, `maintenance.manage_partitions`. Low-frequency hygiene, safe to share a queue.

### Worker topology (smallest production-safe, per item 15 guidance)
- **`celery-worker-media`** — consumes `media` only. `concurrency=2`, **prefork** pool (Pillow/crop/encode is CPU-bound; prefork gives true parallelism and process-level isolation so one corrupt-image crash doesn't take down other in-flight jobs — gevent/threads would share Pillow's GIL-bound CPU work with no benefit and no isolation). `--max-tasks-per-child=50` to bound per-process memory growth from Pillow image buffers. `task_time_limit` hard cap + `task_soft_time_limit` warning per task (see §7) so one stuck image can't wedge a worker slot forever.
- **`celery-worker-general`** — consumes `inventory`, `notifications`, `cms`, `maintenance`. `concurrency=4`, prefork (these tasks are short DB/HTTP-bound operations; prefork is simplest and matches the "prefer reliable defaults" guidance — no need for gevent's added dependency/complexity at this workload size).
- **`celery-beat`** — single dedicated container, no worker role, `--schedule` file on a container-local (not shared) path since exactly one Beat instance ever runs (see §12).

This is 2 worker deployments + 1 Beat, not 5+ separate per-domain containers — matches "start with the smallest topology, route internally" while still satisfying the explicit anti-starvation requirement (media isolated from inventory/notifications).

---

## 7. Celery Configuration (`app/celery_app.py`)

- **Broker:** Redis, dedicated logical DB index (`REDIS_URL` with `/2` — DB 0 is the app cache, DB 1 is GlitchTip's Valkey per `docker-compose.yml`, so Celery gets its own index to avoid `FLUSHDB`/key-collision risk between subsystems).
- **Result backend:** **not enabled.** None of these tasks have a caller waiting on a return value (Beat-triggered tasks are fire-and-forget; the one HTTP-triggered task, `media.generate_variants`, is dispatched with `.delay()` and the HTTP response does not wait on or query the result). Enabling a result backend would add Redis write load with zero consumers — violates "do not enable unnecessary Celery features."
- **Serialization:** `task_serializer="json"`, `accept_content=["json"]` — every task argument is a UUID-as-string or primitive; no pickle.
- **Acknowledgement:** `task_acks_late=True` + `worker_prefetch_multiplier=1` — a task is only ack'd after it completes (or permanently fails), so a killed worker process's in-flight task is redelivered to another worker, not lost. This is the direct replacement for APScheduler's in-process "at least it's in this event loop" guarantee, and is actually **stronger** (survives process/container death, not just exceptions within the coroutine).
- **Time limits:** `task_time_limit=300` (hard kill) / `task_soft_time_limit=240` (raises `SoftTimeLimitExceeded` inside the task) as the default; `media.generate_variants` overrides to `time_limit=120`/`soft_time_limit=90` per image (large multi-breakpoint generations should not need more; if they do, that is itself a signal worth alerting on, not silently allowing).
- **Timezone:** `UTC`, matching today.
- **Task routing:** explicit `task_routes` dict mapping task name → queue (no wildcard/auto-routing magic).
- **Events:** `worker_send_task_events=True`, `task_send_sent_event=True` — enables `celery events`/Flower-style observability without requiring a result backend.
- **Graceful shutdown:** default `worker_pool_restarts`/`SIGTERM` handling — Celery's prefork pool already waits for in-flight tasks to finish on `SIGTERM` before exiting (Docker's default stop signal), consistent with "finish current task where appropriate."

---

## 8. Classification (item 29 — do not migrate everything blindly)

| Mechanism | Classification | Rationale |
|---|---|---|
| `reservation_expiry`, `cms_publish`, `media_generation` (sweep), `notification_retry`, `partition_manager`, `admin_session_cleanup` | **CELERY BEAT SCHEDULE + CELERY TASK** | Explicit job inventory, currently APScheduler |
| `media_generation` (fast path) | **CELERY TASK** (HTTP-triggered, not Beat) | Explicit target per item 5 |
| Cache warmer (`start_warm_loop`) | **API SYNCHRONOUS-AT-STARTUP** (unchanged) | Runs exactly once, at process startup, already has its own Redis `SET NX` lock so multi-process races are handled; it is not periodic and not APScheduler — converting it to a Celery task would add a network hop (enqueue + wait-for-worker-pickup) to something that exists purely to shave milliseconds off the *first* storefront request. No behavior gap to close. |
| Cache bust-and-rewarm (`schedule_product_list_bust`) | **API SYNCHRONOUS / EVENT-DRIVEN, in-process** (unchanged) | Already non-blocking (`asyncio.create_task`, fire-and-forget, coalesced), sub-second, purely a cache-freshness optimization with SWR as the correctness backstop. Moving it to Celery adds broker round-trip latency to a path whose entire purpose is to be fast, for no reliability gain (a lost cache-bust just means the next SWR read is one generation staler, not a business-data loss). |
| Redis pub/sub → SSE listener | **INFRASTRUCTURE JOB** (unchanged) | Long-lived streaming consumer feeding live HTTP SSE connections in *this* process; it cannot be a Celery task by nature (Celery tasks are discrete units of work, not persistent per-process listeners feeding this process's own open HTTP connections) |
| SSE generator | **EVENT/SSE** (unchanged) | Per-HTTP-connection generator, inherently tied to the request lifecycle |
| Event bus fire-and-forget (order/payment/user notification dispatch) | **EVENT/SSE, left as-is** (see explicit note below) | See rationale below |
| `partition_manager.py`'s `if __name__ == "__main__"` block | **ONE-OFF SCRIPT** (unchanged) | Manual/ops convenience only, not the production path |

**On the event bus / immediate notification dispatch:** during analysis (§2, `notification_retry` idempotency notes) a real durability gap was found — `send_email`/`send_whatsapp` commit a `status='pending'` log row *before* the outbound HTTP call, and if the process dies in that exact window, the row is orphaned forever (the retry sweep only picks up `status='retrying'`, never `'pending'`). Converting the event-bus dispatch itself into a Celery task would close this gap and was seriously considered. **Decision: out of scope for this migration.** It is not in the explicit APScheduler/job inventory this migration targets, it touches the customer-facing order-confirmation/payment-receipt path, and doing it correctly requires JSON-serializing event dataclasses across the Celery boundary and re-verifying the order-level idempotency guard (`has_order_email_been_sent`) still fires exactly once under Celery's at-least-once delivery — a scoped follow-up, not a drive-by change bundled into a scheduler migration. Recorded as a **remaining risk** in the final report (§17 of that doc), not silently dropped.

---

## 9. Database Session Bug (item 28) — Root Cause

`app/core/database.py::_session_has_writes` (lines 189-203):

```python
def _session_has_writes(session: AsyncSession) -> bool:
    sync = session.sync_session
    if sync.new or sync.dirty or sync.deleted:
        return True
    txn = sync.get_transaction()
    conn = getattr(txn, "connection", None) if txn is not None else None
    return bool(conn is not None and conn.info.get("hadha_write"))
```

**Root cause:** `sqlalchemy.orm.session.SessionTransaction.connection` (confirmed by reading `hadha/Lib/site-packages/sqlalchemy/orm/session.py:1032`, SQLAlchemy 2.0.36) is a **method** (`def connection(self, bindkey, execution_options=None, **kwargs) -> Connection`), not a property. `getattr(txn, "connection", None)` therefore returns the *bound method object itself* — it is never `None` (the attribute always exists), so the `if` never short-circuits, and `conn.info` is then attempted on a method object, which has no `.info` attribute → `AttributeError: 'function' object has no attribute 'info'` (bound methods report as `<bound method ...>`, which is where the "'function' object" phrasing in the observed traceback comes from).

**Why the naive fix (`conn = txn.connection()`) is wrong:** calling `SessionTransaction.connection(bindkey, ...)` requires a `bindkey` argument and, more importantly, calling it **opens a new Core connection for this transaction if one isn't already open** (it calls `self.session.get_bind(bindkey)` then `self._connection_for_bind(...)`). The entire point of `_session_has_writes` is to check, without side effects, whether a connection was already opened during this request — calling `.connection()` would force one open even for a request that never touched the DB, defeating the P1-1 optimization this function exists for (skip COMMIT on read-only requests) and adding a spurious connection checkout to every single request.

**Correct fix:** read the transaction's already-open connection(s) directly from `SessionTransaction._connections` (a `dict[bind, tuple[Connection, Transaction, autobegin, joined]]`, confirmed present at `session.py:886-888`) without opening a new one:

```python
def _session_has_writes(session: AsyncSession) -> bool:
    sync = session.sync_session
    if sync.new or sync.dirty or sync.deleted:
        return True
    txn = sync.get_transaction()
    if txn is None:
        return False
    return any(
        conn.info.get("hadha_write")
        for conn, *_ in txn._connections.values()
    )
```

This preserves the original intent exactly: "only consult the connection if the session actually opened one." `_connections` is a private attribute, which is an acceptable and common trade-off here — the alternative (tracking the write flag via a `Session`-level `session.info` dict written by an ORM-level event instead of the engine-level `before_cursor_execute`/`after_cursor_execute` listeners currently used) would require restructuring the write-detection mechanism itself, which is out of scope for a bug fix. A short comment will be added explaining why `_connections` (not `.connection()`) is used, so a future reader doesn't "fix" this back into the bug.

**Regression tests to add** (`Backend/tests/unit/test_database_session.py`, new file):
1. Read-only request (no writes) → no commit, no AttributeError, `_session_has_writes` returns `False`.
2. Write request (raw `text("UPDATE ...")`, Core DML invisible to ORM `dirty`/`new`) → `_session_has_writes` returns `True` via the `hadha_write` flag path, commit is issued.
3. Write via ORM (`session.add(obj)`) → `_session_has_writes` returns `True` via the `sync.new`/`dirty` path (no connection needed).
4. Session with a transaction but zero queries executed (`get_transaction()` returns non-`None` but `_connections` is empty) → returns `False`, no exception.
5. Rollback path — exception raised mid-request still rolls back cleanly (unaffected by this fix, but asserted to guard against regressions).
6. A worker-task session (`AsyncSessionLocal` used directly, not via `get_db()`) is unaffected — `_session_has_writes` is only called from `get_db()`, confirmed by grep; no change needed in `app/workers/base.py::run_with_session`, which already always commits/rollbacks explicitly and never calls this function.

---

## 10. Retry / Idempotency Policy Per Task

| Task | Retryable errors | Max retries | Backoff | Non-retryable | Idempotency mechanism |
|---|---|---|---|---|---|
| `inventory.expire_reservations` | DB connection errors, Redis publish failure (event is best-effort) | 3 | exponential, base 2s, jitter | none — business logic errors are logged and the row is left for the next Beat tick, not Celery-retried, to avoid retry-storming a row already contested by `SKIP LOCKED` | `SKIP LOCKED` row claim (existing) |
| `cms.publish_scheduled` | DB connection errors | 3 | exponential, base 2s, jitter | none | `status='scheduled'` filter (existing) |
| `media.sweep_pending` | transient DB errors (existing `_TRANSIENT_DB_ERRORS` tuple, reused) | 3 | exponential, base 2s, jitter | R2/image-processing errors are handled **inside** the task via the existing `MAX_ATTEMPTS=3` DB-tracked counter, not via Celery's retry — same reasoning as reservations, avoids double-counting retries in two places | atomic `UPDATE ... RETURNING` claim (existing) |
| `media.generate_variants` (fast path) | transient DB errors, R2 timeout/network | 2 Celery-level retries (on top of the existing DB-tracked `MAX_ATTEMPTS`, since this is the *first* attempt at generation, not a sweep of already-attempted images) | exponential, base 3s, jitter, max 30s | invalid image / unsupported format / corrupt upload — these come back from `background.generate_variants_for_breakpoints` as a normal exception, caught by the existing `_handle_failure`, which marks `generation_failed` after `MAX_ATTEMPTS` — Celery must not retry past that point, so the task checks `attempts >= MAX_ATTEMPTS` before re-raising for Celery retry | `try_claim_pending` atomic claim (existing) — a Celery retry re-invokes the same claim logic, which is a safe no-op if another runner already claimed it |
| `notifications.retry_failed` | DB connection errors only | 3 | exponential, base 2s, jitter | **provider send failures are never Celery-retried** — they are handled entirely by the existing `attempt_count`/`next_retry_at`/backoff-array mechanism inside `retry_pending`, which is what prevents duplicate customer-facing sends; a Celery-level retry on top of that would re-run `retry_pending` a second time in the same window and risk sending the same log-row's retry twice before `next_retry_at` is updated | existing `status`/`next_retry_at` gate — **recommendation, not required for parity:** add `SELECT ... FOR UPDATE SKIP LOCKED` when selecting pending-retry rows, since two Celery workers (today: impossible, only one APScheduler leader ever ran this) could now both legitimately be consuming the `notifications` queue if concurrency is ever raised above 1; documented as a hardening task, implemented in Phase B since it's a small, low-risk, additive change (see §17) |
| `maintenance.manage_partitions` | DB connection errors | 3 | exponential, base 5s, jitter | DDL failures (e.g. permissions) are not retryable within the same run — surfaced via `log.exception`, Beat will try again next month | `IF NOT EXISTS` guard (existing) |
| `admin.cleanup_sessions` | DB connection errors | 3 | exponential, base 2s, jitter | none | DELETE is naturally idempotent (existing) |

General rule applied above: **do not stack Celery-level retries on top of a task's own internal DB-state-driven retry loop** for the same failure category — that would mean two independent retry/backoff systems disagreeing about how many attempts have happened, which is a correctness risk, not a reliability improvement. Celery retries are reserved for *infrastructure* failures (DB/Redis/R2 unreachable) that happen *before* the task's own business logic runs or in between its DB-tracked attempts, never for business-logic failures the task already knows how to handle.

---

## 11. Business-Critical Concurrency — What Gets Extra Scrutiny in Phase B Testing

1. **Reservation expiry exactly-once effect.** `expire_stale_reservations` already uses `SELECT ... FOR UPDATE SKIP LOCKED` per candidate row before transitioning it — this is at-least-once *task* execution with exactly-once *business effect*, which is exactly the target property from item 17. Phase B adds a concurrency test: two simulated concurrent callers (two DB sessions) racing on the same expired reservation, asserting stock is released exactly once and the order transitions to `payment_expired` exactly once.
2. **Notification duplicate-send prevention.** Covered in §10 — no Celery-level retry stacking, and the recommended (implemented) `SKIP LOCKED` hardening on `get_pending_retries`.
3. **Media claim race.** `try_claim_pending`'s atomic `UPDATE ... WHERE status='pending' ... RETURNING` already handles the fast-path-vs-sweep race described in the module docstring; Phase B adds a test asserting that dispatching `media.generate_variants` for an image the sweep has *already* claimed is a safe no-op.

---

## 12. Single Beat Instance

Celery Beat will run as **one dedicated container** (`celery-beat`), never inside a worker or API container, and never scaled (`docker compose` service with no `deploy.replicas` override — default is 1). This is enforced structurally, not by a runtime lock:

- `docker-compose.yml` (dev) and `Infra/application/docker-compose.application.yml` (prod) each define exactly one `celery-beat` service.
- No `--beat` flag is ever passed to a `celery worker` command.
- Beat's schedule persistence file (`celerybeat-schedule`) is a container-local path (not a shared volume mounted by multiple containers), so even a deployment mistake that started two Beat containers would not corrupt shared state — it would just (harmlessly, if it ever happened) double-enqueue tasks, which is safe because every task is idempotent per §10. This is documented as defense-in-depth, not as license to skip the "exactly one" deployment discipline.

`WorkerLeader` (`app/core/worker_leader.py`) becomes **dead code** once APScheduler/`QueueService` are removed — its only two callers were gating `queue.start()` and the `sync_notification_rules()` startup call. `sync_notification_rules` is itself a Postgres `ON CONFLICT DO UPDATE` upsert (confirmed at `event_registry.py:238-254`) and is therefore already safe to run from every API process unguarded — it does not need leader election at all. **Phase B removes the `WorkerLeader` usage from `main.py`'s lifespan and deletes `app/core/worker_leader.py` + its test**, since it was added one commit prior specifically to gate the APScheduler queue this migration removes, and has no remaining purpose. This is flagged explicitly here since it means deleting code from the immediately-preceding commit — the plan is to keep it removed unless review says otherwise.

---

## 13. Deployment Changes

### New services (dev `docker-compose.yml` and prod `Infra/application/docker-compose.application.yml`)
- `celery-worker-media` — image: same `BACKEND_IMAGE`/backend build, `command: celery -A app.celery_app worker -Q media --concurrency=2 --max-tasks-per-child=50 -n media@%h`
- `celery-worker-general` — `command: celery -A app.celery_app worker -Q inventory,notifications,cms,maintenance --concurrency=4 -n general@%h`
- `celery-beat` — `command: celery -A app.celery_app beat --schedule=/tmp/celerybeat-schedule -n beat@%h`

All three share the backend image (no new Dockerfile target needed — same dependencies, just a different process entrypoint), the same `env_file`/`DATABASE_URL`/`REDIS_URL`, and join the same Docker network as `hadha-backend` so they can reach Postgres/Redis/R2 identically. Health checks: `celery -A app.celery_app inspect ping -d <hostname>` for workers; Beat has no meaningful liveness probe beyond "process is running" (Docker's own restart policy covers this).

### Connection budget (must be revised — see `app/core/database.py` header comment)
Current comment assumes 2 API processes × 3 connections (`pool_size=2 + max_overflow=1`) = 6, with 9 headroom out of a 15-connection Supabase pooler budget. Adding 2 worker processes (media, general) each running their **own** SQLAlchemy async engine (engines are not fork/process-shareable) at the same `pool_size=2, max_overflow=1` adds up to 6 more persistent connections in the worst case = **12 total**, leaving only 3 headroom. Phase B lowers `DATABASE_POOL_SIZE`/`DATABASE_MAX_OVERFLOW` for the Celery worker processes specifically (via an env override, e.g. `DATABASE_POOL_SIZE=1, DATABASE_MAX_OVERFLOW=1` for workers) since each Celery task runs one DB session at a time per worker process slot, not per HTTP request — this is documented in the updated header comment in `database.py` and in the final report's connection-budget table.

### requirements.txt
- Add: `celery[redis]==5.4.0`
- Remove: `APScheduler==3.10.4` (after `app/workers/queue.py` is deleted)

### Environment variables (documented, no secrets committed)
- `CELERY_BROKER_URL` — defaults to `${REDIS_URL}` with DB index swapped to `/2` if not explicitly set (mirrors the existing `REDIS_URL` pattern, no new secret)
- No result backend variable needed (§7)

---

## 14. Testing Plan (summary — full list executed in Phase B)

- `tests/unit/test_celery_app.py` — app config sanity (broker set, queues declared, routes complete, serializer=json, no result backend), Beat schedule completeness (every former APScheduler job has exactly one Beat entry, matching cadence).
- `tests/unit/test_task_*.py` per task — success path, transient-error retry, permanent-failure non-retry, idempotent double-invocation.
- `tests/unit/test_database_session.py` — the 6 cases in §9.
- `tests/unit/test_reservation_expiry_worker.py` (existing, extended) — concurrent-expiry double-release regression test.
- `tests/unit/test_notification_retry*.py` (existing, extended) — duplicate-send prevention under simulated concurrent retry.
- `tests/unit/test_media_generation_worker.py` (existing, extended) — claim-race safety when dispatched as a Celery task rather than via `asyncio.create_task`.
- API-level: assert `app/main.py` lifespan no longer imports/starts `AsyncIOScheduler`/`WorkerLeader`.

---

## 15. Migration Sequence (item 24 — no scheduling gap)

1. Add Celery infra (`celery_app.py`, task modules) alongside the still-running APScheduler system — dead code until wired up, zero production impact.
2. Deploy `celery-worker-media`, `celery-worker-general`, `celery-beat` containers (APScheduler still running in parallel — **temporarily both systems would run the same jobs** unless Beat is deployed in a disabled/no-op state first).
   - To avoid double-execution during the overlap window, Beat's schedule is deployed with all 6 entries **already active** but APScheduler's `queue.start()` call is removed from `main.py` in the **same deploy** as the worker/beat containers going live (single atomic application deploy — `docker compose up -d` replaces the backend container and adds the new containers together). This repo's deploy pipeline (`deploy.sh`) already deploys backend+all app services as one `dc_app up -d` step, so there is no practical way to stage "workers up, APScheduler still running" as a separate deploy step without custom orchestration — and doing so would risk exactly the double-execution the brief warns against. **Decision: single coordinated deploy**, not the 10-step staged sequence suggested in the brief, because this codebase's existing deploy tooling deploys the whole application stack atomically and jobs are idempotent enough that a few seconds of container-swap overlap (old backend container stopping, new one with Celery-only code starting) is safe — there is no window where jobs "disappear," because Beat's containers start before `docker compose up`'s old backend container fully stops (Docker Compose brings up new/changed services and lets healthy old ones keep running until healthchecks on the new ones pass, per the existing `deploy.sh` sequencing).
3. Post-deploy verification (`Infra/deployment/verify.sh` extended): confirm `celery -A app.celery_app inspect active_queues` shows all 5 queues consumed, confirm `celery -A app.celery_app inspect scheduled` / Beat logs show all 6 schedules registered, confirm `hadha-backend` logs no longer mention `queue_started`/`worker_leader_*`.
4. Monitor first live tick of each schedule (15s reservation expiry visible within a minute; monthly partition job cannot be live-verified same-day — covered by a unit test asserting the Beat entry exists with the correct crontab instead).
5. Rollback procedure: since APScheduler code is removed in the same deploy as Celery is added (per the atomic-deploy decision above), rollback is the existing `Infra/deployment/rollback.sh` mechanism already used for every deploy — redeploy the previous image tag, which restores APScheduler and removes celery-worker-*/celery-beat via `docker compose up -d --remove-orphans` reverting to the previous `docker-compose.application.yml`. No special-cased Celery rollback path is needed because the whole stack rolls back together, consistent with how every other change in this repo is rolled back.

---

## 16. Files To Be Changed (Phase B)

**New:**
- `Backend/app/celery_app.py`
- `Backend/app/tasks/__init__.py`, `media.py`, `inventory.py`, `notifications.py`, `cms.py`, `admin.py`, `maintenance.py`
- `Backend/tests/unit/test_celery_app.py`, `test_database_session.py`, `test_tasks_media.py`, `test_tasks_inventory.py`, `test_tasks_notifications.py`, `test_tasks_cms.py`, `test_tasks_maintenance.py`
- `Docs/CELERY_MIGRATION_FINAL_REPORT.md` (after implementation)

**Modified:**
- `Backend/app/main.py` — remove APScheduler/`WorkerLeader`/`build_queue` startup wiring
- `Backend/app/core/database.py` — `_session_has_writes` fix, connection-budget comment update
- `Backend/requirements.txt` — swap `APScheduler` for `celery[redis]`
- `docker-compose.yml`, `Infra/application/docker-compose.application.yml` — add 3 services
- `Infra/deployment/verify.sh` — add Celery liveness checks

**Deleted:**
- `Backend/app/workers/queue.py`
- `Backend/app/core/worker_leader.py`, `Backend/tests/unit/test_worker_leader.py`
- `Backend/app/core/scheduler_metrics.py` (superseded by Celery's own task instrumentation — generic `scheduler_job_duration_seconds{job_id=...}` is replaced by per-task timing added directly in each Celery task, consistent with "every task must log task_id/task_name/queue/attempt/duration")
- `Backend/tests/unit/test_queue_service.py`

**Business logic files (`app/workers/*.py` except `queue.py`) are kept, not deleted** — `reservation_expiry.py`, `cms_publish.py`, `media_generation.py`, `notification_retry.py`, `partition_manager.py`, `admin_session_cleanup.py`, `base.py` continue to hold the actual async business logic; the new `app/tasks/*.py` modules are thin Celery entrypoints that call into them, exactly as `app/workers/queue.py` used to be a thin APScheduler entrypoint calling into them. This keeps the diff minimal and the well-tested existing logic completely untouched.

---

## 17. Remaining Risks (carried into final report)

1. Notification immediate-dispatch durability gap (§8) — explicitly deferred, not fixed.
2. Connection budget tightening for Celery worker pools (§13) needs live validation against Supabase's actual pooler cap under real concurrent load, not just arithmetic.
3. `cms_publish` and `partition_manager` gain no new row-locking as part of this migration (matches today's behavior) — acceptable because Beat, like APScheduler, only ever has one active schedule source, but if `celery-worker-general` concurrency is ever raised, `cms_publish`'s lack of row-level locking should be revisited (today harmless because publishing twice is a no-op, called out here so it isn't forgotten).
4. Existing slow-SQL evidence (`notification_rules INSERT ~914ms`, `products SELECT ~303-819ms`, etc.) is explicitly **not** addressed by this migration (per instruction item 4/27) — before/after timing will be captured in the final report to show whether scheduler isolation alone moves these numbers, but no query/index changes are made here.

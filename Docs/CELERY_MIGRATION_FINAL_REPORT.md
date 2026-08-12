# Celery Migration — Final Report

**Status:** Implementation complete, unit-tested, **not yet live-deployed or performance-validated**.
**Companion doc:** `Docs/CELERY_MIGRATION_PLAN.md` (Phase A analysis + design — read that first for rationale; this report records what was actually built and what remains to prove live).

This report follows item 30's required structure. Section 14 ("Performance BEFORE/AFTER") is the one section that cannot be filled in from this session — see that section for why, and what it takes to close it.

---

## 1. Current Architecture (before this migration)

FastAPI app (`app/main.py`) with 6 periodic jobs run in-process via APScheduler (`app/workers/queue.py`, now deleted), gated by a Redis leader-election layer (`app/core/worker_leader.py`, added one commit prior to this migration, also now deleted). Production runs `uvicorn --workers 2` inside a single `hadha-backend` container — no separate worker process existed for any background job. Full detail in plan §1.

## 2. Old APScheduler Topology

```
hadha-backend (1 container)
 └─ uvicorn --workers 2
     ├─ process A: FastAPI + AsyncIOScheduler (leader, runs 6 jobs)
     └─ process B: FastAPI + AsyncIOScheduler (follower, jobs registered but not started)
```

6 jobs: `reservation_expiry` (15s), `cms_publish` (60s), `media_generation` sweep (5s), `notification_retry` (30s), `partition_manager` (monthly cron), `admin_session_cleanup` (hourly). See plan §2 for the full per-job inventory.

## 3. New Celery Topology

```
hadha-backend (API only — HTTP/SSE, no scheduling)
 └─ uvicorn --workers 2
                      │
                      ▼ (media.generate_variants.delay(...) on image mutation)
                    Redis (broker, DB index 2)
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
celery-worker-  celery-worker-  celery-beat
media           general          (1 instance,
(queue: media)  (queues:          enqueues only)
concurrency=2   inventory,
prefork         notifications,
                cms,
                maintenance)
                concurrency=4
                prefork
```

3 new containers, 0 new external services (reuses the existing Redis). No result backend. Full detail in plan §6/§13.

## 4. Complete Job Migration Matrix

| Former APScheduler job | Celery task | Queue | Beat entry | Cadence (unchanged) |
|---|---|---|---|---|
| `reservation_expiry` | `inventory.expire_reservations` | `inventory` | `reservation-expiry` | 15s |
| `cms_publish` | `cms.publish_scheduled` | `cms` | `cms-publish` | 60s |
| `media_generation` (sweep) | `media.sweep_pending` | `media` | `media-sweep-pending` | 5s |
| `notification_retry` | `notifications.retry_failed` | `notifications` | `notification-retry` | 30s |
| `partition_manager` | `maintenance.manage_partitions` | `maintenance` | `partition-manager` | monthly, `10 0 1 * *` UTC |
| `admin_session_cleanup` | `admin.cleanup_sessions` | `maintenance` | `admin-session-cleanup` | hourly |
| `media_generation` (fast path, was `asyncio.create_task`) | `media.generate_variants` | `media` | — (HTTP-triggered, not Beat) | ad-hoc, per image mutation |

`tests/unit/test_celery_app.py::TestBeatSchedule` asserts this matrix holds (exactly 6 Beat entries, correct task/cadence per entry) so a future edit that drops or mis-schedules one fails CI, not just a manual audit.

## 5. Queue Architecture

- `media` — image variant generation only. Isolated so a burst of uploads cannot starve reservation expiry (explicit anti-starvation requirement).
- `inventory` — reservation expiry, business-critical.
- `notifications` — retry sweep.
- `cms` — scheduled publish.
- `maintenance` — admin session cleanup + partition management (low-frequency hygiene, safely shared).

Routing is explicit (`app/celery_app.py`'s `task_routes` dict), not wildcard/pattern-based — every task's queue is a one-line lookup, and `test_celery_app.py` asserts every registered task has a route.

## 6. Worker Architecture

- **`celery-worker-media`**: `-Q media`, `--concurrency=2`, prefork, `--max-tasks-per-child=50`. Prefork chosen over gevent/eventlet because Pillow's crop/encode work is CPU-bound and process-isolated (one corrupt-image crash can't take the whole pool down); `max-tasks-per-child` bounds per-process memory growth from image buffers.
- **`celery-worker-general`**: `-Q inventory,notifications,cms,maintenance`, `--concurrency=4`, prefork. Short DB/HTTP-bound tasks; prefork is the simplest reliable default at this workload size.
- **`celery-beat`**: no worker role, `--schedule=/tmp/celerybeat-schedule` (container-local, not shared — see §12 of the plan on why exactly-one-instance is structural, not lock-based).

Deployment definitions: `docker-compose.yml` (dev) and `Infra/application/docker-compose.application.yml` (prod), both validated with `docker compose config` / direct YAML parse (no live docker-compose run was performed — see §14).

## 7. Beat Schedules

See §4 above. Configured in `app/celery_app.py::celery_app.conf.beat_schedule`, a plain dict of `timedelta`/`crontab` schedules — no external schedule store, matching Celery's default `PersistentScheduler` (file-backed, container-local).

## 8. Retry Policies

Full per-task table in plan §10. Summary of the governing rule, applied uniformly: **Celery-level retries are reserved for infrastructure failures (DB/Redis unreachable, connection dropped) that happen before or between a task's own DB-state-driven attempts — never for business-logic failures the task's existing code already knows how to handle.** Concretely:

- `inventory.expire_reservations`, `cms.publish_scheduled`, `admin.cleanup_sessions`, `maintenance.manage_partitions`: 3 Celery retries, exponential backoff with jitter (`app/tasks/_common.py::backoff_seconds`), only on `OSError | asyncpg.exceptions.PostgresError | redis.exceptions.RedisError`.
- `media.sweep_pending`: same, 3 retries — the DB-tracked `MAX_ATTEMPTS=3` inside `process_one`/`_handle_failure` governs per-image retry, unchanged.
- `media.generate_variants`: 2 Celery retries (first-attempt infra failures only; the DB-tracked mechanism takes over once a claim succeeds).
- `notifications.retry_failed`: 3 Celery retries on infra failure *before* the per-log send loop starts; provider send failures (Resend/WhatsApp) are never Celery-retried, by design — they're governed entirely by `NotificationService`'s own `attempt_count`/`next_retry_at` backoff (`_RETRY_DELAYS = [1, 5, 15]` minutes), which is what prevents a duplicate customer-facing send.

None of the 6 periodic worker functions (`app/workers/*.py::run`) actually raise past their own outer try/except in today's implementation — reservation_expiry, cms_publish, media_generation sweep, admin_session_cleanup, and partition_manager all self-contain failures via `run_with_session` or their own outer catch. This means the Celery-level retry path for those tasks mainly guards session-acquisition-level failures (e.g. pool exhaustion before the worker function's own try block is reached), not failures inside the worker function itself — documented explicitly in each task module's docstring so a future reader doesn't mistake it for dead code. `notification_retry.run` is the one exception: it has no outer try/except, so DB failures there do reach and exercise the Celery retry path.

## 9. Idempotency Strategy

Every existing idempotency mechanism was preserved unchanged — this migration deliberately did not touch business logic:

- **Reservation expiry**: `SELECT ... FOR UPDATE SKIP LOCKED` per candidate row (`reservation_service.py`), unchanged.
- **Media generation**: atomic `UPDATE ... WHERE status='pending' ... RETURNING` claim (`ImageRepository.try_claim_pending`), unchanged.
- **CMS publish / admin cleanup / partition manager**: `status='scheduled'` filter, natural DELETE idempotency, `CREATE TABLE IF NOT EXISTS` — all unchanged.
- **Notification retry — hardened, not just preserved**: `NotificationRepository.get_pending_retries` gained `.with_for_update(skip_locked=True)`, and `app/tasks/notifications.py::retry_failed` gained a Redis `SET NX` single-flight lock (`hadha:tasks:notifications.retry_failed:lock`, 150s TTL, fail-open on Redis outage). This closes a race that did not exist under the old single-leader APScheduler model but is newly possible under Celery if two invocations of the same periodic task ever overlap (see plan §10/§11 for the full reasoning on why SKIP LOCKED alone only covers the initial SELECT, and the lock is what fully closes the gap).

## 10. Database Transaction Strategy

Unchanged from before this migration, with one exception: **the Celery worker connection budget**. Each Celery worker process gets its own SQLAlchemy async engine (engines are not fork/process-shareable); `app/celery_app.py`'s `worker_process_init` signal handler calls `engine.sync_engine.dispose(close=False)` after fork to discard the parent's inherited connections without attempting to close sockets that belong to a different process. `celery-worker-media` and `celery-worker-general` are deployed with `DATABASE_POOL_SIZE=1`/`DATABASE_MAX_OVERFLOW=1` (env override, no code change — `app/core/config.py` already reads these from env) rather than the API's default of 2/1, since each Celery worker slot holds one DB session per task, not one per concurrent HTTP request. Updated connection-budget arithmetic is documented directly in `app/core/database.py`'s header comment.

## 11. Deployment Changes

- **New files**: `Backend/app/celery_app.py`, `Backend/app/tasks/{__init__,_common,media,inventory,notifications,cms,admin,maintenance}.py`.
- **New compose services** (both `docker-compose.yml` and `Infra/application/docker-compose.application.yml`): `celery-worker-media`, `celery-worker-general`, `celery-beat`. All three reuse the existing backend image — no new Dockerfile target.
- **Modified**: `app/main.py` (APScheduler/WorkerLeader startup removed; `sync_notification_rules` now runs unguarded in every API process since it's a Postgres upsert, not leader-gated), `app/core/database.py` (bug fix + connection-budget comment), `app/core/config.py` (`CELERY_BROKER_URL` setting), `app/core/logging.py` (silence-list updated), `requirements.txt` (`APScheduler` → `celery[redis]==5.4.0`), `Infra/deployment/verify.sh` (Celery worker/beat health checks added).
- **Deleted**: `app/workers/queue.py`, `app/core/worker_leader.py` + its test, `app/core/scheduler_metrics.py`, `tests/unit/test_queue_service.py`. `app/workers/{reservation_expiry,cms_publish,media_generation,notification_retry,partition_manager,admin_session_cleanup,base}.py` were **kept** — they hold the actual business logic and are now called by `app/tasks/*.py` instead of `app/workers/queue.py`.

## 12. Environment Variables

No new secrets. `CELERY_BROKER_URL` (optional, `app/core/config.py`) defaults to `REDIS_URL` with the DB index swapped to `/2` if unset. The two Celery worker compose services additionally set `DATABASE_POOL_SIZE=1`/`DATABASE_MAX_OVERFLOW=1` (already-existing settings, new values for these specific services only).

## 13. Tests

38 new unit tests, all passing alongside the full existing 1255 (1293 total):

- `tests/unit/test_database_session.py` (6 tests) — the DB session bug fix, using a real in-memory SQLite `Session` to exercise actual SQLAlchemy transaction internals rather than mocking them away.
- `tests/unit/test_celery_app.py` (14 tests) — broker/serialization/routing config, Beat schedule completeness against the exact former APScheduler cadences, and an explicit assertion that `main.py`/`requirements.txt` no longer reference APScheduler/WorkerLeader.
- `tests/unit/test_tasks_{admin,cms,maintenance,inventory,media,notifications}.py` (18 tests) — success path, transient-error → `self.retry()` invocation (verified via a `Task.retry` stand-in rather than relying on Celery's eager-vs-worker retry-dispatch nuances), non-transient-error propagation without retry, plus media's claim-race-is-a-safe-no-op case and notifications' full single-flight-lock behavior (acquired/not-acquired/fail-open/released-on-exception).
- Existing `tests/unit/test_media_universal_service.py` and `test_media_generation_worker.py` updated in place (dispatch mechanism changed from `asyncio.create_task` to `.delay()`; the now-removed `enqueue()`/semaphore concurrency test deleted) rather than duplicated.

Full CI gate run this session: **Black — all files unchanged (formatted). Ruff — all checks passed. Mypy — Success: no issues found in 254 source files. Pytest — 1293 passed (unit) + 82 passed (integration) + 10 passed (scripts).**

**Not tested this session** (would require a running Postgres/Redis, i.e. `docker compose up`, which was not exercised): actual Celery worker process startup, Beat actually enqueuing to Redis and a worker consuming it, the `worker_process_init` fork-safety handler under a real prefork pool, and the reservation-expiry/notification-retry concurrency scenarios described in plan §11's "extra scrutiny" list (those need two real concurrent DB sessions racing on the same row, not mocks).

## 14. Performance BEFORE/AFTER

**Not measured.** This session implemented and unit-tested the migration but did not run `docker compose up` against a live Postgres/Redis/R2 stack, so there is no request-latency, task-wait-time, or queue-depth data to report — fabricating numbers here would violate the brief's own instruction ("do not claim improvement without measurements") and this user's standing expectation of real-environment validation before declaring a migration done.

**What closing this requires, concretely:**
1. Deploy the new compose services to a staging environment with the same topology as production (2 uvicorn workers + celery-worker-media + celery-worker-general + celery-beat).
2. Re-run whatever produced the brief's baseline numbers (`r2_put_original ~1803ms`, `db_create_image ~2369ms`, `enqueue_generation ~2715ms`, upload request `~2960ms`; `notification_rules INSERT ~914ms`, etc.) against `POST /api/v1/admin/media/product/upload` and `PATCH /api/v1/admin/products/{id}` before and after cutover.
3. Compare `enqueue_generation` specifically — the fast path went from `asyncio.create_task` (near-zero overhead, same process) to a Redis round-trip (`generate_variants.delay(...)`); this is expected to add single-digit milliseconds to the enqueue step in exchange for durability, and should be confirmed, not assumed.
4. Confirm whether the slow-SQL evidence from item 4/27 of the brief improves from scheduler isolation alone (workers no longer share the API's connection pool) or remains a separate DB-optimization problem — this migration deliberately did not touch any query or index.

## 15. Failure/Recovery Behavior

- **Worker process crash**: `task_acks_late=True` + `worker_prefetch_multiplier=1` means an in-flight task is redelivered to another worker, not lost — stronger than the old in-process `asyncio.create_task` guarantee, which lost the fast-path task entirely on process death (recovered only by the next 5s sweep tick).
- **Beat crash**: `restart: unless-stopped` + Docker's own crash-loop recovery; no in-app leader election needed since exactly one Beat container exists by deployment topology, not by runtime lock (plan §12).
- **Redis outage**: workers/Beat lose their broker — tasks queue up once Redis returns (Beat re-enqueues on its own schedule; nothing is silently dropped, matching Celery's default broker-reconnect behavior). The notification single-flight lock fails open (runs anyway) rather than blocking retries on a Redis outage.
- **DB outage**: every task's transient-error path retries with backoff; `run_with_session`/each worker function's own error handling is unchanged from before this migration.

## 16. Rollback Procedure

Per plan §15: APScheduler removal and Celery addition were deployed as one atomic change (this repo's `deploy.sh` deploys the whole application stack via a single `docker compose up -d`, so there is no practical middle state to stage). Rollback is therefore the **existing** `Infra/deployment/rollback.sh` mechanism already used for every deploy in this repo — redeploy the previous image tag, which restores APScheduler/WorkerLeader and removes the Celery containers via `docker compose up -d --remove-orphans` reverting to the previous `docker-compose.application.yml`. No Celery-specific rollback path was added, deliberately, so rollback behavior stays consistent with how every other change in this repository is rolled back.

## 17. Remaining Risks

1. **No live validation yet** (§13/§14) — the single largest open item. Acceptance criteria in the brief ("the migration is successful only when the actual business jobs have been demonstrated end-to-end") is not yet met; this report covers implementation-complete + unit-tested, not live-verified.
2. **Notification immediate-dispatch durability gap** (plan §8) — `send_email`/`send_whatsapp` commit a `status='pending'` log row before the outbound HTTP call; a process death in that exact window orphans the row (the retry sweep only picks up `status='retrying'`). Found during analysis, deliberately not fixed here — it's not in the APScheduler job inventory this migration targets and touches the customer-facing order-confirmation path; flagged as a scoped follow-up.
3. **Connection budget arithmetic is untested under real load** — the `DATABASE_POOL_SIZE=1`/`MAX_OVERFLOW=1` values for Celery workers are a reasoned estimate (plan §13), not something validated against Supabase's actual pooler behavior under concurrent production traffic.
4. **`cms_publish` has no row-level locking** (unchanged from before) — harmless today because publishing twice is a no-op, but would need revisiting if `celery-worker-general` concurrency is ever raised significantly.
5. **Stale documentation** — several `Docs/*.md` files (dated point-in-time audit/performance reports, e.g. `WORKER_DEPLOYMENT_AUDIT.md`, `CACHE_OPTIMIZATION_REPORT.md`) and `Backend/README.md` still describe the APScheduler/2-uvicorn-worker topology. These were deliberately left untouched as historical snapshots (consistent with how `WORKER_DEPLOYMENT_AUDIT.md` itself documents a now-superseded state), except `Backend/README.md`, which is a living reference doc and should be refreshed in a follow-up — out of scope for this migration's diff.
6. **Existing slow-SQL evidence** (item 27) not re-measured — see §14.

---

## Acceptance Criteria Checklist (item 33)

| Criterion | Status |
|---|---|
| APScheduler no longer used for production scheduling | ✅ code removed, `requirements.txt` updated |
| API containers do not run scheduled jobs | ✅ `main.py` lifespan verified by test |
| Exactly one active Celery Beat exists | ✅ structural (compose service count), not yet live-verified |
| Celery workers execute all migrated background jobs | ✅ implemented, unit-tested; ⬜ not live-verified |
| Every former scheduled job has a verified Celery equivalent | ✅ `test_celery_app.py` asserts the full matrix |
| Retry behavior preserved | ✅ per plan §10, unit-tested |
| Idempotency preserved | ✅ unchanged mechanisms + notification hardening |
| Reservation correctness preserved | ✅ SKIP LOCKED unchanged; ⬜ concurrent-race test needs a real DB |
| Notification delivery not duplicated | ✅ backoff mechanism unchanged + new single-flight lock |
| Media generation reliable | ✅ claim mechanism unchanged, fast path now durable |
| Cache warming works | N/A — deliberately not migrated (plan §8) |
| Worker crash recovery works | ✅ by Celery `acks_late` design; ⬜ not live-verified |
| Graceful shutdown works | ✅ Celery/Docker default `SIGTERM` handling; ⬜ not live-verified |
| Redis broker works | ⬜ not live-verified |
| PostgreSQL connections are safe | ✅ fork-safety handler implemented; ⬜ not live-verified |
| Database session cleanup bug fixed | ✅ fixed + regression-tested |
| All relevant tests pass | ✅ 1293 unit + 82 integration + 10 script tests |
| No secrets committed | ✅ no new secrets introduced |
| Deployment configuration documented | ✅ this report + plan §13 |
| BEFORE/AFTER performance evidence recorded | ⬜ not available — see §14 |

**Bottom line:** code-complete and passing every check this environment can run (formatting, linting, typing, unit/integration tests against mocks and an in-memory DB). The items marked ⬜ all require an actual `docker compose up` against live Postgres/Redis, which was not performed this session — per this repository's own standing expectation for production validation, this should not be treated as "done" until that live pass happens and this report's ⬜ items are updated to ✅ with real evidence.

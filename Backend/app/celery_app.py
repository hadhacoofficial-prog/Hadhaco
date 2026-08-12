"""Celery application — dedicated worker/beat processes for background jobs.

Replaces the in-process APScheduler queue (formerly ``app/workers/queue.py``)
that ran inside every uvicorn worker. See ``Docs/CELERY_MIGRATION_PLAN.md``
for the full rationale, job inventory, and retry/idempotency policy per task.

Deployment topology (enforced by docker-compose, not by code):
  * ``celery-worker-media``   — queue ``media``       (image variant generation)
  * ``celery-worker-general`` — queues ``inventory``, ``notifications``,
                                 ``cms``, ``maintenance``
  * ``celery-beat``           — exactly one instance, enqueues only, never
                                 executes task bodies itself

No result backend is configured: every task here is either Beat-triggered
(fire-and-forget) or dispatched from an HTTP request that does not wait on
or query the result (``media.generate_variants``). Adding one would add
Redis write load with zero consumers.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from urllib.parse import urlsplit, urlunsplit

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init

from app.core.config import settings
from app.core.model_registry import import_all_models

# Register every app.modules.*.models table into Base.metadata before any
# task body can run. Celery's `include=["app.tasks"]` only imports what the
# task modules transitively need — e.g. app.workers.media_generation imports
# app.modules.media.repository but never app.modules.profiles.models — so a
# flush on a model with a cross-module ForeignKey (images.uploaded_by ->
# profiles.id) failed with NoReferencedTableError in production because
# profiles' Table object didn't exist yet in this process. FastAPI's
# app.main gets this for free (every router import cascades into every
# models.py); Celery needs it done explicitly. Runs once here, in the
# parent process, before Celery's prefork pool forks worker children — the
# children inherit the already-populated Base.metadata via fork's
# copy-on-write, so this never needs to repeat per child (unlike the DB
# engine/event loop below, which must be re-initialized per child since
# connections and event loops do NOT survive a fork safely).
import_all_models()


def _default_broker_url() -> str:
    """REDIS_URL with the logical DB index swapped to /2.

    DB 0 is the app cache (app/core/cache.py, app/core/redis.py), DB 1 is
    GlitchTip's Valkey instance (docker-compose.yml) — Celery gets its own
    index so a broker-side ``FLUSHDB`` or key pattern never touches either.
    """
    parts = urlsplit(settings.REDIS_URL)
    path = "/2"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


BROKER_URL = settings.CELERY_BROKER_URL or _default_broker_url()

celery_app = Celery("hadha", broker=BROKER_URL, include=["app.tasks"])

celery_app.conf.update(
    # ── Serialization ────────────────────────────────────────────────────
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    result_backend=None,
    timezone="UTC",
    enable_utc=True,
    # ── Delivery guarantees ──────────────────────────────────────────────
    # A task is only ack'd after it completes (or permanently fails), so a
    # killed worker process's in-flight task is redelivered rather than
    # lost — the direct replacement for APScheduler's "at least it's still
    # in this event loop" guarantee, and stronger (survives process death).
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    # ── Time limits (per-task overrides set in app/tasks/*.py) ───────────
    task_time_limit=300,
    task_soft_time_limit=240,
    # ── Retry defaults (per-task policy documented in app/tasks/*.py) ────
    task_default_retry_delay=5,
    task_default_max_retries=3,
    # ── Observability ─────────────────────────────────────────────────────
    worker_send_task_events=True,
    task_send_sent_event=True,
    # ── Routing ────────────────────────────────────────────────────────────
    task_routes={
        "media.sweep_pending": {"queue": "media"},
        "media.generate_variants": {"queue": "media"},
        "inventory.expire_reservations": {"queue": "inventory"},
        "notifications.retry_failed": {"queue": "notifications"},
        "cms.publish_scheduled": {"queue": "cms"},
        "admin.cleanup_sessions": {"queue": "maintenance"},
        "maintenance.manage_partitions": {"queue": "maintenance"},
    },
    # Deliberately no task_default_queue override: every task above has an
    # explicit route. A task landing on Celery's default "celery" queue
    # (which no worker in this deployment consumes) is a loud signal that a
    # new task was added without a route, not a silent misroute.
    # ── Beat schedule ─────────────────────────────────────────────────────
    # Cadences match app/workers/queue.py::build_queue (see plan §5), with
    # one deliberate deviation: media-sweep-pending was widened from the
    # original 5s to 15s (Docs/MEDIA_SWEEP_OPTIMIZATION_REPORT.md) — the
    # original 5s predates this migration and was chosen so an admin
    # watching "Generating…" isn't stuck long if the fast-path dispatch was
    # ever lost entirely, not primarily to bound the 120s stale-'processing'
    # reclaim window. At 15s the worst-case added wait (~10-13s) is still
    # well inside the frontend's 30s pollImageUntilReady timeout.
    beat_schedule={
        "reservation-expiry": {
            "task": "inventory.expire_reservations",
            "schedule": timedelta(seconds=15),
        },
        "cms-publish": {
            "task": "cms.publish_scheduled",
            "schedule": timedelta(seconds=60),
        },
        "media-sweep-pending": {
            "task": "media.sweep_pending",
            "schedule": timedelta(seconds=15),
        },
        "notification-retry": {
            "task": "notifications.retry_failed",
            "schedule": timedelta(seconds=30),
        },
        "admin-session-cleanup": {
            "task": "admin.cleanup_sessions",
            "schedule": timedelta(seconds=3600),
        },
        "partition-manager": {
            "task": "maintenance.manage_partitions",
            # First of the month, 00:10 UTC — matches
            # CronTrigger.from_crontab("10 0 1 * *", timezone="UTC").
            "schedule": crontab(minute=10, hour=0, day_of_month=1),
        },
    },
)


@worker_process_init.connect
def _reinit_db_engine_after_fork(**kwargs: object) -> None:
    """Discard the parent process's pooled DB connections after fork.

    ``app/core/database.py`` creates its async engine at import time. Celery's
    prefork pool forks worker processes *after* that import, so every child
    inherits the parent's engine object — including its already-open asyncpg
    connections and file descriptors, which are unsafe to share across
    processes (two processes reading/writing the same socket corrupts the
    wire protocol). ``dispose(close=False)`` discards the inherited pool
    without attempting to close those connections (they don't belong to this
    process's event loop) and lets the pool open fresh connections on first
    use in the child — the standard SQLAlchemy fork-safety pattern.

    Also (re)creates this process's persistent event loop — see
    ``get_worker_loop`` below for why one loop must be reused for the whole
    process lifetime rather than created per task.
    """
    from app.core.database import engine

    engine.sync_engine.dispose(close=False)

    global _worker_loop
    if _worker_loop is not None and not _worker_loop.is_closed():
        _worker_loop.close()
    _worker_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_worker_loop)


# ── Per-process persistent event loop ───────────────────────────────────────
# app/tasks/_common.py::run_async used to call asyncio.run(coro_fn()) on every
# task invocation. asyncio.run() creates a new event loop and destroys it when
# the coroutine returns — but app/core/database.py's engine (and its pooled
# asyncpg connections) is created once per *process* and is reused across
# many task invocations within that process. asyncpg connections are bound to
# the event loop that opened them, so the second task's fresh loop would try
# to reuse a connection still attached to the first task's already-destroyed
# loop, producing exactly the failure this fixes:
#   RuntimeError: Task ... got Future ... attached to a different loop
#   asyncpg.exceptions.InterfaceError: cannot perform operation: another
#   operation is in progress
# (confirmed against real worker logs — reservation_expiry, cms_publish, and
# notification_retry all failed this way on the second+ tick in the same
# worker process). The fix: one event loop per process, created once at fork
# (worker_process_init, alongside the engine reinit above) and reused for
# every task via loop.run_until_complete() instead of asyncio.run().
_worker_loop: asyncio.AbstractEventLoop | None = None


def get_worker_loop() -> asyncio.AbstractEventLoop:
    """Return this process's persistent event loop, creating one if the
    worker_process_init signal never fired (e.g. calling a task function
    directly outside a real Celery worker, as the test suite does)."""
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)
    return _worker_loop

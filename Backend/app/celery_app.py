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

from datetime import timedelta
from urllib.parse import urlsplit, urlunsplit

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init

from app.core.config import settings


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
    # Cadences match app/workers/queue.py::build_queue exactly (see plan §5).
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
            "schedule": timedelta(seconds=5),
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
    """
    from app.core.database import engine

    engine.sync_engine.dispose(close=False)

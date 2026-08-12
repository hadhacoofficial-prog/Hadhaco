"""Celery entrypoint for notification retry sweep — Beat-triggered every 30s.

Business logic is untouched: app.workers.notification_retry.run picks up
NotificationLog rows in status='retrying' whose next_retry_at has passed and
re-attempts delivery via the appropriate provider.

Unlike the other periodic workers, app.workers.notification_retry.run has no
outer try/except — a DB failure while listing pending retries propagates
here and IS Celery-retried (infra failures only, see plan §10).

Provider send failures (Resend/WhatsApp) are never Celery-retried: they are
handled entirely by NotificationService's own attempt_count/next_retry_at
backoff (repository._RETRY_DELAYS), which is what prevents a duplicate
customer-facing send. Stacking a Celery retry on top of that would re-run
the whole sweep a second time in the same window before next_retry_at is
updated, risking exactly the duplicate delivery the backoff exists to
prevent — so only errors raised before/between per-log sends (i.e. before
NotificationService.retry_pending's own per-log try/except takes over) ever
reach this task's except block.

Single-flight lock: a plain SELECT (even with FOR UPDATE SKIP LOCKED — see
NotificationRepository.get_pending_retries) only guards the initial row
fetch, because NotificationService._retry_log commits after each row to free
the DB connection before its HTTP call, releasing that row's lock before the
next row in the same batch is processed. Two overlapping runs of this task
(e.g. a slow tick still in flight when the next Beat tick fires 30s later)
could therefore still race past the SELECT-time guard. A Redis SET NX lock
— the same idiom app/core/cache_warmer.py and the former
app/core/worker_leader.py used — makes the whole task body single-flight
across the cluster, closing that gap completely rather than partially.
"""

from __future__ import annotations

import structlog

from app.celery_app import celery_app
from app.core.redis import get_redis_pool, redis_available
from app.tasks._common import backoff_seconds, is_transient, run_async, task_run_log
from app.workers import notification_retry

log = structlog.get_logger(__name__)

_LOCK_KEY = "hadha:tasks:notifications.retry_failed:lock"
# Comfortably above the task's own time_limit=120s hard cap, so the lock
# never expires out from under a still-legitimately-running task.
_LOCK_TTL_SECONDS = 150


async def _run_single_flight() -> None:
    if not redis_available():
        # Fail-open, matching worker_leader's fallback: a Redis outage must
        # not silently stop notification retries from ever running.
        log.warning("retry_failed_lock_skipped", reason="redis_unavailable")
        await notification_retry.run()
        return

    redis = get_redis_pool()
    acquired = False
    try:
        acquired = bool(await redis.set(_LOCK_KEY, "1", nx=True, ex=_LOCK_TTL_SECONDS))
    except Exception as exc:
        log.warning("retry_failed_lock_error", error=str(exc))
        acquired = True  # best-effort — don't stall retries on a lock error

    if not acquired:
        log.info("retry_failed_skipped", reason="already_running")
        return

    try:
        await notification_retry.run()
    finally:
        try:
            await redis.delete(_LOCK_KEY)
        except Exception as exc:
            log.warning("retry_failed_lock_release_error", error=str(exc))


@celery_app.task(
    name="notifications.retry_failed",
    bind=True,
    max_retries=3,
    time_limit=120,
    soft_time_limit=90,
)
def retry_failed(self) -> None:
    with task_run_log(self):
        try:
            run_async(_run_single_flight)
        except Exception as exc:
            if is_transient(exc):
                raise self.retry(
                    exc=exc, countdown=backoff_seconds(self.request.retries)
                ) from exc
            raise

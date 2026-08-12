"""Celery entrypoint for reservation expiry — Beat-triggered every 15s.

Business logic is untouched: app.workers.reservation_expiry.run does the
SKIP LOCKED claim, stock release, and order-side-effect orchestration exactly
as it did under APScheduler. See Docs/CELERY_MIGRATION_PLAN.md §2/§11 for the
exactly-once-effect analysis this task must not disturb.
"""

from __future__ import annotations

from app.celery_app import celery_app
from app.tasks._common import backoff_seconds, is_transient, run_async, task_run_log
from app.workers import reservation_expiry


@celery_app.task(
    name="inventory.expire_reservations",
    bind=True,
    max_retries=3,
    time_limit=120,
    soft_time_limit=90,
)
def expire_reservations(self) -> None:
    with task_run_log(self):
        try:
            run_async(reservation_expiry.run)
        except Exception as exc:
            if is_transient(exc):
                raise self.retry(
                    exc=exc, countdown=backoff_seconds(self.request.retries)
                ) from exc
            # A business-logic failure (not infra) is left for the next Beat
            # tick, 15s later — retrying immediately within the same task
            # would race the SKIP LOCKED claim against itself for no benefit.
            raise

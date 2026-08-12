"""Celery entrypoint for monthly DB partition management.

Beat-triggered on the 1st of each month at 00:10 UTC — matches the former
APScheduler CronTrigger("10 0 1 * *", timezone="UTC") exactly. Business logic
is untouched: app.workers.partition_manager.run creates next month's
analytics_events/audit_logs partitions, guarded by IF NOT EXISTS.
"""

from __future__ import annotations

from app.celery_app import celery_app
from app.tasks._common import backoff_seconds, is_transient, run_async, task_run_log
from app.workers import partition_manager


@celery_app.task(
    name="maintenance.manage_partitions",
    bind=True,
    max_retries=3,
    time_limit=120,
    soft_time_limit=90,
)
def manage_partitions(self) -> None:
    with task_run_log(self):
        try:
            run_async(partition_manager.run)
        except Exception as exc:
            if is_transient(exc):
                raise self.retry(
                    exc=exc, countdown=backoff_seconds(self.request.retries)
                ) from exc
            # DDL permission errors etc. are not retryable within the same
            # run — surfaced via logging, Beat tries again next month.
            raise

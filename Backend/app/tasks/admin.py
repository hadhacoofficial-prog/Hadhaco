"""Celery entrypoint for admin session cleanup — Beat-triggered hourly.

Business logic is untouched: app.workers.admin_session_cleanup.run deletes
AdminSession rows whose 2FA verification expired over an hour ago. Pure
hygiene — expired sessions are already rejected at request time.
"""

from __future__ import annotations

from app.celery_app import celery_app
from app.tasks._common import backoff_seconds, is_transient, run_async, task_run_log
from app.workers import admin_session_cleanup


@celery_app.task(
    name="admin.cleanup_sessions",
    bind=True,
    max_retries=3,
    time_limit=60,
    soft_time_limit=45,
)
def cleanup_sessions(self) -> None:
    with task_run_log(self):
        try:
            run_async(admin_session_cleanup.run)
        except Exception as exc:
            if is_transient(exc):
                raise self.retry(
                    exc=exc, countdown=backoff_seconds(self.request.retries)
                ) from exc
            raise

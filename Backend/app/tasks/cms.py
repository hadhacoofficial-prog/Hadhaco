"""Celery entrypoint for CMS scheduled publishing — Beat-triggered every 60s.

Business logic is untouched: app.workers.cms_publish.run promotes
status='scheduled' sections whose scheduled_at has passed and clears the
homepage cache key, exactly as it did under APScheduler.
"""

from __future__ import annotations

from app.celery_app import celery_app
from app.tasks._common import backoff_seconds, is_transient, run_async, task_run_log
from app.workers import cms_publish


@celery_app.task(
    name="cms.publish_scheduled",
    bind=True,
    max_retries=3,
    time_limit=60,
    soft_time_limit=45,
)
def publish_scheduled(self) -> None:
    with task_run_log(self):
        try:
            run_async(cms_publish.run)
        except Exception as exc:
            if is_transient(exc):
                raise self.retry(
                    exc=exc, countdown=backoff_seconds(self.request.retries)
                ) from exc
            raise

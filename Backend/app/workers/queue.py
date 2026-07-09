"""Background job scheduler.

QueueService wraps APScheduler's AsyncIOScheduler so the rest of the app
never imports APScheduler directly. Jobs are the worker modules in this
package; intervals come from settings so ops can tune them per environment.

Started/stopped from the FastAPI lifespan in app/main.py.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

log = structlog.get_logger(__name__)


class QueueService:
    """Thin abstraction over APScheduler for periodic background jobs."""

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler(timezone="UTC")

    def add_interval_job(
        self, fn: Callable[[], Awaitable[None]], *, seconds: int, job_id: str
    ) -> None:
        self._scheduler.add_job(
            fn,
            IntervalTrigger(seconds=seconds),
            id=job_id,
            max_instances=1,  # never overlap a slow run with the next tick
            coalesce=True,  # collapse missed ticks into one run
            misfire_grace_time=60,
        )

    def add_cron_job(
        self, fn: Callable[[], Awaitable[None]], *, cron: str, job_id: str
    ) -> None:
        self._scheduler.add_job(
            fn,
            CronTrigger.from_crontab(cron, timezone="UTC"),
            id=job_id,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )

    def start(self) -> None:
        self._scheduler.start()
        log.info("queue_started", jobs=[j.id for j in self._scheduler.get_jobs()])

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            log.info("queue_stopped")


def build_queue() -> QueueService:
    """Register periodic workers with their configured intervals."""
    from app.workers import (
        cms_publish,
        media_generation,
        partition_manager,
        reservation_expiry,
    )

    queue = QueueService()
    # Reservation expiry runs every 60s — must fire quickly to free stock
    # so other customers can purchase after a session timeout.
    queue.add_interval_job(
        reservation_expiry.run, seconds=60, job_id="reservation_expiry"
    )
    queue.add_interval_job(cms_publish.run, seconds=60, job_id="cms_publish")
    # Every 5s — the crash-recovery/retry net for image variant generation
    # (docs audit CB-1 Phase 2). The common case is already handled by the
    # asyncio.create_task fast path fired from `_enqueue_generation`; this
    # tick is what catches anything that task never finished (process
    # restart, exception before claim) and is the *only* path in a
    # multi-process deployment. Short interval since an admin waiting on
    # "Generating…" in the editor is the worst case this recovers.
    queue.add_interval_job(media_generation.run, seconds=5, job_id="media_generation")
    # First day of each month, 00:10 UTC — create next month's DB partitions.
    queue.add_cron_job(
        partition_manager.run, cron="10 0 1 * *", job_id="partition_manager"
    )
    return queue

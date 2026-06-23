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

from app.core.config import settings

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
    """Register every periodic worker with its configured interval."""
    from app.workers import (
        abandoned_cart,
        cms_publish,
        inventory_alerts,
        notification_retry,
        partition_manager,
        reservation_expiry,
        review_reminder,
        shipment_sync,
    )

    queue = QueueService()
    # Reservation expiry runs every 60s — must fire before other jobs to free
    # stock quickly so other customers can purchase.
    queue.add_interval_job(
        reservation_expiry.run, seconds=60, job_id="reservation_expiry"
    )
    queue.add_interval_job(cms_publish.run, seconds=60, job_id="cms_publish")
    queue.add_interval_job(
        shipment_sync.run,
        seconds=settings.SHIPMENT_SYNC_INTERVAL,
        job_id="shipment_sync",
    )
    queue.add_interval_job(
        notification_retry.run,
        seconds=settings.NOTIFICATION_RETRY_INTERVAL,
        job_id="notification_retry",
    )
    queue.add_interval_job(
        abandoned_cart.run,
        seconds=settings.ABANDONED_CART_INTERVAL,
        job_id="abandoned_cart",
    )
    queue.add_interval_job(
        inventory_alerts.run,
        seconds=settings.INVENTORY_ALERT_INTERVAL,
        job_id="inventory_alerts",
    )
    # Hourly sweep; the worker itself only emails for orders delivered ≥ REVIEW_REMINDER_DELAY_HOURS ago.
    queue.add_interval_job(review_reminder.run, seconds=3600, job_id="review_reminder")
    # First day of each month, 00:10 UTC — create next month's partitions.
    queue.add_cron_job(
        partition_manager.run, cron="10 0 1 * *", job_id="partition_manager"
    )
    return queue

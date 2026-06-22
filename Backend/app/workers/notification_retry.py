"""
Retry notifications stuck in 'retrying' whose next_retry_at has passed.
Run every NOTIFICATION_RETRY_INTERVAL seconds.
"""

from __future__ import annotations

import time

import structlog

from app.core.database import AsyncSessionLocal
from app.modules.notifications.service import NotificationService

log = structlog.get_logger(__name__)
_svc = NotificationService()


async def run() -> None:
    t0 = time.perf_counter()
    log.info("notification_retry_started")
    try:
        async with AsyncSessionLocal() as db:
            await _svc.retry_pending(db)
        duration_ms = round((time.perf_counter() - t0) * 1000)
        log.info("notification_retry_completed", duration_ms=duration_ms)
    except Exception:
        duration_ms = round((time.perf_counter() - t0) * 1000)
        log.exception("notification_retry_failed", duration_ms=duration_ms)


if __name__ == "__main__":
    import asyncio

    asyncio.run(run())

"""Automatic retry worker for failed notifications.

Runs periodically via APScheduler to pick up notifications in 'retrying'
status whose next_retry_at has passed, and re-attempts delivery through
the appropriate provider (email or whatsapp).
"""

from __future__ import annotations

import structlog

from app.core.database import AsyncSessionLocal

log = structlog.get_logger(__name__)


async def run() -> None:
    from app.modules.notifications.repository import NotificationRepository
    from app.modules.notifications.service import NotificationService

    async with AsyncSessionLocal() as db:
        repo = NotificationRepository()
        pending = await repo.get_pending_retries(db)

        if not pending:
            return

        log.info("notification_retry_start", count=len(pending))

        svc = NotificationService()
        await svc.retry_pending(db)

        log.info("notification_retry_complete", count=len(pending))

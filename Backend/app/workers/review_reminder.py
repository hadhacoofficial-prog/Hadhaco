"""
Send review-request emails for orders delivered REVIEW_REMINDER_DELAY_HOURS ago.
Runs hourly; the window query keeps each order from being emailed twice.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.events import ReviewRequestEvent, event_bus
from app.modules.orders.models import Order
from app.modules.profiles.models import Profile
from app.modules.reviews.repository import ReviewRepository

log = structlog.get_logger(__name__)
_review_repo = ReviewRepository()


async def run() -> None:
    t0 = time.perf_counter()
    log.info("review_reminder_started")
    try:
        delay = timedelta(hours=settings.REVIEW_REMINDER_DELAY_HOURS)
        window_end = datetime.now(UTC) - delay
        window_start = window_end - timedelta(hours=1)  # matches the hourly schedule

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Order, Profile.email)
                .join(Profile, Profile.id == Order.user_id)
                .where(
                    Order.status == "delivered",
                    Order.delivered_at >= window_start,
                    Order.delivered_at < window_end,
                )
            )
            rows = result.all()
            sent = 0
            for order, email in rows:
                if not email:
                    continue
                already_reviewed = await _review_repo.has_any_review(
                    db, order_id=order.id
                )
                if already_reviewed:
                    continue
                await event_bus.publish(
                    ReviewRequestEvent(
                        order_id=str(order.id),
                        user_id=str(order.user_id),
                        customer_email=email,
                        order_number=order.order_number,
                    )
                )
                sent += 1

        duration_ms = round((time.perf_counter() - t0) * 1000)
        log.info(
            "review_reminder_completed",
            candidates=len(rows),
            sent=sent,
            duration_ms=duration_ms,
        )
    except Exception:
        duration_ms = round((time.perf_counter() - t0) * 1000)
        log.exception("review_reminder_failed", duration_ms=duration_ms)


if __name__ == "__main__":
    import asyncio

    asyncio.run(run())

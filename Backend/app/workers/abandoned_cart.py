"""
Detect carts idle past ABANDONED_CART_THRESHOLD_HOURS and send reminder emails
(when the cart_abandonment_emails feature flag is on).
Run every ABANDONED_CART_INTERVAL seconds.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.modules.cart.models import Cart, CartItem
from app.modules.profiles.models import Profile

log = structlog.get_logger(__name__)


async def run() -> None:
    t0 = time.perf_counter()
    log.info("abandoned_cart_started")
    try:
        cutoff = datetime.now(UTC) - timedelta(
            hours=settings.ABANDONED_CART_THRESHOLD_HOURS
        )

        async with AsyncSessionLocal() as db:
            from app.modules.settings.service import SettingsService

            if not await SettingsService.is_feature_enabled(
                db, "cart_abandonment_emails"
            ):
                log.info("abandoned_cart_skipped", reason="feature_disabled")
                return

            result = await db.execute(
                select(Cart.user_id, func.count(CartItem.id).label("item_count"))
                .join(CartItem, CartItem.cart_id == Cart.id)
                .where(Cart.user_id.isnot(None), Cart.updated_at <= cutoff)
                .group_by(Cart.user_id)
            )
            rows = result.all()
            log.info("abandoned_cart_found", candidates=len(rows))

            sent = 0
            for row in rows:
                try:
                    profile_result = await db.execute(
                        select(Profile).where(Profile.id == row.user_id)
                    )
                    profile = profile_result.scalar_one_or_none()
                    if profile and profile.email and profile.is_active:
                        from app.modules.notifications.service import (
                            NotificationService,
                        )

                        await NotificationService().send_email(
                            db,
                            user_id=row.user_id,
                            event_type="abandoned_cart",
                            recipient=profile.email,
                            context={
                                "full_name": profile.full_name or "",
                                "item_count": row.item_count,
                            },
                        )
                        sent += 1
                except Exception:
                    log.exception(
                        "abandoned_cart_send_failed", user_id=str(row.user_id)
                    )

        duration_ms = round((time.perf_counter() - t0) * 1000)
        log.info("abandoned_cart_completed", sent=sent, duration_ms=duration_ms)
    except Exception:
        duration_ms = round((time.perf_counter() - t0) * 1000)
        log.exception("abandoned_cart_failed", duration_ms=duration_ms)


if __name__ == "__main__":
    import asyncio

    asyncio.run(run())

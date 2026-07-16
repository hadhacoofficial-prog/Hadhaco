"""Welcome-email bridge.

Registration happens entirely client-side (Supabase `auth.signUp`; a DB
trigger creates the `profiles` row), so no backend code runs at signup and
`UserRegisteredEvent` had no publisher. This bridge publishes it on the first
authenticated request (`GET /me`, which every session start calls) for
profiles created within the last 48 hours.

Idempotence, in order:
1. Redis SETNX claim (atomic across workers, 7-day TTL)
2. notification_logs existence check (survives Redis restarts)

Any failure is swallowed — /me must never break because of the welcome email.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import UserRegisteredEvent, event_bus
from app.modules.notifications.repository import NotificationRepository

logger = structlog.get_logger(__name__)

_WELCOME_WINDOW = timedelta(hours=48)
_CLAIM_TTL_SECONDS = 7 * 24 * 3600


async def maybe_publish_welcome(db: AsyncSession, redis: Any, profile: Any) -> None:
    try:
        created_at = getattr(profile, "created_at", None)
        if created_at is None:
            return
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        if datetime.now(UTC) - created_at > _WELCOME_WINDOW:
            return

        claimed = True
        try:
            claimed = bool(
                await redis.set(
                    f"notif:welcome_sent:{profile.id}",
                    "1",
                    nx=True,
                    ex=_CLAIM_TTL_SECONDS,
                )
            )
        except Exception:
            pass  # Redis down → fall through to the DB check
        if not claimed:
            return

        if await NotificationRepository().has_log_for_user_event(
            db, user_id=profile.id, event_type="user_registered"
        ):
            return

        await event_bus.publish(
            UserRegisteredEvent(
                user_id=str(profile.id),
                email=profile.email or "",
                full_name=profile.full_name or "",
            )
        )
        logger.info("welcome_email_published", user_id=str(profile.id))
    except Exception as exc:
        logger.warning("welcome_email_bridge_failed", error=str(exc))

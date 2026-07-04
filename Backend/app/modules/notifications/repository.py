from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import (
    NotificationLog,
    NotificationPreference,
    NotificationTemplate,
)

_RETRY_DELAYS = [1, 5, 15]  # minutes


class NotificationRepository:
    async def get_template(
        self, db: AsyncSession, *, event_type: str, channel: str
    ) -> NotificationTemplate | None:
        result = await db.execute(
            select(NotificationTemplate).where(
                NotificationTemplate.event_type == event_type,
                NotificationTemplate.channel == channel,
                NotificationTemplate.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def create_log(self, db: AsyncSession, **kwargs: Any) -> NotificationLog:
        log = NotificationLog(**kwargs)
        db.add(log)
        await db.flush()
        return log

    async def mark_sent(
        self,
        db: AsyncSession,
        log: NotificationLog,
        provider_message_id: str,
        provider: str,
    ) -> None:
        log.status = "sent"
        log.provider = provider
        log.provider_message_id = provider_message_id
        log.attempt_count += 1
        db.add(log)
        await db.flush()

    async def mark_failed(
        self, db: AsyncSession, log: NotificationLog, error: str
    ) -> None:
        """Increment attempt count and schedule exponential-backoff retry."""
        log.attempt_count += 1
        attempt = log.attempt_count
        if attempt < len(_RETRY_DELAYS):
            log.status = "retrying"
            log.next_retry_at = datetime.now(UTC) + timedelta(
                minutes=_RETRY_DELAYS[attempt - 1]
            )
        else:
            log.status = "failed"
            log.next_retry_at = None
        log.error_message = error
        db.add(log)
        await db.flush()

    async def mark_permanently_failed(
        self, db: AsyncSession, log: NotificationLog, error: str
    ) -> None:
        """Mark as failed immediately with no retry scheduled.

        Use for configuration errors (bad API key, unverified domain) that
        cannot self-heal between retry attempts.
        """
        log.attempt_count += 1
        log.status = "failed"
        log.next_retry_at = None
        log.error_message = error
        db.add(log)
        await db.flush()

    async def get_pending_retries(self, db: AsyncSession) -> list[NotificationLog]:
        result = await db.execute(
            select(NotificationLog).where(
                NotificationLog.status == "retrying",
                NotificationLog.next_retry_at <= datetime.now(UTC),
            )
        )
        return list(result.scalars().all())

    async def get_preferences(
        self, db: AsyncSession, user_id: uuid.UUID
    ) -> NotificationPreference | None:
        result = await db.execute(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def upsert_preferences(
        self, db: AsyncSession, user_id: uuid.UUID, data: dict[str, Any]
    ) -> NotificationPreference:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = (
            pg_insert(NotificationPreference)
            .values(user_id=user_id, **data)
            .on_conflict_do_update(
                index_elements=[NotificationPreference.user_id],
                set_=data,
            )
            .returning(NotificationPreference)
        )
        result = await db.execute(stmt)
        await db.flush()
        return result.scalar_one()

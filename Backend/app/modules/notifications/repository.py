from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import (
    NotificationLog,
    NotificationPreference,
    NotificationRule,
    NotificationTemplate,
    NotificationTemplateVersion,
)

_CONTENT_FIELDS = {"subject", "template_body", "variables"}

_RETRY_DELAYS = [1, 5, 15]  # minutes


class NotificationRepository:
    # ── Templates ─────────────────────────────────────────────────────────────

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

    async def list_templates(self, db: AsyncSession) -> list[NotificationTemplate]:
        result = await db.execute(
            select(NotificationTemplate).order_by(NotificationTemplate.event_type)
        )
        return list(result.scalars().all())

    async def get_template_by_id(
        self, db: AsyncSession, template_id: uuid.UUID
    ) -> NotificationTemplate | None:
        result = await db.execute(
            select(NotificationTemplate).where(NotificationTemplate.id == template_id)
        )
        return result.scalar_one_or_none()

    async def update_template(
        self,
        db: AsyncSession,
        template_id: uuid.UUID,
        data: dict[str, Any],
        *,
        updated_by: uuid.UUID | None = None,
    ) -> NotificationTemplate | None:
        template = await self.get_template_by_id(db, template_id)
        if not template:
            return None

        if _CONTENT_FIELDS & data.keys():
            db.add(
                NotificationTemplateVersion(
                    template_id=template.id,
                    version=template.version,
                    subject=template.subject,
                    template_body=template.template_body,
                    variables=template.variables,
                    created_by=updated_by,
                )
            )
            template.version += 1

        for key, value in data.items():
            if hasattr(template, key):
                setattr(template, key, value)
        template.updated_at = datetime.now(UTC)
        db.add(template)
        await db.flush()
        return template

    async def list_template_versions(
        self, db: AsyncSession, template_id: uuid.UUID
    ) -> list[NotificationTemplateVersion]:
        result = await db.execute(
            select(NotificationTemplateVersion)
            .where(NotificationTemplateVersion.template_id == template_id)
            .order_by(NotificationTemplateVersion.version.desc())
        )
        return list(result.scalars().all())

    async def get_template_version(
        self, db: AsyncSession, template_id: uuid.UUID, version: int
    ) -> NotificationTemplateVersion | None:
        result = await db.execute(
            select(NotificationTemplateVersion).where(
                NotificationTemplateVersion.template_id == template_id,
                NotificationTemplateVersion.version == version,
            )
        )
        return result.scalar_one_or_none()

    async def duplicate_template(
        self, db: AsyncSession, template_id: uuid.UUID
    ) -> NotificationTemplate | None:
        """Copy a template's content into a new, inactive row so it never
        competes with the live template for the same (event_type, channel)."""
        source = await self.get_template_by_id(db, template_id)
        if not source:
            return None
        copy = NotificationTemplate(
            name=f"{source.name}_copy_{uuid.uuid4().hex[:8]}",
            channel=source.channel,
            event_type=source.event_type,
            subject=source.subject,
            template_body=source.template_body,
            variables=source.variables,
            is_active=False,
        )
        db.add(copy)
        await db.flush()
        return copy

    # ── Rules (notification matrix) ───────────────────────────────────────────

    async def get_rule(
        self, db: AsyncSession, *, event_type: str
    ) -> NotificationRule | None:
        result = await db.execute(
            select(NotificationRule).where(NotificationRule.event_type == event_type)
        )
        return result.scalar_one_or_none()

    async def list_rules(self, db: AsyncSession) -> list[NotificationRule]:
        result = await db.execute(
            select(NotificationRule).order_by(NotificationRule.event_type)
        )
        rules = list(result.scalars().all())

        triggered_result = await db.execute(
            select(
                NotificationLog.event_type,
                func.max(NotificationLog.created_at).label("last_triggered_at"),
            ).group_by(NotificationLog.event_type)
        )
        last_triggered = {
            row.event_type: row.last_triggered_at for row in triggered_result.all()
        }

        sent_result = await db.execute(
            select(
                NotificationLog.event_type,
                func.max(NotificationLog.created_at).label("last_sent_at"),
            )
            .where(NotificationLog.status.in_(["sent", "delivered", "read"]))
            .group_by(NotificationLog.event_type)
        )
        last_sent = {row.event_type: row.last_sent_at for row in sent_result.all()}

        for rule in rules:
            # Transient, in-memory only — not a mapped column, never persisted.
            rule.last_triggered_at = last_triggered.get(rule.event_type)  # type: ignore[attr-defined]
            rule.last_sent_at = last_sent.get(rule.event_type)  # type: ignore[attr-defined]
        return rules

    async def upsert_rule(
        self,
        db: AsyncSession,
        *,
        event_type: str,
        display_name: str | None = None,
        category: str | None = None,
        description: str | None = None,
        enabled: bool | None = None,
        email_enabled: bool | None = None,
        whatsapp_enabled: bool | None = None,
        priority: str | None = None,
        retry_policy: dict[str, Any] | None = None,
        cooldown_seconds: int | None = None,
        customer_visible: bool | None = None,
        admin_visible: bool | None = None,
        display_order: int | None = None,
    ) -> NotificationRule:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        candidates: dict[str, Any] = {
            "display_name": display_name,
            "category": category,
            "description": description,
            "enabled": enabled,
            "email_enabled": email_enabled,
            "whatsapp_enabled": whatsapp_enabled,
            "priority": priority,
            "retry_policy": retry_policy,
            "cooldown_seconds": cooldown_seconds,
            "customer_visible": customer_visible,
            "admin_visible": admin_visible,
            "display_order": display_order,
        }
        values: dict[str, Any] = {"event_type": event_type}
        values.update({k: v for k, v in candidates.items() if v is not None})

        stmt = (
            pg_insert(NotificationRule)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[NotificationRule.event_type],
                set_={k: v for k, v in values.items() if k != "event_type"},
            )
            .returning(NotificationRule)
        )
        result = await db.execute(stmt)
        await db.flush()
        return result.scalar_one()

    async def should_send(
        self, db: AsyncSession, *, event_type: str, channel: str
    ) -> bool:
        rule = await self.get_rule(db, event_type=event_type)
        if not rule or not rule.enabled:
            return False
        if channel == "email":
            return rule.email_enabled
        if channel == "whatsapp":
            return rule.whatsapp_enabled
        return False

    # ── Logs ──────────────────────────────────────────────────────────────────

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
        log.sent_at = datetime.now(UTC)
        db.add(log)
        await db.flush()

    async def get_log_by_provider_message_id(
        self, db: AsyncSession, provider_message_id: str
    ) -> NotificationLog | None:
        result = await db.execute(
            select(NotificationLog).where(
                NotificationLog.provider_message_id == provider_message_id
            )
        )
        return result.scalar_one_or_none()

    async def get_log_by_id(
        self, db: AsyncSession, log_id: uuid.UUID
    ) -> NotificationLog | None:
        result = await db.execute(
            select(NotificationLog).where(NotificationLog.id == log_id)
        )
        return result.scalar_one_or_none()

    async def mark_delivered(
        self,
        db: AsyncSession,
        log: NotificationLog,
    ) -> None:
        log.status = "delivered"
        log.delivered_at = datetime.now(UTC)
        db.add(log)
        await db.flush()

    async def mark_read(
        self,
        db: AsyncSession,
        log: NotificationLog,
    ) -> None:
        log.status = "read"
        log.read_at = datetime.now(UTC)
        db.add(log)
        await db.flush()

    async def mark_failed(
        self, db: AsyncSession, log: NotificationLog, error: str
    ) -> None:
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
            log.failed_at = datetime.now(UTC)
        log.error_message = error
        db.add(log)
        await db.flush()

    async def mark_permanently_failed(
        self, db: AsyncSession, log: NotificationLog, error: str
    ) -> None:
        log.attempt_count += 1
        log.status = "failed"
        log.next_retry_at = None
        log.failed_at = datetime.now(UTC)
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

    async def list_logs(
        self,
        db: AsyncSession,
        *,
        status: str | None = None,
        channel: str | None = None,
        event_type: str | None = None,
        category: str | None = None,
        provider: str | None = None,
        search: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[NotificationLog], int]:
        q = select(NotificationLog)
        count_q = select(func.count(NotificationLog.id))

        conditions = []
        if status:
            conditions.append(NotificationLog.status == status)
        if channel:
            conditions.append(NotificationLog.channel == channel)
        if event_type:
            conditions.append(NotificationLog.event_type == event_type)
        if category:
            conditions.append(
                NotificationLog.event_type.in_(
                    select(NotificationRule.event_type).where(
                        NotificationRule.category == category
                    )
                )
            )
        if provider:
            conditions.append(NotificationLog.provider == provider)
        if date_from:
            conditions.append(NotificationLog.created_at >= date_from)
        if date_to:
            conditions.append(NotificationLog.created_at <= date_to)
        if search:
            try:
                search_id = uuid.UUID(search)
            except ValueError:
                search_id = None
            if search_id is not None:
                conditions.append(NotificationLog.id == search_id)
            else:
                pattern = f"%{search}%"
                conditions.append(
                    NotificationLog.recipient.ilike(pattern)
                    | NotificationLog.rendered_subject.ilike(pattern)
                    | NotificationLog.rendered_body.ilike(pattern)
                )

        for condition in conditions:
            q = q.where(condition)
            count_q = count_q.where(condition)

        total_result = await db.execute(count_q)
        total = total_result.scalar() or 0

        q = q.order_by(NotificationLog.created_at.desc())
        result = await db.execute(q.offset(offset).limit(limit))
        logs = list(result.scalars().all())

        return logs, total

    async def get_analytics(
        self, db: AsyncSession, *, hours: int = 24
    ) -> dict[str, int]:
        since = datetime.now(UTC) - timedelta(hours=hours)
        base = NotificationLog.created_at >= since

        # Single query for all status-based counters via CASE expressions
        counters_q = await db.execute(
            select(
                func.count(NotificationLog.id)
                .filter(NotificationLog.status == "sent")
                .label("total_sent"),
                func.count(NotificationLog.id)
                .filter(NotificationLog.status == "failed")
                .label("total_failed"),
                func.count(NotificationLog.id)
                .filter(NotificationLog.status == "pending")
                .label("total_pending"),
                func.count(NotificationLog.id)
                .filter(NotificationLog.status == "retrying")
                .label("total_retrying"),
                func.count(NotificationLog.id)
                .filter(NotificationLog.status == "delivered")
                .label("total_delivered"),
                func.count(NotificationLog.id)
                .filter(NotificationLog.status == "read")
                .label("total_read"),
                func.count(NotificationLog.id)
                .filter(NotificationLog.attempt_count > 1)
                .label("total_retried"),
                func.count(NotificationLog.id)
                .filter(
                    (NotificationLog.status == "sent")
                    & (NotificationLog.channel == "email")
                )
                .label("email_sent"),
                func.count(NotificationLog.id)
                .filter(
                    (NotificationLog.status == "failed")
                    & (NotificationLog.channel == "email")
                )
                .label("email_failed"),
                func.count(NotificationLog.id)
                .filter(
                    (NotificationLog.status == "sent")
                    & (NotificationLog.channel == "whatsapp")
                )
                .label("whatsapp_sent"),
                func.count(NotificationLog.id)
                .filter(
                    (NotificationLog.status == "failed")
                    & (NotificationLog.channel == "whatsapp")
                )
                .label("whatsapp_failed"),
            ).where(base)
        )
        row = counters_q.one()
        return {
            "total_sent": row.total_sent,
            "total_failed": row.total_failed,
            "total_pending": row.total_pending,
            "total_retrying": row.total_retrying,
            "email_sent": row.email_sent,
            "email_failed": row.email_failed,
            "whatsapp_sent": row.whatsapp_sent,
            "whatsapp_failed": row.whatsapp_failed,
            "total_delivered": row.total_delivered,
            "total_read": row.total_read,
            "total_retried": row.total_retried,
        }

    async def get_daily_totals(
        self, db: AsyncSession, *, days: int = 14
    ) -> list[dict[str, Any]]:
        since = datetime.now(UTC) - timedelta(days=days)
        day = func.date_trunc("day", NotificationLog.created_at)
        result = await db.execute(
            select(
                day.label("day"),
                func.count(NotificationLog.id)
                .filter(NotificationLog.status == "sent")
                .label("sent"),
                func.count(NotificationLog.id)
                .filter(NotificationLog.status == "delivered")
                .label("delivered"),
                func.count(NotificationLog.id)
                .filter(NotificationLog.status == "failed")
                .label("failed"),
            )
            .where(NotificationLog.created_at >= since)
            .group_by(day)
            .order_by(day)
        )
        return [
            {
                "date": row.day.date().isoformat(),
                "sent": row.sent,
                "delivered": row.delivered,
                "failed": row.failed,
            }
            for row in result.all()
        ]

    async def get_top_templates(
        self, db: AsyncSession, *, limit: int = 5
    ) -> list[dict[str, Any]]:
        sent_count = func.count(NotificationLog.id).label("sent_count")
        result = await db.execute(
            select(
                NotificationTemplate.name,
                NotificationTemplate.event_type,
                NotificationTemplate.channel,
                sent_count,
            )
            .join(
                NotificationLog,
                (NotificationLog.event_type == NotificationTemplate.event_type)
                & (NotificationLog.channel == NotificationTemplate.channel),
            )
            .where(NotificationLog.status.in_(["sent", "delivered", "read"]))
            .group_by(
                NotificationTemplate.name,
                NotificationTemplate.event_type,
                NotificationTemplate.channel,
            )
            .order_by(sent_count.desc())
            .limit(limit)
        )
        return [
            {
                "name": row.name,
                "event_type": row.event_type,
                "channel": row.channel,
                "sent_count": row.sent_count,
            }
            for row in result.all()
        ]

    async def get_provider_success_rate(self, db: AsyncSession) -> dict[str, Any]:
        result = await db.execute(
            select(
                NotificationLog.provider,
                func.count(NotificationLog.id)
                .filter(NotificationLog.status.in_(["sent", "delivered", "read"]))
                .label("sent"),
                func.count(NotificationLog.id)
                .filter(NotificationLog.status == "failed")
                .label("failed"),
            )
            .where(NotificationLog.provider.is_not(None))
            .group_by(NotificationLog.provider)
        )
        rates: dict[str, Any] = {}
        for row in result.all():
            total = row.sent + row.failed
            rates[row.provider] = {
                "sent": row.sent,
                "failed": row.failed,
                "success_rate": (row.sent / total) if total else 0.0,
            }
        return rates

    async def get_average_delivery_seconds(self, db: AsyncSession) -> float | None:
        result = await db.execute(
            select(
                func.avg(
                    func.extract(
                        "epoch", NotificationLog.delivered_at - NotificationLog.sent_at
                    )
                )
            ).where(
                NotificationLog.sent_at.is_not(None),
                NotificationLog.delivered_at.is_not(None),
            )
        )
        avg = result.scalar()
        return float(avg) if avg is not None else None

    # ── Provider health ────────────────────────────────────────────────────────

    async def get_provider_health_stats(
        self, db: AsyncSession, *, channel: str
    ) -> dict[str, Any]:
        last_success = (
            await db.execute(
                select(NotificationLog)
                .where(
                    NotificationLog.channel == channel,
                    NotificationLog.status.in_(["sent", "delivered", "read"]),
                )
                .order_by(NotificationLog.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        last_failure = (
            await db.execute(
                select(NotificationLog)
                .where(
                    NotificationLog.channel == channel,
                    NotificationLog.status == "failed",
                )
                .order_by(NotificationLog.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        last_webhook = (
            await db.execute(
                select(NotificationLog)
                .where(
                    NotificationLog.channel == channel,
                    NotificationLog.status.in_(["delivered", "read"]),
                )
                .order_by(NotificationLog.updated_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        return {
            "last_success_at": last_success.created_at if last_success else None,
            "last_failure_at": last_failure.created_at if last_failure else None,
            "last_failure_message": (
                last_failure.error_message if last_failure else None
            ),
            "last_webhook_at": (last_webhook.updated_at if last_webhook else None),
        }

    # ── Preferences ───────────────────────────────────────────────────────────

    async def get_preferences(
        self, db: AsyncSession, user_id: uuid.UUID
    ) -> NotificationPreference | None:
        result = await db.execute(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def get_preferences_for_channel(
        self, db: AsyncSession, user_id: uuid.UUID, *, channel: str
    ) -> bool:
        """Check if a user has a specific channel enabled. Defaults to True."""
        pref = await self.get_preferences(db, user_id)
        if not pref:
            return True
        if channel == "email":
            return pref.email_enabled
        if channel == "whatsapp":
            return pref.whatsapp_enabled
        return True

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

from __future__ import annotations

import uuid
from typing import Any

import structlog
from jinja2 import BaseLoader, Environment
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.events import (
    OrderCreatedEvent,
    PaymentCapturedEvent,
    PaymentFailedEvent,
    RefundCreatedEvent,
    RefundFailedEvent,
    RefundProcessedEvent,
    UserRegisteredEvent,
    event_bus,
)
from app.modules.notifications.models import NotificationLog
from app.modules.notifications.providers.msg91_sms import MSG91SMSProvider
from app.modules.notifications.providers.resend import (
    ResendAuthError,
    ResendDomainError,
    ResendProvider,
)
from app.modules.notifications.repository import NotificationRepository

logger = structlog.get_logger(__name__)

_jinja = Environment(loader=BaseLoader(), autoescape=True)


class NotificationService:
    def __init__(self) -> None:
        self._repo = NotificationRepository()
        self._email_primary = ResendProvider()
        self._sms = MSG91SMSProvider()

    # ── Core send ─────────────────────────────────────────────────────────────

    async def send_email(
        self,
        db: AsyncSession,
        *,
        user_id: str | uuid.UUID | None,
        event_type: str,
        recipient: str,
        context: dict[str, Any],
    ) -> None:
        template = await self._repo.get_template(
            db, event_type=event_type, channel="email"
        )
        if not template:
            logger.warning("no_email_template", event_type=event_type)
            return

        subject = _jinja.from_string(template.subject or "").render(**context)
        html = _jinja.from_string(template.template_body).render(**context)

        log = await self._repo.create_log(
            db,
            user_id=user_id,
            channel="email",
            event_type=event_type,
            recipient=recipient,
            status="pending",
        )
        await db.commit()

        try:
            msg_id = await self._email_primary.send_email(
                to=recipient, subject=subject, html=html
            )
            await self._repo.mark_sent(db, log, msg_id, "resend")
            await db.commit()
        except (ResendAuthError, ResendDomainError) as err:
            # Auth/domain errors will not self-heal with retries — mark permanently
            # failed immediately so the retry worker doesn't hammer a dead key.
            logger.error(
                "email_provider_config_error",
                event_type=event_type,
                recipient=recipient,
                error=str(err),
            )
            await self._repo.mark_permanently_failed(db, log, str(err))
            await db.commit()
        except Exception as err:
            logger.error(
                "email_send_failed",
                event_type=event_type,
                recipient=recipient,
                error=str(err),
            )
            await self._repo.mark_failed(db, log, str(err))
            await db.commit()

    async def send_sms(
        self,
        db: AsyncSession,
        *,
        user_id: str | uuid.UUID | None,
        event_type: str,
        recipient: str,
        context: dict[str, Any],
    ) -> None:
        if not settings.SMS_ENABLED:
            logger.info(
                "sms_skipped_disabled",
                event_type=event_type,
                extra={"event": event_type},
            )
            return

        template = await self._repo.get_template(
            db, event_type=event_type, channel="sms"
        )
        if not template:
            logger.warning("no_sms_template", event_type=event_type)
            return

        body = _jinja.from_string(template.template_body).render(**context)
        log = await self._repo.create_log(
            db,
            user_id=user_id,
            channel="sms",
            event_type=event_type,
            recipient=recipient,
            status="pending",
        )
        await db.commit()

        try:
            msg_id = await self._sms.send_sms(to=recipient, body=body)
            await self._repo.mark_sent(db, log, msg_id, "msg91")
            logger.info(
                "sms_sent",
                event_type=event_type,
                recipient=recipient,
                request_id=msg_id,
            )
            await db.commit()
        except Exception as err:
            logger.error(
                "sms_send_failed",
                event_type=event_type,
                recipient=recipient,
                error=str(err),
            )
            await self._repo.mark_failed(db, log, str(err))
            await db.commit()

    async def retry_pending(self, db: AsyncSession) -> None:
        logs = await self._repo.get_pending_retries(db)
        # Cache templates by (event_type, channel) — a retry backlog is
        # typically dominated by a handful of distinct pairs, so this turns
        # what used to be one template fetch per log into one per pair.
        template_cache: dict[tuple[str, str], Any] = {}
        for log in logs:
            key = (log.event_type, log.channel)
            if key not in template_cache:
                template_cache[key] = await self._repo.get_template(
                    db, event_type=log.event_type, channel=log.channel
                )
            await self._retry_log(db, log, template_cache[key])

    async def _retry_log(
        self, db: AsyncSession, log: NotificationLog, template: Any
    ) -> None:
        if not template:
            return
        try:
            if log.channel == "email":
                msg_id = await self._email_primary.send_email(
                    to=log.recipient,
                    subject=template.subject or "",
                    html=template.template_body,
                )
                await self._repo.mark_sent(db, log, msg_id, "resend")
            elif log.channel == "sms":
                if not settings.SMS_ENABLED:
                    logger.info("sms_retry_skipped_disabled", log_id=str(log.id))
                    return
                msg_id = await self._sms.send_sms(
                    to=log.recipient, body=template.template_body
                )
                await self._repo.mark_sent(db, log, msg_id, "msg91")
            await db.commit()
        except (ResendAuthError, ResendDomainError) as err:
            # Config errors won't fix themselves on retry — permanently fail.
            logger.error(
                "retry_provider_config_error", log_id=str(log.id), error=str(err)
            )
            await self._repo.mark_permanently_failed(db, log, str(err))
            await db.commit()
        except Exception as err:
            logger.error(
                "retry_failed", log_id=str(log.id), channel=log.channel, error=str(err)
            )
            await self._repo.mark_failed(db, log, str(err))
            await db.commit()

    # ── Event listener registration ───────────────────────────────────────────

    @classmethod
    def register_listeners(cls) -> None:
        svc = cls()

        async def _handle_user_registered(event: UserRegisteredEvent) -> None:
            from app.core.database import AsyncWorkerSessionLocal

            async with AsyncWorkerSessionLocal() as db:
                await svc.send_email(
                    db,
                    user_id=event.user_id,
                    event_type="user_registered",
                    recipient=event.email,
                    context={
                        "full_name": event.full_name,
                        "frontend_url": settings.FRONTEND_URL,
                    },
                )

        async def _handle_order_created(event: OrderCreatedEvent) -> None:
            # Order placed: email always, SMS if enabled
            from app.core.database import AsyncWorkerSessionLocal

            async with AsyncWorkerSessionLocal() as db:
                ctx = {
                    "order_number": event.order_number,
                    "total": event.total_amount,
                    "frontend_url": settings.FRONTEND_URL,
                }
                await svc.send_email(
                    db,
                    user_id=event.user_id,
                    event_type="order_created",
                    recipient=event.customer_email,
                    context=ctx,
                )
                if event.customer_phone:
                    await svc.send_sms(
                        db,
                        user_id=event.user_id,
                        event_type="order_created",
                        recipient=event.customer_phone,
                        context=ctx,
                    )

        async def _handle_payment_captured(event: PaymentCapturedEvent) -> None:
            if not event.customer_email:
                return
            from app.core.database import AsyncWorkerSessionLocal

            async with AsyncWorkerSessionLocal() as db:
                await svc.send_email(
                    db,
                    user_id=event.user_id,
                    event_type="payment_captured",
                    recipient=event.customer_email,
                    context={
                        "order_number": event.order_number,
                        "amount": event.amount,
                        "frontend_url": settings.FRONTEND_URL,
                    },
                )

        async def _handle_payment_failed(event: PaymentFailedEvent) -> None:
            # Optional per product spec — silently skip if we don't have an
            # email to send to (e.g. order resolved from webhook data alone).
            from app.core.database import AsyncWorkerSessionLocal
            from app.modules.orders.repository import OrderRepository
            from app.modules.profiles.repository import ProfileRepository

            async with AsyncWorkerSessionLocal() as db:
                order = await OrderRepository().get_by_id(db, uuid.UUID(event.order_id))
                if not order:
                    return
                profile = await ProfileRepository().get_by_id(db, order.user_id)
                if not profile or not profile.email:
                    return
                await svc.send_email(
                    db,
                    user_id=event.user_id,
                    event_type="payment_failed",
                    recipient=profile.email,
                    context={
                        "order_number": order.order_number,
                        "reason": event.reason,
                        "frontend_url": settings.FRONTEND_URL,
                    },
                )

        async def _handle_refund_created(event: RefundCreatedEvent) -> None:
            if not event.customer_email:
                return
            from app.core.database import AsyncWorkerSessionLocal

            async with AsyncWorkerSessionLocal() as db:
                await svc.send_email(
                    db,
                    user_id=event.user_id,
                    event_type="refund_created",
                    recipient=event.customer_email,
                    context={
                        "order_number": event.order_number,
                        "amount": event.amount,
                        "frontend_url": settings.FRONTEND_URL,
                    },
                )

        async def _handle_refund_processed(event: RefundProcessedEvent) -> None:
            if not event.customer_email:
                return
            from app.core.database import AsyncWorkerSessionLocal

            async with AsyncWorkerSessionLocal() as db:
                await svc.send_email(
                    db,
                    user_id=event.user_id,
                    event_type="refund_processed",
                    recipient=event.customer_email,
                    context={
                        "order_number": event.order_number,
                        "amount": event.amount,
                        "frontend_url": settings.FRONTEND_URL,
                    },
                )

        async def _handle_refund_failed(event: RefundFailedEvent) -> None:
            # Admin alert — refund failures need human follow-up with Razorpay
            # or the customer, they don't resolve themselves.
            from app.core.database import AsyncWorkerSessionLocal

            async with AsyncWorkerSessionLocal() as db:
                await svc.send_email(
                    db,
                    user_id=None,
                    event_type="refund_failed_admin_alert",
                    recipient=settings.ADMIN_ALERT_EMAIL,
                    context={
                        "order_number": event.order_number,
                        "refund_id": event.refund_id,
                        "amount": event.amount,
                        "reason": event.reason,
                    },
                )

        event_bus.on(UserRegisteredEvent, _handle_user_registered)
        event_bus.on(OrderCreatedEvent, _handle_order_created)
        event_bus.on(PaymentCapturedEvent, _handle_payment_captured)
        event_bus.on(PaymentFailedEvent, _handle_payment_failed)
        event_bus.on(RefundCreatedEvent, _handle_refund_created)
        event_bus.on(RefundProcessedEvent, _handle_refund_processed)
        event_bus.on(RefundFailedEvent, _handle_refund_failed)


def register_listeners() -> None:
    NotificationService().register_listeners()

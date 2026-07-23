from __future__ import annotations

import uuid
from typing import Any

import structlog
from jinja2.sandbox import SandboxedEnvironment
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.events import (
    OrderCreatedEvent,
    OrderDeliveredEvent,
    OrderShippedEvent,
    OrderStatusChangedEvent,
    PaymentCapturedEvent,
    PaymentFailedEvent,
    RefundCreatedEvent,
    RefundFailedEvent,
    RefundProcessedEvent,
    ReviewRequestEvent,
    UserRegisteredEvent,
    event_bus,
)
from app.modules.notifications.branding import get_brand_context_db
from app.modules.notifications.context import (
    format_inr_number,
    load_order_context,
)
from app.modules.notifications.dispatcher import dispatcher
from app.modules.notifications.dto import (
    EmailPayload,
    ProviderConfig,
    WhatsAppPayload,
)
from app.modules.notifications.models import NotificationLog, NotificationTemplate
from app.modules.notifications.providers.resend import (
    ResendAuthError,
    ResendDomainError,
)
from app.modules.notifications.providers.whatsapp import WhatsAppAuthError
from app.modules.notifications.repository import NotificationRepository
from app.modules.settings.repository import SettingsRepository

logger = structlog.get_logger(__name__)

# Sandboxed environments: admin-editable templates must not reach Python
# internals (SSTI defense-in-depth). HTML bodies autoescape; subjects and
# WhatsApp bodies are plain text, where autoescaping would leak entities
# like &amp; into the copy.
_jinja = SandboxedEnvironment(autoescape=True)
_jinja_text = SandboxedEnvironment(autoescape=False)


class NotificationService:
    def __init__(self) -> None:
        self._repo = NotificationRepository()
        self._dispatcher = dispatcher
        self._settings_repo = SettingsRepository()

    async def _provider_enabled(self, db: AsyncSession, provider: str) -> bool:
        """DB setting overrides, default enabled — same resolution order as
        every other provider config value."""
        config = await self._settings_repo.get_provider_config(db, provider=provider)
        value = config.get("enabled")
        if value is None:
            return True
        return value.lower() == "true"

    async def _resolve_provider_config(
        self, db: AsyncSession, provider: str
    ) -> ProviderConfig:
        """Read provider settings from DB (with env-fallback defaults) once.

        Returns an immutable ProviderConfig so the subsequent HTTP call never
        needs to touch the database again.
        """
        cfg = await self._settings_repo.get_provider_config(db, provider=provider)
        if provider == "email":
            return ProviderConfig(
                email_api_key=cfg.get("api_key") or settings.RESEND_API_KEY,
                email_from_name=cfg.get("from_name") or settings.EMAIL_FROM_NAME,
                email_from_email=cfg.get("from_email") or settings.EMAIL_FROM,
                email_reply_to=cfg.get("reply_to") or settings.EMAIL_REPLY_TO,
            )
        if provider == "whatsapp":
            return ProviderConfig(
                whatsapp_access_token=cfg.get("access_token")
                or settings.WHATSAPP_ACCESS_TOKEN,
                whatsapp_phone_number_id=cfg.get("phone_number_id")
                or settings.WHATSAPP_PHONE_NUMBER_ID,
                whatsapp_api_version=cfg.get("api_version")
                or settings.WHATSAPP_API_VERSION,
            )
        return ProviderConfig()

    # ── Core send methods ─────────────────────────────────────────────────────

    async def send_email(
        self,
        db: AsyncSession,
        *,
        user_id: str | uuid.UUID | None,
        event_type: str,
        recipient: str,
        context: dict[str, Any],
    ) -> None:
        """Send an email notification.

        All DB reads (template, brand context, provider config) and the log
        creation happen while the session is open.  The transaction is committed
        **before** the HTTP call so the connection is returned to the pool — the
        Resend API call runs without holding any database connection.  Delivery
        status is persisted via ``_update_log_status`` which opens its own
        fresh session.
        """
        if not await self._provider_enabled(db, "email"):
            logger.info("email_skipped_disabled", event_type=event_type)
            return

        template = await self._repo.get_template(
            db, event_type=event_type, channel="email"
        )
        if not template or not template.template_body:
            logger.warning("no_email_template", event_type=event_type)
            return

        ctx = {**await get_brand_context_db(db), **context}
        rendered_subject = _jinja_text.from_string(template.subject or "").render(**ctx)
        rendered_body = _jinja.from_string(template.template_body).render(**ctx)

        # Resolve provider config while the session is still open — this is
        # the LAST DB read before commit.  After commit the connection is
        # returned to the pool and the HTTP call below runs without holding
        # any database connection.
        provider_config = await self._resolve_provider_config(db, "email")

        log = await self._repo.create_log(
            db,
            user_id=user_id,
            channel="email",
            event_type=event_type,
            recipient=recipient,
            status="pending",
            rendered_subject=rendered_subject,
            rendered_body=rendered_body,
            template_id=template.id,
            template_version=template.version,
        )
        log_id = log.id
        await db.commit()

        # ── Connection returned to pool — HTTP below (no DB held) ──────────
        payload = EmailPayload(
            to=recipient,
            subject=rendered_subject,
            html=rendered_body,
            api_key=provider_config.email_api_key,
            from_name=provider_config.email_from_name,
            from_email=provider_config.email_from_email,
            reply_to=provider_config.email_reply_to,
        )

        try:
            msg_id = await self._dispatcher.send_email(payload)
            await self._update_log_status(
                log_id, "sent", msg_id=msg_id, provider="resend"
            )
        except (ResendAuthError, ResendDomainError) as err:
            logger.error(
                "email_provider_config_error",
                event_type=event_type,
                recipient=recipient,
                error=str(err),
            )
            await self._update_log_status(log_id, "permanently_failed", error=str(err))
        except Exception as err:
            logger.error(
                "email_send_failed",
                event_type=event_type,
                recipient=recipient,
                error=str(err),
            )
            await self._update_log_status(log_id, "failed", error=str(err))

    async def _update_log_status(
        self,
        log_id: uuid.UUID,
        status: str,
        *,
        msg_id: str | None = None,
        provider: str | None = None,
        error: str | None = None,
    ) -> None:
        """Open a fresh session to update a single notification log entry."""
        from app.core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            log_entry = await self._repo.get_log_by_id(db, log_id)
            if not log_entry:
                return
            if status == "sent" and msg_id and provider:
                await self._repo.mark_sent(db, log_entry, msg_id, provider)
            elif status == "permanently_failed" and error:
                await self._repo.mark_permanently_failed(db, log_entry, error)
            elif status == "failed" and error:
                await self._repo.mark_failed(db, log_entry, error)
            await db.commit()

    async def send_whatsapp(
        self,
        db: AsyncSession,
        *,
        user_id: str | uuid.UUID | None,
        event_type: str,
        recipient: str,
        context: dict[str, Any],
    ) -> None:
        """Send a WhatsApp template notification.

        All DB reads (template, brand context, provider config) and the log
        creation happen while the session is open.  The transaction is committed
        **before** the HTTP call so the connection is returned to the pool — the
        Meta WhatsApp API call runs without holding any database connection.
        Delivery status is persisted via ``_update_log_status`` which opens its
        own fresh session.
        """
        if not settings.WHATSAPP_ENABLED or not await self._provider_enabled(
            db, "whatsapp"
        ):
            logger.info("whatsapp_skipped_disabled", event_type=event_type)
            return

        template = await self._repo.get_template(
            db, event_type=event_type, channel="whatsapp"
        )
        if not template or not template.template_body:
            logger.warning("no_whatsapp_template", event_type=event_type)
            return

        ctx = {**await get_brand_context_db(db), **context}
        rendered_body = _jinja_text.from_string(template.template_body).render(**ctx)

        variables = template.variables or {}
        wa_params: list[str] = variables.get("params", [])
        whatsapp_params: dict[str, Any] = {
            "template_name": variables.get("whatsapp_template", template.name),
            "language": variables.get("whatsapp_lang", "en_US"),
            "params": [str(ctx.get(p, "")) for p in wa_params],
        }

        log = await self._repo.create_log(
            db,
            user_id=user_id,
            channel="whatsapp",
            event_type=event_type,
            recipient=recipient,
            status="pending",
            rendered_body=rendered_body,
            whatsapp_params=whatsapp_params,
            template_id=template.id,
            template_version=template.version,
        )
        log_id = log.id

        # Resolve provider config while the session is still open — last DB
        # read before commit.  After commit the connection returns to the pool.
        provider_config = await self._resolve_provider_config(db, "whatsapp")
        await db.commit()

        # ── Connection returned to pool — HTTP below (no DB held) ──────────
        components: list[dict] = []
        if wa_params:
            components.append(
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": str(ctx.get(p, ""))} for p in wa_params
                    ],
                }
            )

        payload = WhatsAppPayload(
            to=recipient,
            template_name=whatsapp_params["template_name"],
            language=whatsapp_params["language"],
            components=components,
            access_token=provider_config.whatsapp_access_token,
            phone_number_id=provider_config.whatsapp_phone_number_id,
            api_version=provider_config.whatsapp_api_version,
        )

        try:
            msg_id = await self._dispatcher.send_whatsapp(payload)
            await self._update_log_status(
                log_id, "sent", msg_id=msg_id, provider="whatsapp"
            )
            logger.info(
                "whatsapp_sent",
                event_type=event_type,
                recipient=recipient,
                message_id=msg_id,
            )
        except WhatsAppAuthError as err:
            logger.error(
                "whatsapp_provider_config_error",
                event_type=event_type,
                recipient=recipient,
                error=str(err),
            )
            await self._update_log_status(log_id, "permanently_failed", error=str(err))
        except Exception as err:
            logger.error(
                "whatsapp_send_failed",
                event_type=event_type,
                recipient=recipient,
                error=str(err),
            )
            await self._update_log_status(log_id, "failed", error=str(err))

    # ── Unified dispatch ──────────────────────────────────────────────────────

    async def dispatch(
        self,
        db: AsyncSession,
        *,
        user_id: str | uuid.UUID | None,
        event_type: str,
        recipient: str,
        recipient_phone: str | None = None,
        context: dict[str, Any],
    ) -> None:
        """Send notification to all enabled channels for this event type.

        Checks the notification matrix (NotificationRule) and user preferences
        before sending on each channel.  Each ``send_*`` method commits the
        session before its HTTP call so no database connection is held during
        external API requests.
        """
        # Email channel
        if await self._repo.should_send(db, event_type=event_type, channel="email"):
            if user_id:
                allowed = await self._repo.get_preferences_for_channel(
                    db, uuid.UUID(str(user_id)), channel="email"
                )
                if not allowed:
                    logger.info(
                        "email_skipped_user_preference",
                        event_type=event_type,
                        user_id=str(user_id),
                    )
                else:
                    await self.send_email(
                        db,
                        user_id=user_id,
                        event_type=event_type,
                        recipient=recipient,
                        context=context,
                    )
            else:
                await self.send_email(
                    db,
                    user_id=user_id,
                    event_type=event_type,
                    recipient=recipient,
                    context=context,
                )

        # WhatsApp channel
        if recipient_phone and await self._repo.should_send(
            db, event_type=event_type, channel="whatsapp"
        ):
            if user_id:
                allowed = await self._repo.get_preferences_for_channel(
                    db, uuid.UUID(str(user_id)), channel="whatsapp"
                )
                if not allowed:
                    logger.info(
                        "whatsapp_skipped_user_preference",
                        event_type=event_type,
                        user_id=str(user_id),
                    )
                else:
                    await self.send_whatsapp(
                        db,
                        user_id=user_id,
                        event_type=event_type,
                        recipient=recipient_phone,
                        context=context,
                    )
            else:
                await self.send_whatsapp(
                    db,
                    user_id=user_id,
                    event_type=event_type,
                    recipient=recipient_phone,
                    context=context,
                )

    # ── Retry logic ───────────────────────────────────────────────────────────

    async def retry_pending(self, db: AsyncSession) -> None:
        logs = await self._repo.get_pending_retries(db)
        template_cache: dict[tuple[str, str], NotificationTemplate | None] = {}
        for log_entry in logs:
            cache_key = (log_entry.event_type, log_entry.channel)
            if cache_key not in template_cache:
                template_cache[cache_key] = await self._repo.get_template(
                    db, event_type=log_entry.event_type, channel=log_entry.channel
                )
            await self._retry_log(db, log_entry, template_cache[cache_key])

    async def retry_log_by_id(self, db: AsyncSession, log_id: uuid.UUID) -> bool:
        """Explicit admin-triggered retry of a single log, regardless of its
        current status/next_retry_at gate. Reuses the stored rendered content
        and WhatsApp retry payload from the log entry so variables are not
        lost. Falls back to the current active template for the event_type/
        channel if the pinned template row no longer exists."""
        log_entry = await self._repo.get_log_by_id(db, log_id)
        if not log_entry:
            return False

        template: NotificationTemplate | None = None
        if log_entry.template_id:
            template = await self._repo.get_template_by_id(db, log_entry.template_id)
        if not template:
            template = await self._repo.get_template(
                db, event_type=log_entry.event_type, channel=log_entry.channel
            )
        await self._retry_log(db, log_entry, template)
        return True

    async def _retry_log(
        self,
        db: AsyncSession,
        log_entry: NotificationLog,
        template: NotificationTemplate | None,
    ) -> None:
        """Retry a single notification log entry.

        All DB reads (brand context, provider config) happen here while the
        session is open, then the transaction is committed to return the
        connection to the pool **before** any HTTP call.  The status update
        opens its own fresh session via ``_update_log_status``.
        """
        if not template:
            return
        try:
            if log_entry.channel == "email":
                if not template.template_body:
                    return
                brand = await get_brand_context_db(db)
                rendered_subject = (
                    log_entry.rendered_subject
                    or _jinja_text.from_string(template.subject or "").render(**brand)
                )
                rendered_body = log_entry.rendered_body or _jinja.from_string(
                    template.template_body
                ).render(**brand)
                provider_config = await self._resolve_provider_config(db, "email")
                # ── Commit: return connection to pool before HTTP ───────────
                await db.commit()
                payload = EmailPayload(
                    to=log_entry.recipient,
                    subject=rendered_subject,
                    html=rendered_body,
                    api_key=provider_config.email_api_key,
                    from_name=provider_config.email_from_name,
                    from_email=provider_config.email_from_email,
                    reply_to=provider_config.email_reply_to,
                )
                msg_id = await self._dispatcher.send_email(payload)
                await self._update_log_status(
                    log_entry.id, "sent", msg_id=msg_id, provider="resend"
                )
            elif log_entry.channel == "whatsapp":
                if not settings.WHATSAPP_ENABLED:
                    logger.info(
                        "whatsapp_retry_skipped_disabled", log_id=str(log_entry.id)
                    )
                    return
                if not template.template_body:
                    return
                provider_config = await self._resolve_provider_config(db, "whatsapp")
                # Pre-load brand context if we'll need to re-render from scratch
                brand_ctx: dict[str, Any] = {}
                if not log_entry.whatsapp_params:
                    brand_ctx = await get_brand_context_db(db)
                # ── Commit: return connection to pool before HTTP ───────────
                await db.commit()

                if log_entry.whatsapp_params:
                    wa = log_entry.whatsapp_params
                    components: list[dict] = []
                    params: list[str] = wa.get("params", [])
                    if params:
                        components.append(
                            {
                                "type": "body",
                                "parameters": [
                                    {"type": "text", "text": p} for p in params
                                ],
                            }
                        )
                    wa_payload = WhatsAppPayload(
                        to=log_entry.recipient,
                        template_name=wa["template_name"],
                        language=wa["language"],
                        components=components,
                        access_token=provider_config.whatsapp_access_token,
                        phone_number_id=provider_config.whatsapp_phone_number_id,
                        api_version=provider_config.whatsapp_api_version,
                    )
                    msg_id = await self._dispatcher.send_whatsapp(wa_payload)
                else:
                    # Re-render WhatsApp template from scratch
                    ctx: dict[str, Any] = {**brand_ctx}
                    rendered_body = _jinja_text.from_string(
                        template.template_body
                    ).render(**ctx)
                    variables = template.variables or {}
                    wa_params_list: list[str] = variables.get("params", [])
                    components = []
                    if wa_params_list:
                        components.append(
                            {
                                "type": "body",
                                "parameters": [
                                    {"type": "text", "text": str(ctx.get(p, ""))}
                                    for p in wa_params_list
                                ],
                            }
                        )
                    wa_payload = WhatsAppPayload(
                        to=log_entry.recipient,
                        template_name=variables.get("whatsapp_template", template.name),
                        language=variables.get("whatsapp_lang", "en_US"),
                        components=components,
                        access_token=provider_config.whatsapp_access_token,
                        phone_number_id=provider_config.whatsapp_phone_number_id,
                        api_version=provider_config.whatsapp_api_version,
                    )
                    msg_id = await self._dispatcher.send_whatsapp(wa_payload)
                await self._update_log_status(
                    log_entry.id, "sent", msg_id=msg_id, provider="whatsapp"
                )
        except (ResendAuthError, ResendDomainError, WhatsAppAuthError) as err:
            logger.error(
                "retry_provider_config_error",
                log_id=str(log_entry.id),
                error=str(err),
            )
            await self._update_log_status(
                log_entry.id, "permanently_failed", error=str(err)
            )
        except Exception as err:
            logger.error(
                "retry_failed",
                log_id=str(log_entry.id),
                channel=log_entry.channel,
                error=str(err),
            )
            await self._update_log_status(log_entry.id, "failed", error=str(err))

    # ── Event listener registration ───────────────────────────────────────────

    @classmethod
    def register_listeners(cls) -> None:
        svc = cls()

        async def _profile_phone(db: AsyncSession, user_id: str) -> str | None:
            """Look up the customer's phone so WhatsApp can dispatch for
            events whose publishers only carry an email."""
            if not user_id:
                return None
            from app.modules.profiles.repository import ProfileRepository

            profile = await ProfileRepository().get_by_id(db, uuid.UUID(user_id))
            if profile is None:
                return None
            return getattr(profile, "phone", None)

        async def _handle_user_registered(event: UserRegisteredEvent) -> None:
            from app.core.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                await svc.dispatch(
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
            from app.core.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                _, order_ctx = await load_order_context(db, event.order_id)
                ctx = {
                    **order_ctx,
                    "order_number": event.order_number,
                    "total": order_ctx.get("total")
                    or format_inr_number(event.total_amount),
                    "frontend_url": settings.FRONTEND_URL,
                }
                await svc.dispatch(
                    db,
                    user_id=event.user_id,
                    event_type="order_created",
                    recipient=event.customer_email,
                    recipient_phone=event.customer_phone or None,
                    context=ctx,
                )

        async def _handle_payment_captured(event: PaymentCapturedEvent) -> None:
            if not event.customer_email:
                return
            from app.core.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                _, order_ctx = await load_order_context(db, event.order_id)
                await svc.dispatch(
                    db,
                    user_id=event.user_id,
                    event_type="payment_captured",
                    recipient=event.customer_email,
                    recipient_phone=event.customer_phone or None,
                    context={
                        **order_ctx,
                        "order_number": event.order_number,
                        "amount": format_inr_number(event.amount),
                        "frontend_url": settings.FRONTEND_URL,
                    },
                )

        async def _handle_payment_failed(event: PaymentFailedEvent) -> None:
            from app.core.database import AsyncSessionLocal
            from app.modules.profiles.repository import ProfileRepository

            async with AsyncSessionLocal() as db:
                order, order_ctx = await load_order_context(db, event.order_id)
                if not order:
                    return
                profile = await ProfileRepository().get_by_id(db, order.user_id)
                if not profile or not profile.email:
                    return
                phone = profile.phone if hasattr(profile, "phone") else None
                await svc.dispatch(
                    db,
                    user_id=event.user_id,
                    event_type="payment_failed",
                    recipient=profile.email,
                    recipient_phone=phone,
                    context={
                        **order_ctx,
                        "order_number": order.order_number,
                        "reason": event.reason,
                        "frontend_url": settings.FRONTEND_URL,
                    },
                )

        async def _handle_order_status_changed(
            event: OrderStatusChangedEvent,
        ) -> None:
            from app.core.database import AsyncSessionLocal
            from app.modules.profiles.repository import ProfileRepository

            async with AsyncSessionLocal() as db:
                order, order_ctx = await load_order_context(db, event.order_id)
                if not order:
                    return
                profile = await ProfileRepository().get_by_id(db, order.user_id)
                if not profile or not profile.email:
                    return
                event_type = f"order_{event.new_status}"
                phone = profile.phone if hasattr(profile, "phone") else None
                await svc.dispatch(
                    db,
                    user_id=event.user_id,
                    event_type=event_type,
                    recipient=profile.email,
                    recipient_phone=phone,
                    context={
                        **order_ctx,
                        "order_number": order.order_number,
                        "old_status": event.old_status,
                        "new_status": event.new_status,
                        "frontend_url": settings.FRONTEND_URL,
                    },
                )

        async def _handle_order_shipped(event: OrderShippedEvent) -> None:
            from app.core.database import AsyncSessionLocal
            from app.modules.profiles.repository import ProfileRepository

            async with AsyncSessionLocal() as db:
                order, order_ctx = await load_order_context(db, event.order_id)
                if not order:
                    return
                profile = await ProfileRepository().get_by_id(db, order.user_id)
                if not profile or not profile.email:
                    return
                phone = profile.phone if hasattr(profile, "phone") else None
                await svc.dispatch(
                    db,
                    user_id=event.user_id,
                    event_type="order_shipped",
                    recipient=profile.email,
                    recipient_phone=phone,
                    context={
                        **order_ctx,
                        "order_number": order.order_number,
                        "tracking_number": event.tracking_number
                        or order_ctx.get("tracking_number", ""),
                        "tracking_url": event.tracking_url,
                        "awb": event.awb,
                        "timeline_stage": 4,
                        "frontend_url": settings.FRONTEND_URL,
                    },
                )

        async def _handle_order_delivered(event: OrderDeliveredEvent) -> None:
            from app.core.database import AsyncSessionLocal
            from app.modules.profiles.repository import ProfileRepository

            async with AsyncSessionLocal() as db:
                order, order_ctx = await load_order_context(db, event.order_id)
                if not order:
                    return
                profile = await ProfileRepository().get_by_id(db, order.user_id)
                if not profile or not profile.email:
                    return
                phone = profile.phone if hasattr(profile, "phone") else None
                await svc.dispatch(
                    db,
                    user_id=event.user_id,
                    event_type="order_delivered",
                    recipient=profile.email,
                    recipient_phone=phone,
                    context={
                        **order_ctx,
                        "order_number": order.order_number,
                        "timeline_stage": 5,
                        "frontend_url": settings.FRONTEND_URL,
                    },
                )

        async def _handle_refund_created(event: RefundCreatedEvent) -> None:
            if not event.customer_email:
                return
            from app.core.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                _, order_ctx = await load_order_context(db, event.order_id)
                await svc.dispatch(
                    db,
                    user_id=event.user_id,
                    event_type="refund_created",
                    recipient=event.customer_email,
                    recipient_phone=await _profile_phone(db, event.user_id),
                    context={
                        **order_ctx,
                        "order_number": event.order_number,
                        "amount": format_inr_number(event.amount),
                        "frontend_url": settings.FRONTEND_URL,
                    },
                )

        async def _handle_refund_processed(event: RefundProcessedEvent) -> None:
            if not event.customer_email:
                return
            from app.core.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                _, order_ctx = await load_order_context(db, event.order_id)
                await svc.dispatch(
                    db,
                    user_id=event.user_id,
                    event_type="refund_processed",
                    recipient=event.customer_email,
                    recipient_phone=await _profile_phone(db, event.user_id),
                    context={
                        **order_ctx,
                        "order_number": event.order_number,
                        "amount": format_inr_number(event.amount),
                        "frontend_url": settings.FRONTEND_URL,
                    },
                )

        async def _handle_refund_failed(event: RefundFailedEvent) -> None:
            from app.core.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                await svc.dispatch(
                    db,
                    user_id=None,
                    event_type="refund_failed_admin_alert",
                    recipient=settings.ADMIN_ALERT_EMAIL,
                    context={
                        "order_number": event.order_number,
                        "refund_id": event.refund_id,
                        "amount": format_inr_number(event.amount),
                        "reason": event.reason,
                        "admin_order_url": (
                            f"{settings.ADMIN_URL.rstrip('/')}/orders/{event.order_id}"
                            if event.order_id
                            else settings.ADMIN_URL.rstrip("/")
                        ),
                    },
                )

        async def _handle_review_request(event: ReviewRequestEvent) -> None:
            from app.core.database import AsyncSessionLocal
            from app.modules.profiles.repository import ProfileRepository

            email = event.customer_email or event.user_email
            if not email:
                return
            async with AsyncSessionLocal() as db:
                phone = None
                if event.user_id:
                    profile = await ProfileRepository().get_by_id(
                        db, uuid.UUID(event.user_id)
                    )
                    if profile and hasattr(profile, "phone"):
                        phone = profile.phone
                _, order_ctx = await load_order_context(db, event.order_id)
                await svc.dispatch(
                    db,
                    user_id=event.user_id or None,
                    event_type="review_request",
                    recipient=email,
                    recipient_phone=phone,
                    context={
                        **order_ctx,
                        "order_number": event.order_number,
                        "frontend_url": settings.FRONTEND_URL,
                    },
                )

        event_bus.on(UserRegisteredEvent, _handle_user_registered)
        event_bus.on(OrderCreatedEvent, _handle_order_created)
        event_bus.on(PaymentCapturedEvent, _handle_payment_captured)
        event_bus.on(PaymentFailedEvent, _handle_payment_failed)
        event_bus.on(OrderStatusChangedEvent, _handle_order_status_changed)
        event_bus.on(OrderShippedEvent, _handle_order_shipped)
        event_bus.on(OrderDeliveredEvent, _handle_order_delivered)
        event_bus.on(RefundCreatedEvent, _handle_refund_created)
        event_bus.on(RefundProcessedEvent, _handle_refund_processed)
        event_bus.on(RefundFailedEvent, _handle_refund_failed)
        event_bus.on(ReviewRequestEvent, _handle_review_request)


def register_listeners() -> None:
    NotificationService().register_listeners()

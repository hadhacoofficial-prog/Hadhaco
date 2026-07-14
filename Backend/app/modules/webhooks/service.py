"""Razorpay webhook processing.

Production event flow for a single webhook delivery:

  1. Verify HMAC signature (RAZORPAY_WEBHOOK_SECRET) before touching the DB.
  2. Idempotency guard: look up (provider, event_id). If already fully
     processed, return immediately without re-running any business logic.
     If seen before but not yet successfully processed (a Razorpay retry of
     a previously-failed delivery), reuse the same row and bump
     processing_attempts instead of colliding with the unique constraint.
  3. Dispatch by event_type via a handler registry (no if/elif chain).
  4. The handler runs inside a SAVEPOINT (db.begin_nested()) so a failure
     partway through rolls back only its own writes, not the whole request.
  5. On success: commit (so event-bus listeners opening a fresh session see
     committed data), then publish the domain event the handler returned,
     then mark the webhook_events row processed and commit again.
  6. On failure: mark the row failed, commit, and return a non-"ok" status
     so the router responds non-2xx — Razorpay will retry the delivery.

All business logic (reservations, payments, orders, invoices, audit) is
delegated to the existing services — this module only orchestrates and
verifies.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.events import BaseEvent
from app.core.security import verify_razorpay_webhook_signature
from app.modules.webhooks.models import WebhookEvent

log = structlog.get_logger()


@dataclass
class _HandlerResult:
    """What a handler learned, for the dispatcher to act on after commit."""

    order_id: uuid.UUID | None
    event: BaseEvent | None


class WebhookService:
    def __init__(self) -> None:
        self._handlers = {
            "payment.captured": self._on_payment_captured,
            "payment.failed": self._on_payment_failed,
            "order.paid": self._on_order_paid,
            "refund.created": self._on_refund_created,
            "refund.processed": self._on_refund_processed,
            "refund.failed": self._on_refund_failed,
        }

    # ── Idempotency store ────────────────────────────────────────────────────

    async def _get_or_create_event(
        self,
        db: AsyncSession,
        *,
        provider: str,
        event_type: str,
        event_id: str | None,
        payload_raw: str,
        headers: dict[str, str] | None,
        razorpay_payment_id: str | None,
        razorpay_order_id: str | None,
    ) -> tuple[WebhookEvent, bool]:
        """Returns (event_row, already_processed).

        already_processed=True means a row for this (provider, event_id)
        exists AND is already status='processed' — the caller must not run
        the handler again. Any other existing status (received/failed) is
        a retry: the same row is reused and processing_attempts increments,
        rather than colliding with the unique (provider, event_id)
        constraint by inserting a second row.
        """
        existing: WebhookEvent | None = None
        if event_id:
            result = await db.execute(
                select(WebhookEvent).where(
                    WebhookEvent.provider == provider,
                    WebhookEvent.event_id == event_id,
                )
            )
            existing = result.scalar_one_or_none()

        if existing:
            if existing.status == "processed":
                return existing, True
            existing.processing_attempts += 1
            existing.payload = payload_raw
            existing.headers = headers
            existing.razorpay_payment_id = (
                razorpay_payment_id or existing.razorpay_payment_id
            )
            existing.razorpay_order_id = razorpay_order_id or existing.razorpay_order_id
            existing.status = "received"
            existing.error_message = None
            await db.flush()
            return existing, False

        event = WebhookEvent(
            id=uuid.uuid4(),
            provider=provider,
            event_type=event_type,
            event_id=event_id,
            payload=payload_raw,
            headers=headers,
            razorpay_payment_id=razorpay_payment_id,
            razorpay_order_id=razorpay_order_id,
            status="received",
            processing_attempts=1,
        )
        db.add(event)
        await db.flush()
        return event, False

    async def _mark_processed(
        self, db: AsyncSession, event_id: uuid.UUID, *, order_id: uuid.UUID | None
    ) -> None:
        await db.execute(
            update(WebhookEvent)
            .where(WebhookEvent.id == event_id)
            .values(
                status="processed", processed_at=datetime.now(UTC), order_id=order_id
            )
        )

    async def _mark_failed(
        self, db: AsyncSession, event_id: uuid.UUID, error: str
    ) -> None:
        await db.execute(
            update(WebhookEvent)
            .where(WebhookEvent.id == event_id)
            .values(status="failed", error_message=error[:2000])
        )

    async def _mark_ignored(self, db: AsyncSession, event_id: uuid.UUID) -> None:
        await db.execute(
            update(WebhookEvent)
            .where(WebhookEvent.id == event_id)
            .values(status="ignored")
        )

    @staticmethod
    def _extract_ids(payload: dict) -> tuple[str | None, str | None]:
        """Pull whatever Razorpay payment/order id is present, from whichever
        sub-entity this event type carries."""
        data = payload.get("payload", {})
        payment_entity = data.get("payment", {}).get("entity", {})
        order_entity = data.get("order", {}).get("entity", {})
        refund_entity = data.get("refund", {}).get("entity", {})

        rzp_payment_id = payment_entity.get("id") or refund_entity.get("payment_id")
        rzp_order_id = order_entity.get("id") or payment_entity.get("order_id")
        return rzp_payment_id, rzp_order_id

    # ── Entry point ──────────────────────────────────────────────────────────

    async def handle_razorpay(
        self,
        db: AsyncSession,
        body: bytes,
        signature: str,
        headers: dict[str, str] | None = None,
    ) -> dict:
        if not verify_razorpay_webhook_signature(body, signature):
            log.warning("razorpay_webhook_invalid_signature")
            return {"status": "invalid_signature"}

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            log.warning("razorpay_webhook_invalid_json")
            return {"status": "invalid_payload"}

        event_type: str = payload.get("event", "unknown")
        event_id: str | None = payload.get("id")
        rzp_payment_id, rzp_order_id = self._extract_ids(payload)

        event_row, already_processed = await self._get_or_create_event(
            db,
            provider="razorpay",
            event_type=event_type,
            event_id=event_id,
            payload_raw=body.decode(),
            headers=headers,
            razorpay_payment_id=rzp_payment_id,
            razorpay_order_id=rzp_order_id,
        )
        if already_processed:
            log.info(
                "razorpay_webhook_already_processed",
                event_type=event_type,
                event_id=event_id,
            )
            return {"status": "already_processed"}

        handler = self._handlers.get(event_type)
        if handler is None:
            await self._mark_ignored(db, event_row.id)
            return {"status": "ignored"}

        try:
            async with db.begin_nested():
                result = await handler(db, payload)
            # Commit before publishing — event-bus listeners open a fresh
            # session and only see committed rows.
            await db.commit()
        except Exception as exc:
            log.error(
                "razorpay_webhook_handler_error",
                event_type=event_type,
                event_id=event_id,
                error=str(exc),
            )
            await self._mark_failed(db, event_row.id, str(exc))
            await db.commit()
            return {"status": "processing_failed"}

        if result.event is not None:
            from app.core.events import event_bus

            await event_bus.publish(result.event)

        await self._mark_processed(db, event_row.id, order_id=result.order_id)
        await db.commit()

        return {"status": "ok"}

    # ── payment.captured / order.paid ────────────────────────────────────────

    async def _on_payment_captured(
        self, db: AsyncSession, payload: dict
    ) -> _HandlerResult:
        payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        return await self._process_payment_captured(db, payment_entity)

    async def _on_order_paid(self, db: AsyncSession, payload: dict) -> _HandlerResult:
        """
        order.paid is a confirmatory event Razorpay fires alongside (or in
        place of, for some payment methods) payment.captured. If the order
        is already marked paid, this is a safe no-op — we never re-run
        fulfillment for the same order twice. Otherwise it's treated exactly
        like payment.captured, since it carries the same payment sub-entity.
        """
        from app.modules.orders.repository import OrderRepository

        order_entity = payload.get("payload", {}).get("order", {}).get("entity", {})
        payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        rzp_order_id = order_entity.get("id") or payment_entity.get("order_id", "")

        order = await OrderRepository().get_by_razorpay_order_id(db, rzp_order_id)
        if order and order.payment_status == "paid":
            log.info("order_paid_already_processed", order_id=str(order.id))
            return _HandlerResult(order_id=order.id, event=None)

        if not payment_entity:
            log.warning(
                "order_paid_missing_payment_entity", razorpay_order_id=rzp_order_id
            )
            return _HandlerResult(order_id=order.id if order else None, event=None)

        return await self._process_payment_captured(db, payment_entity)

    async def _process_payment_captured(
        self, db: AsyncSession, payment_entity: dict
    ) -> _HandlerResult:
        from app.modules.audit.service import AuditService
        from app.modules.inventory.reservation_service import ReservationService
        from app.modules.invoices.service import InvoiceService
        from app.modules.orders.repository import OrderRepository
        from app.modules.payments.repository import PaymentRepository
        from app.modules.profiles.repository import ProfileRepository

        rzp_payment_id: str = payment_entity.get("id", "")
        rzp_order_id: str = payment_entity.get("order_id", "")
        amount_paise: int = payment_entity.get("amount", 0)
        currency: str = payment_entity.get("currency", "")
        method: str = payment_entity.get("method", "")

        payment_repo = PaymentRepository()
        order_repo = OrderRepository()

        payment = await payment_repo.get_by_razorpay_order_id(db, rzp_order_id)
        if payment and payment.status == "captured":
            # Already handled — e.g. verify_and_fulfill from the frontend
            # already ran, or this is a repeat delivery of this same event.
            return _HandlerResult(order_id=payment.order_id, event=None)

        if payment:
            order = await order_repo.get_by_id(db, payment.order_id)
        else:
            # Webhook arrived before any Payment row existed for this order
            # (e.g. verify_and_fulfill hasn't run yet, or never will).
            order = await order_repo.get_by_razorpay_order_id(db, rzp_order_id)

        if not order:
            raise ValueError(f"No order found for razorpay_order_id={rzp_order_id}")

        # Verify amount/currency against what we expect before trusting the
        # webhook — a mismatch here means something is wrong (bug, tampering,
        # or a stale/replayed payload) and must not silently confirm the order.
        expected_paise = int(round(float(order.total) * 100))
        if amount_paise and amount_paise != expected_paise:
            raise ValueError(
                f"Amount mismatch for order {order.id}: "
                f"webhook={amount_paise} expected={expected_paise}"
            )
        if currency and currency != settings.RAZORPAY_CURRENCY:
            raise ValueError(
                f"Currency mismatch for order {order.id}: "
                f"webhook={currency} expected={settings.RAZORPAY_CURRENCY}"
            )

        if order.payment_status == "paid":
            # Confirmed through another path already — idempotent no-op.
            return _HandlerResult(order_id=order.id, event=None)

        now = datetime.now(UTC)
        if payment:
            await payment_repo.update(
                db,
                payment.id,
                {
                    "status": "captured",
                    "razorpay_payment_id": rzp_payment_id,
                    "method": method,
                    "captured_at": now,
                },
            )
        else:
            # No Payment row at all — create one so refunds/invoices/admin
            # views have something to reference.
            await payment_repo.create(
                db,
                {
                    "id": uuid.uuid4(),
                    "order_id": order.id,
                    "user_id": order.user_id,
                    "razorpay_order_id": rzp_order_id,
                    "razorpay_payment_id": rzp_payment_id,
                    "amount": float(order.total),
                    "currency": currency or settings.RAZORPAY_CURRENCY,
                    "method": method,
                    "status": "captured",
                    "captured_at": now,
                },
            )

        # Complete stock reservation (reserved -> sold). Idempotent: checks
        # for ACTIVE reservations, silently no-ops if already completed.
        # For late payments where reservations expired, handle the deduction.
        await ReservationService().complete_order_reservations(db, order.id)

        # Handle late payments: if the order's reservations were expired,
        # we still need to deduct stock (sold_quantity).
        has_expired = await db.execute(
            text(
                "SELECT 1 FROM inventory_reservations "
                "WHERE order_id = :oid AND status = 'EXPIRED' LIMIT 1"
            ),
            {"oid": str(order.id)},
        )
        if has_expired.fetchone():
            await ReservationService().complete_expired_order_reservations(db, order.id)

        await order_repo.update(
            db,
            order.id,
            {
                "payment_status": "paid",
                "razorpay_payment_id": rzp_payment_id,
                "status": "confirmed",
            },
        )

        # Generate invoice — idempotent (checks for an existing invoice first).
        refreshed_order = await order_repo.get_by_id(db, order.id)
        if refreshed_order:
            await InvoiceService().generate_and_store(db, refreshed_order)

        await AuditService().log(
            db,
            actor_id=None,
            action="payment.captured",
            resource_type="order",
            resource_id=order.id,
            metadata={
                "razorpay_payment_id": rzp_payment_id,
                "razorpay_order_id": rzp_order_id,
                "amount": amount_paise / 100 if amount_paise else float(order.total),
            },
            source="webhook",
        )

        profile = await ProfileRepository().get_by_id(db, order.user_id)
        from app.core.events import PaymentCapturedEvent

        event = PaymentCapturedEvent(
            order_id=str(order.id),
            payment_id=rzp_payment_id,
            user_id=str(order.user_id),
            amount=float(order.total),
            order_number=order.order_number,
            customer_email=(profile.email if profile else "") or "",
            customer_phone=(profile.phone if profile else None) or "",
        )
        return _HandlerResult(order_id=order.id, event=event)

    # ── payment.failed ───────────────────────────────────────────────────────

    async def _on_payment_failed(
        self, db: AsyncSession, payload: dict
    ) -> _HandlerResult:
        from app.modules.audit.service import AuditService
        from app.modules.inventory.reservation_service import ReservationService
        from app.modules.orders.repository import OrderRepository
        from app.modules.payments.repository import PaymentRepository

        payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        rzp_payment_id: str = payment_entity.get("id", "")
        rzp_order_id: str = payment_entity.get("order_id", "")
        error_desc: str = payment_entity.get("error_description") or "Payment failed"

        payment_repo = PaymentRepository()
        order_repo = OrderRepository()

        payment = await payment_repo.get_by_razorpay_order_id(db, rzp_order_id)
        if payment and payment.status == "failed":
            return _HandlerResult(order_id=payment.order_id, event=None)

        if payment:
            order_id = payment.order_id
            await payment_repo.update(
                db,
                payment.id,
                {
                    "status": "failed",
                    "razorpay_payment_id": rzp_payment_id,
                    "failure_reason": error_desc,
                },
            )
        else:
            order = await order_repo.get_by_razorpay_order_id(db, rzp_order_id)
            if not order:
                raise ValueError(
                    f"No order/payment found for razorpay_order_id={rzp_order_id}"
                )
            order_id = order.id

        order = await order_repo.get_by_id(db, order_id)
        if order and order.payment_status == "paid":
            # Already paid via another path — never downgrade a paid order.
            return _HandlerResult(order_id=order_id, event=None)

        # Release the stock reservation — idempotent, no-ops if already
        # released/completed.
        await ReservationService().release_order_reservations(
            db, order_id, reason="RELEASED"
        )

        # Restore coupon usage so the slot becomes available again.
        if order and order.coupon_id:
            from app.modules.coupons.service import CouponService

            await CouponService().revert_usage(
                db, order.coupon_id, order.user_id, order_id
            )

        await order_repo.update(
            db, order_id, {"status": "payment_failed", "payment_status": "failed"}
        )

        await AuditService().log(
            db,
            actor_id=None,
            action="payment.failed",
            resource_type="order",
            resource_id=order_id,
            metadata={"razorpay_payment_id": rzp_payment_id, "reason": error_desc},
            source="webhook",
        )

        event = None
        if order:
            from app.core.events import PaymentFailedEvent

            event = PaymentFailedEvent(
                order_id=str(order_id),
                payment_id=rzp_payment_id,
                user_id=str(order.user_id),
                reason=error_desc,
            )
        return _HandlerResult(order_id=order_id, event=event)

    # ── refund.created ───────────────────────────────────────────────────────

    async def _on_refund_created(
        self, db: AsyncSession, payload: dict
    ) -> _HandlerResult:
        from app.modules.audit.service import AuditService
        from app.modules.orders.repository import OrderRepository
        from app.modules.payments.repository import PaymentRepository
        from app.modules.profiles.repository import ProfileRepository

        refund_entity = payload.get("payload", {}).get("refund", {}).get("entity", {})
        rzp_refund_id: str = refund_entity.get("id", "")
        rzp_payment_id: str = refund_entity.get("payment_id", "")
        amount = (refund_entity.get("amount", 0) or 0) / 100

        payment_repo = PaymentRepository()
        existing_refund = await payment_repo.get_refund_by_razorpay_id(
            db, rzp_refund_id
        )
        if existing_refund:
            # Already created — e.g. via the admin-initiated refund flow, or
            # a repeat delivery of this event. Idempotent no-op.
            return _HandlerResult(order_id=existing_refund.order_id, event=None)

        payment = await payment_repo.get_by_razorpay_payment_id(db, rzp_payment_id)
        if not payment:
            raise ValueError(
                f"No payment found for razorpay_payment_id={rzp_payment_id}"
            )

        notes = refund_entity.get("notes")
        reason = notes.get("reason") if isinstance(notes, dict) else None

        refund = await payment_repo.create_refund(
            db,
            {
                "id": uuid.uuid4(),
                "payment_id": payment.id,
                "order_id": payment.order_id,
                "razorpay_refund_id": rzp_refund_id,
                "amount": amount,
                "reason": reason,
                "status": "pending",
            },
        )

        order_repo = OrderRepository()
        order = await order_repo.get_by_id(db, payment.order_id)
        if order and order.status != "refunded":
            await order_repo.update(db, order.id, {"status": "processing"})

        await AuditService().log(
            db,
            actor_id=None,
            action="refund.created",
            resource_type="order",
            resource_id=payment.order_id,
            metadata={
                "refund_id": str(refund.id),
                "razorpay_refund_id": rzp_refund_id,
                "amount": amount,
            },
            source="webhook",
        )

        event = None
        if order:
            profile = await ProfileRepository().get_by_id(db, order.user_id)
            from app.core.events import RefundCreatedEvent

            event = RefundCreatedEvent(
                refund_id=str(refund.id),
                order_id=str(order.id),
                user_id=str(order.user_id),
                amount=amount,
                order_number=order.order_number,
                customer_email=(profile.email if profile else "") or "",
            )
        return _HandlerResult(order_id=payment.order_id, event=event)

    # ── refund.processed ─────────────────────────────────────────────────────

    async def _on_refund_processed(
        self, db: AsyncSession, payload: dict
    ) -> _HandlerResult:
        from app.modules.audit.service import AuditService
        from app.modules.orders.repository import OrderRepository
        from app.modules.payments.repository import PaymentRepository
        from app.modules.profiles.repository import ProfileRepository

        refund_entity = payload.get("payload", {}).get("refund", {}).get("entity", {})
        rzp_refund_id: str = refund_entity.get("id", "")
        amount = (refund_entity.get("amount", 0) or 0) / 100

        payment_repo = PaymentRepository()
        refund = await payment_repo.get_refund_by_razorpay_id(db, rzp_refund_id)

        if not refund:
            # refund.processed arrived before/without refund.created —
            # create-then-process in one step so we never lose the refund.
            rzp_payment_id: str = refund_entity.get("payment_id", "")
            payment = await payment_repo.get_by_razorpay_payment_id(db, rzp_payment_id)
            if not payment:
                raise ValueError(
                    f"No payment found for razorpay_payment_id={rzp_payment_id}"
                )
            refund = await payment_repo.create_refund(
                db,
                {
                    "id": uuid.uuid4(),
                    "payment_id": payment.id,
                    "order_id": payment.order_id,
                    "razorpay_refund_id": rzp_refund_id,
                    "amount": amount,
                    "status": "pending",
                },
            )

        if refund.status == "processed":
            return _HandlerResult(order_id=refund.order_id, event=None)

        await payment_repo.update_refund(
            db, refund.id, {"status": "processed", "processed_at": datetime.now(UTC)}
        )

        order_repo = OrderRepository()
        payment = await payment_repo.get_by_id(db, refund.payment_id)
        if payment:
            all_refunds = await payment_repo.get_refunds_for_order(db, refund.order_id)
            total_refunded = sum(
                float(r.amount) for r in all_refunds if r.status == "processed"
            )
            is_full = abs(total_refunded - float(payment.amount)) < 0.01
            new_payment_status = "refunded" if is_full else "partially_refunded"
            await payment_repo.update(db, payment.id, {"status": new_payment_status})
            await order_repo.update(
                db,
                refund.order_id,
                {
                    "payment_status": new_payment_status,
                    "status": "refunded" if is_full else "processing",
                },
            )

        await AuditService().log(
            db,
            actor_id=None,
            action="refund.processed",
            resource_type="order",
            resource_id=refund.order_id,
            metadata={
                "refund_id": str(refund.id),
                "razorpay_refund_id": rzp_refund_id,
                "amount": amount,
            },
            source="webhook",
        )

        order = await order_repo.get_by_id(db, refund.order_id)
        event = None
        if order:
            profile = await ProfileRepository().get_by_id(db, order.user_id)
            from app.core.events import RefundProcessedEvent

            event = RefundProcessedEvent(
                refund_id=str(refund.id),
                order_id=str(order.id),
                user_id=str(order.user_id),
                amount=float(refund.amount),
                order_number=order.order_number,
                customer_email=(profile.email if profile else "") or "",
            )
        return _HandlerResult(order_id=refund.order_id, event=event)

    # ── refund.failed ────────────────────────────────────────────────────────

    async def _on_refund_failed(
        self, db: AsyncSession, payload: dict
    ) -> _HandlerResult:
        from app.modules.audit.service import AuditService
        from app.modules.orders.repository import OrderRepository
        from app.modules.payments.repository import PaymentRepository

        refund_entity = payload.get("payload", {}).get("refund", {}).get("entity", {})
        rzp_refund_id: str = refund_entity.get("id", "")
        reason: str = refund_entity.get("error_description") or "Refund failed"

        payment_repo = PaymentRepository()
        refund = await payment_repo.get_refund_by_razorpay_id(db, rzp_refund_id)
        if not refund:
            log.warning(
                "refund_failed_unknown_refund", razorpay_refund_id=rzp_refund_id
            )
            return _HandlerResult(order_id=None, event=None)

        if refund.status == "failed":
            return _HandlerResult(order_id=refund.order_id, event=None)

        await payment_repo.update_refund(
            db, refund.id, {"status": "failed", "failure_reason": reason}
        )

        await AuditService().log(
            db,
            actor_id=None,
            action="refund.failed",
            resource_type="order",
            resource_id=refund.order_id,
            metadata={
                "refund_id": str(refund.id),
                "razorpay_refund_id": rzp_refund_id,
                "reason": reason,
            },
            source="webhook",
        )

        order_repo = OrderRepository()
        order = await order_repo.get_by_id(db, refund.order_id)
        from app.core.events import RefundFailedEvent

        event = RefundFailedEvent(
            refund_id=str(refund.id),
            order_id=str(refund.order_id),
            user_id=str(order.user_id) if order else "",
            amount=float(refund.amount),
            order_number=order.order_number if order else "",
            reason=reason,
        )
        return _HandlerResult(order_id=refund.order_id, event=event)

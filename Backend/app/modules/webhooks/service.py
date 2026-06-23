import json
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_razorpay_webhook_signature
from app.modules.webhooks.models import WebhookEvent

log = structlog.get_logger()


class WebhookService:
    async def _record_event(
        self,
        db: AsyncSession,
        provider: str,
        event_type: str,
        event_id: str | None,
        payload_raw: str,
    ) -> WebhookEvent | None:
        """Insert event row. Returns None if event_id already exists (idempotency guard)."""
        if event_id:
            existing = await db.execute(
                select(WebhookEvent).where(
                    WebhookEvent.provider == provider,
                    WebhookEvent.event_id == event_id,
                )
            )
            if existing.scalar_one_or_none():
                return None

        event = WebhookEvent(
            id=uuid.uuid4(),
            provider=provider,
            event_type=event_type,
            event_id=event_id,
            payload=payload_raw,
            status="received",
        )
        db.add(event)
        await db.flush()
        return event

    async def _mark_processed(self, db: AsyncSession, event_id: uuid.UUID) -> None:
        await db.execute(
            update(WebhookEvent)
            .where(WebhookEvent.id == event_id)
            .values(status="processed", processed_at=datetime.now(UTC))
        )

    async def _mark_failed(
        self, db: AsyncSession, event_id: uuid.UUID, error: str
    ) -> None:
        await db.execute(
            update(WebhookEvent)
            .where(WebhookEvent.id == event_id)
            .values(status="failed", error_message=error[:2000])
        )

    # ── Razorpay ──────────────────────────────────────────────────────────────

    async def handle_razorpay(
        self,
        db: AsyncSession,
        body: bytes,
        signature: str,
    ) -> dict:
        if not verify_razorpay_webhook_signature(body, signature):
            return {"status": "invalid_signature"}

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return {"status": "invalid_payload"}

        event_type: str = payload.get("event", "unknown")
        event_id: str | None = payload.get("id")

        event_row = await self._record_event(
            db, "razorpay", event_type, event_id, body.decode()
        )
        if event_row is None:
            return {"status": "already_processed"}

        try:
            if event_type == "payment.captured":
                await self._on_payment_captured(db, payload)
            elif event_type == "payment.failed":
                await self._on_payment_failed(db, payload)
            elif event_type in ("refund.created", "refund.processed"):
                await self._on_refund_event(db, payload, event_type)
            else:
                await db.execute(
                    update(WebhookEvent)
                    .where(WebhookEvent.id == event_row.id)
                    .values(status="ignored")
                )
                return {"status": "ignored"}

            await self._mark_processed(db, event_row.id)
        except Exception as exc:
            log.error(
                "razorpay_webhook_handler_error", event_type=event_type, error=str(exc)
            )
            await self._mark_failed(db, event_row.id, str(exc))

        return {"status": "ok"}

    async def _on_payment_captured(self, db: AsyncSession, payload: dict) -> None:
        """
        Webhook fires when Razorpay captures payment (may arrive before or after
        verify_and_fulfill from the frontend). Both paths are idempotent because
        complete_order_reservations checks for already-COMPLETED reservations.
        """
        rzp_payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
        rzp_payment_id: str = rzp_payment.get("id", "")
        rzp_order_id: str = rzp_payment.get("order_id", "")
        method: str = rzp_payment.get("method", "")

        from app.modules.payments.repository import PaymentRepository

        repo = PaymentRepository()
        payment = await repo.get_by_razorpay_order_id(db, rzp_order_id)

        if payment and payment.status == "captured":
            # Frontend already fulfilled via verify_and_fulfill — nothing to do
            return

        from app.modules.orders.repository import OrderRepository

        order_repo = OrderRepository()

        if payment:
            now = datetime.now(UTC)
            await repo.update(
                db,
                payment.id,
                {
                    "status": "captured",
                    "razorpay_payment_id": rzp_payment_id,
                    "method": method,
                    "captured_at": now,
                },
            )
            order = await order_repo.get_by_id(db, payment.order_id)
        else:
            # Webhook arrived first (before verify_and_fulfill created the payment row)
            # Find the order by razorpay_order_id stored on the order row
            from sqlalchemy import text

            result = await db.execute(
                text(
                    "SELECT id, user_id, total, status, payment_status "
                    "FROM orders WHERE razorpay_order_id = :rzp_oid LIMIT 1"
                ),
                {"rzp_oid": rzp_order_id},
            )
            row = result.fetchone()
            if not row:
                log.warning(
                    "webhook_payment_captured_unknown_order",
                    razorpay_order_id=rzp_order_id,
                )
                return
            order = await order_repo.get_by_id(db, row[0])

        if not order:
            return

        if order.payment_status == "paid":
            # Already processed — idempotent
            return

        # Complete stock reservation (idempotent)
        from app.modules.inventory.reservation_service import ReservationService

        await ReservationService().complete_order_reservations(db, order.id)

        # Confirm order
        await order_repo.update(
            db,
            order.id,
            {
                "payment_status": "paid",
                "razorpay_payment_id": rzp_payment_id,
                "status": "confirmed",
            },
        )

        # Generate invoice if not already generated
        from app.modules.invoices.service import InvoiceService

        refreshed_order = await order_repo.get_by_id(db, order.id)
        if refreshed_order:
            await InvoiceService().generate_and_store(db, refreshed_order)

        from app.core.events import PaymentCapturedEvent, event_bus

        await event_bus.publish(
            PaymentCapturedEvent(
                order_id=str(order.id),
                payment_id=rzp_payment_id,
                amount=float(order.total),
            )
        )

    async def _on_payment_failed(self, db: AsyncSession, payload: dict) -> None:
        """
        Release reserved stock and mark the order as payment_failed so the
        inventory is immediately available for other customers.
        """
        rzp_payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
        rzp_order_id: str = rzp_payment.get("order_id", "")
        error_desc: str = rzp_payment.get("error_description", "Payment failed")

        from sqlalchemy import text

        # Find the order by razorpay_order_id
        result = await db.execute(
            text("SELECT id FROM orders WHERE razorpay_order_id = :rzp_oid LIMIT 1"),
            {"rzp_oid": rzp_order_id},
        )
        row = result.fetchone()
        if not row:
            from app.modules.payments.repository import PaymentRepository

            repo = PaymentRepository()
            payment = await repo.get_by_razorpay_order_id(db, rzp_order_id)
            if not payment:
                return
            order_id = payment.order_id
            await repo.update(
                db, payment.id, {"status": "failed", "failure_reason": error_desc}
            )
        else:
            order_id = row[0]

        # Release stock reservation
        from app.modules.inventory.reservation_service import ReservationService

        await ReservationService().release_order_reservations(
            db, order_id, reason="RELEASED"
        )

        # Mark order as payment_failed
        from app.modules.orders.repository import OrderRepository

        await OrderRepository().update(
            db,
            order_id,
            {"status": "payment_failed", "payment_status": "failed"},
        )

        from app.core.events import PaymentFailedEvent, event_bus

        await event_bus.publish(
            PaymentFailedEvent(
                order_id=str(order_id),
                payment_id="",
                reason=error_desc,
            )
        )

    async def _on_refund_event(
        self, db: AsyncSession, payload: dict, event_type: str
    ) -> None:
        rzp_refund = payload.get("payload", {}).get("refund", {}).get("entity", {})
        rzp_refund_id: str = rzp_refund.get("id", "")
        amount_paise: int = rzp_refund.get("amount", 0)
        amount = amount_paise / 100

        from app.modules.payments.models import Refund
        from app.modules.payments.repository import PaymentRepository

        result = await db.execute(
            select(Refund).where(Refund.razorpay_refund_id == rzp_refund_id)
        )
        refund = result.scalar_one_or_none()
        if refund and event_type == "refund.processed":
            await PaymentRepository().update_refund(
                db,
                refund.id,
                {"status": "processed", "processed_at": datetime.now(UTC)},
            )
            from app.core.events import RefundProcessedEvent, event_bus

            await event_bus.publish(
                RefundProcessedEvent(
                    order_id=str(refund.order_id),
                    refund_id=str(refund.id),
                    amount=amount,
                )
            )

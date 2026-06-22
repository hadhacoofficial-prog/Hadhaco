import json
import uuid
from datetime import UTC, datetime, timezone

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_razorpay_webhook_signature, verify_delivery_one_webhook_signature
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
        """
        Insert event row. Returns None if event_id already exists (idempotency guard).
        """
        if event_id:
            existing = await db.execute(
                select(WebhookEvent).where(
                    WebhookEvent.provider == provider,
                    WebhookEvent.event_id == event_id,
                )
            )
            if existing.scalar_one_or_none():
                return None  # Already processed

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
            update(WebhookEvent).where(WebhookEvent.id == event_id).values(
                status="processed",
                processed_at=datetime.now(UTC),
            )
        )

    async def _mark_failed(self, db: AsyncSession, event_id: uuid.UUID, error: str) -> None:
        await db.execute(
            update(WebhookEvent).where(WebhookEvent.id == event_id).values(
                status="failed",
                error_message=error[:2000],
            )
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

        event_row = await self._record_event(db, "razorpay", event_type, event_id, body.decode())
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
                    update(WebhookEvent).where(WebhookEvent.id == event_row.id).values(status="ignored")
                )
                return {"status": "ignored"}

            await self._mark_processed(db, event_row.id)
        except Exception as exc:
            log.error("razorpay_webhook_handler_error", event_type=event_type, error=str(exc))
            await self._mark_failed(db, event_row.id, str(exc))

        return {"status": "ok"}

    async def _on_payment_captured(self, db: AsyncSession, payload: dict) -> None:
        rzp_payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
        rzp_payment_id: str = rzp_payment.get("id", "")
        rzp_order_id: str = rzp_payment.get("order_id", "")
        method: str = rzp_payment.get("method", "")

        from app.modules.payments.repository import PaymentRepository
        repo = PaymentRepository()
        payment = await repo.get_by_razorpay_order_id(db, rzp_order_id)
        if not payment or payment.status == "captured":
            return

        now = datetime.now(UTC)
        await repo.update(db, payment.id, {
            "status": "captured",
            "razorpay_payment_id": rzp_payment_id,
            "method": method,
            "captured_at": now,
        })

        from app.modules.orders.repository import OrderRepository
        await OrderRepository().update(db, payment.order_id, {
            "payment_status": "paid",
            "razorpay_payment_id": rzp_payment_id,
            "status": "confirmed",
        })

        # Generate invoice
        from app.modules.invoices.service import InvoiceService
        from app.modules.orders.repository import OrderRepository as OR
        order = await OR().get_by_id(db, payment.order_id)
        if order:
            await InvoiceService().generate_and_store(db, order)

        from app.core.events import PaymentCapturedEvent, event_bus
        await event_bus.publish(PaymentCapturedEvent(
            order_id=str(payment.order_id),
            payment_id=str(payment.id),
            amount=float(payment.amount),
        ))

    async def _on_payment_failed(self, db: AsyncSession, payload: dict) -> None:
        rzp_payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
        rzp_order_id: str = rzp_payment.get("order_id", "")
        error_desc: str = rzp_payment.get("error_description", "Payment failed")

        from app.modules.payments.repository import PaymentRepository
        repo = PaymentRepository()
        payment = await repo.get_by_razorpay_order_id(db, rzp_order_id)
        if not payment:
            return

        await repo.update(db, payment.id, {
            "status": "failed",
            "failure_reason": error_desc,
        })

        from app.core.events import PaymentFailedEvent, event_bus
        await event_bus.publish(PaymentFailedEvent(
            order_id=str(payment.order_id),
            payment_id=str(payment.id),
            reason=error_desc,
        ))

    async def _on_refund_event(self, db: AsyncSession, payload: dict, event_type: str) -> None:
        rzp_refund = payload.get("payload", {}).get("refund", {}).get("entity", {})
        rzp_refund_id: str = rzp_refund.get("id", "")
        amount_paise: int = rzp_refund.get("amount", 0)
        amount = amount_paise / 100

        from app.modules.payments.repository import PaymentRepository
        from sqlalchemy import select
        from app.modules.payments.models import Refund
        result = await db.execute(
            select(Refund).where(Refund.razorpay_refund_id == rzp_refund_id)
        )
        refund = result.scalar_one_or_none()
        if refund and event_type == "refund.processed":
            from app.modules.payments.repository import PaymentRepository
            await PaymentRepository().update_refund(db, refund.id, {
                "status": "processed",
                "processed_at": datetime.now(UTC),
            })
            from app.core.events import RefundProcessedEvent, event_bus
            await event_bus.publish(RefundProcessedEvent(
                order_id=str(refund.order_id),
                refund_id=str(refund.id),
                amount=amount,
            ))

    # ── Delivery One ──────────────────────────────────────────────────────────

    async def handle_delivery_one(
        self,
        db: AsyncSession,
        body: bytes,
        signature: str,
    ) -> dict:
        if not verify_delivery_one_webhook_signature(body, signature):
            return {"status": "invalid_signature"}

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return {"status": "invalid_payload"}

        event_type: str = payload.get("event", "unknown")
        event_id: str | None = payload.get("id")

        event_row = await self._record_event(db, "delivery_one", event_type, event_id, body.decode())
        if event_row is None:
            return {"status": "already_processed"}

        try:
            await self._on_shipment_event(db, payload, event_type)
            await self._mark_processed(db, event_row.id)
        except Exception as exc:
            log.error("delivery_one_webhook_error", event_type=event_type, error=str(exc))
            await self._mark_failed(db, event_row.id, str(exc))

        return {"status": "ok"}

    async def _on_shipment_event(self, db: AsyncSession, payload: dict, event_type: str) -> None:
        data = payload.get("data", {})
        order_number: str = data.get("order_reference", "")
        tracking_number: str = data.get("tracking_number", "")

        if not order_number:
            return

        from app.modules.orders.repository import OrderRepository
        order = await OrderRepository().get_by_order_number(db, order_number)
        if not order:
            return

        update_data: dict = {}
        if event_type == "shipment.dispatched":
            update_data = {"status": "shipped", "tracking_number": tracking_number}
        elif event_type == "shipment.delivered":
            update_data = {
                "status": "delivered",
                "delivered_at": datetime.now(UTC),
            }

        if update_data:
            await OrderRepository().update(db, order.id, update_data)
            from app.core.events import OrderStatusChangedEvent, event_bus
            await event_bus.publish(OrderStatusChangedEvent(
                order_id=str(order.id),
                user_id=str(order.user_id),
                old_status=order.status,
                new_status=update_data["status"],
            ))

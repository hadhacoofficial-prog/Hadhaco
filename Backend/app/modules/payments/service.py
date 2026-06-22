import hashlib
import hmac
import uuid
from datetime import UTC, datetime

import razorpay
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.events import PaymentCapturedEvent, PaymentFailedEvent, event_bus
from app.core.exceptions import NotFoundError, ValidationError
from app.modules.payments.repository import PaymentRepository
from app.modules.payments.schemas import (
    CreatePaymentOrderRequest,
    PaymentOrderResponse,
    PaymentResponse,
    RefundRequest,
    RefundResponse,
    VerifyPaymentRequest,
)

_repo = PaymentRepository()


def _razorpay_client() -> razorpay.Client:
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def _verify_signature(rzp_order_id: str, rzp_payment_id: str, signature: str) -> bool:
    msg = f"{rzp_order_id}|{rzp_payment_id}"
    expected = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode(),
        msg.encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


class PaymentService:
    async def create_razorpay_order(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        payload: CreatePaymentOrderRequest,
    ) -> PaymentOrderResponse:
        # Fetch the order and verify ownership
        from app.modules.orders.repository import OrderRepository

        order = await OrderRepository().get_by_id(db, payload.order_id)
        if not order or order.user_id != user_id:
            raise NotFoundError("Order not found")
        if order.payment_status == "paid":
            raise ValidationError("Order is already paid")
        if order.status == "cancelled":
            raise ValidationError("Cannot pay for a cancelled order")

        # Amount in paise (INR × 100)
        amount_paise = int(round(float(order.total) * 100))

        client = _razorpay_client()
        rzp_order = client.order.create(
            {
                "amount": amount_paise,
                "currency": "INR",
                "receipt": str(order.id),
                "notes": {"order_number": order.order_number},
            }
        )

        # Record payment
        payment = await _repo.create(
            db,
            {
                "id": uuid.uuid4(),
                "order_id": order.id,
                "user_id": user_id,
                "razorpay_order_id": rzp_order["id"],
                "amount": float(order.total),
                "currency": "INR",
                "status": "created",
            },
        )

        # Persist razorpay_order_id on order record
        from app.modules.orders.repository import OrderRepository

        await OrderRepository().update(db, order.id, {"razorpay_order_id": rzp_order["id"]})

        return PaymentOrderResponse(
            razorpay_order_id=rzp_order["id"],
            amount_paise=amount_paise,
            currency="INR",
            order_id=order.id,
            payment_id=payment.id,
            key_id=settings.RAZORPAY_KEY_ID,
        )

    async def verify_and_capture(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        payload: VerifyPaymentRequest,
    ) -> PaymentResponse:
        payment = await _repo.get_by_id(db, payload.payment_id)
        if not payment or payment.user_id != user_id:
            raise NotFoundError("Payment not found")
        if payment.status == "captured":
            return PaymentResponse.model_validate(payment)

        # Verify HMAC signature
        if not _verify_signature(
            payload.razorpay_order_id,
            payload.razorpay_payment_id,
            payload.razorpay_signature,
        ):
            # Record failure
            await _repo.update(
                db,
                payment.id,
                {
                    "status": "failed",
                    "razorpay_payment_id": payload.razorpay_payment_id,
                    "failure_reason": "Signature verification failed",
                },
            )
            await event_bus.publish(
                PaymentFailedEvent(
                    order_id=str(payment.order_id),
                    payment_id=str(payment.id),
                    reason="Signature verification failed",
                )
            )
            raise ValidationError("Payment signature verification failed")

        # Update payment record
        now = datetime.now(UTC)
        updated_payment = await _repo.update(
            db,
            payment.id,
            {
                "status": "captured",
                "razorpay_payment_id": payload.razorpay_payment_id,
                "razorpay_signature": payload.razorpay_signature,
                "captured_at": now,
            },
        )

        # Update order payment status + razorpay_payment_id
        from app.modules.orders.repository import OrderRepository

        order = await OrderRepository().update(
            db,
            payment.order_id,
            {
                "payment_status": "paid",
                "razorpay_payment_id": payload.razorpay_payment_id,
                "status": "confirmed",
            },
        )

        from app.modules.profiles.repository import ProfileRepository

        profile = await ProfileRepository().get_by_id(db, user_id)
        await event_bus.publish(
            PaymentCapturedEvent(
                order_id=str(payment.order_id),
                payment_id=str(payment.id),
                user_id=str(user_id),
                amount=float(payment.amount),
                order_number=order.order_number if order else "",
                customer_email=(profile.email if profile else "") or "",
                customer_phone=(profile.phone if profile else None) or "",
            )
        )

        return PaymentResponse.model_validate(updated_payment)

    async def get_payment_for_order(
        self, db: AsyncSession, order_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> PaymentResponse:
        payment = await _repo.get_for_order(db, order_id)
        if not payment:
            raise NotFoundError("Payment not found")
        if user_id and payment.user_id != user_id:
            raise NotFoundError("Payment not found")
        return PaymentResponse.model_validate(payment)

    async def initiate_refund(
        self,
        db: AsyncSession,
        order_id: uuid.UUID,
        payload: RefundRequest,
    ) -> RefundResponse:
        payment = await _repo.get_for_order(db, order_id)
        if not payment:
            raise NotFoundError("No payment found for this order")
        if payment.status not in ("captured",):
            raise ValidationError(f"Cannot refund payment with status '{payment.status}'")

        refund_amount = payload.amount if payload.amount else float(payment.amount)
        if refund_amount > float(payment.amount):
            raise ValidationError("Refund amount exceeds payment amount")

        # Call Razorpay
        client = _razorpay_client()
        rzp_refund = client.payment.refund(
            payment.razorpay_payment_id,
            {"amount": int(refund_amount * 100), "speed": "normal"},
        )

        refund = await _repo.create_refund(
            db,
            {
                "id": uuid.uuid4(),
                "payment_id": payment.id,
                "order_id": order_id,
                "razorpay_refund_id": rzp_refund.get("id"),
                "amount": refund_amount,
                "reason": payload.reason,
                "status": "processed",
                "processed_at": datetime.now(UTC),
            },
        )

        # Update payment status
        is_full = abs(refund_amount - float(payment.amount)) < 0.01
        new_status = "refunded" if is_full else "partially_refunded"
        await _repo.update(db, payment.id, {"status": new_status})

        # Update order payment_status
        from app.modules.orders.repository import OrderRepository

        await OrderRepository().update(
            db,
            order_id,
            {
                "payment_status": new_status,
                "status": "refunded" if is_full else "processing",
            },
        )

        from app.core.events import RefundCreatedEvent
        from app.modules.profiles.repository import ProfileRepository

        order = await OrderRepository().get_by_id(db, order_id)
        profile = await ProfileRepository().get_by_id(db, payment.user_id)
        await event_bus.publish(
            RefundCreatedEvent(
                order_id=str(order_id),
                refund_id=str(refund.id),
                user_id=str(payment.user_id),
                amount=refund_amount,
                order_number=order.order_number if order else "",
                customer_email=(profile.email if profile else "") or "",
            )
        )

        return RefundResponse.model_validate(refund)

    async def list_refunds(self, db: AsyncSession, order_id: uuid.UUID) -> list[RefundResponse]:
        refunds = await _repo.get_refunds_for_order(db, order_id)
        return [RefundResponse.model_validate(r) for r in refunds]

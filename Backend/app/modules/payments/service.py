import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import event_bus
from app.core.exceptions import NotFoundError, ValidationError
from app.core.security import get_razorpay_client
from app.modules.payments.repository import PaymentRepository
from app.modules.payments.schemas import (
    PaymentResponse,
    RefundRequest,
    RefundResponse,
)

_repo = PaymentRepository()
log = structlog.get_logger(__name__)


class PaymentService:
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
        # SELECT ... FOR UPDATE on the payment row to prevent concurrent refund
        # race conditions. Two admin users clicking "Refund" simultaneously
        # would otherwise both pass the status check and both create Razorpay
        # refunds, resulting in a double refund.
        payment = await _repo.get_for_order_with_lock(db, order_id)
        if not payment:
            raise NotFoundError("No payment found for this order")
        if payment.status not in ("captured",):
            raise ValidationError(
                f"Cannot refund payment with status '{payment.status}'"
            )

        refund_amount = payload.amount if payload.amount else float(payment.amount)

        # Calculate remaining refundable amount by summing all non-failed
        # refunds. This prevents partial refund overflow where two concurrent
        # requests each try to refund the full remaining balance.
        total_refunded = await _repo.get_total_refunded_for_payment(db, payment.id)
        remaining_refundable = float(payment.amount) - total_refunded

        if refund_amount > remaining_refundable:
            raise ValidationError(
                f"Refund amount ₹{refund_amount:.2f} exceeds remaining "
                f"refundable amount ₹{remaining_refundable:.2f}"
            )

        if refund_amount <= 0:
            raise ValidationError("No refundable amount remaining")

        # Call Razorpay
        client = get_razorpay_client()
        rzp_refund = client.payment.refund(
            payment.razorpay_payment_id,
            {"amount": int(refund_amount * 100), "speed": "normal"},
        )

        # Record the refund.  Wrapped in a SAVEPOINT (begin_nested) to handle
        # the race where the Razorpay refund.created webhook arrives and
        # creates the Refund row before this transaction commits — the
        # UNIQUE index on razorpay_refund_id would otherwise raise
        # IntegrityError.  On conflict we retrieve the existing row so the
        # response is still correct.
        rzp_refund_id = rzp_refund.get("id")
        refund = None
        try:
            async with db.begin_nested():
                refund = await _repo.create_refund(
                    db,
                    {
                        "id": uuid.uuid4(),
                        "payment_id": payment.id,
                        "order_id": order_id,
                        "razorpay_refund_id": rzp_refund_id,
                        "amount": refund_amount,
                        "reason": payload.reason,
                        "status": "processed",
                        "processed_at": datetime.now(UTC),
                    },
                )
        except IntegrityError:
            log.info(
                "refund_already_recorded",
                order_id=str(order_id),
                razorpay_refund_id=rzp_refund_id,
            )
            refund = await _repo.get_refund_by_razorpay_id(db, rzp_refund_id)
            if not refund:
                raise

        # Update payment status
        new_total_refunded = total_refunded + refund_amount
        is_full = abs(new_total_refunded - float(payment.amount)) < 0.01
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

        # Commit BEFORE publishing — listeners open fresh sessions and read
        # order/refund state.  This also releases the FOR UPDATE lock acquired
        # at the top of this method.
        await db.commit()

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

    async def list_refunds(
        self, db: AsyncSession, order_id: uuid.UUID
    ) -> list[RefundResponse]:
        refunds = await _repo.get_refunds_for_order(db, order_id)
        return [RefundResponse.model_validate(r) for r in refunds]

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, ok
from app.core.database import get_db
from app.core.dependencies import (
    get_current_user,
    require_2fa_verified,
    require_admin,
    require_customer,
)
from app.modules.payments.schemas import (
    CreatePaymentOrderRequest,
    PaymentOrderResponse,
    PaymentResponse,
    RefundRequest,
    RefundResponse,
    VerifyPaymentRequest,
)
from app.modules.payments.service import PaymentService
from app.modules.profiles.models import Profile

router = APIRouter()
_service = PaymentService()


@router.post(
    "/payments/create-order",
    response_model=BaseSuccessResponse[PaymentOrderResponse],
    dependencies=[Depends(require_customer)],
)
async def create_payment_order(
    payload: CreatePaymentOrderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    result = await _service.create_razorpay_order(db, current_user.id, payload)
    return ok(
        result, ResponseCode.PAYMENT_ORDER_CREATED, "Payment order created successfully"
    )


@router.post(
    "/payments/verify",
    response_model=BaseSuccessResponse[PaymentResponse],
    dependencies=[Depends(require_customer)],
)
async def verify_payment(
    payload: VerifyPaymentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    result = await _service.verify_and_capture(db, current_user.id, payload)
    return ok(result, ResponseCode.PAYMENT_VERIFIED, "Payment verified successfully")


@router.get(
    "/orders/{order_id}/payment",
    response_model=BaseSuccessResponse[PaymentResponse],
    dependencies=[Depends(require_customer)],
)
async def get_order_payment(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    result = await _service.get_payment_for_order(db, order_id, user_id=current_user.id)
    return ok(result, ResponseCode.PAYMENT_FETCHED, "Payment fetched successfully")


# ── Admin ─────────────────────────────────────────────────────────────────────


@router.post(
    "/admin/orders/{order_id}/refund",
    response_model=BaseSuccessResponse[RefundResponse],
    dependencies=[Depends(require_2fa_verified)],
)
async def initiate_refund(
    order_id: uuid.UUID,
    payload: RefundRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await _service.initiate_refund(db, order_id, payload)
    return ok(result, ResponseCode.REFUND_INITIATED, "Refund initiated successfully")


@router.get(
    "/admin/orders/{order_id}/refunds",
    response_model=BaseSuccessResponse[list[RefundResponse]],
    dependencies=[Depends(require_admin)],
)
async def list_refunds(order_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await _service.list_refunds(db, order_id)
    return ok(result, ResponseCode.REFUND_LISTED, "Refunds listed successfully")

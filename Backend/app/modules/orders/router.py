import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, ok
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin, require_customer
from app.modules.orders.schemas import (
    CancelOrderRequest,
    CreatePaymentIntentRequest,
    CreatePaymentIntentResponse,
    OrderListResponse,
    OrderResponse,
    SetComplimentaryGiftRequest,
    UpdateOrderStatusRequest,
    VerifyOrderPaymentRequest,
    VerifyOrderPaymentResponse,
)
from app.modules.orders.service import OrderService
from app.modules.profiles.models import Profile

router = APIRouter()
_service = OrderService()


# ── Customer endpoints ────────────────────────────────────────────────────────


@router.get(
    "/orders",
    response_model=BaseSuccessResponse[OrderListResponse],
    dependencies=[Depends(require_customer)],
)
async def list_my_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    result = await _service.list_my_orders(
        db, current_user.id, page=page, page_size=page_size, status=status
    )
    return ok(result, ResponseCode.ORDER_LISTED, "Orders listed successfully")


@router.get(
    "/orders/{order_id}",
    response_model=BaseSuccessResponse[OrderResponse],
    dependencies=[Depends(require_customer)],
)
async def get_my_order(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    result = await _service.get_order(db, order_id, user_id=current_user.id)
    return ok(result, ResponseCode.ORDER_FETCHED, "Order fetched successfully")


@router.post(
    "/orders/create-payment",
    response_model=BaseSuccessResponse[CreatePaymentIntentResponse],
    status_code=201,
    dependencies=[Depends(require_customer)],
)
async def create_payment_intent(
    payload: CreatePaymentIntentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    from app.common.responses import created

    result = await _service.create_payment_intent(db, current_user.id, payload)
    return created(result, ResponseCode.ORDER_CREATED, "Payment intent created")


@router.post(
    "/orders/verify-payment",
    response_model=BaseSuccessResponse[VerifyOrderPaymentResponse],
    dependencies=[Depends(require_customer)],
)
async def verify_order_payment(
    payload: VerifyOrderPaymentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    result = await _service.verify_and_fulfill(db, current_user.id, payload)
    return ok(
        result, ResponseCode.ORDER_CREATED, "Payment verified and order confirmed"
    )


@router.patch(
    "/orders/{order_id}/complimentary-gift",
    response_model=BaseSuccessResponse[OrderResponse],
    dependencies=[Depends(require_customer)],
)
async def set_complimentary_gift(
    order_id: uuid.UUID,
    payload: SetComplimentaryGiftRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    result = await _service.set_complimentary_gift(
        db, order_id, current_user.id, payload
    )
    return ok(result, ResponseCode.ORDER_STATUS_UPDATED, "Complimentary gift saved")


@router.post(
    "/orders/{order_id}/cancel",
    response_model=BaseSuccessResponse[OrderResponse],
    dependencies=[Depends(require_customer)],
)
async def cancel_order(
    order_id: uuid.UUID,
    payload: CancelOrderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    result = await _service.cancel_order(db, order_id, current_user.id, payload)
    return ok(result, ResponseCode.ORDER_CANCELLED, "Order cancelled successfully")


# ── Admin endpoints ───────────────────────────────────────────────────────────


@router.get(
    "/admin/orders",
    response_model=BaseSuccessResponse[OrderListResponse],
    dependencies=[Depends(require_admin)],
)
async def admin_list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    payment_status: str | None = None,
    user_id: uuid.UUID | None = None,
    search: str | None = Query(None, max_length=100),
    db: AsyncSession = Depends(get_db),
):
    result = await _service.admin_list_orders(
        db,
        page=page,
        page_size=page_size,
        status=status,
        payment_status=payment_status,
        user_id=user_id,
        search=search,
    )
    return ok(result, ResponseCode.ORDER_LISTED, "Orders listed successfully")


@router.get(
    "/admin/orders/{order_id}",
    response_model=BaseSuccessResponse[OrderResponse],
    dependencies=[Depends(require_admin)],
)
async def admin_get_order(order_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await _service.get_order(db, order_id)
    return ok(result, ResponseCode.ORDER_FETCHED, "Order fetched successfully")


@router.patch(
    "/admin/orders/{order_id}/status",
    response_model=BaseSuccessResponse[OrderResponse],
    dependencies=[Depends(require_admin)],
)
async def update_order_status(
    order_id: uuid.UUID,
    payload: UpdateOrderStatusRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await _service.update_status(db, order_id, payload)
    return ok(
        result, ResponseCode.ORDER_STATUS_UPDATED, "Order status updated successfully"
    )

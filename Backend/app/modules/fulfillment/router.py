import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, ok
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.modules.fulfillment.schemas import (
    ConfirmPaymentRequest,
    DispatchOrderRequest,
    FulfillmentTimelineListResponse,
    PackingSlipResponse,
    ShippingLabelResponse,
)
from app.modules.fulfillment.service import FulfillmentService
from app.modules.orders.schemas import OrderResponse
from app.modules.profiles.models import Profile

router = APIRouter(prefix="/admin/orders", tags=["fulfillment"])
_service = FulfillmentService()


@router.patch(
    "/{order_id}/fulfillment/confirm-payment",
    response_model=BaseSuccessResponse[OrderResponse],
    dependencies=[Depends(require_admin)],
)
async def confirm_payment(
    order_id: uuid.UUID,
    payload: ConfirmPaymentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    """Confirm payment and move order to confirmed status."""
    try:
        order = await _service.confirm_payment(
            db, order_id, current_user.id, current_user.email or "Admin"
        )
        await db.commit()
        await db.refresh(order)
        return ok(
            OrderResponse.model_validate(order),
            ResponseCode.ORDER_STATUS_UPDATED,
            "Payment confirmed successfully",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.patch(
    "/{order_id}/fulfillment/mark-packing",
    response_model=BaseSuccessResponse[OrderResponse],
    dependencies=[Depends(require_admin)],
)
async def mark_packing(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    """Mark order as being packed."""
    try:
        order = await _service.mark_packing(
            db, order_id, current_user.id, current_user.email or "Admin"
        )
        await db.commit()
        await db.refresh(order)
        return ok(
            OrderResponse.model_validate(order),
            ResponseCode.ORDER_STATUS_UPDATED,
            "Order marked for packing",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post(
    "/{order_id}/fulfillment/shipping-label",
    response_model=BaseSuccessResponse[ShippingLabelResponse],
    dependencies=[Depends(require_admin)],
)
async def generate_shipping_label(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    """Generate and download shipping label PDF."""
    try:
        result = await _service.generate_shipping_label(
            db, order_id, current_user.id, current_user.email or "Admin"
        )
        await db.commit()
        return ok(
            result,
            ResponseCode.ORDER_STATUS_UPDATED,
            "Shipping label generated successfully",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post(
    "/{order_id}/fulfillment/packing-slip",
    response_model=BaseSuccessResponse[PackingSlipResponse],
    dependencies=[Depends(require_admin)],
)
async def generate_packing_slip(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    """Generate and download packing slip PDF."""
    try:
        result = await _service.generate_packing_slip(db, order_id)
        return ok(
            result,
            ResponseCode.ORDER_STATUS_UPDATED,
            "Packing slip generated successfully",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.patch(
    "/{order_id}/fulfillment/dispatch",
    response_model=BaseSuccessResponse[OrderResponse],
    dependencies=[Depends(require_admin)],
)
async def dispatch_order(
    order_id: uuid.UUID,
    payload: DispatchOrderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    """Mark order as dispatched with shipping provider and tracking info."""
    try:
        order = await _service.dispatch_order(
            db, order_id, payload, current_user.id, current_user.email or "Admin"
        )
        await db.commit()
        await db.refresh(order)
        return ok(
            OrderResponse.model_validate(order),
            ResponseCode.ORDER_STATUS_UPDATED,
            f"Order dispatched via {payload.shipping_provider.value}",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.patch(
    "/{order_id}/fulfillment/mark-in-transit",
    response_model=BaseSuccessResponse[OrderResponse],
    dependencies=[Depends(require_admin)],
)
async def mark_in_transit(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    """Mark order as in transit."""
    try:
        order = await _service.mark_in_transit(
            db, order_id, current_user.id, current_user.email or "Admin"
        )
        await db.commit()
        await db.refresh(order)
        return ok(
            OrderResponse.model_validate(order),
            ResponseCode.ORDER_STATUS_UPDATED,
            "Order marked as in transit",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.patch(
    "/{order_id}/fulfillment/mark-delivered",
    response_model=BaseSuccessResponse[OrderResponse],
    dependencies=[Depends(require_admin)],
)
async def mark_delivered(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    """Mark order as delivered."""
    try:
        order = await _service.mark_delivered(
            db, order_id, current_user.id, current_user.email or "Admin"
        )
        await db.commit()
        await db.refresh(order)
        return ok(
            OrderResponse.model_validate(order),
            ResponseCode.ORDER_STATUS_UPDATED,
            "Order marked as delivered",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get(
    "/{order_id}/fulfillment/timeline",
    response_model=BaseSuccessResponse[FulfillmentTimelineListResponse],
    dependencies=[Depends(require_admin)],
)
async def get_fulfillment_timeline(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get fulfillment timeline for an order."""
    try:
        timeline = await _service.get_fulfillment_timeline(db, order_id)
        from app.modules.fulfillment.schemas import FulfillmentTimelineResponse

        timeline_responses = [
            FulfillmentTimelineResponse.model_validate(entry) for entry in timeline
        ]
        return ok(
            FulfillmentTimelineListResponse(timeline=timeline_responses),
            ResponseCode.ORDER_FETCHED,
            "Timeline retrieved successfully",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

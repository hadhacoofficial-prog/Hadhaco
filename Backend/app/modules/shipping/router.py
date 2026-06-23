import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, created, ok
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin, require_customer
from app.modules.profiles.models import Profile
from app.modules.shipping.schemas import (
    CreateShipmentRequest,
    ShipmentResponse,
    ShippingRateResponse,
    TrackingResponse,
    UpdateShipmentRequest,
)
from app.modules.shipping.service import ShippingService

router = APIRouter()
_service = ShippingService()


# ── Customer ──────────────────────────────────────────────────────────────────


@router.get(
    "/orders/{order_id}/shipment",
    response_model=BaseSuccessResponse[ShipmentResponse],
    dependencies=[Depends(require_customer)],
)
async def get_shipment(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    result = await _service.get_shipment(db, order_id, user_id=current_user.id)
    return ok(result, ResponseCode.SHIPMENT_FETCHED, "Shipment fetched successfully")


@router.get(
    "/orders/{order_id}/tracking",
    response_model=BaseSuccessResponse[TrackingResponse],
    dependencies=[Depends(require_customer)],
)
async def get_tracking(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    result = await _service.get_tracking(db, order_id, user_id=current_user.id)
    return ok(
        result, ResponseCode.SHIPMENT_TRACKED, "Tracking info fetched successfully"
    )


@router.get(
    "/shipping/rates",
    response_model=BaseSuccessResponse[list[ShippingRateResponse]],
)
async def get_shipping_rates(
    weight_grams: int = Query(500, ge=1),
    pincode: str = Query(..., min_length=6, max_length=6),
):
    result = await _service.get_rates(weight_grams, pincode)
    return ok(
        result,
        ResponseCode.SHIPPING_RATES_FETCHED,
        "Shipping rates fetched successfully",
    )


# ── Admin ─────────────────────────────────────────────────────────────────────


@router.post(
    "/admin/orders/{order_id}/shipment",
    response_model=BaseSuccessResponse[ShipmentResponse],
    status_code=201,
    dependencies=[Depends(require_admin)],
)
async def create_shipment(
    order_id: uuid.UUID,
    payload: CreateShipmentRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await _service.create_shipment(db, order_id, payload)
    return created(
        result, ResponseCode.SHIPMENT_CREATED, "Shipment created successfully"
    )


@router.patch(
    "/admin/orders/{order_id}/shipment",
    response_model=BaseSuccessResponse[ShipmentResponse],
    dependencies=[Depends(require_admin)],
)
async def update_shipment(
    order_id: uuid.UUID,
    payload: UpdateShipmentRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await _service.update_shipment(db, order_id, payload)
    return ok(result, ResponseCode.SHIPMENT_UPDATED, "Shipment updated successfully")


@router.get(
    "/admin/orders/{order_id}/shipment",
    response_model=BaseSuccessResponse[ShipmentResponse],
    dependencies=[Depends(require_admin)],
)
async def admin_get_shipment(order_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await _service.get_shipment(db, order_id)
    return ok(result, ResponseCode.SHIPMENT_FETCHED, "Shipment fetched successfully")


@router.delete(
    "/admin/orders/{order_id}/shipment",
    response_model=BaseSuccessResponse[ShipmentResponse],
    dependencies=[Depends(require_admin)],
)
async def cancel_shipment(
    order_id: uuid.UUID,
    reason: str = Query(default="", max_length=500),
    db: AsyncSession = Depends(get_db),
):
    result = await _service.cancel_shipment(db, order_id, reason)
    return ok(
        result, ResponseCode.SHIPMENT_CANCELLED, "Shipment cancelled successfully"
    )

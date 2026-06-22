import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, deleted, ok
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin, require_customer
from app.modules.coupons.schemas import (
    CouponCreateRequest,
    CouponResponse,
    CouponUpdateRequest,
    CouponValidateRequest,
    CouponValidateResponse,
)
from app.modules.coupons.service import CouponService
from app.modules.profiles.models import Profile

router = APIRouter()
_service = CouponService()


@router.post(
    "/coupons/validate",
    response_model=BaseSuccessResponse[CouponValidateResponse],
    dependencies=[Depends(require_customer)],
)
async def validate_coupon(
    payload: CouponValidateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    result = await _service.validate(db, payload.code, payload.order_subtotal, current_user.id)
    return ok(result, ResponseCode.COUPON_VALIDATED, "Coupon validated successfully")


@router.get(
    "/admin/coupons",
    response_model=BaseSuccessResponse[list[CouponResponse]],
    dependencies=[Depends(require_admin)],
)
async def list_coupons(
    is_active: bool | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    result = await _service.list_all(db, is_active=is_active)
    return ok(result, ResponseCode.COUPON_LISTED, "Coupons listed successfully")


@router.post(
    "/admin/coupons",
    response_model=BaseSuccessResponse[CouponResponse],
    status_code=201,
    dependencies=[Depends(require_admin)],
)
async def create_coupon(
    payload: CouponCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    from app.common.responses import created
    result = await _service.create(db, payload)
    return created(result, ResponseCode.COUPON_CREATED, "Coupon created successfully")


@router.patch(
    "/admin/coupons/{coupon_id}",
    response_model=BaseSuccessResponse[CouponResponse],
    dependencies=[Depends(require_admin)],
)
async def update_coupon(
    coupon_id: uuid.UUID,
    payload: CouponUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await _service.update(db, coupon_id, payload)
    return ok(result, ResponseCode.COUPON_UPDATED, "Coupon updated successfully")


@router.delete(
    "/admin/coupons/{coupon_id}",
    response_model=BaseSuccessResponse[None],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def delete_coupon(
    coupon_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    await _service.delete(db, coupon_id)
    return deleted(ResponseCode.COUPON_DELETED, "Coupon deleted successfully")

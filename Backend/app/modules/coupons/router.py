import math
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, deleted, ok
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin, require_customer
from app.modules.coupons.schemas import (
    CouponCreateRequest,
    CouponListResponse,
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
    result = await _service.validate_with_email_check(
        db,
        payload.code,
        payload.order_subtotal,
        current_user.id,
        user_email=current_user.email or "",
        user_phone=getattr(current_user, "phone", None),
        ctx=payload,
    )
    return ok(result, ResponseCode.COUPON_VALIDATED, "Coupon validated successfully")


@router.get(
    "/admin/coupons",
    response_model=BaseSuccessResponse[CouponListResponse],
    dependencies=[Depends(require_admin)],
)
async def list_coupons(
    is_active: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    items, total = await _service.list_all(
        db, is_active=is_active, page=page, page_size=page_size
    )
    total_pages = math.ceil(total / page_size) if total else 1
    data = CouponListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
    return ok(data, ResponseCode.COUPON_LISTED, "Coupons listed successfully")


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

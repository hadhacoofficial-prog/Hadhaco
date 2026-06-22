import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.coupons.models import Coupon
from app.modules.coupons.repository import CouponRepository
from app.modules.coupons.schemas import (
    CouponCreateRequest,
    CouponResponse,
    CouponUpdateRequest,
    CouponValidateResponse,
)

_repo = CouponRepository()


def _ensure_utc(dt: datetime | None) -> datetime | None:
    """Return a UTC-aware datetime regardless of whether the input has tzinfo."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _calculate_discount(coupon: Coupon, subtotal: float) -> float:
    if coupon.coupon_type == "percentage":
        discount = round(subtotal * float(coupon.value) / 100, 2)
        if coupon.max_discount:
            discount = min(discount, float(coupon.max_discount))
    elif coupon.coupon_type == "fixed_amount":
        discount = min(float(coupon.value), subtotal)
    else:  # free_shipping — discount applied separately in order creation
        discount = 0.0
    return discount


class CouponService:
    async def list_all(
        self, db: AsyncSession, is_active: bool | None = None
    ) -> list[CouponResponse]:
        coupons = await _repo.list_all(db, is_active=is_active)
        return [CouponResponse.model_validate(c) for c in coupons]

    async def create(self, db: AsyncSession, payload: CouponCreateRequest) -> CouponResponse:
        existing = await _repo.get_by_code(db, payload.code)
        if existing:
            raise ConflictError(f"Coupon code '{payload.code}' already exists")

        data = payload.model_dump()
        data["id"] = uuid.uuid4()
        if not data.get("valid_from"):
            data["valid_from"] = datetime.now(UTC)

        coupon = await _repo.create(db, data)
        return CouponResponse.model_validate(coupon)

    async def update(
        self, db: AsyncSession, coupon_id: uuid.UUID, payload: CouponUpdateRequest
    ) -> CouponResponse:
        coupon = await _repo.get_by_id(db, coupon_id)
        if not coupon:
            raise NotFoundError("Coupon not found")
        updated = await _repo.update(db, coupon_id, payload.model_dump(exclude_unset=True))
        return CouponResponse.model_validate(updated)

    async def validate(
        self,
        db: AsyncSession,
        code: str,
        subtotal: float,
        user_id: uuid.UUID,
    ) -> CouponValidateResponse:
        coupon = await _repo.get_by_code(db, code)
        now = datetime.now(UTC)

        if not coupon:
            return CouponValidateResponse(
                valid=False, discount_amount=0, message="Invalid coupon code"
            )

        if not coupon.is_active:
            return CouponValidateResponse(
                valid=False, discount_amount=0, message="Coupon is inactive"
            )

        valid_from = _ensure_utc(coupon.valid_from)
        valid_until = _ensure_utc(coupon.valid_until)

        if valid_from and valid_from > now:
            return CouponValidateResponse(
                valid=False, discount_amount=0, message="Coupon is not yet active"
            )

        if valid_until and valid_until < now:
            return CouponValidateResponse(
                valid=False, discount_amount=0, message="Coupon has expired"
            )

        if coupon.usage_limit and coupon.usage_count >= coupon.usage_limit:
            return CouponValidateResponse(
                valid=False, discount_amount=0, message="Coupon usage limit reached"
            )

        if subtotal < float(coupon.min_order_amount):
            return CouponValidateResponse(
                valid=False,
                discount_amount=0,
                message=f"Minimum order amount is ₹{coupon.min_order_amount:.2f}",
            )

        user_usage = await _repo.get_user_usage_count(db, coupon.id, user_id)
        if user_usage >= coupon.per_user_limit:
            return CouponValidateResponse(
                valid=False, discount_amount=0, message="You have already used this coupon"
            )

        discount = _calculate_discount(coupon, subtotal)
        return CouponValidateResponse(
            valid=True,
            discount_amount=discount,
            message="Coupon applied successfully",
            coupon=CouponResponse.model_validate(coupon),
        )

    async def apply_and_reserve(
        self,
        db: AsyncSession,
        code: str,
        subtotal: float,
        user_id: uuid.UUID,
    ) -> tuple[float, uuid.UUID]:
        """
        Validates and records a pending coupon usage (order_id filled later).
        Returns (discount_amount, coupon_id).
        Raises ValidationError if coupon is invalid.
        """
        result = await self.validate(db, code, subtotal, user_id)
        if not result.valid:
            raise ValidationError(result.message)

        coupon = await _repo.get_by_code(db, code)
        await _repo.record_usage(db, coupon.id, user_id, result.discount_amount, order_id=None)
        await _repo.increment_usage(db, coupon.id)
        return result.discount_amount, coupon.id

    async def delete(self, db: AsyncSession, coupon_id: uuid.UUID) -> None:
        coupon = await _repo.get_by_id(db, coupon_id)
        if not coupon:
            raise NotFoundError("Coupon not found")
        await _repo.delete(db, coupon_id)
        await db.commit()

    async def finalize_usage(
        self,
        db: AsyncSession,
        coupon_id: uuid.UUID,
        user_id: uuid.UUID,
        order_id: uuid.UUID,
    ) -> None:
        await _repo.update_usage_order_id(db, coupon_id, user_id, order_id)

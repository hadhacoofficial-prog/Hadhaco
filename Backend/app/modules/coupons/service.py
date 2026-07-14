import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.coupons.models import Coupon
from app.modules.coupons.repository import CouponRepository
from app.modules.coupons.schemas import (
    CouponCreateRequest,
    CouponResponse,
    CouponUpdateRequest,
    CouponValidateRequest,
    CouponValidateResponse,
)

_repo = CouponRepository()
log = structlog.get_logger(__name__)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _invalid(msg: str) -> CouponValidateResponse:
    return CouponValidateResponse(valid=False, discount_amount=0.0, message=msg)


def _calculate_discount(coupon: Coupon, subtotal: float) -> float:
    if coupon.coupon_type == "percentage":
        discount = round(subtotal * float(coupon.value) / 100, 2)
        if coupon.max_discount:
            discount = min(discount, float(coupon.max_discount))
    elif coupon.coupon_type == "fixed_amount":
        discount = min(float(coupon.value), subtotal)
    else:  # free_shipping — shipping override handled in order service
        discount = 0.0
    return discount


def _nonempty(lst: list | None) -> list | None:
    """Return the list only if it has at least one element, else None."""
    return lst if lst else None


class CouponService:
    async def list_all(
        self, db: AsyncSession, is_active: bool | None = None
    ) -> list[CouponResponse]:
        coupons = await _repo.list_all(db, is_active=is_active)
        return [CouponResponse.model_validate(c) for c in coupons]

    async def create(
        self, db: AsyncSession, payload: CouponCreateRequest
    ) -> CouponResponse:
        existing = await _repo.get_by_code(db, payload.code)
        if existing:
            raise ConflictError(f"Coupon code '{payload.code}' already exists")

        data = payload.model_dump(exclude={"is_active"})
        data["id"] = uuid.uuid4()
        if not data.get("valid_from"):
            data["valid_from"] = datetime.now(UTC)
        # Sync is_active with status for backward compat
        data["is_active"] = data.get("status") == "active"

        coupon = await _repo.create(db, data)
        return CouponResponse.model_validate(coupon)

    async def update(
        self, db: AsyncSession, coupon_id: uuid.UUID, payload: CouponUpdateRequest
    ) -> CouponResponse:
        coupon = await _repo.get_by_id(db, coupon_id)
        if not coupon:
            raise NotFoundError("Coupon not found")

        updates = payload.model_dump(exclude_unset=True)
        # Keep is_active in sync when status changes
        if "status" in updates:
            updates.setdefault("is_active", updates["status"] == "active")
        elif "is_active" in updates:
            updates.setdefault(
                "status", "active" if updates["is_active"] else "inactive"
            )

        updated = await _repo.update(db, coupon_id, updates)
        return CouponResponse.model_validate(updated)

    async def validate(
        self,
        db: AsyncSession,
        code: str,
        subtotal: float,
        user_id: uuid.UUID,
        ctx: CouponValidateRequest | None = None,
    ) -> CouponValidateResponse:
        """
        Full 16-step validation chain.  ctx carries the optional checkout context
        (cart items, payment method, region, etc.).  When ctx is None (e.g. called
        from apply_and_reserve) only the order-agnostic rules are evaluated.
        """
        now = datetime.now(UTC)

        # ── 1. Coupon exists ─────────────────────────────────────────────────
        coupon = await _repo.get_by_code(db, code)
        if not coupon:
            return _invalid("Invalid coupon code.")

        # ── 2. Status ────────────────────────────────────────────────────────
        if coupon.status != "active":
            label = "draft" if coupon.status == "draft" else "inactive"
            return _invalid(f"This coupon is {label} and cannot be applied.")

        # ── 3. Validity period ───────────────────────────────────────────────
        valid_from = _ensure_utc(coupon.valid_from)
        valid_until = _ensure_utc(coupon.valid_until)
        if valid_from and valid_from > now:
            return _invalid("This coupon is not yet active.")
        if valid_until and valid_until < now:
            return _invalid("This coupon has expired.")

        # ── 4. Global usage limit ────────────────────────────────────────────
        if coupon.usage_limit and coupon.usage_count >= coupon.usage_limit:
            return _invalid("This coupon is no longer available.")

        # ── 5. Per-customer usage limit ──────────────────────────────────────
        user_usage = await _repo.get_user_usage_count(db, coupon.id, user_id)
        effective_limit = 1 if coupon.one_time_per_customer else coupon.per_user_limit
        if user_usage >= effective_limit:
            return _invalid("You have already used this coupon.")

        # ── 6. Customer eligibility ──────────────────────────────────────────
        if (
            coupon.first_order_only
            or coupon.new_customer_only
            or coupon.returning_customer_only
        ):
            order_count = await _repo.get_user_completed_order_count(db, user_id)
            if coupon.first_order_only and order_count > 0:
                return _invalid("This coupon is valid only on your first order.")
            if coupon.new_customer_only and order_count > 0:
                return _invalid("This coupon is for new customers only.")
            if coupon.returning_customer_only and order_count == 0:
                return _invalid("This coupon is for returning customers only.")

        # ── 7. Minimum order value ───────────────────────────────────────────
        min_amt = float(coupon.min_order_amount)
        if subtotal < min_amt:
            gap = round(min_amt - subtotal, 2)
            return _invalid(f"Add ₹{gap:,.0f} more to use this coupon.")

        # ── 8. Maximum order value ───────────────────────────────────────────
        if coupon.max_order_amount and subtotal > float(coupon.max_order_amount):
            return _invalid(
                f"This coupon is only valid for orders up to ₹{coupon.max_order_amount:,.0f}."
            )

        # ── Context-dependent rules (skipped when ctx is None) ───────────────
        if ctx is not None:
            cart_product_ids = set(ctx.cart_product_ids)
            cart_category_slugs = set(ctx.cart_category_slugs)

            # ── 9. Eligible product restrictions ─────────────────────────────
            if eligible := _nonempty(coupon.eligible_product_ids):
                if not cart_product_ids.intersection(eligible):
                    return _invalid(
                        "This coupon is not applicable to the products in your cart."
                    )

            # ── 10. Eligible category restrictions ───────────────────────────
            if eligible_cats := _nonempty(coupon.eligible_category_slugs):
                if not cart_category_slugs.intersection(eligible_cats):
                    return _invalid(
                        "This coupon is not applicable to the categories in your cart."
                    )

            # ── 11. Excluded products ─────────────────────────────────────────
            if excl := _nonempty(coupon.excluded_product_ids):
                # Reject only when every item in the cart is excluded
                if cart_product_ids and cart_product_ids.issubset(set(excl)):
                    return _invalid(
                        "This coupon cannot be applied to the items in your cart."
                    )

            # ── 12. Excluded categories ───────────────────────────────────────
            if excl_cats := _nonempty(coupon.excluded_category_slugs):
                if cart_category_slugs and cart_category_slugs.issubset(set(excl_cats)):
                    return _invalid(
                        "This coupon cannot be applied to the categories in your cart."
                    )

            # ── 14. Payment method ────────────────────────────────────────────
            if methods := _nonempty(coupon.allowed_payment_methods):
                if ctx.payment_method and ctx.payment_method not in methods:
                    return _invalid(
                        f"This coupon is only valid for: {', '.join(methods)}."
                    )

            # ── 15. Shipping method ───────────────────────────────────────────
            if ship_methods := _nonempty(coupon.allowed_shipping_methods):
                if ctx.shipping_method and ctx.shipping_method not in ship_methods:
                    return _invalid(
                        f"This coupon is only valid for: {', '.join(ship_methods)} delivery."
                    )

            # ── 16. Region ────────────────────────────────────────────────────
            if states := _nonempty(coupon.allowed_states):
                if ctx.delivery_state and ctx.delivery_state not in states:
                    return _invalid("This coupon is not available in your state.")
            if cities := _nonempty(coupon.allowed_cities):
                if ctx.delivery_city and ctx.delivery_city not in cities:
                    return _invalid("This coupon is not available in your city.")
            if pincodes := _nonempty(coupon.allowed_pincodes):
                if ctx.delivery_pincode and ctx.delivery_pincode not in pincodes:
                    return _invalid("This coupon is not available for your PIN code.")

        # ── Calculate discount ────────────────────────────────────────────────
        discount = _calculate_discount(coupon, subtotal)
        return CouponValidateResponse(
            valid=True,
            discount_amount=discount,
            message="Coupon applied successfully.",
            coupon=CouponResponse.model_validate(coupon),
            stackable=coupon.stackable,
        )

    async def validate_with_email_check(
        self,
        db: AsyncSession,
        code: str,
        subtotal: float,
        user_id: uuid.UUID,
        user_email: str,
        user_phone: str | None,
        ctx: CouponValidateRequest | None = None,
    ) -> CouponValidateResponse:
        """Validate with additional email/phone audience checks."""
        result = await self.validate(db, code, subtotal, user_id, ctx)
        if not result.valid or result.coupon is None:
            return result

        # result.coupon already carries allowed_emails/allowed_phone_numbers
        # from validate()'s fetch — no need to re-fetch the same row by code.
        coupon = result.coupon

        if emails := _nonempty(coupon.allowed_emails):
            if user_email.lower() not in [e.lower() for e in emails]:
                return _invalid("This coupon is not valid for your account.")

        if phones := _nonempty(coupon.allowed_phone_numbers):
            if user_phone and user_phone not in phones:
                return _invalid("This coupon is not valid for your account.")

        return result

    async def apply_and_reserve(
        self,
        db: AsyncSession,
        code: str,
        subtotal: float,
        user_id: uuid.UUID,
    ) -> tuple[float, uuid.UUID, str]:
        """Validate, record a pending usage (order_id filled later), return
        (discount, coupon_id, coupon_type) — coupon_type is already known
        here, so callers don't need a separate fetch just to read it.

        validate() reads usage_count/per-user usage without a lock — fine
        for a preview, not fine for the point of actually reserving usage.
        Re-checks both limits here under a row lock on the coupon so two
        concurrent checkouts can't both pass validate() and both reserve
        usage, oversubscribing a capped promo or double-redeeming a
        one-time-per-customer coupon.
        """
        result = await self.validate(db, code, subtotal, user_id)
        if not result.valid:
            raise ValidationError(result.message)

        coupon = await _repo.get_by_code_for_update(db, code)
        if coupon is None:
            raise ValidationError(result.message)

        if coupon.usage_limit and coupon.usage_count >= coupon.usage_limit:
            raise ValidationError("This coupon is no longer available.")

        effective_limit = 1 if coupon.one_time_per_customer else coupon.per_user_limit
        user_usage = await _repo.get_user_usage_count(db, coupon.id, user_id)
        if user_usage >= effective_limit:
            raise ValidationError("You have already used this coupon.")

        await _repo.record_usage(
            db, coupon.id, user_id, result.discount_amount, order_id=None
        )
        await _repo.increment_usage(db, coupon.id)
        return result.discount_amount, coupon.id, coupon.coupon_type

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
        rowcount = await _repo.update_usage_order_id(db, coupon_id, user_id, order_id)
        if rowcount != 1:
            log.warning(
                "coupon_usage_finalize_unexpected_rowcount",
                coupon_id=str(coupon_id),
                user_id=str(user_id),
                order_id=str(order_id),
                rowcount=rowcount,
            )

    async def revert_usage(
        self,
        db: AsyncSession,
        coupon_id: uuid.UUID,
        user_id: uuid.UUID,
        order_id: uuid.UUID | None = None,
    ) -> None:
        """Revert coupon usage when payment fails, is cancelled, or the
        reservation expires before payment.  Removes the usage row and
        decrements the coupon's usage_count so the slot becomes available
        again for other customers.
        """
        deleted = await _repo.revert_usage(db, coupon_id, user_id, order_id)
        if deleted:
            log.info(
                "coupon_usage_reverted",
                coupon_id=str(coupon_id),
                user_id=str(user_id),
                order_id=str(order_id) if order_id else None,
            )

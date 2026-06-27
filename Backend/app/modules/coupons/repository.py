import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.coupons.models import Coupon, CouponUsage

_COMPLETED_STATUSES = ("confirmed", "shipped", "delivered")


class CouponRepository:
    async def get_by_code(self, db: AsyncSession, code: str) -> Coupon | None:
        result = await db.execute(select(Coupon).where(Coupon.code == code.upper()))
        return result.scalar_one_or_none()

    async def get_by_id(self, db: AsyncSession, coupon_id: uuid.UUID) -> Coupon | None:
        result = await db.execute(select(Coupon).where(Coupon.id == coupon_id))
        return result.scalar_one_or_none()

    async def list_all(
        self, db: AsyncSession, *, is_active: bool | None = None
    ) -> list[Coupon]:
        q = select(Coupon).order_by(Coupon.created_at.desc())
        if is_active is not None:
            q = q.where(Coupon.is_active == is_active)
        return list((await db.execute(q)).scalars().all())

    async def create(self, db: AsyncSession, data: dict[str, Any]) -> Coupon:
        coupon = Coupon(**data)
        db.add(coupon)
        await db.flush()
        await db.refresh(coupon)
        return coupon

    async def update(
        self, db: AsyncSession, coupon_id: uuid.UUID, data: dict[str, Any]
    ) -> Coupon | None:
        await db.execute(update(Coupon).where(Coupon.id == coupon_id).values(**data))
        return await self.get_by_id(db, coupon_id)

    async def increment_usage(self, db: AsyncSession, coupon_id: uuid.UUID) -> None:
        await db.execute(
            update(Coupon)
            .where(Coupon.id == coupon_id)
            .values(usage_count=Coupon.usage_count + 1)
        )

    async def get_user_usage_count(
        self, db: AsyncSession, coupon_id: uuid.UUID, user_id: uuid.UUID
    ) -> int:
        result = await db.execute(
            select(func.count())
            .select_from(CouponUsage)
            .where(
                CouponUsage.coupon_id == coupon_id,
                CouponUsage.user_id == user_id,
            )
        )
        return result.scalar_one()

    async def record_usage(
        self,
        db: AsyncSession,
        coupon_id: uuid.UUID,
        user_id: uuid.UUID,
        discount: float,
        order_id: uuid.UUID | None = None,
    ) -> CouponUsage:
        usage = CouponUsage(
            id=uuid.uuid4(),
            coupon_id=coupon_id,
            user_id=user_id,
            order_id=order_id,
            discount=discount,
        )
        db.add(usage)
        await db.flush()
        return usage

    async def update_usage_order_id(
        self,
        db: AsyncSession,
        coupon_id: uuid.UUID,
        user_id: uuid.UUID,
        order_id: uuid.UUID,
    ) -> None:
        await db.execute(
            update(CouponUsage)
            .where(
                CouponUsage.coupon_id == coupon_id,
                CouponUsage.user_id == user_id,
                CouponUsage.order_id.is_(None),
            )
            .values(order_id=order_id)
        )

    async def get_user_completed_order_count(
        self, db: AsyncSession, user_id: uuid.UUID
    ) -> int:
        """Count orders in a terminal-success status for eligibility checks."""
        from sqlalchemy import text

        result = await db.execute(
            text(
                "SELECT COUNT(*) FROM orders "
                "WHERE user_id = :uid AND status = ANY(:statuses)"
            ),
            {"uid": str(user_id), "statuses": list(_COMPLETED_STATUSES)},
        )
        return result.scalar_one()

    async def delete(self, db: AsyncSession, coupon_id: uuid.UUID) -> None:
        coupon = await self.get_by_id(db, coupon_id)
        if coupon:
            await db.delete(coupon)
            await db.flush()

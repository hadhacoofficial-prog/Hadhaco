import uuid
from datetime import UTC
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.orders.models import Order, OrderItem


class OrderRepository:
    def _with_items(self):
        return selectinload(Order.items)

    async def get_by_id(self, db: AsyncSession, order_id: uuid.UUID) -> Order | None:
        result = await db.execute(
            select(Order).where(Order.id == order_id).options(self._with_items())
        )
        return result.scalar_one_or_none()

    async def get_by_order_number(
        self, db: AsyncSession, order_number: str
    ) -> Order | None:
        result = await db.execute(
            select(Order)
            .where(Order.order_number == order_number)
            .options(self._with_items())
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _item_count_subquery():
        """Correlated scalar subquery that returns ORDER item count without loading rows."""
        return (
            select(func.count(OrderItem.id))
            .where(OrderItem.order_id == Order.id)
            .correlate(Order)
            .scalar_subquery()
        )

    async def list_for_user(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 10,
        status: str | None = None,
    ) -> tuple[list[Order], int]:
        item_count_sq = self._item_count_subquery()

        q = select(Order, item_count_sq.label("_item_count")).where(
            Order.user_id == user_id
        )
        count_q = select(func.count(Order.id)).where(Order.user_id == user_id)

        if status:
            q = q.where(Order.status == status)
            count_q = count_q.where(Order.status == status)

        total = (await db.execute(count_q)).scalar_one()

        q = (
            q.order_by(Order.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(q)

        orders: list[Order] = []
        for order_obj, item_count in result.all():
            order_obj._item_count = item_count
            orders.append(order_obj)
        return orders, total

    async def list_all(
        self,
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        payment_status: str | None = None,
        user_id: uuid.UUID | None = None,
        search: str | None = None,
    ) -> tuple[list[Order], int]:
        item_count_sq = self._item_count_subquery()

        q = select(Order, item_count_sq.label("_item_count"))
        count_q = select(func.count(Order.id))

        if status:
            q = q.where(Order.status == status)
            count_q = count_q.where(Order.status == status)
        if payment_status:
            q = q.where(Order.payment_status == payment_status)
            count_q = count_q.where(Order.payment_status == payment_status)
        if user_id:
            q = q.where(Order.user_id == user_id)
            count_q = count_q.where(Order.user_id == user_id)
        if search:
            q = q.where(Order.order_number.ilike(f"%{search}%"))
            count_q = count_q.where(Order.order_number.ilike(f"%{search}%"))

        total = (await db.execute(count_q)).scalar_one()

        q = (
            q.order_by(Order.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(q)

        orders: list[Order] = []
        for order_obj, item_count in result.all():
            order_obj._item_count = item_count
            orders.append(order_obj)
        return orders, total

    async def create(self, db: AsyncSession, data: dict[str, Any]) -> Order:
        order = Order(**data)
        db.add(order)
        await db.flush()
        await db.refresh(order)
        return order

    async def add_item(self, db: AsyncSession, data: dict[str, Any]) -> OrderItem:
        item = OrderItem(**data)
        db.add(item)
        await db.flush()
        return item

    async def update(
        self, db: AsyncSession, order_id: uuid.UUID, data: dict[str, Any]
    ) -> Order | None:
        await db.execute(update(Order).where(Order.id == order_id).values(**data))
        return await self.get_by_id(db, order_id)

    async def generate_order_number(self, db: AsyncSession) -> str:
        """Generate sequential order number: HDH-YYYYMM-NNNNNN"""
        from datetime import datetime

        now = datetime.now(UTC)
        prefix = f"HDH-{now.year}{now.month:02d}-"
        result = await db.execute(
            select(func.count(Order.id)).where(Order.order_number.like(f"{prefix}%"))
        )
        seq = result.scalar_one() + 1
        return f"{prefix}{seq:06d}"

from __future__ import annotations

import uuid
from collections.abc import Collection
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import DEFAULT_RETURN_WINDOW_DAYS, Product
from app.modules.orders.models import Order, OrderItem
from app.modules.returns.models import Return, ReturnItem


class ReturnRepository:
    async def get(self, db: AsyncSession, return_id: uuid.UUID) -> Return | None:
        result = await db.execute(select(Return).where(Return.id == return_id))
        return result.scalar_one_or_none()

    async def get_for_update(
        self, db: AsyncSession, return_id: uuid.UUID
    ) -> Return | None:
        """Row-locked fetch so two concurrent status updates serialise."""
        result = await db.execute(
            select(Return)
            .where(Return.id == return_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def returned_quantities(
        self, db: AsyncSession, order_id: uuid.UUID
    ) -> dict[uuid.UUID, int]:
        """Units already claimed per order item by non-rejected/cancelled returns."""
        result = await db.execute(
            select(ReturnItem.order_item_id, func.sum(ReturnItem.quantity))
            .join(Return, Return.id == ReturnItem.return_id)
            .where(
                Return.order_id == order_id,
                Return.status.notin_(("rejected", "cancelled")),
            )
            .group_by(ReturnItem.order_item_id)
        )
        return {row[0]: int(row[1] or 0) for row in result.all()}

    async def list_for_customer(
        self, db: AsyncSession, customer_id: uuid.UUID
    ) -> list[Return]:
        result = await db.execute(
            select(Return)
            .where(Return.customer_id == customer_id)
            .order_by(Return.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_all(
        self, db: AsyncSession, offset: int = 0, limit: int = 50
    ) -> list[Return]:
        result = await db.execute(
            select(Return)
            .order_by(Return.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create(self, db: AsyncSession, **kwargs: Any) -> Return:
        r = Return(**kwargs)
        db.add(r)
        await db.flush()
        return r

    async def add_item(self, db: AsyncSession, **kwargs: Any) -> ReturnItem:
        item = ReturnItem(**kwargs)
        db.add(item)
        await db.flush()
        return item

    async def update_status(
        self, db: AsyncSession, ret: Return, status: str, **kwargs: Any
    ) -> Return:
        ret.status = status
        for k, v in kwargs.items():
            setattr(ret, k, v)
        db.add(ret)
        await db.flush()
        return ret

    async def is_within_return_window(
        self,
        db: AsyncSession,
        order_id: uuid.UUID,
        customer_id: uuid.UUID,
        order_item_ids: Collection[uuid.UUID],
    ) -> bool:
        """True only when the order is the customer's, delivered, and EVERY
        requested line is a returnable product still inside its own window
        (``return_window_days``, store default when unset)."""
        wanted = set(order_item_ids)
        if not wanted:
            return False
        window = func.make_interval(
            0,
            0,
            0,
            func.coalesce(Product.return_window_days, DEFAULT_RETURN_WINDOW_DAYS),
        )
        result = await db.execute(
            select(func.count(OrderItem.id))
            .join(Order, Order.id == OrderItem.order_id)
            .join(Product, Product.id == OrderItem.product_id)
            .where(
                Order.id == order_id,
                Order.user_id == customer_id,
                Order.status == "delivered",
                OrderItem.id.in_(wanted),
                Product.is_returnable.is_(True),
                Order.delivered_at >= func.now() - window,
            )
        )
        return result.scalar_one() == len(wanted)

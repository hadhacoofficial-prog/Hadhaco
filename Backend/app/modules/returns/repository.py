from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.returns.models import Return, ReturnItem


class ReturnRepository:
    async def get(self, db: AsyncSession, return_id: uuid.UUID) -> Return | None:
        result = await db.execute(select(Return).where(Return.id == return_id))
        return result.scalar_one_or_none()

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
        self, db: AsyncSession, order_id: uuid.UUID, customer_id: uuid.UUID
    ) -> bool:
        result = await db.execute(
            text("""
                SELECT 1 FROM orders
                WHERE id = :order_id
                  AND user_id = :customer_id
                  AND status = 'delivered'
                  AND delivered_at >= NOW() - INTERVAL '7 days'
            """),
            {"order_id": order_id, "customer_id": customer_id},
        )
        return result.fetchone() is not None

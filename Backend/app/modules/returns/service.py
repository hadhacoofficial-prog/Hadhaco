from __future__ import annotations
import uuid
from datetime import UTC, datetime, timezone
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.returns.models import Return
from app.modules.returns.repository import ReturnRepository
from app.modules.returns.schemas import ReturnCreate, AdminReturnStatusUpdate


class ReturnService:
    def __init__(self) -> None:
        self._repo = ReturnRepository()

    async def create_return(self, db: AsyncSession, *, customer_id: uuid.UUID, data: ReturnCreate) -> Return:
        if not await self._repo.is_within_return_window(db, data.order_id):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Order not eligible for return (not delivered or outside 7-day window)")
        ret = await self._repo.create(db, order_id=data.order_id, customer_id=customer_id, reason=data.reason)
        for item in data.items:
            await self._repo.add_item(db, return_id=ret.id, order_item_id=item.order_item_id, quantity=item.quantity, reason=item.reason)
        await db.commit()
        await db.refresh(ret)
        return ret

    async def list_customer_returns(self, db: AsyncSession, customer_id: uuid.UUID) -> list[Return]:
        return await self._repo.list_for_customer(db, customer_id)

    async def list_all(self, db: AsyncSession, offset: int = 0, limit: int = 50) -> list[Return]:
        return await self._repo.list_all(db, offset=offset, limit=limit)

    async def admin_update_status(self, db: AsyncSession, *, return_id: uuid.UUID, admin_id: uuid.UUID, data: AdminReturnStatusUpdate) -> Return:
        ret = await self._repo.get(db, return_id)
        if not ret:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Return not found")
        kwargs: dict = {"admin_notes": data.admin_notes, "reviewed_by": admin_id, "reviewed_at": datetime.now(UTC)}
        ret = await self._repo.update_status(db, ret, data.status, **{k: v for k, v in kwargs.items() if v is not None})
        await db.commit()
        await db.refresh(ret)
        return ret

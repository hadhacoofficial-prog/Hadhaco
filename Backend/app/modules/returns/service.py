from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.orders.models import OrderItem
from app.modules.returns.models import Return
from app.modules.returns.repository import ReturnRepository
from app.modules.returns.schemas import AdminReturnStatusUpdate, ReturnCreate

# Statuses at which the physical item is confirmed back in the warehouse and
# stock should be returned to sellable inventory. Gated on `received_at` being
# unset so re-saving the same (or a later) status never double-restocks.
_RESTOCK_STATUSES = {"received", "restocked"}


class ReturnService:
    def __init__(self) -> None:
        self._repo = ReturnRepository()

    async def create_return(
        self, db: AsyncSession, *, customer_id: uuid.UUID, data: ReturnCreate
    ) -> Return:
        if not await self._repo.is_within_return_window(db, data.order_id, customer_id):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Order not eligible for return (not delivered or outside 7-day window)",
            )
        ret = await self._repo.create(
            db, order_id=data.order_id, customer_id=customer_id, reason=data.reason
        )
        for item in data.items:
            await self._repo.add_item(
                db,
                return_id=ret.id,
                order_item_id=item.order_item_id,
                quantity=item.quantity,
                reason=item.reason,
            )
        await db.commit()
        await db.refresh(ret)
        return ret

    async def list_customer_returns(
        self, db: AsyncSession, customer_id: uuid.UUID
    ) -> list[Return]:
        return await self._repo.list_for_customer(db, customer_id)

    async def list_all(
        self, db: AsyncSession, offset: int = 0, limit: int = 50
    ) -> list[Return]:
        return await self._repo.list_all(db, offset=offset, limit=limit)

    async def admin_update_status(
        self,
        db: AsyncSession,
        *,
        return_id: uuid.UUID,
        admin_id: uuid.UUID,
        data: AdminReturnStatusUpdate,
    ) -> Return:
        ret = await self._repo.get(db, return_id)
        if not ret:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Return not found")

        # Gate on received_at (not just the status string) so re-submitting
        # the same status, or advancing through a later status, never
        # restocks the same return twice.
        should_restock = data.status in _RESTOCK_STATUSES and ret.received_at is None

        kwargs: dict = {
            "admin_notes": data.admin_notes,
            "reviewed_by": admin_id,
            "reviewed_at": datetime.now(UTC),
        }
        if should_restock:
            kwargs["received_at"] = datetime.now(UTC)

        ret = await self._repo.update_status(
            db, ret, data.status, **{k: v for k, v in kwargs.items() if v is not None}
        )

        if should_restock:
            # Approving/receiving a return doesn't itself return stock to
            # sellable inventory unless we explicitly do it here — previously
            # this method only ever touched the `returns` row, so processed
            # returns silently never came back into available_stock.
            from app.modules.inventory.reservation_service import ReservationService

            order_item_ids = [item.order_item_id for item in ret.items]
            order_items: dict[uuid.UUID, OrderItem] = {}
            if order_item_ids:
                result = await db.execute(
                    select(OrderItem).where(OrderItem.id.in_(order_item_ids))
                )
                order_items = {oi.id: oi for oi in result.scalars().all()}

            reservation_svc = ReservationService()
            for item in ret.items:
                order_item = order_items.get(item.order_item_id)
                if order_item is None or order_item.product_id is None:
                    continue
                await reservation_svc.record_return(
                    db,
                    product_id=order_item.product_id,
                    variant_id=order_item.variant_id,
                    quantity=item.quantity,
                    order_id=ret.order_id,
                    reference=f"return:{ret.id}",
                )

        await db.commit()
        await db.refresh(ret)
        return ret

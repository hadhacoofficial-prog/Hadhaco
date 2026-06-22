import uuid
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.models import InventoryMovement


class InventoryRepository:
    async def record(self, db: AsyncSession, data: dict[str, Any]) -> InventoryMovement:
        movement = InventoryMovement(**data)
        db.add(movement)
        await db.flush()
        await db.refresh(movement)
        return movement

    async def list_for_product(
        self,
        db: AsyncSession,
        product_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
        movement_type: str | None = None,
    ) -> tuple[list[InventoryMovement], int]:
        q = select(InventoryMovement).where(InventoryMovement.product_id == product_id)
        if movement_type:
            q = q.where(InventoryMovement.movement_type == movement_type)

        count_q = select(func.count()).select_from(q.subquery())
        total: int = (await db.execute(count_q)).scalar_one()

        q = (
            q.order_by(InventoryMovement.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(q)
        return list(result.scalars().all()), total

    async def get_low_stock(self, db: AsyncSession) -> list[dict]:
        result = await db.execute(
            text(
                "SELECT id, sku, name, stock_quantity, low_stock_threshold, status, category_id "
                "FROM low_stock_products ORDER BY stock_quantity ASC"
            )
        )
        return [dict(r._mapping) for r in result.fetchall()]

    async def get_stock_snapshot(
        self, db: AsyncSession, product_id: uuid.UUID
    ) -> dict | None:
        result = await db.execute(
            text(
                "SELECT stock_quantity, low_stock_threshold, track_inventory, allow_backorder "
                "FROM products WHERE id = :id AND deleted_at IS NULL"
            ),
            {"id": str(product_id)},
        )
        row = result.fetchone()
        return dict(row._mapping) if row else None

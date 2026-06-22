import math
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import LowInventoryAlertEvent, event_bus
from app.core.exceptions import NotFoundError, ValidationError
from app.modules.inventory.repository import InventoryRepository
from app.modules.inventory.schemas import (
    InventoryMovementListResponse,
    InventoryMovementResponse,
    LowStockItem,
    ManualAdjustmentRequest,
)

_repo = InventoryRepository()


class InventoryService:

    async def record_movement(
        self,
        db: AsyncSession,
        *,
        product_id: uuid.UUID,
        delta: int,
        movement_type: str,
        variant_id: uuid.UUID | None = None,
        reference_type: str | None = None,
        reference_id: str | None = None,
        notes: str | None = None,
        created_by: uuid.UUID | None = None,
    ) -> InventoryMovementResponse:
        """
        Core method called by order, return, and admin flows.
        Atomically updates product stock and records the ledger entry.
        Publishes LowInventoryAlertEvent when stock drops to or below threshold.
        """
        snapshot = await _repo.get_stock_snapshot(db, product_id)
        if not snapshot:
            raise NotFoundError("Product not found")

        quantity_before: int = snapshot["stock_quantity"]
        quantity_after = quantity_before + delta

        if quantity_after < 0 and not snapshot["allow_backorder"]:
            raise ValidationError(
                f"Insufficient stock: available {quantity_before}, requested {abs(delta)}"
            )

        # Atomic stock update
        await db.execute(
            text(
                "UPDATE products SET stock_quantity = stock_quantity + :delta "
                "WHERE id = :id AND deleted_at IS NULL"
            ),
            {"delta": delta, "id": str(product_id)},
        )

        # Ledger entry
        movement = await _repo.record(
            db,
            {
                "id": uuid.uuid4(),
                "product_id": product_id,
                "variant_id": variant_id,
                "movement_type": movement_type,
                "delta": delta,
                "quantity_before": quantity_before,
                "quantity_after": quantity_after,
                "reference_type": reference_type,
                "reference_id": reference_id,
                "notes": notes,
                "created_by": created_by,
            },
        )

        # Low-stock alert — fire after flush so DB state is consistent
        threshold: int = snapshot["low_stock_threshold"]
        if delta < 0 and quantity_after <= threshold:
            await event_bus.publish(
                LowInventoryAlertEvent(
                    product_id=str(product_id),
                    sku=snapshot.get("sku", ""),
                    product_name=snapshot.get("product_name", ""),
                    current_qty=quantity_after,
                    quantity_after=quantity_after,
                    threshold=threshold,
                )
            )

        return InventoryMovementResponse.model_validate(movement)

    async def manual_adjustment(
        self,
        db: AsyncSession,
        product_id: uuid.UUID,
        payload: ManualAdjustmentRequest,
        actor_id: uuid.UUID,
    ) -> InventoryMovementResponse:
        return await self.record_movement(
            db,
            product_id=product_id,
            delta=payload.delta,
            movement_type="adjustment",
            variant_id=payload.variant_id,
            reference_type="manual_adjustment",
            reference_id=None,
            notes=payload.notes,
            created_by=actor_id,
        )

    async def get_history(
        self,
        db: AsyncSession,
        product_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
        movement_type: str | None = None,
    ) -> InventoryMovementListResponse:
        # Verify product exists
        snapshot = await _repo.get_stock_snapshot(db, product_id)
        if not snapshot:
            raise NotFoundError("Product not found")

        items, total = await _repo.list_for_product(
            db,
            product_id,
            page=page,
            page_size=page_size,
            movement_type=movement_type,
        )
        return InventoryMovementListResponse(
            items=[InventoryMovementResponse.model_validate(m) for m in items],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=math.ceil(total / page_size) if total else 0,
        )

    async def get_low_stock(self, db: AsyncSession) -> list[LowStockItem]:
        rows = await _repo.get_low_stock(db)
        return [LowStockItem(**r) for r in rows]

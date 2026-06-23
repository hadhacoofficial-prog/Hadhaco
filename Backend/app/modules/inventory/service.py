import math
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.modules.inventory.repository import InventoryRepository
from app.modules.inventory.schemas import (
    InventoryMovementListResponse,
    InventoryMovementResponse,
    InventoryTransactionListResponse,
    InventoryTransactionResponse,
    LowStockItem,
    ManualAdjustmentRequest,
    ProductStockSummary,
    ReservationListResponse,
    ReservationResponse,
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
        Legacy movement recorder — updates stock_quantity for restock/adjustment ops.
        New flows (checkout, payment) use ReservationService instead.
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

        await db.execute(
            text(
                "UPDATE products SET stock_quantity = stock_quantity + :delta "
                "WHERE id = :id AND deleted_at IS NULL"
            ),
            {"delta": delta, "id": str(product_id)},
        )

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

    # ── New reservation-aware queries ─────────────────────────────────────────

    async def get_stock_summary(
        self, db: AsyncSession, product_id: uuid.UUID
    ) -> ProductStockSummary:
        data = await _repo.get_stock_summary(db, product_id)
        if not data:
            raise NotFoundError("Product not found")
        return ProductStockSummary(**data)

    async def list_reservations(
        self,
        db: AsyncSession,
        *,
        product_id: uuid.UUID | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ReservationListResponse:
        items, total = await _repo.list_reservations(
            db, product_id=product_id, status=status, page=page, page_size=page_size
        )
        return ReservationListResponse(
            items=[ReservationResponse.model_validate(r) for r in items],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=math.ceil(total / page_size) if total else 0,
        )

    async def list_transactions(
        self,
        db: AsyncSession,
        *,
        product_id: uuid.UUID | None = None,
        transaction_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> InventoryTransactionListResponse:
        items, total = await _repo.list_transactions(
            db,
            product_id=product_id,
            transaction_type=transaction_type,
            page=page,
            page_size=page_size,
        )
        return InventoryTransactionListResponse(
            items=[InventoryTransactionResponse.model_validate(t) for t in items],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=math.ceil(total / page_size) if total else 0,
        )

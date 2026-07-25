import uuid
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.models import (
    InventoryMovement,
    InventoryReservation,
    InventoryTransaction,
)


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
        variant_id: uuid.UUID | None = None,
    ) -> tuple[list[InventoryMovement], int]:
        q = select(InventoryMovement).where(InventoryMovement.product_id == product_id)
        if variant_id:
            q = q.where(InventoryMovement.variant_id == variant_id)
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

    async def get_low_stock(self, db: AsyncSession, *, limit: int = 500) -> list[dict]:
        result = await db.execute(
            text(
                "SELECT variant_id, product_id, sku, variant_name, product_name, "
                "available_stock, stock_quantity, low_stock_threshold, status, "
                "category_id FROM low_stock_products "
                "ORDER BY available_stock ASC LIMIT :limit"
            ),
            {"limit": limit},
        )
        return [dict(r._mapping) for r in result.fetchall()]

    async def get_stock_snapshot(
        self, db: AsyncSession, product_id: uuid.UUID
    ) -> dict | None:
        result = await db.execute(
            text(
                "SELECT stock_quantity, reserved_quantity, sold_quantity, "
                "low_stock_threshold, track_inventory, allow_backorder "
                "FROM products WHERE id = :id AND deleted_at IS NULL"
            ),
            {"id": str(product_id)},
        )
        row = result.fetchone()
        return dict(row._mapping) if row else None

    # ── Reservations ──────────────────────────────────────────────────────────

    async def list_reservations(
        self,
        db: AsyncSession,
        *,
        product_id: uuid.UUID | None = None,
        variant_id: uuid.UUID | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[InventoryReservation], int]:
        q = select(InventoryReservation)
        if product_id:
            q = q.where(InventoryReservation.product_id == product_id)
        if variant_id:
            q = q.where(InventoryReservation.variant_id == variant_id)
        if status:
            q = q.where(InventoryReservation.status == status)

        count_q = select(func.count()).select_from(q.subquery())
        total: int = (await db.execute(count_q)).scalar_one()

        q = (
            q.order_by(InventoryReservation.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(q)
        return list(result.scalars().all()), total

    # ── Transactions ──────────────────────────────────────────────────────────

    async def list_transactions(
        self,
        db: AsyncSession,
        *,
        product_id: uuid.UUID | None = None,
        variant_id: uuid.UUID | None = None,
        transaction_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[InventoryTransaction], int]:
        q = select(InventoryTransaction)
        if product_id:
            q = q.where(InventoryTransaction.product_id == product_id)
        if variant_id:
            q = q.where(InventoryTransaction.variant_id == variant_id)
        if transaction_type:
            q = q.where(InventoryTransaction.transaction_type == transaction_type)

        count_q = select(func.count()).select_from(q.subquery())
        total: int = (await db.execute(count_q)).scalar_one()

        q = (
            q.order_by(InventoryTransaction.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(q)
        return list(result.scalars().all()), total

    async def get_stock_summary(
        self,
        db: AsyncSession,
        product_id: uuid.UUID,
        *,
        variant_id: uuid.UUID | None = None,
    ) -> dict | None:
        """Stock summary for a product. With variant_id, summarizes that one
        variant. Without, aggregates across all of the product's active
        variants (every product is guaranteed >=1 post-backfill — see
        migration 0060) rather than reading the product's own vestigial
        stock_quantity/reserved_quantity/sold_quantity columns, which are
        not kept in sync for variant-bearing products."""
        if variant_id is not None:
            result = await db.execute(
                text("""
                    SELECT
                        p.id AS product_id,
                        v.sku,
                        p.name,
                        v.stock_quantity AS total_stock,
                        v.reserved_quantity,
                        v.sold_quantity,
                        GREATEST(v.stock_quantity - v.reserved_quantity - v.sold_quantity, 0)
                            AS available_quantity,  -- mirrors compute_available_stock()
                        (SELECT COUNT(*) FROM inventory_reservations ir
                         WHERE ir.variant_id = v.id
                         AND ir.status IN ('ACTIVE', 'CHECKOUT_IN_PROGRESS')) AS active_reservations
                    FROM product_variants v
                    JOIN products p ON p.id = v.product_id
                    WHERE v.id = :vid AND v.product_id = :pid AND p.deleted_at IS NULL
                    """),
                {"vid": str(variant_id), "pid": str(product_id)},
            )
            row = result.fetchone()
            return dict(row._mapping) if row else None

        result = await db.execute(
            text("""
                SELECT
                    p.id AS product_id,
                    p.sku,
                    p.name,
                    COALESCE(SUM(v.stock_quantity), 0) AS total_stock,
                    COALESCE(SUM(v.reserved_quantity), 0) AS reserved_quantity,
                    COALESCE(SUM(v.sold_quantity), 0) AS sold_quantity,
                    COALESCE(SUM(GREATEST(v.stock_quantity - v.reserved_quantity
                        - v.sold_quantity, 0)), 0) AS available_quantity,  -- mirrors compute_available_stock()
                    (SELECT COUNT(*) FROM inventory_reservations ir
                     WHERE ir.product_id = p.id
                     AND ir.status IN ('ACTIVE', 'CHECKOUT_IN_PROGRESS')) AS active_reservations
                FROM products p
                LEFT JOIN product_variants v
                    ON v.product_id = p.id AND v.is_active = true
                WHERE p.id = :pid AND p.deleted_at IS NULL
                GROUP BY p.id, p.sku, p.name
                """),
            {"pid": str(product_id)},
        )
        row = result.fetchone()
        return dict(row._mapping) if row else None

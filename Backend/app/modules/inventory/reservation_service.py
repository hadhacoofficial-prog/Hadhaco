"""
Stock reservation service — the concurrency-safe core of the inventory system.

All operations that change reserved_quantity or sold_quantity MUST go through
this service. Every method that modifies stock state:
  1. Acquires a PostgreSQL row-level lock via SELECT ... FOR UPDATE
  2. Reads the current stock state inside that lock
  3. Validates the operation
  4. Writes atomically
  5. Logs an InventoryTransaction record
  6. Returns without committing — the caller owns the transaction boundary
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InventoryError, NotFoundError, ValidationError
from app.core.redis import (
    get_redis_pool,
    mark_redis_error,
    redis_available,
    safe_redis_delete,
)
from app.modules.inventory.models import InventoryReservation, InventoryTransaction

log = structlog.get_logger(__name__)

_RESERVATION_TTL_MINUTES = 10


def _generate_reservation_number() -> str:
    suffix = uuid.uuid4().hex[:8].upper()
    return f"RES-{suffix}"


class ReservationService:
    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _lock_stock_target(
        self,
        db: AsyncSession,
        product_id: uuid.UUID,
        variant_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        """Lock the row that owns inventory for this line item."""
        if variant_id:
            result = await db.execute(
                text(
                    "SELECT v.id AS target_id, v.product_id, v.name AS variant_name, "
                    "v.stock_quantity, v.reserved_quantity, v.sold_quantity, "
                    "p.name AS product_name, p.track_inventory, p.allow_backorder "
                    "FROM product_variants v "
                    "JOIN products p ON p.id = v.product_id "
                    "WHERE v.id = :vid AND v.product_id = :pid "
                    "AND v.is_active = true "
                    "AND p.deleted_at IS NULL AND p.status = 'active' "
                    "FOR UPDATE OF v"
                ),
                {"vid": str(variant_id), "pid": str(product_id)},
            )
            row = result.fetchone()
            if not row:
                raise NotFoundError(
                    f"Variant {variant_id} is no longer available for product {product_id}"
                )
            stock = dict(row._mapping)
            stock["table_name"] = "product_variants"
            stock["id_column"] = "id"
            stock["variant_id"] = variant_id
            stock["item_name"] = (
                f"{stock['product_name']} - {stock['variant_name']}"
                if stock.get("variant_name")
                else stock["product_name"]
            )
            return stock

        result = await db.execute(
            text(
                "SELECT id, name, sku, stock_quantity, reserved_quantity, sold_quantity, "
                "track_inventory, allow_backorder "
                "FROM products "
                "WHERE id = :pid AND deleted_at IS NULL AND status = 'active' "
                "FOR UPDATE"
            ),
            {"pid": str(product_id)},
        )
        row = result.fetchone()
        if not row:
            raise NotFoundError(f"Product {product_id} is no longer available")
        stock = dict(row._mapping)
        stock["target_id"] = product_id
        stock["product_id"] = product_id
        stock["variant_id"] = None
        stock["table_name"] = "products"
        stock["id_column"] = "id"
        item_name = str(stock.get("name") or "Product")
        stock["product_name"] = item_name
        stock["item_name"] = item_name
        return stock

    async def _invalidate_inventory_cache(
        self, product_id: uuid.UUID, variant_id: uuid.UUID | None
    ) -> None:
        """Best-effort cache-aside invalidation for all inventory-derived views."""
        if not redis_available():
            return
        redis = get_redis_pool()
        direct_keys = [
            f"product:{product_id}",
            f"product_details:{product_id}",
            "featured_products",
            "cms:homepage",
        ]
        if variant_id:
            direct_keys.append(f"variant:{variant_id}")

        patterns = [
            "products:list:v1:*",
            "product:list:*",
            "product_details:*",
            "category:*",
            "collection:*",
            "homepage:*",
            "search:*",
            "recommendation:*",
            "recommendations:*",
        ]

        try:
            await safe_redis_delete(redis, *direct_keys)
            pattern_keys: list[str] = []
            for pattern in patterns:
                keys = await asyncio.wait_for(redis.keys(pattern), timeout=0.3)
                pattern_keys.extend(str(key) for key in keys)
            if pattern_keys:
                await safe_redis_delete(redis, *set(pattern_keys))
        except Exception:
            mark_redis_error()

    async def _update_stock_target(
        self,
        db: AsyncSession,
        stock: dict[str, Any],
        set_clause: str,
        params: dict[str, Any],
    ) -> None:
        await db.execute(
            text(
                f"UPDATE {stock['table_name']} "
                f"SET {set_clause} "
                f"WHERE {stock['id_column']} = :target_id"
            ),
            {**params, "target_id": str(stock["target_id"])},
        )

    async def _log_transaction(
        self,
        db: AsyncSession,
        *,
        product_id: uuid.UUID,
        variant_id: uuid.UUID | None,
        reservation_id: uuid.UUID | None,
        order_id: uuid.UUID | None,
        transaction_type: str,
        quantity: int,
        before_stock: dict,
        after_reserved: int,
        after_sold: int,
        after_stock_quantity: int | None = None,
        reference: str | None = None,
    ) -> None:
        total = before_stock["stock_quantity"]
        b_res = before_stock["reserved_quantity"]
        b_sold = before_stock["sold_quantity"]
        b_avail = total - b_res - b_sold

        a_res = after_reserved
        a_sold = after_sold
        a_total = after_stock_quantity if after_stock_quantity is not None else total
        a_avail = a_total - a_res - a_sold

        txn = InventoryTransaction(
            id=uuid.uuid4(),
            product_id=product_id,
            variant_id=variant_id,
            reservation_id=reservation_id,
            order_id=order_id,
            transaction_type=transaction_type,
            quantity=quantity,
            before_available=b_avail,
            after_available=a_avail,
            before_reserved=b_res,
            after_reserved=a_res,
            before_sold=b_sold,
            after_sold=a_sold,
            reference=reference,
        )
        db.add(txn)

    # ── Public API ────────────────────────────────────────────────────────────

    async def reserve_items(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        items: list[
            dict
        ],  # [{"product_id": UUID, "variant_id": UUID|None, "quantity": int}]
    ) -> list[InventoryReservation]:
        """
        Reserve stock for each item. Called at checkout start.

        Uses SELECT FOR UPDATE so concurrent checkouts queue behind each other.
        Raises InventoryError if any item lacks sufficient available stock.
        Returns the created InventoryReservation rows (not yet committed).
        """
        expires_at = datetime.now(UTC) + timedelta(minutes=_RESERVATION_TTL_MINUTES)
        reservations: list[InventoryReservation] = []

        for item in items:
            product_id: uuid.UUID = item["product_id"]
            variant_id: uuid.UUID | None = item.get("variant_id")
            quantity: int = item["quantity"]

            stock = await self._lock_stock_target(db, product_id, variant_id)

            available = (
                stock["stock_quantity"]
                - stock["reserved_quantity"]
                - stock["sold_quantity"]
            )
            if not stock["allow_backorder"] and available < quantity:
                raise InventoryError(
                    f"Only {max(available, 0)} item(s) available for "
                    f"'{stock['item_name']}'. Please adjust your quantity."
                )

            await self._update_stock_target(
                db,
                stock,
                "reserved_quantity = reserved_quantity + :qty",
                {"qty": quantity},
            )

            # Create reservation record
            reservation = InventoryReservation(
                id=uuid.uuid4(),
                reservation_number=_generate_reservation_number(),
                user_id=user_id,
                order_id=None,  # linked to order after order creation
                product_id=product_id,
                variant_id=variant_id,
                quantity=quantity,
                status="ACTIVE",
                expires_at=expires_at,
            )
            db.add(reservation)
            await db.flush()  # get reservation.id without committing

            after_reserved = stock["reserved_quantity"] + quantity
            await self._log_transaction(
                db,
                product_id=product_id,
                variant_id=variant_id,
                reservation_id=reservation.id,
                order_id=None,
                transaction_type="RESERVE",
                quantity=quantity,
                before_stock=stock,
                after_reserved=after_reserved,
                after_sold=stock["sold_quantity"],
                reference=reservation.reservation_number,
            )
            await self._invalidate_inventory_cache(product_id, variant_id)

            reservations.append(reservation)
            log.info(
                "stock_reserved",
                product_id=str(product_id),
                quantity=quantity,
                available_before=available,
                reservation_number=reservation.reservation_number,
            )

        return reservations

    async def link_reservations_to_order(
        self,
        db: AsyncSession,
        reservations: list[InventoryReservation],
        order_id: uuid.UUID,
    ) -> None:
        """Attach order_id to reservations created before the order existed."""
        res_ids = [str(r.id) for r in reservations]
        if not res_ids:
            return
        placeholders = ", ".join(f":id_{i}" for i in range(len(res_ids)))
        params: dict = {"order_id": str(order_id)}
        for i, rid in enumerate(res_ids):
            params[f"id_{i}"] = rid
        await db.execute(
            text(
                f"UPDATE inventory_reservations "
                f"SET order_id = :order_id "
                f"WHERE id IN ({placeholders})"
            ),
            params,
        )
        # Also update transaction log rows
        await db.execute(
            text(
                f"UPDATE inventory_transactions "
                f"SET order_id = :order_id "
                f"WHERE reservation_id IN ({placeholders})"
            ),
            params,
        )

    async def complete_order_reservations(
        self, db: AsyncSession, order_id: uuid.UUID
    ) -> None:
        """
        Called after payment verification. Converts ACTIVE reservations to COMPLETED.
        Moves quantity from reserved_quantity → sold_quantity.
        Idempotent: already-COMPLETED reservations are silently skipped.
        """
        result = await db.execute(
            text(
                "SELECT id, product_id, variant_id, quantity "
                "FROM inventory_reservations "
                "WHERE order_id = :oid AND status = 'ACTIVE' "
                "FOR UPDATE"
            ),
            {"oid": str(order_id)},
        )
        rows = result.fetchall()

        if not rows:
            # Check if already completed (idempotency)
            check = await db.execute(
                text(
                    "SELECT COUNT(*) FROM inventory_reservations "
                    "WHERE order_id = :oid AND status = 'COMPLETED'"
                ),
                {"oid": str(order_id)},
            )
            if check.scalar_one() > 0:
                log.info("reservation_already_completed", order_id=str(order_id))
                return
            # No reservations at all — unusual but handled
            log.warning("no_active_reservation_for_order", order_id=str(order_id))
            return

        for row in rows:
            res_id: uuid.UUID = row[0]
            product_id: uuid.UUID = row[1]
            variant_id: uuid.UUID | None = row[2]
            quantity: int = row[3]

            # Lock and read current product state
            try:
                stock = await self._lock_stock_target(db, product_id, variant_id)
            except NotFoundError:
                log.error(
                    "inventory_target_missing_during_complete",
                    product_id=str(product_id),
                    variant_id=str(variant_id) if variant_id else None,
                )
                continue

            # Move from reserved → sold
            await self._update_stock_target(
                db,
                stock,
                "reserved_quantity = GREATEST(reserved_quantity - :qty, 0), "
                "sold_quantity = sold_quantity + :qty",
                {"qty": quantity},
            )

            await db.execute(
                text(
                    "UPDATE inventory_reservations "
                    "SET status = 'COMPLETED', updated_at = now() "
                    "WHERE id = :rid"
                ),
                {"rid": str(res_id)},
            )

            after_reserved = max(stock["reserved_quantity"] - quantity, 0)
            after_sold = stock["sold_quantity"] + quantity
            await self._log_transaction(
                db,
                product_id=product_id,
                variant_id=variant_id,
                reservation_id=res_id,
                order_id=order_id,
                transaction_type="SALE",
                quantity=quantity,
                before_stock=stock,
                after_reserved=after_reserved,
                after_sold=after_sold,
                reference=str(order_id),
            )
            await self._invalidate_inventory_cache(product_id, variant_id)

            log.info(
                "reservation_completed",
                reservation_id=str(res_id),
                product_id=str(product_id),
                quantity=quantity,
                order_id=str(order_id),
            )

    async def release_order_reservations(
        self,
        db: AsyncSession,
        order_id: uuid.UUID,
        reason: str = "RELEASED",
    ) -> None:
        """
        Called on payment failure / cancellation.
        Releases ACTIVE reservations → frees stock back to available.
        reason must be 'RELEASED' or 'EXPIRED'.
        """
        result = await db.execute(
            text(
                "SELECT id, product_id, variant_id, quantity "
                "FROM inventory_reservations "
                "WHERE order_id = :oid AND status = 'ACTIVE' "
                "FOR UPDATE"
            ),
            {"oid": str(order_id)},
        )
        rows = result.fetchall()

        if not rows:
            log.info(
                "no_active_reservations_to_release",
                order_id=str(order_id),
                reason=reason,
            )
            return

        for row in rows:
            res_id: uuid.UUID = row[0]
            product_id: uuid.UUID = row[1]
            variant_id: uuid.UUID | None = row[2]
            quantity: int = row[3]

            try:
                stock = await self._lock_stock_target(db, product_id, variant_id)
            except NotFoundError:
                continue

            await self._update_stock_target(
                db,
                stock,
                "reserved_quantity = GREATEST(reserved_quantity - :qty, 0)",
                {"qty": quantity},
            )

            await db.execute(
                text(
                    "UPDATE inventory_reservations "
                    f"SET status = '{reason}', updated_at = now() "
                    "WHERE id = :rid"
                ),
                {"rid": str(res_id)},
            )

            after_reserved = max(stock["reserved_quantity"] - quantity, 0)
            await self._log_transaction(
                db,
                product_id=product_id,
                variant_id=variant_id,
                reservation_id=res_id,
                order_id=order_id,
                transaction_type="RELEASE",
                quantity=quantity,
                before_stock=stock,
                after_reserved=after_reserved,
                after_sold=stock["sold_quantity"],
                reference=reason,
            )
            await self._invalidate_inventory_cache(product_id, variant_id)

            log.info(
                "reservation_released",
                reservation_id=str(res_id),
                product_id=str(product_id),
                quantity=quantity,
                reason=reason,
            )

    async def expire_stale_reservations(self, db: AsyncSession) -> int:
        """
        Called by the reservation_expiry background worker every minute.
        Finds all ACTIVE reservations past their expires_at and transitions them
        to EXPIRED, freeing reserved_quantity back to available.
        Returns the number of reservations expired.
        """
        # Identify expired reservations (no lock yet — just finding candidates)
        result = await db.execute(
            text(
                "SELECT id, product_id, variant_id, order_id, quantity "
                "FROM inventory_reservations "
                "WHERE status = 'ACTIVE' AND expires_at < now() "
                "LIMIT 500"
            )
        )
        candidates = result.fetchall()
        if not candidates:
            return 0

        expired_count = 0
        for row in candidates:
            res_id: uuid.UUID = row[0]
            product_id: uuid.UUID = row[1]
            variant_id: uuid.UUID | None = row[2]
            order_id: uuid.UUID | None = row[3]
            quantity: int = row[4]

            # Re-lock this specific reservation row
            locked = await db.execute(
                text(
                    "SELECT status FROM inventory_reservations "
                    "WHERE id = :rid FOR UPDATE SKIP LOCKED"
                ),
                {"rid": str(res_id)},
            )
            locked_row = locked.fetchone()
            if not locked_row or locked_row[0] != "ACTIVE":
                # Already processed by another worker instance
                continue

            # Lock and read product
            try:
                stock = await self._lock_stock_target(db, product_id, variant_id)
            except NotFoundError:
                continue

            await self._update_stock_target(
                db,
                stock,
                "reserved_quantity = GREATEST(reserved_quantity - :qty, 0)",
                {"qty": quantity},
            )

            await db.execute(
                text(
                    "UPDATE inventory_reservations "
                    "SET status = 'EXPIRED', updated_at = now() "
                    "WHERE id = :rid"
                ),
                {"rid": str(res_id)},
            )

            if order_id:
                await db.execute(
                    text(
                        "UPDATE orders SET status = 'payment_expired', updated_at = now() "
                        "WHERE id = :oid "
                        "AND status NOT IN ('confirmed','cancelled','payment_expired')"
                    ),
                    {"oid": str(order_id)},
                )

            after_reserved = max(stock["reserved_quantity"] - quantity, 0)
            await self._log_transaction(
                db,
                product_id=product_id,
                variant_id=variant_id,
                reservation_id=res_id,
                order_id=order_id,
                transaction_type="RELEASE",
                quantity=quantity,
                before_stock=stock,
                after_reserved=after_reserved,
                after_sold=stock["sold_quantity"],
                reference="EXPIRED",
            )
            await self._invalidate_inventory_cache(product_id, variant_id)

            expired_count += 1
            log.info(
                "reservation_expired",
                reservation_id=str(res_id),
                product_id=str(product_id),
                quantity=quantity,
                order_id=str(order_id) if order_id else None,
            )

        return expired_count

    async def get_available_stock(self, db: AsyncSession, product_id: uuid.UUID) -> int:
        """Returns available = total - reserved - sold. No locking."""
        result = await db.execute(
            text(
                "SELECT stock_quantity - reserved_quantity - sold_quantity AS available "
                "FROM products WHERE id = :pid AND deleted_at IS NULL"
            ),
            {"pid": str(product_id)},
        )
        row = result.fetchone()
        if not row:
            raise NotFoundError(f"Product {product_id} not found")
        return max(int(row[0]), 0)

    async def record_restock(
        self,
        db: AsyncSession,
        *,
        product_id: uuid.UUID,
        variant_id: uuid.UUID | None,
        quantity: int,
        reference: str | None = None,
    ) -> None:
        """
        Admin restock: adds to stock_quantity (the warehouse total).
        Uses FOR UPDATE to prevent concurrent restock conflicts.
        """
        if quantity <= 0:
            raise ValidationError("Restock quantity must be positive")

        stock = await self._lock_stock_target(db, product_id, variant_id)
        new_stock = stock["stock_quantity"] + quantity

        await self._update_stock_target(
            db,
            stock,
            "stock_quantity = stock_quantity + :qty",
            {"qty": quantity},
        )

        await self._log_transaction(
            db,
            product_id=product_id,
            variant_id=variant_id,
            reservation_id=None,
            order_id=None,
            transaction_type="RESTOCK",
            quantity=quantity,
            before_stock=stock,
            after_reserved=stock["reserved_quantity"],
            after_sold=stock["sold_quantity"],
            after_stock_quantity=new_stock,
            reference=reference,
        )
        await self._invalidate_inventory_cache(product_id, variant_id)

    async def record_return(
        self,
        db: AsyncSession,
        *,
        product_id: uuid.UUID,
        variant_id: uuid.UUID | None,
        quantity: int,
        order_id: uuid.UUID | None = None,
        reference: str | None = None,
    ) -> None:
        """Return: decrements sold_quantity so the items become available again."""
        if quantity <= 0:
            raise ValidationError("Return quantity must be positive")

        stock = await self._lock_stock_target(db, product_id, variant_id)
        new_sold = max(stock["sold_quantity"] - quantity, 0)

        await self._update_stock_target(
            db,
            stock,
            "sold_quantity = :new_sold",
            {"new_sold": new_sold},
        )

        await self._log_transaction(
            db,
            product_id=product_id,
            variant_id=variant_id,
            reservation_id=None,
            order_id=order_id,
            transaction_type="RETURN",
            quantity=quantity,
            before_stock=stock,
            after_reserved=stock["reserved_quantity"],
            after_sold=new_sold,
            reference=reference,
        )
        await self._invalidate_inventory_cache(product_id, variant_id)

    async def record_adjustment(
        self,
        db: AsyncSession,
        *,
        product_id: uuid.UUID,
        variant_id: uuid.UUID | None,
        delta: int,
        reference: str | None = None,
    ) -> int:
        """Admin correction: applies a signed delta to stock_quantity."""
        if delta == 0:
            raise ValidationError("Adjustment delta must be non-zero")

        stock = await self._lock_stock_target(db, product_id, variant_id)
        new_stock = stock["stock_quantity"] + delta
        if new_stock < 0:
            raise ValidationError("Insufficient stock")
        if new_stock < stock["reserved_quantity"] + stock["sold_quantity"]:
            raise ValidationError("Adjustment would make available stock negative")

        await self._update_stock_target(
            db,
            stock,
            "stock_quantity = :new_stock",
            {"new_stock": new_stock},
        )
        await self._log_transaction(
            db,
            product_id=product_id,
            variant_id=variant_id,
            reservation_id=None,
            order_id=None,
            transaction_type="ADJUSTMENT",
            quantity=abs(delta),
            before_stock=stock,
            after_reserved=stock["reserved_quantity"],
            after_sold=stock["sold_quantity"],
            after_stock_quantity=new_stock,
            reference=reference,
        )
        await self._invalidate_inventory_cache(product_id, variant_id)
        return int(new_stock)

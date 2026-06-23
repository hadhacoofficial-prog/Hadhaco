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

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InventoryError, NotFoundError, ValidationError
from app.modules.inventory.models import InventoryReservation, InventoryTransaction

log = structlog.get_logger(__name__)

_RESERVATION_TTL_MINUTES = 10


def _generate_reservation_number() -> str:
    suffix = uuid.uuid4().hex[:8].upper()
    return f"RES-{suffix}"


class ReservationService:
    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _lock_product(self, db: AsyncSession, product_id: uuid.UUID) -> dict:
        """Lock the product row for the duration of the current transaction."""
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
        return dict(row._mapping)

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
        reference: str | None = None,
    ) -> None:
        total = before_stock["stock_quantity"]
        b_res = before_stock["reserved_quantity"]
        b_sold = before_stock["sold_quantity"]
        b_avail = total - b_res - b_sold

        a_res = after_reserved
        a_sold = after_sold
        a_avail = total - a_res - a_sold

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

            # Acquire row-level lock
            prod = await self._lock_product(db, product_id)

            available = (
                prod["stock_quantity"]
                - prod["reserved_quantity"]
                - prod["sold_quantity"]
            )
            if not prod["allow_backorder"] and available < quantity:
                raise InventoryError(
                    f"Only {max(available, 0)} item(s) available for "
                    f"'{prod['name']}'. Please adjust your quantity."
                )

            # Increment reserved_quantity
            await db.execute(
                text(
                    "UPDATE products "
                    "SET reserved_quantity = reserved_quantity + :qty "
                    "WHERE id = :pid"
                ),
                {"qty": quantity, "pid": str(product_id)},
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

            after_reserved = prod["reserved_quantity"] + quantity
            await self._log_transaction(
                db,
                product_id=product_id,
                variant_id=variant_id,
                reservation_id=reservation.id,
                order_id=None,
                transaction_type="RESERVE",
                quantity=quantity,
                before_stock=prod,
                after_reserved=after_reserved,
                after_sold=prod["sold_quantity"],
                reference=reservation.reservation_number,
            )

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
            prod_result = await db.execute(
                text(
                    "SELECT stock_quantity, reserved_quantity, sold_quantity "
                    "FROM products WHERE id = :pid FOR UPDATE"
                ),
                {"pid": str(product_id)},
            )
            prod_row = prod_result.fetchone()
            if not prod_row:
                log.error("product_missing_during_complete", product_id=str(product_id))
                continue

            prod = dict(prod_row._mapping)

            # Move from reserved → sold
            await db.execute(
                text(
                    "UPDATE products "
                    "SET reserved_quantity = GREATEST(reserved_quantity - :qty, 0), "
                    "    sold_quantity = sold_quantity + :qty "
                    "WHERE id = :pid"
                ),
                {"qty": quantity, "pid": str(product_id)},
            )

            await db.execute(
                text(
                    "UPDATE inventory_reservations "
                    "SET status = 'COMPLETED', updated_at = now() "
                    "WHERE id = :rid"
                ),
                {"rid": str(res_id)},
            )

            after_reserved = max(prod["reserved_quantity"] - quantity, 0)
            after_sold = prod["sold_quantity"] + quantity
            await self._log_transaction(
                db,
                product_id=product_id,
                variant_id=variant_id,
                reservation_id=res_id,
                order_id=order_id,
                transaction_type="SALE",
                quantity=quantity,
                before_stock=prod,
                after_reserved=after_reserved,
                after_sold=after_sold,
                reference=str(order_id),
            )

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

            prod_result = await db.execute(
                text(
                    "SELECT stock_quantity, reserved_quantity, sold_quantity "
                    "FROM products WHERE id = :pid FOR UPDATE"
                ),
                {"pid": str(product_id)},
            )
            prod_row = prod_result.fetchone()
            if not prod_row:
                continue

            prod = dict(prod_row._mapping)

            await db.execute(
                text(
                    "UPDATE products "
                    "SET reserved_quantity = GREATEST(reserved_quantity - :qty, 0) "
                    "WHERE id = :pid"
                ),
                {"qty": quantity, "pid": str(product_id)},
            )

            await db.execute(
                text(
                    "UPDATE inventory_reservations "
                    f"SET status = '{reason}', updated_at = now() "
                    "WHERE id = :rid"
                ),
                {"rid": str(res_id)},
            )

            after_reserved = max(prod["reserved_quantity"] - quantity, 0)
            await self._log_transaction(
                db,
                product_id=product_id,
                variant_id=variant_id,
                reservation_id=res_id,
                order_id=order_id,
                transaction_type="RELEASE",
                quantity=quantity,
                before_stock=prod,
                after_reserved=after_reserved,
                after_sold=prod["sold_quantity"],
                reference=reason,
            )

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
            prod_result = await db.execute(
                text(
                    "SELECT stock_quantity, reserved_quantity, sold_quantity "
                    "FROM products WHERE id = :pid FOR UPDATE"
                ),
                {"pid": str(product_id)},
            )
            prod_row = prod_result.fetchone()
            if not prod_row:
                continue

            prod = dict(prod_row._mapping)

            await db.execute(
                text(
                    "UPDATE products "
                    "SET reserved_quantity = GREATEST(reserved_quantity - :qty, 0) "
                    "WHERE id = :pid"
                ),
                {"qty": quantity, "pid": str(product_id)},
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

            after_reserved = max(prod["reserved_quantity"] - quantity, 0)
            await self._log_transaction(
                db,
                product_id=product_id,
                variant_id=variant_id,
                reservation_id=res_id,
                order_id=order_id,
                transaction_type="RELEASE",
                quantity=quantity,
                before_stock=prod,
                after_reserved=after_reserved,
                after_sold=prod["sold_quantity"],
                reference="EXPIRED",
            )

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

        prod_result = await db.execute(
            text(
                "SELECT stock_quantity, reserved_quantity, sold_quantity "
                "FROM products WHERE id = :pid AND deleted_at IS NULL FOR UPDATE"
            ),
            {"pid": str(product_id)},
        )
        prod_row = prod_result.fetchone()
        if not prod_row:
            raise NotFoundError(f"Product {product_id} not found")

        prod = dict(prod_row._mapping)

        await db.execute(
            text(
                "UPDATE products SET stock_quantity = stock_quantity + :qty WHERE id = :pid"
            ),
            {"qty": quantity, "pid": str(product_id)},
        )

        await self._log_transaction(
            db,
            product_id=product_id,
            variant_id=variant_id,
            reservation_id=None,
            order_id=None,
            transaction_type="RESTOCK",
            quantity=quantity,
            before_stock=prod,
            after_reserved=prod["reserved_quantity"],
            after_sold=prod["sold_quantity"],
            reference=reference,
        )

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

        prod_result = await db.execute(
            text(
                "SELECT stock_quantity, reserved_quantity, sold_quantity "
                "FROM products WHERE id = :pid AND deleted_at IS NULL FOR UPDATE"
            ),
            {"pid": str(product_id)},
        )
        prod_row = prod_result.fetchone()
        if not prod_row:
            raise NotFoundError(f"Product {product_id} not found")

        prod = dict(prod_row._mapping)
        new_sold = max(prod["sold_quantity"] - quantity, 0)

        await db.execute(
            text("UPDATE products SET sold_quantity = :new_sold WHERE id = :pid"),
            {"new_sold": new_sold, "pid": str(product_id)},
        )

        await self._log_transaction(
            db,
            product_id=product_id,
            variant_id=variant_id,
            reservation_id=None,
            order_id=order_id,
            transaction_type="RETURN",
            quantity=quantity,
            before_stock=prod,
            after_reserved=prod["reserved_quantity"],
            after_sold=new_sold,
            reference=reference,
        )

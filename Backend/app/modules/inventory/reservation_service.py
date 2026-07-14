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
from typing import Any, cast

import structlog
from sqlalchemy import text
from sqlalchemy.engine import CursorResult
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
        self, targets: list[tuple[uuid.UUID, uuid.UUID | None]]
    ) -> None:
        """Best-effort cache-aside invalidation for all inventory-derived views.

        Call once per checkout/batch operation (with every affected
        product/variant collected up front) rather than once per line item —
        the pattern-based scan below is shared across the whole batch instead
        of being repeated per item. Uses SCAN (via scan_iter), not the
        blocking KEYS command, so it never stalls the Redis server even on a
        large keyspace.
        """
        if not redis_available() or not targets:
            return
        redis = get_redis_pool()
        direct_keys = {"featured_products", "cms:homepage"}
        for product_id, variant_id in targets:
            direct_keys.add(f"product:{product_id}")
            direct_keys.add(f"product_details:{product_id}")
            if variant_id:
                direct_keys.add(f"variant:{variant_id}")

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

        async def _collect_pattern_keys() -> list[str]:
            collected: list[str] = []
            for pattern in patterns:
                async for key in redis.scan_iter(match=pattern, count=500):
                    collected.append(str(key))
            return collected

        try:
            await safe_redis_delete(redis, *direct_keys)
            pattern_keys = await asyncio.wait_for(_collect_pattern_keys(), timeout=1.0)
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
                f"UPDATE {stock['table_name']} "  # nosec B608
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

        If the user already has an ACTIVE reservation for the same product/variant,
        the existing reservation is reused (expiry extended) instead of creating
        a duplicate.  This prevents the self-blocking scenario where a customer's
        own reservation counts against them on retry.

        Returns the InventoryReservation rows (new or reused, not yet committed).
        """
        expires_at = datetime.now(UTC) + timedelta(minutes=_RESERVATION_TTL_MINUTES)
        reservations: list[InventoryReservation] = []
        cache_targets: list[tuple[uuid.UUID, uuid.UUID | None]] = []

        # Fetch existing ACTIVE reservations for this user up-front so we can
        # match them inside the lock without extra queries per item.
        existing_reservations = await self.get_user_active_reservations(db, user_id)
        # Key by (product_id, variant_id) for O(1) lookup.
        # None variant_id is stored as a sentinel to distinguish "no variant"
        # from "any variant".
        existing_by_key: dict[tuple[str, str | None], dict[str, Any]] = {}
        for er in existing_reservations:
            key = (
                str(er["product_id"]),
                str(er["variant_id"]) if er["variant_id"] else None,
            )
            existing_by_key[key] = er

        # Lock rows in a fixed (product_id, variant_id) order, not
        # cart-iteration order — two checkouts sharing 2+ products in
        # reversed order would otherwise deadlock (Postgres detects and
        # aborts one side after ~1s, surfacing as a checkout 500).
        items = sorted(
            items, key=lambda i: (str(i["product_id"]), str(i.get("variant_id") or ""))
        )

        for item in items:
            product_id: uuid.UUID = item["product_id"]
            variant_id: uuid.UUID | None = item.get("variant_id")
            quantity: int = item["quantity"]

            # ── Check for existing ACTIVE reservation ────────────────────────
            lookup_key = (str(product_id), str(variant_id) if variant_id else None)
            existing = existing_by_key.get(lookup_key)

            if existing:
                # Reuse: extend expiry, don't double-count reserved_quantity.
                new_expires = expires_at.isoformat()
                await db.execute(
                    text(
                        "UPDATE inventory_reservations "
                        "SET expires_at = :expires, updated_at = now() "
                        "WHERE id = :rid AND status = 'ACTIVE'"
                    ),
                    {"expires": new_expires, "rid": str(existing["id"])},
                )
                await db.flush()

                # Build a lightweight ORM-like object so callers see a
                # consistent return type.
                reservation = InventoryReservation(
                    id=existing["id"],
                    reservation_number=existing["reservation_number"],
                    user_id=user_id,
                    order_id=existing.get("order_id"),
                    product_id=product_id,
                    variant_id=variant_id,
                    quantity=existing["quantity"],
                    status="ACTIVE",
                    expires_at=expires_at,
                )
                reservations.append(reservation)
                log.info(
                    "reservation_reused",
                    reservation_number=existing["reservation_number"],
                    product_id=str(product_id),
                    quantity=existing["quantity"],
                    user_id=str(user_id),
                )
                continue

            # ── New reservation: lock, validate, reserve ─────────────────────
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
            cache_targets.append((product_id, variant_id))

            reservations.append(reservation)
            log.info(
                "stock_reserved",
                product_id=str(product_id),
                quantity=quantity,
                available_before=available,
                reservation_number=reservation.reservation_number,
            )

        await self._invalidate_inventory_cache(cache_targets)
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
                f"UPDATE inventory_reservations "  # nosec B608
                f"SET order_id = :order_id "
                f"WHERE id IN ({placeholders})"
            ),
            params,
        )
        # Also update transaction log rows
        await db.execute(
            text(
                f"UPDATE inventory_transactions "  # nosec B608
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

        cache_targets: list[tuple[uuid.UUID, uuid.UUID | None]] = []
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
            cache_targets.append((product_id, variant_id))

            log.info(
                "reservation_completed",
                reservation_id=str(res_id),
                product_id=str(product_id),
                quantity=quantity,
                order_id=str(order_id),
            )

        await self._invalidate_inventory_cache(cache_targets)

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

        cache_targets: list[tuple[uuid.UUID, uuid.UUID | None]] = []
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
                    "SET status = :status, updated_at = now() "
                    "WHERE id = :rid"
                ),
                {"rid": str(res_id), "status": reason},
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
            cache_targets.append((product_id, variant_id))

            log.info(
                "reservation_released",
                reservation_id=str(res_id),
                product_id=str(product_id),
                quantity=quantity,
                reason=reason,
            )

        await self._invalidate_inventory_cache(cache_targets)

    async def expire_stale_reservations(self, db: AsyncSession) -> list[uuid.UUID]:
        """Expire stale reservations and release reserved stock.

        Called by the reservation_expiry background worker every minute.
        Finds all ACTIVE reservations past their ``expires_at`` and transitions
        them to EXPIRED, freeing ``reserved_quantity`` back to available.

        Returns a list of order IDs that were transitioned to
        ``payment_expired`` so the caller can handle downstream side-effects
        (coupon restoration, notifications, etc.).

        Orders with ``payment_status='paid'`` are never transitioned — a late
        payment capture may still arrive for them.
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
            return []

        expired_count = 0
        cache_targets: list[tuple[uuid.UUID, uuid.UUID | None]] = []
        transitioned_order_ids: list[uuid.UUID] = []
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

            # Only transition orders that are NOT already paid and NOT in a
            # terminal state.  An order with payment_status='paid' may still
            # receive a late webhook — we must not mark it expired.
            if order_id:
                update_cursor = cast(
                    CursorResult,
                    await db.execute(
                        text(
                            "UPDATE orders SET status = 'payment_expired', "
                            "updated_at = now() "
                            "WHERE id = :oid "
                            "AND status NOT IN "
                            "('confirmed','cancelled','payment_expired',"
                            "'payment_failed') "
                            "AND payment_status != 'paid'"
                        ),
                        {"oid": str(order_id)},
                    ),
                )
                if update_cursor.rowcount > 0:
                    transitioned_order_ids.append(order_id)

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
            cache_targets.append((product_id, variant_id))

            expired_count += 1
            log.info(
                "reservation_expired",
                reservation_id=str(res_id),
                product_id=str(product_id),
                quantity=quantity,
                order_id=str(order_id) if order_id else None,
            )

        await self._invalidate_inventory_cache(cache_targets)

        return transitioned_order_ids

    async def complete_expired_order_reservations(
        self, db: AsyncSession, order_id: uuid.UUID
    ) -> None:
        """Handle late payment confirmations for orders whose reservations expired.

        When a reservation expires the reserved_quantity is released.  If a
        payment capture arrives later (Razorpay webhook or frontend verify),
        we still need to move sold_quantity.  This method finds EXPIRED or
        COMPLETED reservations for the order and, for any that are EXPIRED,
        directly increments sold_quantity to account for the stock that was
        already released.

        Idempotent: if all reservations are already COMPLETED, this is a no-op.
        """
        result = await db.execute(
            text(
                "SELECT id, product_id, variant_id, quantity, status "
                "FROM inventory_reservations "
                "WHERE order_id = :oid AND status IN ('EXPIRED', 'COMPLETED') "
                "FOR UPDATE"
            ),
            {"oid": str(order_id)},
        )
        rows = result.fetchall()

        if not rows:
            log.warning(
                "no_expired_reservations_for_late_payment",
                order_id=str(order_id),
            )
            return

        cache_targets: list[tuple[uuid.UUID, uuid.UUID | None]] = []
        for row in rows:
            res_id: uuid.UUID = row[0]
            product_id: uuid.UUID = row[1]
            variant_id: uuid.UUID | None = row[2]
            quantity: int = row[3]
            status: str = row[4]

            if status == "COMPLETED":
                # Already converted to sale — nothing to do.
                continue

            # status == "EXPIRED": reserved_quantity was already released by
            # the expiry worker.  We need to increment sold_quantity directly.
            try:
                stock = await self._lock_stock_target(db, product_id, variant_id)
            except NotFoundError:
                log.error(
                    "inventory_target_missing_during_late_payment",
                    product_id=str(product_id),
                    variant_id=str(variant_id) if variant_id else None,
                )
                continue

            await self._update_stock_target(
                db,
                stock,
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
                after_reserved=stock["reserved_quantity"],
                after_sold=after_sold,
                reference=f"late_payment:{order_id}",
            )
            cache_targets.append((product_id, variant_id))

            log.info(
                "expired_reservation_completed_late_payment",
                reservation_id=str(res_id),
                product_id=str(product_id),
                quantity=quantity,
                order_id=str(order_id),
            )

        await self._invalidate_inventory_cache(cache_targets)

    async def get_user_active_reservations(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        product_id: uuid.UUID | None = None,
        variant_id: uuid.UUID | None = None,
    ) -> list[dict[str, Any]]:
        """Return ACTIVE reservations for a user, optionally filtered by product/variant.

        Used by:
        - reserve_items() to detect and reuse existing reservations
        - The active-reservations endpoint to show customers what they have reserved
        """
        conditions = ["user_id = :uid", "status = 'ACTIVE'", "expires_at > now()"]
        params: dict[str, Any] = {"uid": str(user_id)}

        if product_id:
            conditions.append("product_id = :pid")
            params["pid"] = str(product_id)
        if variant_id:
            conditions.append("variant_id = :vid")
            params["vid"] = str(variant_id)
        elif variant_id is None and product_id:
            conditions.append("variant_id IS NULL")

        where = " AND ".join(conditions)
        result = await db.execute(
            text(
                f"SELECT id, reservation_number, product_id, variant_id, "
                f"quantity, expires_at, order_id "
                f"FROM inventory_reservations "
                f"WHERE {where}"  # nosec B608
            ),
            params,
        )
        return [dict(row._mapping) for row in result.fetchall()]

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
        await self._invalidate_inventory_cache([(product_id, variant_id)])

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
        await self._invalidate_inventory_cache([(product_id, variant_id)])

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
        await self._invalidate_inventory_cache([(product_id, variant_id)])
        return int(new_stock)

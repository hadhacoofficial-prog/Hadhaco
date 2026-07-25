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
from typing import Any, Literal, cast

import structlog
from sqlalchemy import text
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import PREFIX_PRODUCT_DETAIL
from app.core.config import settings
from app.core.exceptions import InventoryError, NotFoundError, ValidationError
from app.core.redis import (
    get_redis_pool,
    mark_redis_error,
    redis_available,
    safe_redis_delete,
)
from app.modules.inventory.metrics import (
    checkout_completed_total,
    checkout_failed_total,
    checkout_started_total,
    inventory_adjustments_total,
    oversell_prevented_total,
    reservation_created_total,
    reservation_expired_total,
    reservation_released_total,
)
from app.modules.inventory.models import InventoryReservation, InventoryTransaction

log = structlog.get_logger(__name__)

_RESERVATION_TTL_MINUTES = 2

# Reservations in these statuses are "live" — they hold stock.
# Used in every raw-SQL status filter across the inventory, cart, catalog,
# and orders domains.  Tuples format as ('A','B') which is valid SQL IN ().
ACTIVE_OR_CHECKOUT_STATUSES: tuple[str, ...] = ("ACTIVE", "CHECKOUT_IN_PROGRESS")


def _generate_reservation_number() -> str:
    suffix = uuid.uuid4().hex[:8].upper()
    return f"RES-{suffix}"


def _compute_available(
    stock: dict[str, Any], after_reserved: int, after_sold: int
) -> int:
    """available = total - reserved - sold, using the row already read/locked
    by the caller plus the reserved/sold values it's about to write —
    avoids a redundant read query just to learn the same number back."""
    return max(stock["stock_quantity"] - after_reserved - after_sold, 0)


async def invalidate_inventory_cache(
    targets: list[tuple[uuid.UUID, uuid.UUID | None]],
) -> None:
    """Best-effort Redis cache invalidation for inventory-derived views.

    Extracted as a standalone async function so callers that don't own a
    ``ReservationService`` instance (e.g. ``InventoryService.record_movement``)
    can still invalidate the same set of cache keys after publishing an
    ``InventoryChangedEvent``.

    For the full SSE + cache pipeline, prefer ``ReservationService._invalidate_inventory_cache``
    which calls this function internally after publishing the event.
    """
    if not targets:
        return
    if not redis_available():
        return
    redis = get_redis_pool()
    direct_keys: set[str] = {"featured_products", "cms:homepage"}
    for product_id, variant_id in targets:
        direct_keys.add(f"product:{product_id}")
        direct_keys.add(f"product_details:{product_id}")
        if variant_id:
            direct_keys.add(f"variant:{variant_id}")

    patterns = [
        "products:list:v1:*",
        "product:list:*",
        f"{PREFIX_PRODUCT_DETAIL}:*",
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
        self,
        db: AsyncSession,
        targets: list[tuple[uuid.UUID, uuid.UUID | None]],
        available_by_product: dict[str, int] | None = None,
    ) -> dict[str, int]:
        """Best-effort cache-aside invalidation for all inventory-derived views.

        Call once per checkout/batch operation (with every affected
        product/variant collected up front) rather than once per line item —
        the pattern-based scan below is shared across the whole batch instead
        of being repeated per item. Uses SCAN (via scan_iter), not the
        blocking KEYS command, so it never stalls the Redis server even on a
        large keyspace.

        Additionally publishes InventoryChangedEvent via the event bus so that
        SSE subscribers (frontend SyncBus) receive real-time notifications.
        This is the **single canonical pipeline** for all inventory mutations:
        every method that modifies stock state calls this method, which
        guarantees both cache invalidation AND SSE broadcasting.

        ``available_by_product`` should be the {product_id: available_stock}
        the caller already knows from the row it just locked and updated —
        every call site has this for free from its own before/after
        arithmetic, so passing it here avoids a redundant read query. Callers
        that genuinely don't have it (none currently) can omit it and pay for
        one extra read per product instead.

        Returns the {product_id: available_stock} used for the event, so
        callers publishing a follow-up event (e.g. ReservationCreatedEvent)
        can attach the same numbers, and so subscribers can update their UI
        straight from the event payload instead of round-tripping back to a
        REST endpoint to learn the new number.
        """
        if not targets:
            return {}

        product_ids = list({str(pid) for pid, _ in targets})

        if available_by_product is None:
            # Fallback for a caller that hasn't computed it — one extra
            # read per product, no locking (see get_available_stock).
            available_by_product = {}
            for pid in product_ids:
                try:
                    available_by_product[pid] = await self.get_available_stock(
                        db, uuid.UUID(pid)
                    )
                except NotFoundError:
                    continue

        # ── Publish SSE event (always, even if Redis cache is down) ──────────
        try:
            from app.core.events import InventoryChangedEvent, event_bus

            await event_bus.publish(
                InventoryChangedEvent(
                    product_ids=product_ids,
                    available_by_product=available_by_product,
                )
            )
        except Exception as exc:
            log.error("inventory_event_publish_failed", error=str(exc))

        # ── Invalidate Redis cache (best-effort) ────────────────────────────
        await invalidate_inventory_cache(targets)

        return available_by_product

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
        performed_by: uuid.UUID | None = None,
        request_id: str | None = None,
        adjustment_mode: str | None = None,
        reason: str | None = None,
        notes: str | None = None,
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
            performed_by=performed_by,
            request_id=request_id,
            adjustment_mode=adjustment_mode,
            reason=reason,
            notes=notes,
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
        available_by_product: dict[str, int] = {}

        # Fetch existing ACTIVE reservations for this user up-front so we can
        # match them inside the lock without extra queries per item.
        existing_reservations = await self.get_user_active_reservations(db, user_id)
        # Key by (product_id, variant_id) for O(1) lookup.
        # None variant_id is stored as a sentinel to distinguish "no variant"
        # from "any variant".
        existing_by_key: dict[tuple[str, str | None], dict[str, Any]] = {}
        for er in existing_reservations:
            # Only reuse unlinked (free) reservations.  Reservations already
            # linked to an order are owned by that order and must never be
            # modified — adjusting them would desynchronise the original
            # order's stock accounting.
            if er.get("order_id") is not None:
                continue
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
                # Reuse unlinked reservation with delta-based reconciliation.
                # Adjust reserved_quantity by the delta between the old and new
                # quantities so the stock counters always match the reservation.
                old_qty: int = existing["quantity"]
                delta: int = quantity - old_qty

                if delta > 0:
                    # Need more stock — lock and validate availability.
                    stock = await self._lock_stock_target(db, product_id, variant_id)
                    available = (
                        stock["stock_quantity"]
                        - stock["reserved_quantity"]
                        - stock["sold_quantity"]
                    )
                    if not stock["allow_backorder"] and available < delta:
                        oversell_prevented_total.inc()
                        raise InventoryError(
                            f"Only {max(available, 0)} additional item(s) "
                            f"available for '{stock['item_name']}'. "
                            f"Please reduce your quantity."
                        )
                    await self._update_stock_target(
                        db,
                        stock,
                        "reserved_quantity = reserved_quantity + :qty",
                        {"qty": delta},
                    )
                    after_reserved = stock["reserved_quantity"] + delta
                    available_by_product[str(product_id)] = _compute_available(
                        stock, after_reserved, stock["sold_quantity"]
                    )
                elif delta < 0:
                    # Releasing stock back — lock row and decrement.
                    stock = await self._lock_stock_target(db, product_id, variant_id)
                    await self._update_stock_target(
                        db,
                        stock,
                        "reserved_quantity = GREATEST(reserved_quantity - :qty, 0)",
                        {"qty": -delta},
                    )
                    after_reserved = max(stock["reserved_quantity"] + delta, 0)
                    available_by_product[str(product_id)] = _compute_available(
                        stock, after_reserved, stock["sold_quantity"]
                    )
                # delta == 0: no stock change needed.

                # Bind the datetime directly — this is raw asyncpg SQL, which
                # encodes a datetime as timestamptz. Passing expires_at.isoformat()
                # (a str) raises DataError: "expected a datetime, got 'str'".
                await db.execute(
                    text(
                        "UPDATE inventory_reservations "
                        "SET quantity = :qty, expires_at = :expires, "
                        "updated_at = now() "
                        "WHERE id = :rid AND status = 'ACTIVE'"
                    ),
                    {
                        "qty": quantity,
                        "expires": expires_at,
                        "rid": str(existing["id"]),
                    },
                )
                await db.flush()

                reservation = InventoryReservation(
                    id=existing["id"],
                    reservation_number=existing["reservation_number"],
                    user_id=user_id,
                    order_id=None,
                    product_id=product_id,
                    variant_id=variant_id,
                    quantity=quantity,
                    status="ACTIVE",
                    expires_at=expires_at,
                )
                reservations.append(reservation)
                log.info(
                    "reservation_reused",
                    reservation_number=existing["reservation_number"],
                    product_id=str(product_id),
                    old_quantity=old_qty,
                    new_quantity=quantity,
                    delta=delta,
                    user_id=str(user_id),
                )
                if delta != 0:
                    cache_targets.append((product_id, variant_id))
                continue

            # ── New reservation: lock, validate, reserve ─────────────────────
            stock = await self._lock_stock_target(db, product_id, variant_id)

            available = (
                stock["stock_quantity"]
                - stock["reserved_quantity"]
                - stock["sold_quantity"]
            )
            if not stock["allow_backorder"] and available < quantity:
                oversell_prevented_total.inc()
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
            available_by_product[str(product_id)] = _compute_available(
                stock, after_reserved, stock["sold_quantity"]
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

        available_by_product = await self._invalidate_inventory_cache(
            db, cache_targets, available_by_product
        )

        # Publish ReservationCreatedEvent so frontend shows reservation badges
        # and countdown timers. Only for genuinely new reservations (not reuses).
        new_reservations = [r for r in reservations if r.order_id is None]
        if new_reservations:
            reservation_created_total.inc(len(new_reservations))
            try:
                from app.core.events import ReservationCreatedEvent, event_bus

                await event_bus.publish(
                    ReservationCreatedEvent(
                        reservation_id=str(new_reservations[0].id),
                        user_id=str(user_id),
                        product_ids=[str(pid) for pid, _ in cache_targets],
                        available_by_product=available_by_product,
                    )
                )
            except Exception as exc:
                log.error("reservation_created_event_publish_failed", error=str(exc))

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

    async def lock_for_checkout(
        self, db: AsyncSession, order_id: uuid.UUID
    ) -> datetime:
        """
        Move an order's reservations from ACTIVE to CHECKOUT_IN_PROGRESS.

        Called from OrderService.create_payment_intent immediately after the
        Razorpay order is accepted (i.e. the customer is now actually on the
        payment gateway, not just browsing checkout). Resets expires_at to a
        fresh RESERVATION_CHECKOUT_GRACE_MINUTES window — independent of and
        longer than the 2-minute cart-hold TTL in _RESERVATION_TTL_MINUTES —
        so the reservation_expiry worker's short-TTL sweep does not release
        stock out from under a customer who is mid-payment. See the inventory
        domain plan §2.1a for why these are two separate timers.

        No row lock needed beyond the single-row UPDATE's own atomicity — the
        WHERE clause only matches ACTIVE rows, so this is a no-op (and safe
        to call, though it never should be) on a reservation that already
        moved to any other state.

        Does not publish InventoryChangedEvent: reserved_quantity/
        available_stock are unchanged by this transition, only status/
        expires_at — nothing for a listener to react to.

        Returns the new expires_at so the caller can hand it back to the
        frontend — without this, the checkout countdown UI has no way to
        learn that its hold just got extended past the original 2-minute
        cart TTL, and fires a false "reservation expired" at the 2-minute
        mark while the server is still actually holding the stock.
        """
        expires_at = datetime.now(UTC) + timedelta(
            minutes=settings.RESERVATION_CHECKOUT_GRACE_MINUTES
        )
        result = await db.execute(
            text(
                "UPDATE inventory_reservations "
                "SET status = 'CHECKOUT_IN_PROGRESS', expires_at = :expires, "
                "updated_at = now() "
                "WHERE order_id = :oid AND status = 'ACTIVE'"
            ),
            {"oid": str(order_id), "expires": expires_at},
        )
        cursor = cast(CursorResult, result)
        if cursor.rowcount > 0:
            checkout_started_total.inc(cursor.rowcount)
        log.info("checkout_locked", order_id=str(order_id))
        return expires_at

    async def complete_order_reservations(
        self, db: AsyncSession, order_id: uuid.UUID
    ) -> None:
        """
        Called after payment verification. Converts ACTIVE/CHECKOUT_IN_PROGRESS
        reservations to COMPLETED. Moves quantity from reserved_quantity → sold_quantity.
        Idempotent: already-COMPLETED reservations are silently skipped.
        """
        result = await db.execute(
            text(
                "SELECT id, product_id, variant_id, quantity "
                "FROM inventory_reservations "
                "WHERE order_id = :oid AND status IN :statuses "
                "FOR UPDATE"
            ),
            {"oid": str(order_id), "statuses": ACTIVE_OR_CHECKOUT_STATUSES},
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
        available_by_product: dict[str, int] = {}
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
            available_by_product[str(product_id)] = _compute_available(
                stock, after_reserved, after_sold
            )
            cache_targets.append((product_id, variant_id))

            log.info(
                "reservation_completed",
                reservation_id=str(res_id),
                product_id=str(product_id),
                quantity=quantity,
                order_id=str(order_id),
            )

        await self._invalidate_inventory_cache(db, cache_targets, available_by_product)

    async def complete_reservations_for_order(
        self, db: AsyncSession, order_id: uuid.UUID
    ) -> str:
        """Complete an order's reservations, applying the late-payment policy.

        Orchestrates the sequence shared by every payment-capture path
        (frontend verify and the Razorpay webhook):
          1. Complete any ACTIVE/CHECKOUT_IN_PROGRESS reservations (reserved -> sold).
          2. If reservations had already expired before payment was captured
             (stock was released by the expiry worker), do NOT re-acquire
             stock — inventory domain plan §2.2a, "Option A": a payment
             arriving after expiry is real captured money but the hold on
             inventory is gone, so we never fabricate stock to fulfil it.
             Returns "refund_required" so the caller (OrderService /
             webhooks.service) can record the payment, route the order to
             refund_pending, and trigger PaymentService.initiate_refund.

        Runs inside the caller's existing transaction — does not commit.

        Returns "fulfilled" if the order's reservations completed normally,
        "refund_required" if the reservation had already expired.
        """
        await self.complete_order_reservations(db, order_id)

        has_expired = await db.execute(
            text(
                "SELECT 1 FROM inventory_reservations "
                "WHERE order_id = :oid AND status = 'EXPIRED' LIMIT 1"
            ),
            {"oid": str(order_id)},
        )
        if has_expired.fetchone():
            return "refund_required"

        checkout_completed_total.inc()
        return "fulfilled"

    async def release_orphan_reservations(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        reason: str = "RELEASED",
    ) -> None:
        """Release ACTIVE reservations not linked to any order.

        Used by the IntegrityError recovery path in create_payment_intent
        when the order INSERT fails due to the partial unique index and the
        reservations were never linked to an order.
        """
        result = await db.execute(
            text(
                "SELECT id, product_id, variant_id, quantity "
                "FROM inventory_reservations "
                "WHERE user_id = :uid AND status = 'ACTIVE' AND order_id IS NULL "
                "FOR UPDATE"
            ),
            {"uid": str(user_id)},
        )
        rows = result.fetchall()
        if not rows:
            return

        cache_targets: list[tuple[uuid.UUID, uuid.UUID | None]] = []
        available_by_product: dict[str, int] = {}
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
                order_id=None,
                transaction_type="RELEASE",
                quantity=quantity,
                before_stock=stock,
                after_reserved=after_reserved,
                after_sold=stock["sold_quantity"],
                reference=reason,
            )
            cache_targets.append((product_id, variant_id))
            available_by_product[str(product_id)] = _compute_available(
                stock, after_reserved, stock["sold_quantity"]
            )

        await self._invalidate_inventory_cache(db, cache_targets, available_by_product)

    async def release_order_reservations(
        self,
        db: AsyncSession,
        order_id: uuid.UUID,
        reason: Literal[
            "RELEASED", "EXPIRED", "CANCELLED", "PAYMENT_FAILED"
        ] = "RELEASED",
    ) -> None:
        """
        Called on payment failure / cancellation.
        Releases ACTIVE/CHECKOUT_IN_PROGRESS reservations → frees stock back
        to available, writing `reason` directly as the reservation's new
        terminal status. Use CANCELLED for explicit user/admin cancellation,
        PAYMENT_FAILED for a payment-infrastructure failure (e.g. the
        Razorpay order-create call itself failing), RELEASED for system
        cleanup (orphan/duplicate-order recovery) that isn't attributable to
        either.
        """
        result = await db.execute(
            text(
                "SELECT id, product_id, variant_id, quantity "
                "FROM inventory_reservations "
                "WHERE order_id = :oid AND status IN :statuses "
                "FOR UPDATE"
            ),
            {"oid": str(order_id), "statuses": ACTIVE_OR_CHECKOUT_STATUSES},
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
        available_by_product: dict[str, int] = {}
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
            available_by_product[str(product_id)] = _compute_available(
                stock, after_reserved, stock["sold_quantity"]
            )

            log.info(
                "reservation_released",
                reservation_id=str(res_id),
                product_id=str(product_id),
                quantity=quantity,
                reason=reason,
            )

        reservation_released_total.labels(reason=reason).inc(len(rows))
        if reason in ("PAYMENT_FAILED", "CANCELLED"):
            checkout_failed_total.labels(reason=reason).inc(len(rows))

        await self._invalidate_inventory_cache(db, cache_targets, available_by_product)

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
                "SELECT id, product_id, variant_id, order_id, quantity, user_id "
                "FROM inventory_reservations "
                "WHERE status IN :statuses "
                "AND expires_at < now() "
                "LIMIT 500"
            ),
            {"statuses": ACTIVE_OR_CHECKOUT_STATUSES},
        )
        candidates = result.fetchall()
        if not candidates:
            return []

        expired_count = 0
        cache_targets: list[tuple[uuid.UUID, uuid.UUID | None]] = []
        available_by_product: dict[str, int] = {}
        transitioned_order_ids: list[uuid.UUID] = []
        expired_user_ids: set[uuid.UUID] = set()
        for row in candidates:
            res_id: uuid.UUID = row[0]
            product_id: uuid.UUID = row[1]
            variant_id: uuid.UUID | None = row[2]
            order_id: uuid.UUID | None = row[3]
            quantity: int = row[4]
            expired_user_ids.add(row[5])

            # Re-lock this specific reservation row
            locked = await db.execute(
                text(
                    "SELECT status FROM inventory_reservations "
                    "WHERE id = :rid FOR UPDATE SKIP LOCKED"
                ),
                {"rid": str(res_id)},
            )
            locked_row = locked.fetchone()
            if not locked_row or locked_row[0] not in (
                "ACTIVE",
                "CHECKOUT_IN_PROGRESS",
            ):
                # Already processed by another worker instance, or already
                # moved to a terminal state (COMPLETED/CANCELLED/etc.)
                continue
            was_checkout = locked_row[0] == "CHECKOUT_IN_PROGRESS"

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
            available_by_product[str(product_id)] = _compute_available(
                stock, after_reserved, stock["sold_quantity"]
            )

            expired_count += 1
            log.info(
                "reservation_expired",
                reservation_id=str(res_id),
                product_id=str(product_id),
                quantity=quantity,
                order_id=str(order_id) if order_id else None,
                was_checkout_in_progress=was_checkout,
            )
            reservation_expired_total.labels(
                was_checkout=str(was_checkout).lower()
            ).inc()

        # Commit before invalidating the cache / publishing SSE events.
        # A concurrent reader who refetches a product on the SSE signal
        # opens a fresh session under read-committed isolation -- if we
        # publish first, it can't see the reserved_quantity decrement
        # above yet, recomputes available_stock as still-reserved, and
        # re-populates the Redis cache with that stale value for the
        # full TTL. Committing first guarantees readers see the release.
        await db.commit()

        available_by_product = await self._invalidate_inventory_cache(
            db, cache_targets, available_by_product
        )

        try:
            from app.core.events import ReservationExpiredEvent, event_bus

            await event_bus.publish(
                ReservationExpiredEvent(
                    reservation_id="batch",
                    user_ids=[str(uid) for uid in expired_user_ids],
                    product_ids=[str(pid) for pid, _ in cache_targets],
                    available_by_product=available_by_product,
                )
            )
        except Exception as exc:
            log.error("reservation_expired_event_publish_failed", error=str(exc))

        return transitioned_order_ids

    async def complete_expired_order_reservations(
        self, db: AsyncSession, order_id: uuid.UUID
    ) -> None:
        """Manual/admin reconciliation only — NOT called automatically.

        Historically this was invoked from complete_reservations_for_order to
        silently re-acquire stock (directly incrementing sold_quantity) for a
        late payment on an EXPIRED reservation. That created an oversell
        vector: the released stock may already have been sold to someone
        else by the time the late payment arrives.

        Per the inventory domain plan §2.2a (Late Payment Policy, Option A),
        complete_reservations_for_order now returns "refund_required" instead
        of calling this method — a late payment against expired stock is
        refunded, never silently fulfilled from re-acquired capacity. This
        method is kept only as an explicit, admin-invoked escape hatch for a
        human who has manually verified enough stock genuinely exists to
        honor a specific late order (e.g. a restock happened to land at the
        right time) — it must never be wired back into the automatic
        payment-verification path.

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
        available_by_product: dict[str, int] = {}
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
            available_by_product[str(product_id)] = _compute_available(
                stock, stock["reserved_quantity"], after_sold
            )

            log.info(
                "expired_reservation_completed_late_payment",
                reservation_id=str(res_id),
                product_id=str(product_id),
                quantity=quantity,
                order_id=str(order_id),
            )

        await self._invalidate_inventory_cache(db, cache_targets, available_by_product)

    async def get_user_active_reservations(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        product_id: uuid.UUID | None = None,
        variant_id: uuid.UUID | None = None,
    ) -> list[dict[str, Any]]:
        """Return ACTIVE reservations for a user, optionally filtered by product/variant.

        Used by:
        - reserve_items() to detect and reuse existing reservations (only
          unlinked, order_id IS NULL rows are ever eligible for reuse — see
          the caller's own filter — and CHECKOUT_IN_PROGRESS rows always have
          order_id set, so widening this to include them doesn't change reuse
          behaviour, only fixes the "Reserved for You" badge disappearing the
          instant checkout starts)
        - The active-reservations endpoint to show customers what they have reserved
        """
        conditions = [
            "user_id = :uid",
            f"status IN {ACTIVE_OR_CHECKOUT_STATUSES}",  # nosec B608
            "expires_at > now()",
        ]
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

    async def get_available_stock(
        self,
        db: AsyncSession,
        product_id: uuid.UUID,
        variant_id: uuid.UUID | None = None,
    ) -> int:
        """Returns available = total - reserved - sold. No locking.

        With ``variant_id``, reads directly off that variant. Without one,
        replicates Product.available_stock's exact ORM semantics: sum
        active variants' available stock if any exist, else fall back to
        the product's own columns — so this and the ORM property can never
        disagree. Uses GREATEST(...) (mirrors compute_available_stock() in
        inventory/status.py) throughout.
        """
        if variant_id is not None:
            result = await db.execute(
                text(
                    "SELECT GREATEST(v.stock_quantity - v.reserved_quantity "
                    "- v.sold_quantity, 0) AS available "  # mirrors compute_available_stock()
                    "FROM product_variants v "
                    "JOIN products p ON p.id = v.product_id "
                    "WHERE v.id = :vid AND v.product_id = :pid "
                    "AND p.deleted_at IS NULL"
                ),
                {"vid": str(variant_id), "pid": str(product_id)},
            )
            row = result.fetchone()
            if not row:
                raise NotFoundError(
                    f"Variant {variant_id} not found for product {product_id}"
                )
            return max(int(row[0]), 0)

        result = await db.execute(
            text(
                "SELECT "
                "(SELECT SUM(GREATEST(v.stock_quantity - v.reserved_quantity "
                "- v.sold_quantity, 0)) "  # mirrors compute_available_stock(); NULL
                # when zero active variants exist, distinguishing that case from
                # "active variants summing to zero" so we know when to fall back.
                " FROM product_variants v "
                " WHERE v.product_id = p.id AND v.is_active = true) AS variant_sum, "
                "GREATEST(p.stock_quantity - p.reserved_quantity - p.sold_quantity, 0) "
                "AS own_available "  # mirrors compute_available_stock()
                "FROM products p WHERE p.id = :pid AND p.deleted_at IS NULL"
            ),
            {"pid": str(product_id)},
        )
        row = result.fetchone()
        if not row:
            raise NotFoundError(f"Product {product_id} not found")
        variant_sum, own_available = row[0], row[1]
        if variant_sum is not None:
            return max(int(variant_sum), 0)
        return max(int(own_available), 0)

    async def record_restock(
        self,
        db: AsyncSession,
        *,
        product_id: uuid.UUID,
        variant_id: uuid.UUID | None,
        quantity: int,
        reference: str | None = None,
        performed_by: uuid.UUID | None = None,
        request_id: str | None = None,
        reason: str | None = None,
        notes: str | None = None,
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
            performed_by=performed_by,
            request_id=request_id,
            reason=reason,
            notes=notes,
        )
        available = max(
            new_stock - stock["reserved_quantity"] - stock["sold_quantity"], 0
        )
        await self._invalidate_inventory_cache(
            db, [(product_id, variant_id)], {str(product_id): available}
        )
        inventory_adjustments_total.labels(type="RESTOCK").inc()

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
        available = _compute_available(stock, stock["reserved_quantity"], new_sold)
        await self._invalidate_inventory_cache(
            db, [(product_id, variant_id)], {str(product_id): available}
        )
        inventory_adjustments_total.labels(type="RETURN").inc()

    async def record_adjustment(
        self,
        db: AsyncSession,
        *,
        product_id: uuid.UUID,
        variant_id: uuid.UUID | None,
        delta: int | None = None,
        target_quantity: int | None = None,
        reference: str | None = None,
        performed_by: uuid.UUID | None = None,
        request_id: str | None = None,
        adjustment_mode: str | None = None,
        reason: str | None = None,
        notes: str | None = None,
    ) -> int:
        """Admin correction: applies a signed delta to stock_quantity.

        Exactly one of ``delta`` (relative add/remove) or ``target_quantity``
        (absolute "set to") must be supplied. For ``target_quantity``, the
        delta is computed from the value read *inside* the row lock acquired
        by ``_lock_stock_target`` below — never from a pre-lock read — so two
        concurrent "set to X" calls can't race each other.

        A delta that computes to zero (an admin re-confirming a count via
        "set" to the current value, or an explicit add/remove of 0) is a
        successful no-op: the stock row is still touched and an
        InventoryTransaction with quantity=0 is still written so a confirmed
        recount stays visible in the audit trail. Only genuinely invalid
        *results* (negative stock, or reserved+sold exceeding stock) raise.
        """
        if (delta is None) == (target_quantity is None):
            raise ValidationError(
                "Exactly one of delta or target_quantity must be provided"
            )

        stock = await self._lock_stock_target(db, product_id, variant_id)
        if target_quantity is not None:
            delta = target_quantity - stock["stock_quantity"]
        assert delta is not None  # narrowed by the exactly-one check above

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
            performed_by=performed_by,
            request_id=request_id,
            adjustment_mode=adjustment_mode,
            reason=reason,
            notes=notes,
        )
        available = max(
            new_stock - stock["reserved_quantity"] - stock["sold_quantity"], 0
        )
        await self._invalidate_inventory_cache(
            db, [(product_id, variant_id)], {str(product_id): available}
        )
        inventory_adjustments_total.labels(type="ADJUSTMENT").inc()
        return int(new_stock)

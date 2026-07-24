import asyncio
import hashlib
import hmac
import math
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.events import (
    OrderCreatedEvent,
    OrderStatusChangedEvent,
    PaymentCapturedEvent,
    event_bus,
)
from app.core.exceptions import InventoryError, NotFoundError, ValidationError
from app.core.security import get_razorpay_client
from app.modules.inventory.reservation_service import ReservationService
from app.modules.orders.repository import OrderRepository
from app.modules.orders.schemas import (
    CancelOrderRequest,
    CreatePaymentIntentRequest,
    CreatePaymentIntentResponse,
    OrderListItem,
    OrderListResponse,
    OrderResponse,
    SetComplimentaryGiftRequest,
    UpdateOrderStatusRequest,
    VerifyOrderPaymentRequest,
    VerifyOrderPaymentResponse,
)
from app.modules.settings.service import SettingsService

log = structlog.get_logger(__name__)

_repo = OrderRepository()
_reservation_svc = ReservationService()

_CANCELLABLE_STATUSES = {"pending", "stock_reserved", "confirmed"}
_FREE_SHIPPING_THRESHOLD = 999.0
_SHIPPING_CHARGE = 99.0


class OrderService:
    # ── Shared helpers ────────────────────────────────────────────────────────

    async def _resolve_line_items(
        self, db: AsyncSession, cart_items: list
    ) -> list[dict]:
        """Validate cart items against DB and compute per-item tax. No stock lock.

        Three batched queries (products, variants, primary images) instead of
        one round trip per cart line item. Kept as independent lookups rather
        than a single joined query so a product that appears in the cart both
        with and without a variant across different lines still resolves
        correctly for each line.
        """
        product_ids = [str(ci.product_id) for ci in cart_items]
        variant_ids = [str(ci.variant_id) for ci in cart_items if ci.variant_id]

        product_rows = await db.execute(
            text(
                "SELECT id, name, sku, base_price, tax_rate "
                "FROM products "
                "WHERE id = ANY(CAST(:pids AS uuid[])) "
                "  AND deleted_at IS NULL AND status = 'active'"
            ),
            {"pids": product_ids},
        )
        products_by_id = {r.id: r for r in product_rows.fetchall()}

        variants_by_id: dict = {}
        if variant_ids:
            variant_rows = await db.execute(
                text(
                    "SELECT id, name, price_adjustment "
                    "FROM product_variants WHERE id = ANY(CAST(:vids AS uuid[]))"
                ),
                {"vids": variant_ids},
            )
            variants_by_id = {r.id: r for r in variant_rows.fetchall()}

        image_rows = await db.execute(
            text(
                "SELECT DISTINCT ON (i.owner_id) i.owner_id AS product_id, iv.url "
                "FROM images i "
                "JOIN image_variants iv ON iv.image_id = i.id "
                "WHERE i.owner_type = 'product' "
                "  AND i.owner_id = ANY(CAST(:pids AS uuid[])) "
                "  AND i.deleted_at IS NULL "
                "  AND iv.variant_name = 'thumbnail' AND iv.breakpoint = 'desktop' "
                "  AND iv.status = 'ready' "
                "ORDER BY i.owner_id, i.is_primary DESC, i.sort_order ASC"
            ),
            {"pids": product_ids},
        )
        images_by_product = {r.product_id: r.url for r in image_rows.fetchall()}

        line_items = []
        for ci in cart_items:
            prod = products_by_id.get(ci.product_id)
            if not prod:
                raise ValidationError(f"Product {ci.product_id} is no longer available")
            variant = variants_by_id.get(ci.variant_id) if ci.variant_id else None

            price_adj = float(variant.price_adjustment) if variant else 0.0
            unit_price = float(prod.base_price) + price_adj
            tax_rate = float(prod.tax_rate)
            # unit_price is the listed, GST-inclusive price (what the customer
            # sees on the storefront) — tax is a component already contained
            # within it, not an additional charge. line_total therefore equals
            # the plain price × quantity; tax_amt is only extracted for GST
            # invoicing (CGST/SGST/IGST breakdown), never added on top.
            line_total = round(unit_price * ci.quantity, 2)
            tax_amt = round(line_total * tax_rate / (100 + tax_rate), 2)

            line_items.append(
                {
                    "id": uuid.uuid4(),
                    "product_id": ci.product_id,
                    "variant_id": ci.variant_id,
                    "product_name": prod.name,
                    "product_sku": prod.sku,
                    "variant_name": variant.name if variant else None,
                    "image_url": images_by_product.get(ci.product_id),
                    "unit_price": unit_price,
                    "quantity": ci.quantity,
                    "tax_rate": tax_rate,
                    "tax_amount": tax_amt,
                    "line_total": line_total,
                }
            )
        return line_items

    async def _find_matching_pending_order(
        self, db: AsyncSession, user_id: uuid.UUID, line_items: list[dict]
    ) -> Any:
        """Return an existing pending order whose items match *line_items* exactly.

        Checked before creating a new order to prevent duplicate pending
        orders from multi-tab or rapid-retry scenarios.  Returns ``None``
        if no matching order is found.

        Any other pending order found for the user is released here. The
        partial unique index idx_one_pending_order_per_user allows only one
        'stock_reserved'/'payment_pending' order per user regardless of its
        items, so a stale order left over from an abandoned attempt or a
        cart the user has since changed would otherwise make the insert in
        create_payment_intent fail with an IntegrityError.
        """
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from app.modules.orders.models import Order

        result = await db.execute(
            select(Order)
            .where(
                Order.user_id == user_id,
                Order.status.in_(["stock_reserved", "payment_pending"]),
            )
            .options(selectinload(Order.items))
            .order_by(Order.created_at.desc())
            .limit(5)
        )
        candidates = result.scalars().all()

        # Build a comparable set from the incoming line_items.
        incoming: dict[tuple[str, str | None], int] = {}
        for li in line_items:
            key = (
                str(li["product_id"]),
                str(li["variant_id"]) if li.get("variant_id") else None,
            )
            incoming[key] = incoming.get(key, 0) + li["quantity"]

        matched_order = None
        for order in candidates:
            existing: dict[tuple[str, str | None], int] = {}
            for oi in order.items:
                key = (
                    str(oi.product_id),
                    str(oi.variant_id) if oi.variant_id else None,
                )
                existing[key] = existing.get(key, 0) + oi.quantity
            if existing == incoming and matched_order is None:
                matched_order = order
                continue
            # Stale pending order for this user with a different set of
            # items — release it so it doesn't collide with the partial
            # unique index when the new order is inserted below.
            log.info(
                "stale_pending_order_released",
                stale_order_id=str(order.id),
                user_id=str(user_id),
            )
            await _repo.update(db, order.id, {"status": "payment_failed"})
            await _reservation_svc.release_order_reservations(
                db, order.id, reason="RELEASED"
            )

        return matched_order

    async def _compute_totals(
        self,
        db: AsyncSession,
        line_items: list[dict],
        coupon_code: str | None,
        user_id: uuid.UUID,
    ) -> tuple[float, float, float, float, uuid.UUID | None, str | None]:
        subtotal = round(sum(i["unit_price"] * i["quantity"] for i in line_items), 2)
        total_tax = round(sum(i["tax_amount"] for i in line_items), 2)
        shipping_charge = (
            0.0 if subtotal >= _FREE_SHIPPING_THRESHOLD else _SHIPPING_CHARGE
        )
        discount = 0.0
        coupon_id = None
        applied_coupon_code = None

        if coupon_code:
            from app.modules.coupons.service import CouponService

            coupon_svc = CouponService()
            discount, coupon_id, coupon_type = await coupon_svc.apply_and_reserve(
                db, coupon_code, subtotal, user_id
            )
            applied_coupon_code = coupon_code.upper()
            if coupon_type == "free_shipping":
                shipping_charge = 0.0
                discount = _SHIPPING_CHARGE

        return (
            subtotal,
            total_tax,
            shipping_charge,
            discount,
            coupon_id,
            applied_coupon_code,
        )

    async def _get_address(
        self, db: AsyncSession, address_id: uuid.UUID, user_id: uuid.UUID
    ) -> dict:
        from app.modules.addresses.repository import AddressRepository

        addr = await AddressRepository().get(db, address_id, user_id)
        if not addr:
            raise NotFoundError("Address not found")
        return {
            "full_name": addr.full_name,
            "phone": addr.phone,
            "alternate_phone": addr.alternate_phone,
            "line1": addr.line1,
            "line2": addr.line2,
            "landmark": addr.landmark,
            "city": addr.city,
            "state": addr.state,
            "postal_code": addr.postal_code,
            "country": addr.country,
        }

    def _build_address_data(self, prefix: str, addr: dict) -> dict:
        return {
            f"{prefix}_full_name": addr["full_name"],
            f"{prefix}_phone": addr.get("phone"),
            f"{prefix}_alternate_phone": addr.get("alternate_phone"),
            f"{prefix}_line1": addr["line1"],
            f"{prefix}_line2": addr.get("line2"),
            f"{prefix}_landmark": addr.get("landmark"),
            f"{prefix}_city": addr["city"],
            f"{prefix}_state": addr["state"],
            f"{prefix}_postal": addr["postal_code"],
            f"{prefix}_country": addr["country"],
        }

    # ── Razorpay flow — Phase 1: reserve stock + create pending order ─────────

    async def create_payment_intent(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        payload: CreatePaymentIntentRequest,
    ) -> CreatePaymentIntentResponse:
        """
        Razorpay checkout — Phase 1.

        1. Validate cart items against DB
        2. Acquire row-level locks (SELECT FOR UPDATE) and reserve stock
        3. Create the DB order in status=stock_reserved
        4. Link reservations to order
        5. Commit — releases the row locks from step 2 before the external call
        6. Create Razorpay order (no DB transaction open during this call)
        7. Attach razorpay_order_id, flip to status=payment_pending
        8. Return response to frontend

        Splitting the commit before the Razorpay HTTP call (T3) matters: without
        it, the FOR UPDATE locks acquired in step 2 are held for the full
        external round trip (hundreds of ms to seconds, or a timeout), blocking
        any other concurrent checkout or admin stock adjustment touching the
        same product — worst exactly during flash-sale-style contention on hot
        SKUs, and risking exhaustion of the project's small connection pool.

        Stock is held for exactly 10 minutes. If payment is not completed by then
        the reservation_expiry background worker releases the inventory automatically.

        Concurrency: a per-user advisory lock serialises concurrent checkout
        requests for the same user so the duplicate-order guard always sees
        committed state.  The lock is transaction-scoped (released on
        commit/rollback) so it does NOT block the later Razorpay HTTP call.
        """
        t0 = time.perf_counter()

        # ── Per-user advisory lock (serialises concurrent checkouts) ──────────
        # Ensures the duplicate-order guard below always reads committed state.
        # pg_advisory_xact_lock is released when the first transaction ends
        # (the db.commit() at line 388), well before the Razorpay HTTP call.
        _lock_key = user_id.int % (2**31)
        await db.execute(text("SELECT pg_advisory_xact_lock(:lk)"), {"lk": _lock_key})

        from app.modules.cart.repository import CartRepository

        cart_repo = CartRepository()
        cart = await cart_repo.get_for_user(db, user_id)
        if not cart or not cart.items:
            raise ValidationError("Cart is empty")

        addr = await self._get_address(db, payload.shipping_address_id, user_id)
        bill_addr = addr
        if payload.billing_address_id:
            bill_addr = await self._get_address(db, payload.billing_address_id, user_id)

        line_items = await self._resolve_line_items(db, cart.items)

        # ── Duplicate-order guard ─────────────────────────────────────────────
        # If the user already has a pending order covering the exact same
        # products and quantities, return that order's Razorpay details
        # instead of creating a duplicate.  Prevents orphan reservations
        # from multi-tab or rapid retry scenarios.
        existing_order = await self._find_matching_pending_order(
            db, user_id, line_items
        )
        if existing_order is not None:
            if existing_order.razorpay_order_id:
                log.info(
                    "duplicate_order_redirected",
                    existing_order_id=str(existing_order.id),
                    user_id=str(user_id),
                )
                amount_paise = int(round(float(existing_order.total) * 100))
                return CreatePaymentIntentResponse(
                    order_id=str(existing_order.id),
                    razorpay_order_id=existing_order.razorpay_order_id,
                    amount=amount_paise,
                    currency=settings.RAZORPAY_CURRENCY,
                    key=settings.RAZORPAY_KEY_ID,
                )
            # Order exists with matching items but no razorpay_order_id yet.
            # This means the Razorpay call for the first attempt is still in
            # progress (concurrent tab/device).  Tell the frontend to retry —
            # the first attempt will either succeed (and this request will be
            # redirected on the next call) or fail and be cleaned up by the
            # expiry worker.
            log.info(
                "duplicate_order_in_flight",
                existing_order_id=str(existing_order.id),
                user_id=str(user_id),
            )
            raise ValidationError(
                "A payment for this order is already being processed. "
                "Please wait a moment and try again."
            )

        # ── Atomic stock reservation with row-level locking ───────────────────
        reservation_items = [
            {
                "product_id": li["product_id"],
                "variant_id": li["variant_id"],
                "quantity": li["quantity"],
            }
            for li in line_items
        ]
        try:
            reservations = await _reservation_svc.reserve_items(
                db, user_id=user_id, items=reservation_items
            )
        except InventoryError:
            raise  # re-raise with the human-readable message from reservation_service

        subtotal, total_tax, shipping_charge, discount, coupon_id, coupon_code = (
            await self._compute_totals(db, line_items, payload.coupon_code, user_id)
        )
        # subtotal is already GST-inclusive (see _resolve_line_items) — total_tax
        # is only the informational tax component within it, not added again.
        total = round(max(subtotal + shipping_charge - discount, 0), 2)

        # ── Create DB order ───────────────────────────────────────────────────
        order_number = await _repo.generate_order_number(db)
        order_data = {
            "id": uuid.uuid4(),
            "order_number": order_number,
            "user_id": user_id,
            "status": "stock_reserved",
            "payment_status": "pending",
            **self._build_address_data("shipping", addr),
            **self._build_address_data("billing", bill_addr),
            "subtotal": subtotal,
            "tax_amount": total_tax,
            "shipping_charge": shipping_charge,
            "discount": discount,
            "total": total,
            "coupon_code": coupon_code,
            "coupon_id": coupon_id,
            "payment_method": "razorpay",
            "notes": payload.notes,
        }
        order = await _repo.create(db, order_data)

        for item_data in line_items:
            item_data["order_id"] = order.id
            await _repo.add_item(db, item_data)

        # Link all reservations to the new order
        await _reservation_svc.link_reservations_to_order(db, reservations, order.id)

        # Commit before the Razorpay HTTP call — releases the row locks
        # acquired by reserve_items instead of holding them for the full
        # external round trip. A new transaction opens implicitly on the
        # next statement (the release-on-failure path below, or the
        # razorpay_order_id update on success).
        await db.commit()

        # ── Create Razorpay order (offloaded to thread pool) ──────────────────
        amount_paise = int(round(total * 100))
        client = get_razorpay_client()
        rzp_payload = {
            "amount": amount_paise,
            "currency": settings.RAZORPAY_CURRENCY,
            "receipt": str(order.id),
            "notes": {"order_number": order_number},
        }
        try:
            rzp_order = await asyncio.get_running_loop().run_in_executor(
                None, lambda: client.order.create(rzp_payload)
            )
        except Exception as exc:
            log.error(
                "razorpay_order_create_failed", order_id=str(order.id), error=str(exc)
            )
            # Transition order to payment_failed BEFORE releasing stock so the
            # duplicate-order guard won't match this order on retry.  Without
            # this the orphan order stays in 'stock_reserved' and would either
            # match the guard (falling through without a razorpay_order_id) or
            # block the partial unique index from allowing a retry.
            await _repo.update(db, order.id, {"status": "payment_failed"})
            # Release stock if Razorpay call fails so customer isn't locked out.
            # Committed explicitly here — get_db's generic rollback on the
            # ValidationError raised below would otherwise undo the release,
            # leaving stock locked for the full 10-minute reservation TTL
            # after a failed checkout the customer was told to retry.
            await _reservation_svc.release_order_reservations(
                db, order.id, reason="RELEASED"
            )
            await db.commit()
            raise ValidationError(
                "Failed to create payment order. Please try again."
            ) from exc

        await _repo.update(
            db,
            order.id,
            {
                "razorpay_order_id": rzp_order["id"],
                "status": "payment_pending",
            },
        )

        duration_ms = round((time.perf_counter() - t0) * 1000)
        log.info(
            "checkout_reserved",
            order_id=str(order.id),
            order_number=order_number,
            items=len(line_items),
            total=total,
            duration_ms=duration_ms,
        )

        return CreatePaymentIntentResponse(
            order_id=str(order.id),
            razorpay_order_id=rzp_order["id"],
            amount=amount_paise,
            currency=settings.RAZORPAY_CURRENCY,
            key=settings.RAZORPAY_KEY_ID,
        )

    # ── Razorpay flow — Phase 2: verify payment + fulfill ────────────────────

    async def verify_and_fulfill(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        payload: VerifyOrderPaymentRequest,
    ) -> VerifyOrderPaymentResponse:
        """
        Razorpay checkout — Phase 2 (called from frontend after Razorpay modal closes).

        Sequence (order is critical):
          1. Load + ownership check
          2. Idempotency guard
          3. HMAC verification (no DB writes if signature bad)
          4. Complete reservations (reserved → sold, SELECT FOR UPDATE)
             - If reservations already expired (late payment), deduct stock directly
          5. Finalize coupon
          6. Clear cart
          7. Record payment
          8. Confirm order
          9. db.commit()
         10. Publish events

        The Razorpay webhook (_on_payment_captured) may fire before or after this
        call — both paths are idempotent via the reservation status check.
        """
        t0 = time.perf_counter()

        order = await _repo.get_by_id(db, payload.order_id)
        if not order or order.user_id != user_id:
            raise NotFoundError("Order not found")
        if order.status == "cancelled":
            raise ValidationError("This order has been cancelled.")

        # Idempotency: already fulfilled
        if order.payment_status == "paid":
            log.info(
                "payment_already_verified",
                order_id=str(order.id),
                order_number=order.order_number,
            )
            return VerifyOrderPaymentResponse(
                success=True,
                order_id=str(order.id),
                order_number=order.order_number,
            )

        # Allow late payments: if the order is in payment_expired status but
        # the HMAC is valid, we still process the payment.  The stock may
        # have been released by the expiry worker — complete_expired_order_reservations
        # will handle the deduction.

        # HMAC verification before any writes
        msg = f"{payload.razorpay_order_id}|{payload.razorpay_payment_id}"
        expected = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode(),
            msg.encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, payload.razorpay_signature):
            log.warning("payment_signature_invalid", order_id=str(order.id))
            raise ValidationError("Payment signature verification failed")

        log.info("payment_signature_verified", order_id=str(order.id))

        # Complete stock reservation (reserved → sold) with row-level locking,
        # falling back to the late-payment path if reservations had already
        # expired before this call. See ReservationService.
        await _reservation_svc.complete_reservations_for_order(db, order.id)

        # Finalize coupon
        if order.coupon_id:
            from app.modules.coupons.service import CouponService

            await CouponService().finalize_usage(db, order.coupon_id, user_id, order.id)

        # Clear cart
        from app.modules.cart.repository import CartRepository

        cart_repo = CartRepository()
        cart = await cart_repo.get_for_user(db, user_id)
        if cart:
            await cart_repo.clear_items(db, cart.id)

        # Record payment. Wrapped in a SAVEPOINT (begin_nested) rather than
        # a plain try/except: a duplicate razorpay_payment_id (frontend
        # retry racing the Razorpay webhook, both reaching this method
        # before either commits) raises IntegrityError against the unique
        # index on that column — the savepoint rolls back only this insert,
        # not the reservation-completion/coupon/cart work already done in
        # this same transaction.
        from app.modules.payments.repository import PaymentRepository

        now = datetime.now(UTC)
        try:
            async with db.begin_nested():
                await PaymentRepository().create(
                    db,
                    {
                        "id": uuid.uuid4(),
                        "order_id": order.id,
                        "user_id": user_id,
                        "razorpay_order_id": payload.razorpay_order_id,
                        "razorpay_payment_id": payload.razorpay_payment_id,
                        "razorpay_signature": payload.razorpay_signature,
                        "amount": float(order.total),
                        "currency": settings.RAZORPAY_CURRENCY,
                        "status": "captured",
                        "captured_at": now,
                    },
                )
        except IntegrityError:
            log.info(
                "payment_already_recorded",
                order_id=str(order.id),
                razorpay_payment_id=payload.razorpay_payment_id,
            )

        # Confirm order
        await _repo.update(
            db,
            order.id,
            {
                "status": "confirmed",
                "payment_status": "paid",
                "razorpay_payment_id": payload.razorpay_payment_id,
            },
        )

        # Commit BEFORE publishing events — listeners open new sessions and read order state
        await db.commit()

        from app.modules.profiles.repository import ProfileRepository

        profile = await ProfileRepository().get_by_id(db, user_id)
        customer_email = (profile.email if profile else "") or ""
        customer_phone = (
            (profile.phone if profile else None) or order.shipping_phone or ""
        )

        await event_bus.publish(
            OrderCreatedEvent(
                order_id=str(order.id),
                user_id=str(user_id),
                order_number=order.order_number,
                total_amount=float(order.total),
                customer_email=customer_email,
                customer_phone=customer_phone,
            )
        )
        await event_bus.publish(
            PaymentCapturedEvent(
                order_id=str(order.id),
                payment_id=payload.razorpay_payment_id,
                user_id=str(user_id),
                amount=float(order.total),
                order_number=order.order_number,
                customer_email=customer_email,
                customer_phone=customer_phone,
            )
        )

        duration_ms = round((time.perf_counter() - t0) * 1000)
        log.info(
            "payment_verified",
            order_id=str(order.id),
            order_number=order.order_number,
            amount=float(order.total),
            duration_ms=duration_ms,
        )

        return VerifyOrderPaymentResponse(
            success=True,
            order_id=str(order.id),
            order_number=order.order_number,
        )

    # ── Read operations ───────────────────────────────────────────────────────

    async def get_order(
        self, db: AsyncSession, order_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> OrderResponse:
        order = await _repo.get_by_id(db, order_id)
        if not order:
            raise NotFoundError("Order not found")
        if user_id and order.user_id != user_id:
            raise NotFoundError("Order not found")
        response = OrderResponse.model_validate(order)
        if user_id and order.status == "delivered":
            await self._enrich_review_states(db, response, user_id)
        return response

    async def _enrich_review_states(
        self, db: AsyncSession, response: OrderResponse, user_id: uuid.UUID
    ) -> None:
        """Attach product slugs and the customer's own review state to each
        item of a delivered order, so the storefront can render Write Review /
        Reviewed reminders without extra API calls.

        Two bulk queries (slugs, reviews) regardless of item count. Read-only:
        this only reports state and never gates who may submit a review.
        """
        from app.modules.reviews.repository import ReviewRepository

        product_ids = [i.product_id for i in response.items if i.product_id]
        if not product_ids:
            return

        slug_rows = await db.execute(
            text("SELECT id, slug FROM products WHERE id = ANY(CAST(:pids AS uuid[]))"),
            {"pids": [str(p) for p in product_ids]},
        )
        slugs = {r.id: r.slug for r in slug_rows.fetchall()}

        reviews = await ReviewRepository().list_by_products_user(
            db, product_ids=product_ids, user_id=user_id
        )
        reviews_by_product = {r.product_id: r for r in reviews}

        for item in response.items:
            if not item.product_id:
                continue
            review = reviews_by_product.get(item.product_id)
            item.product_slug = slugs.get(item.product_id)
            item.is_reviewed = review is not None
            item.review_id = review.id if review else None
            item.review_rating = review.rating if review else None

    async def list_my_orders(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 10,
        status: str | None = None,
    ) -> OrderListResponse:
        items, total = await _repo.list_for_user(
            db, user_id, page=page, page_size=page_size, status=status
        )
        list_items = [
            OrderListItem(
                id=o.id,
                order_number=o.order_number,
                status=o.status,
                payment_status=o.payment_status,
                fulfillment_status=o.fulfillment_status,
                total=float(o.total),
                item_count=getattr(o, "_item_count", 0),
                complimentary_gift=o.complimentary_gift,
                created_at=o.created_at,
            )
            for o in items
        ]
        return OrderListResponse(
            items=list_items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=math.ceil(total / page_size) if total else 0,
        )

    async def admin_list_orders(
        self,
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        payment_status: str | None = None,
        user_id: uuid.UUID | None = None,
        search: str | None = None,
    ) -> OrderListResponse:
        items, total = await _repo.list_all(
            db,
            page=page,
            page_size=page_size,
            status=status,
            payment_status=payment_status,
            user_id=user_id,
            search=search,
        )
        list_items = [
            OrderListItem(
                id=o.id,
                order_number=o.order_number,
                status=o.status,
                payment_status=o.payment_status,
                fulfillment_status=o.fulfillment_status,
                total=float(o.total),
                item_count=getattr(o, "_item_count", 0),
                complimentary_gift=o.complimentary_gift,
                created_at=o.created_at,
            )
            for o in items
        ]
        return OrderListResponse(
            items=list_items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=math.ceil(total / page_size) if total else 0,
        )

    async def update_status(
        self,
        db: AsyncSession,
        order_id: uuid.UUID,
        payload: UpdateOrderStatusRequest,
    ) -> OrderResponse:
        order = await _repo.get_by_id(db, order_id)
        if not order:
            raise NotFoundError("Order not found")

        data: dict = {"status": payload.status}
        if payload.status == "cancelled":
            data["cancellation_reason"] = payload.cancellation_reason
            data["cancelled_at"] = datetime.now(UTC)
            # Restock inventory only when transitioning *into* cancelled
            if order.status != "cancelled":
                await self._restock_cancelled_order(db, order, order_id)
        if payload.status == "delivered":
            data["delivered_at"] = datetime.now(UTC)
        if payload.tracking_number:
            data["tracking_number"] = payload.tracking_number
        if payload.shipping_provider:
            data["shipping_provider"] = payload.shipping_provider
        if payload.estimated_delivery:
            data["estimated_delivery"] = payload.estimated_delivery

        prev_status = order.status
        updated = await _repo.update(db, order_id, data)

        # Commit BEFORE publishing — listeners open fresh sessions.
        await db.commit()

        await event_bus.publish(
            OrderStatusChangedEvent(
                order_id=str(order_id),
                user_id=str(order.user_id),
                old_status=prev_status,
                new_status=payload.status,
            )
        )

        return OrderResponse.model_validate(updated)

    async def set_complimentary_gift(
        self,
        db: AsyncSession,
        order_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: SetComplimentaryGiftRequest,
    ) -> OrderResponse:
        if not await SettingsService.is_feature_enabled(
            db, "complimentary_gift_enabled"
        ):
            raise ValidationError("Complimentary gift is currently unavailable")
        order = await _repo.get_by_id(db, order_id)
        if not order or order.user_id != user_id:
            raise NotFoundError("Order not found")
        if order.payment_status != "paid":
            raise ValidationError("Order must be paid before selecting a gift")
        if float(order.total) < 2000:
            raise ValidationError("Order is not eligible for a complimentary gift")
        if order.complimentary_gift:
            raise ValidationError("Complimentary gift has already been selected")
        updated = await _repo.update(db, order_id, {"complimentary_gift": payload.gift})
        await db.commit()
        return OrderResponse.model_validate(updated)

    async def _restock_cancelled_order(
        self,
        db: AsyncSession,
        order,
        order_id: uuid.UUID,
    ) -> None:
        """
        Idempotent inventory + coupon release for a cancellation.
        - Releases any remaining ACTIVE reservations (pre-payment / stock_reserved orders).
        - If the order was confirmed, reverses sold_quantity for each item (handles
          both COD orders [payment_status=pending] and paid orders [payment_status=paid]).
        - Restores coupon usage so the slot becomes available again.
        Already-cancelled orders produce no-ops in both sub-calls.
        """
        await _reservation_svc.release_order_reservations(
            db, order_id, reason="RELEASED"
        )
        if order.status == "confirmed":
            for item in order.items:
                if item.product_id:
                    await _reservation_svc.record_return(
                        db,
                        product_id=item.product_id,
                        variant_id=item.variant_id,
                        quantity=item.quantity,
                        order_id=order_id,
                        reference=f"cancel:{order_id}",
                    )
                    log.info(
                        "order_cancel_restock",
                        order_id=str(order_id),
                        product_id=str(item.product_id),
                        variant_id=str(item.variant_id) if item.variant_id else None,
                        quantity=item.quantity,
                    )

        # Restore coupon usage so the slot becomes available again.
        if order.coupon_id:
            from app.modules.coupons.service import CouponService

            await CouponService().revert_usage(
                db, order.coupon_id, order.user_id, order_id
            )

    async def handle_expired_order_side_effects(
        self, db: AsyncSession, order_ids: list[uuid.UUID]
    ) -> None:
        """Handle coupon restoration for orders transitioned to payment_expired.

        Called by the reservation_expiry worker after
        ``ReservationService.expire_stale_reservations()`` returns a list of
        order IDs that were transitioned.  Batch-loads all orders in a single
        query to avoid N+1, then reverts coupon usage for each order that had
        a coupon applied.

        Coupon revert is idempotent — if ``finalize_usage()`` was never called,
        the fallback in ``revert_usage()`` finds the pending (order_id=NULL)
        row.
        """
        if not order_ids:
            return

        from app.modules.coupons.service import CouponService

        coupon_svc = CouponService()
        orders = await _repo.get_by_ids(db, order_ids)
        orders_by_id = {o.id: o for o in orders}

        for oid in order_ids:
            order = orders_by_id.get(oid)
            if not order or not order.coupon_id:
                continue
            try:
                await coupon_svc.revert_usage(db, order.coupon_id, order.user_id, oid)
            except Exception:
                log.error("coupon_revert_failed_on_expiry", order_id=str(oid))

    async def get_active_reservations(
        self, db: AsyncSession, user_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """Return the user's current ACTIVE reservations with product details.

        Used by the storefront to display 'Reserved for you' instead of
        'Out of Stock' for items the customer has pending in a checkout.
        """
        reservations = await _reservation_svc.get_user_active_reservations(db, user_id)
        if not reservations:
            return []

        # Batch-fetch product/variant names in one query.
        product_ids = list({str(r["product_id"]) for r in reservations})
        variant_ids = [
            str(r["variant_id"]) for r in reservations if r.get("variant_id")
        ]

        product_rows = await db.execute(
            text(
                "SELECT id, name FROM products " "WHERE id = ANY(CAST(:pids AS uuid[]))"
            ),
            {"pids": product_ids},
        )
        products_by_id = {r.id: r.name for r in product_rows.fetchall()}

        variants_by_id: dict = {}
        if variant_ids:
            variant_rows = await db.execute(
                text(
                    "SELECT id, name FROM product_variants "
                    "WHERE id = ANY(CAST(:vids AS uuid[]))"
                ),
                {"vids": variant_ids},
            )
            variants_by_id = {r.id: r.name for r in variant_rows.fetchall()}

        result = []
        for r in reservations:
            pid = r["product_id"]
            vid = r.get("variant_id")
            result.append(
                {
                    "reservation_number": r["reservation_number"],
                    "product_id": pid,
                    "variant_id": vid,
                    "product_name": products_by_id.get(pid, ""),
                    "variant_name": variants_by_id.get(vid) if vid else None,
                    "quantity": r["quantity"],
                    "expires_at": r["expires_at"],
                }
            )
        return result

    async def cancel_order(
        self,
        db: AsyncSession,
        order_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: CancelOrderRequest,
    ) -> OrderResponse:
        order = await _repo.get_by_id(db, order_id)
        if not order:
            raise NotFoundError("Order not found")
        if order.user_id != user_id:
            raise NotFoundError("Order not found")
        if order.status not in _CANCELLABLE_STATUSES:
            raise ValidationError(
                f"Order in '{order.status}' status cannot be cancelled"
            )

        await self._restock_cancelled_order(db, order, order_id)

        updated = await _repo.update(
            db,
            order_id,
            {
                "status": "cancelled",
                "cancellation_reason": payload.reason,
                "cancelled_at": datetime.now(UTC),
            },
        )

        # Commit BEFORE publishing — listeners open fresh sessions.
        await db.commit()

        await event_bus.publish(
            OrderStatusChangedEvent(
                order_id=str(order_id),
                user_id=str(user_id),
                old_status=order.status,
                new_status="cancelled",
            )
        )

        return OrderResponse.model_validate(updated)

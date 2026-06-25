import asyncio
import hashlib
import hmac
import math
import time
import uuid
from datetime import UTC, datetime

import razorpay
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.events import (
    OrderCreatedEvent,
    OrderStatusChangedEvent,
    PaymentCapturedEvent,
    event_bus,
)
from app.core.exceptions import InventoryError, NotFoundError, ValidationError
from app.modules.inventory.reservation_service import ReservationService
from app.modules.orders.repository import OrderRepository
from app.modules.orders.schemas import (
    CancelOrderRequest,
    CreateOrderRequest,
    CreatePaymentIntentRequest,
    CreatePaymentIntentResponse,
    OrderListItem,
    OrderListResponse,
    OrderResponse,
    UpdateOrderStatusRequest,
    VerifyOrderPaymentRequest,
    VerifyOrderPaymentResponse,
)

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
        """Validate cart items against DB and compute per-item tax. No stock lock."""
        line_items = []
        for ci in cart_items:
            row = await db.execute(
                text(
                    "SELECT p.name, p.sku, p.base_price, p.tax_rate, "
                    "p.stock_quantity, p.reserved_quantity, p.sold_quantity, "
                    "p.allow_backorder, p.track_inventory, "
                    "v.name AS variant_name, "
                    "COALESCE(v.price_adjustment, 0) AS price_adj, "
                    "(SELECT pi.thumbnail_url FROM product_images pi "
                    " WHERE pi.product_id = p.id "
                    " ORDER BY pi.is_primary DESC, pi.sort_order ASC LIMIT 1"
                    ") AS image_url "
                    "FROM products p "
                    "LEFT JOIN product_variants v ON v.id = :vid "
                    "WHERE p.id = :pid AND p.deleted_at IS NULL AND p.status = 'active'"
                ),
                {
                    "pid": str(ci.product_id),
                    "vid": str(ci.variant_id) if ci.variant_id else None,
                },
            )
            prod = row.fetchone()
            if not prod:
                raise ValidationError(f"Product {ci.product_id} is no longer available")

            unit_price = float(prod.base_price) + float(prod.price_adj)
            tax_rate = float(prod.tax_rate)
            pre_tax = round(unit_price * ci.quantity, 2)
            tax_amt = round(pre_tax * tax_rate / 100, 2)
            line_total = round(pre_tax + tax_amt, 2)

            line_items.append(
                {
                    "id": uuid.uuid4(),
                    "product_id": ci.product_id,
                    "variant_id": ci.variant_id,
                    "product_name": prod.name,
                    "product_sku": prod.sku,
                    "variant_name": prod.variant_name,
                    "image_url": prod.image_url,
                    "unit_price": unit_price,
                    "quantity": ci.quantity,
                    "tax_rate": tax_rate,
                    "tax_amount": tax_amt,
                    "line_total": line_total,
                }
            )
        return line_items

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
            discount, coupon_id = await coupon_svc.apply_and_reserve(
                db, coupon_code, subtotal, user_id
            )
            applied_coupon_code = coupon_code.upper()
            if coupon_id:
                from app.modules.coupons.repository import CouponRepository

                c = await CouponRepository().get_by_id(db, coupon_id)
                if c and c.coupon_type == "free_shipping":
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
            "line1": addr.line1,
            "line2": addr.line2,
            "city": addr.city,
            "state": addr.state,
            "postal_code": addr.postal_code,
            "country": addr.country,
        }

    def _build_address_data(self, prefix: str, addr: dict) -> dict:
        return {
            f"{prefix}_full_name": addr["full_name"],
            f"{prefix}_phone": addr.get("phone"),
            f"{prefix}_line1": addr["line1"],
            f"{prefix}_line2": addr.get("line2"),
            f"{prefix}_city": addr["city"],
            f"{prefix}_state": addr["state"],
            f"{prefix}_postal": addr["postal_code"],
            f"{prefix}_country": addr["country"],
        }

    # ── COD flow ──────────────────────────────────────────────────────────────

    async def create_from_cart(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        payload: CreateOrderRequest,
    ) -> OrderResponse:
        """
        COD checkout. Locks stock via SELECT FOR UPDATE and immediately
        transitions quantity to sold (no 10-minute reservation window needed
        because the order is confirmed on the spot).
        """
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

        # Lock and validate available stock for each item
        reservation_items = [
            {
                "product_id": li["product_id"],
                "variant_id": li["variant_id"],
                "quantity": li["quantity"],
            }
            for li in line_items
        ]
        # Use reserve_items to lock and check stock, then immediately complete
        reservations = await _reservation_svc.reserve_items(
            db, user_id=user_id, items=reservation_items
        )

        subtotal, total_tax, shipping_charge, discount, coupon_id, coupon_code = (
            await self._compute_totals(db, line_items, payload.coupon_code, user_id)
        )
        total = round(max(subtotal + total_tax + shipping_charge - discount, 0), 2)

        order_number = await _repo.generate_order_number(db)
        order_data = {
            "id": uuid.uuid4(),
            "order_number": order_number,
            "user_id": user_id,
            "status": "confirmed",
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
            "payment_method": payload.payment_method,
            "notes": payload.notes,
        }
        order = await _repo.create(db, order_data)

        for item_data in line_items:
            item_data["order_id"] = order.id
            await _repo.add_item(db, item_data)

        # Link reservations to order then immediately complete them (COD)
        await _reservation_svc.link_reservations_to_order(db, reservations, order.id)
        await _reservation_svc.complete_order_reservations(db, order.id)

        if coupon_id:
            from app.modules.coupons.service import CouponService

            await CouponService().finalize_usage(db, coupon_id, user_id, order.id)

        await CartRepository().clear_items(db, cart.id)

        from app.modules.profiles.repository import ProfileRepository

        profile = await ProfileRepository().get_by_id(db, user_id)
        await event_bus.publish(
            OrderCreatedEvent(
                order_id=str(order.id),
                user_id=str(user_id),
                order_number=order_number,
                total_amount=float(total),
                customer_email=(profile.email if profile else "") or "",
                customer_phone=(profile.phone if profile else None)
                or addr.get("phone")
                or "",
            )
        )

        order = await _repo.get_by_id(db, order.id)  # type: ignore[assignment]
        assert order is not None
        return OrderResponse.model_validate(order)

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
        5. Create Razorpay order
        6. Return response to frontend

        Stock is held for exactly 10 minutes. If payment is not completed by then
        the reservation_expiry background worker releases the inventory automatically.
        """
        t0 = time.perf_counter()

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
        total = round(max(subtotal + total_tax + shipping_charge - discount, 0), 2)

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

        # ── Create Razorpay order (offloaded to thread pool) ──────────────────
        amount_paise = int(round(total * 100))
        client = razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        )
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
            # Release stock if Razorpay call fails so customer isn't locked out
            await _reservation_svc.release_order_reservations(
                db, order.id, reason="RELEASED"
            )
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
        if order.status in ("cancelled", "payment_expired"):
            raise ValidationError(
                "Your reservation has expired. Please start a new checkout."
            )

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

        # Complete stock reservation (reserved → sold) with row-level locking
        await _reservation_svc.complete_order_reservations(db, order.id)

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

        # Record payment
        from app.modules.payments.repository import PaymentRepository

        now = datetime.now(UTC)
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
        return OrderResponse.model_validate(order)

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

        await event_bus.publish(
            OrderStatusChangedEvent(
                order_id=str(order_id),
                user_id=str(order.user_id),
                old_status=prev_status,
                new_status=payload.status,
            )
        )

        return OrderResponse.model_validate(updated)

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

        # Release any active stock reservations
        await _reservation_svc.release_order_reservations(
            db, order_id, reason="RELEASED"
        )

        # If the order was already confirmed (paid), restore sold stock as return
        if order.status == "confirmed" and order.payment_status == "paid":
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

        updated = await _repo.update(
            db,
            order_id,
            {
                "status": "cancelled",
                "cancellation_reason": payload.reason,
                "cancelled_at": datetime.now(UTC),
            },
        )

        await event_bus.publish(
            OrderStatusChangedEvent(
                order_id=str(order_id),
                user_id=str(user_id),
                old_status=order.status,
                new_status="cancelled",
            )
        )

        return OrderResponse.model_validate(updated)

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
from app.core.exceptions import NotFoundError, ValidationError

log = structlog.get_logger(__name__)
from app.modules.orders.repository import OrderRepository
from app.modules.orders.schemas import (
    CancelOrderRequest,
    CreateOrderRequest,
    CreatePaymentIntentRequest,
    CreatePaymentIntentResponse,
    OrderListResponse,
    OrderResponse,
    UpdateOrderStatusRequest,
    VerifyOrderPaymentRequest,
    VerifyOrderPaymentResponse,
)

_repo = OrderRepository()

_CANCELLABLE_STATUSES = {"pending", "confirmed"}
_FREE_SHIPPING_THRESHOLD = 999.0  # ₹999+ → free shipping
_SHIPPING_CHARGE = 99.0


class OrderService:
    async def create_from_cart(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        payload: CreateOrderRequest,
    ) -> OrderResponse:
        # 1. Fetch cart
        from app.modules.cart.repository import CartRepository

        cart_repo = CartRepository()
        cart = await cart_repo.get_for_user(db, user_id)
        if not cart or not cart.items:
            raise ValidationError("Cart is empty")

        # 2. Fetch shipping address
        addr = await self._get_address(db, payload.shipping_address_id, user_id)

        # 3. Resolve billing address
        if payload.billing_address_id:
            bill_addr = await self._get_address(db, payload.billing_address_id, user_id)
        else:
            bill_addr = addr

        # 4. Validate all cart items and compute per-item tax
        line_items = []
        for ci in cart.items:
            row = await db.execute(
                text(
                    "SELECT p.name, p.sku, p.base_price, p.tax_rate, p.stock_quantity, "
                    "p.allow_backorder, p.track_inventory, "
                    "v.name AS variant_name, "
                    "COALESCE(v.price_adjustment, 0) AS price_adj "
                    "FROM products p "
                    "LEFT JOIN product_variants v ON v.id = :vid "
                    "WHERE p.id = :pid AND p.deleted_at IS NULL AND p.status = 'active'"
                ),
                {"pid": str(ci.product_id), "vid": str(ci.variant_id) if ci.variant_id else None},
            )
            prod = row.fetchone()
            if not prod:
                raise ValidationError(f"Product {ci.product_id} is no longer available")

            if prod.track_inventory and not prod.allow_backorder:
                if prod.stock_quantity < ci.quantity:
                    raise ValidationError(
                        f"Insufficient stock for '{prod.name}': "
                        f"requested {ci.quantity}, available {prod.stock_quantity}"
                    )

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
                    "unit_price": unit_price,
                    "quantity": ci.quantity,
                    "tax_rate": tax_rate,
                    "tax_amount": tax_amt,
                    "line_total": line_total,
                }
            )

        # 5. Totals before coupon
        subtotal = round(sum(i["unit_price"] * i["quantity"] for i in line_items), 2)
        total_tax = round(sum(i["tax_amount"] for i in line_items), 2)
        shipping_charge = 0.0 if subtotal >= _FREE_SHIPPING_THRESHOLD else _SHIPPING_CHARGE

        # 6. Coupon
        discount = 0.0
        coupon_id = None
        coupon_code = None
        if payload.coupon_code:
            from app.modules.coupons.service import CouponService

            coupon_svc = CouponService()
            discount, coupon_id = await coupon_svc.apply_and_reserve(
                db, payload.coupon_code, subtotal, user_id
            )
            coupon_code = payload.coupon_code.upper()
            # Free shipping coupon type overrides shipping charge
            if coupon_id:
                from app.modules.coupons.repository import CouponRepository

                c = await CouponRepository().get_by_id(db, coupon_id)
                if c and c.coupon_type == "free_shipping":
                    shipping_charge = 0.0
                    discount = shipping_charge  # discount = the saved shipping cost

        total = round(max(subtotal + total_tax + shipping_charge - discount, 0), 2)

        # 7. Create order
        order_number = await _repo.generate_order_number(db)
        order_data = {
            "id": uuid.uuid4(),
            "order_number": order_number,
            "user_id": user_id,
            "status": "pending",
            "payment_status": "pending",
            # Shipping snapshot
            "shipping_full_name": addr["full_name"],
            "shipping_phone": addr.get("phone"),
            "shipping_line1": addr["line1"],
            "shipping_line2": addr.get("line2"),
            "shipping_city": addr["city"],
            "shipping_state": addr["state"],
            "shipping_postal": addr["postal_code"],
            "shipping_country": addr["country"],
            # Billing snapshot
            "billing_full_name": bill_addr["full_name"],
            "billing_phone": bill_addr.get("phone"),
            "billing_line1": bill_addr["line1"],
            "billing_line2": bill_addr.get("line2"),
            "billing_city": bill_addr["city"],
            "billing_state": bill_addr["state"],
            "billing_postal": bill_addr["postal_code"],
            "billing_country": bill_addr["country"],
            # Financials
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

        # 8. Create order items
        for item_data in line_items:
            item_data["order_id"] = order.id
            await _repo.add_item(db, item_data)

        # 9. Reserve inventory (deduct stock)
        from app.modules.inventory.service import InventoryService

        inv_svc = InventoryService()
        for item in line_items:
            await inv_svc.record_movement(
                db,
                product_id=item["product_id"],
                delta=-item["quantity"],
                movement_type="sale",
                variant_id=item["variant_id"],
                reference_type="order",
                reference_id=str(order.id),
            )

        # 10. Finalize coupon usage
        if coupon_id:
            from app.modules.coupons.service import CouponService

            await CouponService().finalize_usage(db, coupon_id, user_id, order.id)

        # 11. Clear cart
        from app.modules.cart.repository import CartRepository

        await CartRepository().clear_items(db, cart.id)

        # 12. Publish event (recipient details resolved here so listeners stay DB-free)
        from app.modules.profiles.repository import ProfileRepository

        profile = await ProfileRepository().get_by_id(db, user_id)
        await event_bus.publish(
            OrderCreatedEvent(
                order_id=str(order.id),
                user_id=str(user_id),
                order_number=order_number,
                total_amount=float(total),
                customer_email=(profile.email if profile else "") or "",
                customer_phone=(profile.phone if profile else None) or addr.get("phone") or "",
            )
        )

        order = await _repo.get_by_id(db, order.id)
        return OrderResponse.model_validate(order)

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
        list_items = []
        for o in items:
            list_items.append(
                {
                    "id": o.id,
                    "order_number": o.order_number,
                    "status": o.status,
                    "payment_status": o.payment_status,
                    "total": float(o.total),
                    "item_count": getattr(o, "_item_count", 0),
                    "created_at": o.created_at,
                }
            )
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
            {
                "id": o.id,
                "order_number": o.order_number,
                "status": o.status,
                "payment_status": o.payment_status,
                "total": float(o.total),
                "item_count": getattr(o, "_item_count", 0),
                "created_at": o.created_at,
            }
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
            raise ValidationError(f"Order in '{order.status}' status cannot be cancelled")

        updated = await _repo.update(
            db,
            order_id,
            {
                "status": "cancelled",
                "cancellation_reason": payload.reason,
                "cancelled_at": datetime.now(UTC),
            },
        )

        # Return stock
        from app.modules.inventory.service import InventoryService

        inv_svc = InventoryService()
        for item in order.items:
            if item.product_id:
                await inv_svc.record_movement(
                    db,
                    product_id=item.product_id,
                    delta=item.quantity,
                    movement_type="return",
                    variant_id=item.variant_id,
                    reference_type="order_cancellation",
                    reference_id=str(order_id),
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

    async def create_payment_intent(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        payload: CreatePaymentIntentRequest,
    ) -> CreatePaymentIntentResponse:
        """
        Phase 1 of the Razorpay direct checkout flow.
        Validates the cart, creates the DB order (without deducting inventory),
        creates a Razorpay order, and returns the details needed to open the
        Razorpay Checkout modal on the frontend.
        """
        # 1. Fetch cart
        from app.modules.cart.repository import CartRepository

        cart_repo = CartRepository()
        cart = await cart_repo.get_for_user(db, user_id)
        if not cart or not cart.items:
            raise ValidationError("Cart is empty")

        # 2. Resolve addresses
        addr = await self._get_address(db, payload.shipping_address_id, user_id)
        bill_addr = addr
        if payload.billing_address_id:
            bill_addr = await self._get_address(db, payload.billing_address_id, user_id)

        # 3. Validate cart items and compute per-item tax
        line_items = []
        for ci in cart.items:
            row = await db.execute(
                text(
                    "SELECT p.name, p.sku, p.base_price, p.tax_rate, p.stock_quantity, "
                    "p.allow_backorder, p.track_inventory, "
                    "v.name AS variant_name, "
                    "COALESCE(v.price_adjustment, 0) AS price_adj "
                    "FROM products p "
                    "LEFT JOIN product_variants v ON v.id = :vid "
                    "WHERE p.id = :pid AND p.deleted_at IS NULL AND p.status = 'active'"
                ),
                {"pid": str(ci.product_id), "vid": str(ci.variant_id) if ci.variant_id else None},
            )
            prod = row.fetchone()
            if not prod:
                raise ValidationError(f"Product {ci.product_id} is no longer available")

            if prod.track_inventory and not prod.allow_backorder:
                if prod.stock_quantity < ci.quantity:
                    raise ValidationError(
                        f"Insufficient stock for '{prod.name}': "
                        f"requested {ci.quantity}, available {prod.stock_quantity}"
                    )

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
                    "unit_price": unit_price,
                    "quantity": ci.quantity,
                    "tax_rate": tax_rate,
                    "tax_amount": tax_amt,
                    "line_total": line_total,
                }
            )

        # 4. Totals before coupon
        subtotal = round(sum(i["unit_price"] * i["quantity"] for i in line_items), 2)
        total_tax = round(sum(i["tax_amount"] for i in line_items), 2)
        shipping_charge = 0.0 if subtotal >= _FREE_SHIPPING_THRESHOLD else _SHIPPING_CHARGE

        # 5. Coupon (reserve but do not finalize — finalization happens after payment)
        discount = 0.0
        coupon_id = None
        coupon_code = None
        if payload.coupon_code:
            from app.modules.coupons.service import CouponService

            coupon_svc = CouponService()
            discount, coupon_id = await coupon_svc.apply_and_reserve(
                db, payload.coupon_code, subtotal, user_id
            )
            coupon_code = payload.coupon_code.upper()
            if coupon_id:
                from app.modules.coupons.repository import CouponRepository

                c = await CouponRepository().get_by_id(db, coupon_id)
                if c and c.coupon_type == "free_shipping":
                    shipping_charge = 0.0
                    discount = shipping_charge

        total = round(max(subtotal + total_tax + shipping_charge - discount, 0), 2)

        # 6. Create DB order (status=pending, payment_status=pending, no inventory deducted)
        order_number = await _repo.generate_order_number(db)
        order_data = {
            "id": uuid.uuid4(),
            "order_number": order_number,
            "user_id": user_id,
            "status": "pending",
            "payment_status": "pending",
            "shipping_full_name": addr["full_name"],
            "shipping_phone": addr.get("phone"),
            "shipping_line1": addr["line1"],
            "shipping_line2": addr.get("line2"),
            "shipping_city": addr["city"],
            "shipping_state": addr["state"],
            "shipping_postal": addr["postal_code"],
            "shipping_country": addr["country"],
            "billing_full_name": bill_addr["full_name"],
            "billing_phone": bill_addr.get("phone"),
            "billing_line1": bill_addr["line1"],
            "billing_line2": bill_addr.get("line2"),
            "billing_city": bill_addr["city"],
            "billing_state": bill_addr["state"],
            "billing_postal": bill_addr["postal_code"],
            "billing_country": bill_addr["country"],
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

        # 7. Create Razorpay order
        # razorpay-python uses the synchronous `requests` library internally.
        # Running it directly inside an async function blocks the entire event
        # loop for the duration of the HTTP call (~200-500 ms).  We push it
        # into the default thread-pool executor so other coroutines can run.
        amount_paise = int(round(total * 100))
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
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
            log.error("razorpay_order_create_failed", order_id=str(order.id), error=str(exc))
            raise ValidationError("Failed to create payment order. Please try again.") from exc

        # 8. Persist razorpay_order_id on DB order
        await _repo.update(db, order.id, {"razorpay_order_id": rzp_order["id"]})

        return CreatePaymentIntentResponse(
            order_id=str(order.id),
            razorpay_order_id=rzp_order["id"],
            amount=amount_paise,
            currency=settings.RAZORPAY_CURRENCY,
            key=settings.RAZORPAY_KEY_ID,
        )

    async def verify_and_fulfill(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        payload: VerifyOrderPaymentRequest,
    ) -> VerifyOrderPaymentResponse:
        """
        Phase 2 of the Razorpay checkout flow.

        Sequence that MUST be preserved:
          1. Load + ownership check
          2. Idempotency guard (already paid → return success immediately)
          3. HMAC verification (no DB writes if signature is bad)
          4. Inventory deduction
          5. Coupon finalization
          6. Cart clear
          7. Payment record
          8. Order status → confirmed / paid
          9. db.commit()  ← BEFORE publishing events
         10. Publish events (fire-and-forget background tasks)

        Step 9 is critical.  Event listeners open their own DB sessions and read
        the order status.  If we publish before committing, they see the old
        "pending" status and shipment creation fails.
        """
        t0 = time.perf_counter()

        # 1. Load order and verify ownership
        order = await _repo.get_by_id(db, payload.order_id)
        if not order or order.user_id != user_id:
            raise NotFoundError("Order not found")
        if order.status == "cancelled":
            raise ValidationError("Order has been cancelled")

        # 2. Idempotency: already fulfilled
        if order.payment_status == "paid":
            log.info(
                "payment_already_verified", order_id=str(order.id), order_number=order.order_number
            )
            return VerifyOrderPaymentResponse(
                success=True,
                order_id=str(order.id),
                order_number=order.order_number,
            )

        log.info(
            "payment_verification_started", order_id=str(order.id), order_number=order.order_number
        )

        # 3. Verify HMAC signature before any DB writes
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

        # 4. Deduct inventory
        from app.modules.inventory.service import InventoryService

        inv_svc = InventoryService()
        for item in order.items:
            if item.product_id:
                await inv_svc.record_movement(
                    db,
                    product_id=item.product_id,
                    delta=-item.quantity,
                    movement_type="sale",
                    variant_id=item.variant_id,
                    reference_type="order",
                    reference_id=str(order.id),
                )
        log.info("inventory_deducted", order_id=str(order.id), item_count=len(order.items))

        # 5. Finalize coupon
        if order.coupon_id:
            from app.modules.coupons.service import CouponService

            await CouponService().finalize_usage(db, order.coupon_id, user_id, order.id)
            log.info("coupon_finalized", order_id=str(order.id), coupon_id=str(order.coupon_id))

        # 6. Clear cart
        from app.modules.cart.repository import CartRepository

        cart_repo = CartRepository()
        cart = await cart_repo.get_for_user(db, user_id)
        if cart:
            await cart_repo.clear_items(db, cart.id)

        # 7. Record payment
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

        # 8. Mark order as confirmed + paid
        await _repo.update(
            db,
            order.id,
            {
                "status": "confirmed",
                "payment_status": "paid",
                "razorpay_payment_id": payload.razorpay_payment_id,
            },
        )
        log.info("order_confirmed", order_id=str(order.id), order_number=order.order_number)

        # 9. Commit BEFORE publishing events.
        # Listeners run as background asyncio tasks (fire-and-forget).  They
        # open their own DB sessions; those sessions must see the "confirmed"
        # status we just wrote.  If we skip this commit, the shipment listener
        # reads "pending" and raises "Cannot create shipment for order in
        # 'pending' status".
        await db.commit()

        # 10. Publish events — non-blocking, returns immediately.
        # Subsequent get_db commit (in the FastAPI dependency) is now a no-op.
        from app.modules.profiles.repository import ProfileRepository

        profile = await ProfileRepository().get_by_id(db, user_id)
        customer_email = (profile.email if profile else "") or ""
        customer_phone = (profile.phone if profile else None) or order.shipping_phone or ""

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

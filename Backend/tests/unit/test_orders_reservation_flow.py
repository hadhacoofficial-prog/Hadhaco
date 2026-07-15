"""Tests for order-service paths that exercise the reservation system.

Covers:
  - create_payment_intent: reserves stock, releases on Razorpay failure
  - verify_and_fulfill: idempotency, HMAC, complete reservations
  - create_from_cart (COD): reserve + immediately complete
  - cancel_order: release ACTIVE reservations

WebhookService tests (payment.captured/payment.failed/handle_razorpay
idempotency, all 6 Razorpay event types) live in
tests/unit/test_service_webhooks.py.

All repos/services are imported locally inside function bodies, so patches must
target the source module, not app.modules.orders.service.ClassName.
"""

import hashlib
import hmac
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Force mapper init — all models must be imported for SQLAlchemy's registry.
import app.modules.addresses.models  # noqa: F401
import app.modules.cart.models  # noqa: F401
import app.modules.catalog.models  # noqa: F401
import app.modules.categories.models  # noqa: F401
import app.modules.collections.models  # noqa: F401
import app.modules.coupons.models  # noqa: F401
import app.modules.inventory.models  # noqa: F401
import app.modules.orders.models  # noqa: F401
import app.modules.payments.models  # noqa: F401
import app.modules.profiles.models  # noqa: F401
import app.modules.returns.models  # noqa: F401
import app.modules.reviews.models  # noqa: F401
import app.modules.shipping.models  # noqa: F401
import app.modules.support.models  # noqa: F401
import app.modules.wishlist.models  # noqa: F401

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_cart_item(product_id: uuid.UUID | None = None, quantity: int = 2):
    ci = MagicMock()
    ci.product_id = product_id or uuid.uuid4()
    ci.variant_id = None
    ci.quantity = quantity
    return ci


def _make_product_row(
    product_id: uuid.UUID | None = None,
    name: str = "Ring",
    sku: str = "RNG-001",
    base_price: float = 500.0,
    tax_rate: float = 3.0,
    stock: int = 10,
    reserved: int = 0,
    sold: int = 0,
    allow_backorder: bool = False,
    track_inventory: bool = True,
):
    row = MagicMock()
    row.id = product_id or uuid.uuid4()
    row.product_id = row.id
    row.name = name
    row.sku = sku
    row.base_price = base_price
    row.tax_rate = tax_rate
    row.stock_quantity = stock
    row.reserved_quantity = reserved
    row.sold_quantity = sold
    row.allow_backorder = allow_backorder
    row.track_inventory = track_inventory
    row.variant_name = None
    row.price_adj = 0.0
    row.thumbnail_url = None
    return row


def _mock_db_for_line_items(prod_row):
    """_resolve_line_items issues up to 3 batched queries (products,
    variants, images); a single variant-less cart item only triggers the
    product and image queries, both served by the same .fetchall() result.
    """
    result = MagicMock()
    result.fetchall.return_value = [prod_row]
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    return db


def _make_address():
    addr = MagicMock()
    addr.full_name = "Test User"
    addr.phone = "9999999999"
    addr.line1 = "123 Main St"
    addr.line2 = ""
    addr.city = "Hyderabad"
    addr.state = "Telangana"
    addr.postal_code = "500001"
    addr.country = "IN"
    return addr


def _make_order(
    *,
    status: str = "payment_pending",
    payment_status: str = "pending",
    user_id: uuid.UUID | None = None,
    order_id: uuid.UUID | None = None,
    coupon_id: uuid.UUID | None = None,
    total: float = 1060.0,
):
    order = MagicMock()
    order.id = order_id or uuid.uuid4()
    order.user_id = user_id or uuid.uuid4()
    order.status = status
    order.payment_status = payment_status
    order.coupon_id = coupon_id
    order.total = total
    order.order_number = "ORD-2024-001"
    order.shipping_phone = "9999999999"
    order.razorpay_order_id = "rzp_ord_test123"
    order.items = []
    return order


def _make_reservation():
    r = MagicMock()
    r.id = uuid.uuid4()
    return r


# ── TestCreatePaymentIntent ───────────────────────────────────────────────────


class TestCreatePaymentIntentReservation:
    def setup_method(self):
        from app.modules.orders.service import OrderService

        self.svc = OrderService()

    async def test_reserves_stock_on_checkout(self):
        """create_payment_intent must call reserve_items exactly once."""
        user_id = uuid.uuid4()
        product_id = uuid.uuid4()
        cart_item = _make_cart_item(product_id=product_id, quantity=2)
        mock_cart = MagicMock()
        mock_cart.id = uuid.uuid4()
        mock_cart.items = [cart_item]

        prod_row = _make_product_row(
            product_id=product_id, base_price=500.0, tax_rate=3.0, stock=10
        )
        db = _mock_db_for_line_items(prod_row)

        addr = _make_address()
        reservation = _make_reservation()
        mock_order = _make_order(user_id=user_id)
        mock_order.id = uuid.uuid4()

        payload = MagicMock()
        payload.shipping_address_id = uuid.uuid4()
        payload.billing_address_id = None
        payload.coupon_code = None
        payload.notes = None

        # CartRepository and AddressRepository are imported locally in the service,
        # so patch them in their source modules.
        with patch("app.modules.cart.repository.CartRepository") as MockCartRepo:
            MockCartRepo.return_value.get_for_user = AsyncMock(return_value=mock_cart)
            with patch(
                "app.modules.addresses.repository.AddressRepository"
            ) as MockAddrRepo:
                MockAddrRepo.return_value.get = AsyncMock(return_value=addr)
                with patch(
                    "app.modules.orders.service._reservation_svc.reserve_items",
                    AsyncMock(return_value=[reservation]),
                ) as mock_reserve:
                    with patch(
                        "app.modules.orders.service._reservation_svc.link_reservations_to_order",
                        AsyncMock(),
                    ):
                        with patch(
                            "app.modules.orders.service._repo.generate_order_number",
                            AsyncMock(return_value="ORD-2024-001"),
                        ):
                            with patch(
                                "app.modules.orders.service._repo.create",
                                AsyncMock(return_value=mock_order),
                            ):
                                with patch(
                                    "app.modules.orders.service._repo.add_item",
                                    AsyncMock(),
                                ):
                                    with patch(
                                        "app.modules.orders.service._repo.update",
                                        AsyncMock(),
                                    ):
                                        with patch(
                                            "asyncio.get_running_loop"
                                        ) as mock_loop:
                                            mock_loop.return_value.run_in_executor = (
                                                AsyncMock(
                                                    return_value={
                                                        "id": "rzp_ord_test123"
                                                    }
                                                )
                                            )
                                            response = (
                                                await self.svc.create_payment_intent(
                                                    db, user_id, payload
                                                )
                                            )

        mock_reserve.assert_called_once()
        assert response.razorpay_order_id == "rzp_ord_test123"

    async def test_releases_stock_when_razorpay_call_fails(self):
        """If Razorpay order creation fails, stock must be released immediately."""
        user_id = uuid.uuid4()
        product_id = uuid.uuid4()
        cart_item = _make_cart_item(product_id=product_id, quantity=1)
        mock_cart = MagicMock()
        mock_cart.id = uuid.uuid4()
        mock_cart.items = [cart_item]

        prod_row = _make_product_row(product_id=product_id)
        db = _mock_db_for_line_items(prod_row)

        addr = _make_address()
        reservation = _make_reservation()
        mock_order = _make_order(user_id=user_id)

        payload = MagicMock()
        payload.shipping_address_id = uuid.uuid4()
        payload.billing_address_id = None
        payload.coupon_code = None
        payload.notes = None

        with patch("app.modules.cart.repository.CartRepository") as MockCartRepo:
            MockCartRepo.return_value.get_for_user = AsyncMock(return_value=mock_cart)
            with patch(
                "app.modules.addresses.repository.AddressRepository"
            ) as MockAddrRepo:
                MockAddrRepo.return_value.get = AsyncMock(return_value=addr)
                with patch(
                    "app.modules.orders.service._reservation_svc.reserve_items",
                    AsyncMock(return_value=[reservation]),
                ):
                    with patch(
                        "app.modules.orders.service._reservation_svc.link_reservations_to_order",
                        AsyncMock(),
                    ):
                        with patch(
                            "app.modules.orders.service._reservation_svc.release_order_reservations",
                            AsyncMock(),
                        ) as mock_release:
                            with patch(
                                "app.modules.orders.service._repo.generate_order_number",
                                AsyncMock(return_value="ORD-2024-001"),
                            ):
                                with patch(
                                    "app.modules.orders.service._repo.create",
                                    AsyncMock(return_value=mock_order),
                                ):
                                    with patch(
                                        "app.modules.orders.service._repo.add_item",
                                        AsyncMock(),
                                    ):
                                        with patch(
                                            "asyncio.get_running_loop"
                                        ) as mock_loop:
                                            mock_loop.return_value.run_in_executor = (
                                                AsyncMock(
                                                    side_effect=Exception(
                                                        "Razorpay down"
                                                    )
                                                )
                                            )

                                            from app.core.exceptions import (
                                                ValidationError,
                                            )

                                            with pytest.raises(ValidationError):
                                                await self.svc.create_payment_intent(
                                                    db, user_id, payload
                                                )

                                            mock_release.assert_called_once_with(
                                                db, mock_order.id, reason="RELEASED"
                                            )

    async def test_empty_cart_raises_validation_error(self):
        from app.core.exceptions import ValidationError

        db = AsyncMock()
        payload = MagicMock()
        payload.shipping_address_id = uuid.uuid4()
        payload.billing_address_id = None
        payload.coupon_code = None
        payload.notes = None

        with patch("app.modules.cart.repository.CartRepository") as MockCartRepo:
            MockCartRepo.return_value.get_for_user = AsyncMock(return_value=None)

            with pytest.raises(ValidationError, match="Cart is empty"):
                await self.svc.create_payment_intent(db, uuid.uuid4(), payload)

    async def test_inventory_error_propagates_from_reserve(self):
        """InventoryError from reserve_items propagates to the caller."""
        from app.core.exceptions import InventoryError

        user_id = uuid.uuid4()
        product_id = uuid.uuid4()
        cart_item = _make_cart_item(product_id=product_id, quantity=10)
        mock_cart = MagicMock()
        mock_cart.id = uuid.uuid4()
        mock_cart.items = [cart_item]

        prod_row = _make_product_row(product_id=product_id, stock=2)
        db = _mock_db_for_line_items(prod_row)

        addr = _make_address()
        payload = MagicMock()
        payload.shipping_address_id = uuid.uuid4()
        payload.billing_address_id = None
        payload.coupon_code = None
        payload.notes = None

        with patch("app.modules.cart.repository.CartRepository") as MockCartRepo:
            MockCartRepo.return_value.get_for_user = AsyncMock(return_value=mock_cart)
            with patch(
                "app.modules.addresses.repository.AddressRepository"
            ) as MockAddrRepo:
                MockAddrRepo.return_value.get = AsyncMock(return_value=addr)
                with patch(
                    "app.modules.orders.service._reservation_svc.reserve_items",
                    AsyncMock(side_effect=InventoryError("Only 2 item(s) available")),
                ):
                    with pytest.raises(InventoryError, match="2 item"):
                        await self.svc.create_payment_intent(db, user_id, payload)


# ── TestVerifyAndFulfill ──────────────────────────────────────────────────────


class TestVerifyAndFulfill:
    def setup_method(self):
        from app.modules.orders.service import OrderService

        self.svc = OrderService()

    def _valid_signature(self, rzp_order_id: str, rzp_payment_id: str) -> str:
        from app.core.config import settings

        msg = f"{rzp_order_id}|{rzp_payment_id}"
        return hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode(),
            msg.encode(),
            hashlib.sha256,
        ).hexdigest()

    async def test_already_paid_returns_success_no_commit(self):
        user_id = uuid.uuid4()
        order = _make_order(user_id=user_id, status="confirmed", payment_status="paid")

        with patch(
            "app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=order)
        ):
            payload = MagicMock()
            payload.order_id = order.id
            payload.razorpay_order_id = "rzp_ord_test"
            payload.razorpay_payment_id = "rzp_pay_test"
            payload.razorpay_signature = "sig"

            db = AsyncMock()
            response = await self.svc.verify_and_fulfill(db, user_id, payload)

        assert response.success is True
        db.commit.assert_not_called()

    async def test_expired_order_raises_validation_error(self):
        from app.core.exceptions import ValidationError

        user_id = uuid.uuid4()
        order = _make_order(user_id=user_id, status="payment_expired")

        with patch(
            "app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=order)
        ):
            payload = MagicMock()
            payload.order_id = order.id
            payload.razorpay_order_id = "rzp_ord_test"
            payload.razorpay_payment_id = "rzp_pay_test"
            payload.razorpay_signature = "bad_sig"

            db = AsyncMock()
            with pytest.raises(ValidationError, match="signature"):
                await self.svc.verify_and_fulfill(db, user_id, payload)

    async def test_cancelled_order_raises_validation_error(self):
        from app.core.exceptions import ValidationError

        user_id = uuid.uuid4()
        order = _make_order(user_id=user_id, status="cancelled")

        with patch(
            "app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=order)
        ):
            payload = MagicMock()
            payload.order_id = order.id

            db = AsyncMock()
            with pytest.raises(ValidationError, match="cancelled"):
                await self.svc.verify_and_fulfill(db, user_id, payload)

    async def test_invalid_signature_raises_validation_error(self):
        from app.core.exceptions import ValidationError

        user_id = uuid.uuid4()
        order = _make_order(user_id=user_id, status="payment_pending")

        with patch(
            "app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=order)
        ):
            payload = MagicMock()
            payload.order_id = order.id
            payload.razorpay_order_id = "rzp_ord_test"
            payload.razorpay_payment_id = "rzp_pay_test"
            payload.razorpay_signature = "bad_signature"

            db = AsyncMock()
            with pytest.raises(ValidationError, match="signature"):
                await self.svc.verify_and_fulfill(db, user_id, payload)

    async def test_order_not_found_raises_not_found(self):
        from app.core.exceptions import NotFoundError

        with patch(
            "app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=None)
        ):
            db = AsyncMock()
            payload = MagicMock()
            payload.order_id = uuid.uuid4()

            with pytest.raises(NotFoundError):
                await self.svc.verify_and_fulfill(db, uuid.uuid4(), payload)

    async def test_valid_payment_completes_reservations(self):
        """Happy path: valid HMAC → complete_reservations_for_order called, commit issued."""
        user_id = uuid.uuid4()
        order = _make_order(
            user_id=user_id, status="payment_pending", payment_status="pending"
        )
        order.coupon_id = None

        rzp_order_id = "rzp_ord_ABC"
        rzp_payment_id = "rzp_pay_XYZ"
        sig = self._valid_signature(rzp_order_id, rzp_payment_id)

        payload = MagicMock()
        payload.order_id = order.id
        payload.razorpay_order_id = rzp_order_id
        payload.razorpay_payment_id = rzp_payment_id
        payload.razorpay_signature = sig

        db = AsyncMock()
        # db.begin_nested() is used as an async context manager around the
        # payment insert (SAVEPOINT for the duplicate-payment race guard).
        nested_cm = AsyncMock()
        nested_cm.__aenter__ = AsyncMock(return_value=None)
        nested_cm.__aexit__ = AsyncMock(return_value=False)
        db.begin_nested = MagicMock(return_value=nested_cm)

        with patch(
            "app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=order)
        ):
            with patch(
                "app.modules.orders.service._reservation_svc.complete_reservations_for_order",
                AsyncMock(),
            ) as mock_complete:
                with patch(
                    "app.modules.cart.repository.CartRepository"
                ) as MockCartRepo:
                    MockCartRepo.return_value.get_for_user = AsyncMock(
                        return_value=None
                    )
                    with patch(
                        "app.modules.payments.repository.PaymentRepository"
                    ) as MockPayRepo:
                        MockPayRepo.return_value.create = AsyncMock()
                        with patch(
                            "app.modules.orders.service._repo.update", AsyncMock()
                        ):
                            with patch(
                                "app.modules.profiles.repository.ProfileRepository"
                            ) as MockProfile:
                                MockProfile.return_value.get_by_id = AsyncMock(
                                    return_value=None
                                )
                                with patch(
                                    "app.modules.orders.service.event_bus.publish",
                                    AsyncMock(),
                                ):
                                    response = await self.svc.verify_and_fulfill(
                                        db, user_id, payload
                                    )

        assert response.success is True
        mock_complete.assert_called_once_with(db, order.id)
        db.commit.assert_called_once()


# ── TestCreateFromCart (COD) ───────────────────────────────────────────────────


class TestCreateFromCartCOD:
    def setup_method(self):
        from app.modules.orders.service import OrderService

        self.svc = OrderService()

    async def test_reserves_and_links_on_checkout(self):
        """create_payment_intent: reserve_items and link_reservations_to_order are called."""
        user_id = uuid.uuid4()
        product_id = uuid.uuid4()
        cart_item = _make_cart_item(product_id=product_id, quantity=1)
        mock_cart = MagicMock()
        mock_cart.id = uuid.uuid4()
        mock_cart.items = [cart_item]

        prod_row = _make_product_row(
            product_id=product_id, base_price=500.0, tax_rate=3.0
        )
        db = _mock_db_for_line_items(prod_row)

        addr = _make_address()
        reservation = _make_reservation()
        mock_order = _make_order(user_id=user_id, status="payment_pending")

        payload = MagicMock()
        payload.shipping_address_id = uuid.uuid4()
        payload.billing_address_id = None
        payload.coupon_code = None
        payload.notes = None

        with patch("app.modules.cart.repository.CartRepository") as MockCartRepo:
            MockCartRepo.return_value.get_for_user = AsyncMock(return_value=mock_cart)
            with patch(
                "app.modules.addresses.repository.AddressRepository"
            ) as MockAddrRepo:
                MockAddrRepo.return_value.get = AsyncMock(return_value=addr)
                with patch(
                    "app.modules.orders.service._reservation_svc.reserve_items",
                    AsyncMock(return_value=[reservation]),
                ) as mock_reserve:
                    with patch(
                        "app.modules.orders.service._reservation_svc.link_reservations_to_order",
                        AsyncMock(),
                    ) as mock_link:
                        with patch(
                            "app.modules.orders.service._repo.generate_order_number",
                            AsyncMock(return_value="ORD-2024-001"),
                        ):
                            with patch(
                                "app.modules.orders.service._repo.create",
                                AsyncMock(return_value=mock_order),
                            ):
                                with patch(
                                    "app.modules.orders.service._repo.add_item",
                                    AsyncMock(),
                                ):
                                    with patch(
                                        "app.modules.orders.service._repo.update",
                                        AsyncMock(),
                                    ):
                                        with patch(
                                            "asyncio.get_running_loop"
                                        ) as mock_loop:
                                            mock_loop.return_value.run_in_executor = (
                                                AsyncMock(
                                                    return_value={
                                                        "id": "rzp_ord_cod_test"
                                                    }
                                                )
                                            )
                                            await self.svc.create_payment_intent(
                                                db, user_id, payload
                                            )

        mock_reserve.assert_called_once()
        mock_link.assert_called_once()

    async def test_cod_empty_cart_raises_validation_error(self):
        from app.core.exceptions import ValidationError

        db = AsyncMock()
        payload = MagicMock()
        payload.shipping_address_id = uuid.uuid4()
        payload.billing_address_id = None
        payload.coupon_code = None
        payload.notes = None
        payload.payment_method = "cod"

        with patch("app.modules.cart.repository.CartRepository") as MockCartRepo:
            MockCartRepo.return_value.get_for_user = AsyncMock(return_value=None)

            with pytest.raises(ValidationError, match="Cart is empty"):
                await self.svc.create_payment_intent(db, uuid.uuid4(), payload)


# ── TestCancelOrderReservation ────────────────────────────────────────────────


class TestCancelOrderReservation:
    def setup_method(self):
        from app.modules.orders.service import OrderService

        self.svc = OrderService()

    async def test_cancel_stock_reserved_order_releases_reservations(self):
        """Cancelling a stock_reserved order must release ACTIVE reservations."""
        user_id = uuid.uuid4()
        order = _make_order(
            user_id=user_id,
            status="stock_reserved",  # in _CANCELLABLE_STATUSES
            payment_status="pending",
        )
        payload = MagicMock()
        payload.reason = "Customer request"

        db = AsyncMock()
        mock_updated = MagicMock()

        with patch(
            "app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=order)
        ):
            with patch(
                "app.modules.orders.service._reservation_svc.release_order_reservations",
                AsyncMock(),
            ) as mock_release:
                with patch(
                    "app.modules.orders.service._repo.update",
                    AsyncMock(return_value=mock_updated),
                ):
                    with patch(
                        "app.modules.orders.service.event_bus.publish", AsyncMock()
                    ):
                        with patch(
                            "app.modules.orders.schemas.OrderResponse.model_validate",
                            MagicMock(return_value=MagicMock()),
                        ):
                            # Note: cancel_order signature is (db, order_id, user_id, payload)
                            await self.svc.cancel_order(db, order.id, user_id, payload)

        mock_release.assert_called_once_with(db, order.id, reason="RELEASED")

    async def test_cancel_pending_order_releases_reservations(self):
        """Cancelling a 'pending' order also releases reservations."""
        user_id = uuid.uuid4()
        order = _make_order(
            user_id=user_id,
            status="pending",
            payment_status="pending",
        )
        payload = MagicMock()
        payload.reason = "Changed mind"

        db = AsyncMock()
        mock_updated = MagicMock()

        with patch(
            "app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=order)
        ):
            with patch(
                "app.modules.orders.service._reservation_svc.release_order_reservations",
                AsyncMock(),
            ) as mock_release:
                with patch(
                    "app.modules.orders.service._repo.update",
                    AsyncMock(return_value=mock_updated),
                ):
                    with patch(
                        "app.modules.orders.service.event_bus.publish", AsyncMock()
                    ):
                        with patch(
                            "app.modules.orders.schemas.OrderResponse.model_validate",
                            MagicMock(return_value=MagicMock()),
                        ):
                            await self.svc.cancel_order(db, order.id, user_id, payload)

        mock_release.assert_called_once_with(db, order.id, reason="RELEASED")

    async def test_cancel_shipped_order_raises_validation_error(self):
        from app.core.exceptions import ValidationError

        user_id = uuid.uuid4()
        order = _make_order(user_id=user_id, status="shipped", payment_status="paid")
        payload = MagicMock()
        payload.reason = "Changed mind"

        with patch(
            "app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=order)
        ):
            db = AsyncMock()
            with pytest.raises(ValidationError):
                await self.svc.cancel_order(db, order.id, user_id, payload)

    async def test_cancel_order_not_found_raises_not_found(self):
        from app.core.exceptions import NotFoundError

        with patch(
            "app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=None)
        ):
            db = AsyncMock()
            payload = MagicMock()
            payload.reason = "test"
            with pytest.raises(NotFoundError):
                await self.svc.cancel_order(db, uuid.uuid4(), uuid.uuid4(), payload)

    async def test_cancel_wrong_user_raises_not_found(self):
        from app.core.exceptions import NotFoundError

        owner_id = uuid.uuid4()
        other_user = uuid.uuid4()
        order = _make_order(user_id=owner_id, status="pending")
        payload = MagicMock()
        payload.reason = "test"

        with patch(
            "app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=order)
        ):
            db = AsyncMock()
            with pytest.raises(NotFoundError):
                await self.svc.cancel_order(db, order.id, other_user, payload)

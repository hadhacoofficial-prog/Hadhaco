"""Tests for OrderService.create_from_cart success path."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.modules.addresses.models  # noqa: F401
import app.modules.cart.models  # noqa: F401

# Force mapper init
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


def _make_cart_item(product_id=None, variant_id=None, quantity=2):
    ci = MagicMock()
    ci.product_id = product_id or uuid.uuid4()
    ci.variant_id = variant_id
    ci.quantity = quantity
    return ci


def _make_prod_row(
    name="Ring",
    sku="RNG-001",
    base_price=500.0,
    tax_rate=3.0,
    stock_quantity=10,
    allow_backorder=False,
    track_inventory=True,
    variant_name=None,
    price_adj=0.0,
):
    row = MagicMock()
    row.name = name
    row.sku = sku
    row.base_price = base_price
    row.tax_rate = tax_rate
    row.stock_quantity = stock_quantity
    row.allow_backorder = allow_backorder
    row.track_inventory = track_inventory
    row.variant_name = variant_name
    row.price_adj = price_adj
    return row


def _make_address():
    addr = MagicMock()
    addr.full_name = "Haris"
    addr.phone = "9999999999"
    addr.line1 = "123 Main St"
    addr.line2 = ""
    addr.city = "Hyderabad"
    addr.state = "Telangana"
    addr.postal_code = "500001"
    addr.country = "IN"
    return addr


class TestOrderServiceCreateFromCart:
    def setup_method(self):
        from app.modules.orders.service import OrderService

        self.svc = OrderService()

    async def test_create_from_cart_success_no_coupon(self):
        from app.modules.addresses.repository import AddressRepository
        from app.modules.cart.repository import CartRepository
        from app.modules.inventory.service import InventoryService
        from app.modules.orders.schemas import CreateOrderRequest, OrderResponse
        from app.modules.profiles.repository import ProfileRepository

        user_id = uuid.uuid4()
        addr_id = uuid.uuid4()
        product_id = uuid.uuid4()
        cart_item = _make_cart_item(product_id=product_id, quantity=2)
        mock_cart = MagicMock()
        mock_cart.id = uuid.uuid4()
        mock_cart.items = [cart_item]

        mock_addr = _make_address()
        prod_row = _make_prod_row(base_price=500.0, tax_rate=3.0, stock_quantity=10)

        # db.execute returns fetchone row for product query
        prod_result = MagicMock()
        prod_result.fetchone.return_value = prod_row
        db = AsyncMock()
        db.execute = AsyncMock(return_value=prod_result)
        db.commit = AsyncMock()

        mock_order = MagicMock()
        mock_order.id = uuid.uuid4()
        mock_order.items = []

        mock_profile = MagicMock()
        mock_profile.email = "haris@example.com"
        mock_profile.phone = "9999999999"

        mock_final_order = MagicMock()
        mock_response = MagicMock()

        with (
            patch.object(CartRepository, "get_for_user", AsyncMock(return_value=mock_cart)),
            patch.object(AddressRepository, "get", AsyncMock(return_value=mock_addr)),
            patch(
                "app.modules.orders.service._repo.generate_order_number",
                AsyncMock(return_value="ORD-2026-0001"),
            ),
            patch("app.modules.orders.service._repo.create", AsyncMock(return_value=mock_order)),
            patch("app.modules.orders.service._repo.add_item", AsyncMock()),
            patch.object(InventoryService, "record_movement", AsyncMock()),
            patch.object(CartRepository, "clear_items", AsyncMock()),
            patch.object(ProfileRepository, "get_by_id", AsyncMock(return_value=mock_profile)),
            patch("app.core.events.event_bus.publish", AsyncMock()),
            patch(
                "app.modules.orders.service._repo.get_by_id",
                AsyncMock(return_value=mock_final_order),
            ),
            patch.object(OrderResponse, "model_validate", return_value=mock_response),
        ):
            result = await self.svc.create_from_cart(
                db,
                user_id=user_id,
                payload=CreateOrderRequest(
                    shipping_address_id=addr_id,
                    payment_method="razorpay",
                ),
            )

        assert result is mock_response

    async def test_create_from_cart_product_not_found_raises(self):
        from app.core.exceptions import ValidationError
        from app.modules.addresses.repository import AddressRepository
        from app.modules.cart.repository import CartRepository
        from app.modules.orders.schemas import CreateOrderRequest

        user_id = uuid.uuid4()
        cart_item = _make_cart_item()
        mock_cart = MagicMock()
        mock_cart.items = [cart_item]
        mock_addr = _make_address()

        # Product row returns None
        none_result = MagicMock()
        none_result.fetchone.return_value = None
        db = AsyncMock()
        db.execute = AsyncMock(return_value=none_result)

        with (
            patch.object(CartRepository, "get_for_user", AsyncMock(return_value=mock_cart)),
            patch.object(AddressRepository, "get", AsyncMock(return_value=mock_addr)),
            patch(
                "app.modules.orders.service._repo.generate_order_number",
                AsyncMock(return_value="ORD-2026-0001"),
            ),
        ):
            with pytest.raises(ValidationError, match="no longer available"):
                await self.svc.create_from_cart(
                    db,
                    user_id=user_id,
                    payload=CreateOrderRequest(
                        shipping_address_id=uuid.uuid4(),
                        payment_method="razorpay",
                    ),
                )

    async def test_create_from_cart_insufficient_stock_raises(self):
        from app.core.exceptions import ValidationError
        from app.modules.addresses.repository import AddressRepository
        from app.modules.cart.repository import CartRepository
        from app.modules.orders.schemas import CreateOrderRequest

        user_id = uuid.uuid4()
        # Request 10, only 3 in stock, no backorder
        cart_item = _make_cart_item(quantity=10)
        mock_cart = MagicMock()
        mock_cart.items = [cart_item]
        mock_addr = _make_address()

        prod_row = _make_prod_row(stock_quantity=3, track_inventory=True, allow_backorder=False)
        prod_result = MagicMock()
        prod_result.fetchone.return_value = prod_row
        db = AsyncMock()
        db.execute = AsyncMock(return_value=prod_result)

        with (
            patch.object(CartRepository, "get_for_user", AsyncMock(return_value=mock_cart)),
            patch.object(AddressRepository, "get", AsyncMock(return_value=mock_addr)),
            patch(
                "app.modules.orders.service._repo.generate_order_number",
                AsyncMock(return_value="ORD-2026-0001"),
            ),
        ):
            with pytest.raises(ValidationError, match="Insufficient stock"):
                await self.svc.create_from_cart(
                    db,
                    user_id=user_id,
                    payload=CreateOrderRequest(
                        shipping_address_id=uuid.uuid4(),
                        payment_method="razorpay",
                    ),
                )

    async def test_create_from_cart_with_billing_address(self):
        from app.modules.addresses.repository import AddressRepository
        from app.modules.cart.repository import CartRepository
        from app.modules.inventory.service import InventoryService
        from app.modules.orders.schemas import CreateOrderRequest, OrderResponse
        from app.modules.profiles.repository import ProfileRepository

        user_id = uuid.uuid4()
        cart_item = _make_cart_item(quantity=1)
        mock_cart = MagicMock()
        mock_cart.id = uuid.uuid4()
        mock_cart.items = [cart_item]

        mock_addr = _make_address()
        prod_row = _make_prod_row(base_price=200.0, tax_rate=0.0)
        prod_result = MagicMock()
        prod_result.fetchone.return_value = prod_row
        db = AsyncMock()
        db.execute = AsyncMock(return_value=prod_result)

        mock_order = MagicMock()
        mock_order.id = uuid.uuid4()
        mock_order.items = []
        mock_final_order = MagicMock()
        mock_response = MagicMock()
        mock_profile = MagicMock()
        mock_profile.email = "test@example.com"
        mock_profile.phone = None

        with (
            patch.object(CartRepository, "get_for_user", AsyncMock(return_value=mock_cart)),
            patch.object(AddressRepository, "get", AsyncMock(return_value=mock_addr)),
            patch(
                "app.modules.orders.service._repo.generate_order_number",
                AsyncMock(return_value="ORD-2026-0002"),
            ),
            patch("app.modules.orders.service._repo.create", AsyncMock(return_value=mock_order)),
            patch("app.modules.orders.service._repo.add_item", AsyncMock()),
            patch.object(InventoryService, "record_movement", AsyncMock()),
            patch.object(CartRepository, "clear_items", AsyncMock()),
            patch.object(ProfileRepository, "get_by_id", AsyncMock(return_value=mock_profile)),
            patch("app.core.events.event_bus.publish", AsyncMock()),
            patch(
                "app.modules.orders.service._repo.get_by_id",
                AsyncMock(return_value=mock_final_order),
            ),
            patch.object(OrderResponse, "model_validate", return_value=mock_response),
        ):
            result = await self.svc.create_from_cart(
                db,
                user_id=user_id,
                payload=CreateOrderRequest(
                    shipping_address_id=uuid.uuid4(),
                    billing_address_id=uuid.uuid4(),  # separate billing
                    payment_method="cod",
                ),
            )
        assert result is mock_response

    async def test_create_from_cart_with_coupon(self):
        from app.modules.addresses.repository import AddressRepository
        from app.modules.cart.repository import CartRepository
        from app.modules.coupons.repository import CouponRepository
        from app.modules.coupons.service import CouponService
        from app.modules.inventory.service import InventoryService
        from app.modules.orders.schemas import CreateOrderRequest, OrderResponse
        from app.modules.profiles.repository import ProfileRepository

        user_id = uuid.uuid4()
        coupon_id = uuid.uuid4()
        cart_item = _make_cart_item(quantity=2)
        mock_cart = MagicMock()
        mock_cart.id = uuid.uuid4()
        mock_cart.items = [cart_item]

        mock_addr = _make_address()
        prod_row = _make_prod_row(base_price=600.0, tax_rate=3.0, stock_quantity=10)
        prod_result = MagicMock()
        prod_result.fetchone.return_value = prod_row
        db = AsyncMock()
        db.execute = AsyncMock(return_value=prod_result)

        mock_order = MagicMock()
        mock_order.id = uuid.uuid4()
        mock_order.items = []
        mock_coupon = MagicMock()
        mock_coupon.coupon_type = "percentage"
        mock_final_order = MagicMock()
        mock_response = MagicMock()
        mock_profile = MagicMock()
        mock_profile.email = "test@example.com"
        mock_profile.phone = "9999999999"

        with (
            patch.object(CartRepository, "get_for_user", AsyncMock(return_value=mock_cart)),
            patch.object(AddressRepository, "get", AsyncMock(return_value=mock_addr)),
            patch(
                "app.modules.orders.service._repo.generate_order_number",
                AsyncMock(return_value="ORD-2026-0003"),
            ),
            patch("app.modules.orders.service._repo.create", AsyncMock(return_value=mock_order)),
            patch("app.modules.orders.service._repo.add_item", AsyncMock()),
            patch.object(
                CouponService, "apply_and_reserve", AsyncMock(return_value=(50.0, coupon_id))
            ),
            patch.object(CouponRepository, "get_by_id", AsyncMock(return_value=mock_coupon)),
            patch.object(CouponService, "finalize_usage", AsyncMock()),
            patch.object(InventoryService, "record_movement", AsyncMock()),
            patch.object(CartRepository, "clear_items", AsyncMock()),
            patch.object(ProfileRepository, "get_by_id", AsyncMock(return_value=mock_profile)),
            patch("app.core.events.event_bus.publish", AsyncMock()),
            patch(
                "app.modules.orders.service._repo.get_by_id",
                AsyncMock(return_value=mock_final_order),
            ),
            patch.object(OrderResponse, "model_validate", return_value=mock_response),
        ):
            result = await self.svc.create_from_cart(
                db,
                user_id=user_id,
                payload=CreateOrderRequest(
                    shipping_address_id=uuid.uuid4(),
                    payment_method="razorpay",
                    coupon_code="SAVE10",
                ),
            )
        assert result is mock_response

    async def test_create_from_cart_free_shipping_coupon(self):
        """A free_shipping coupon type overrides shipping charge."""
        from app.modules.addresses.repository import AddressRepository
        from app.modules.cart.repository import CartRepository
        from app.modules.coupons.repository import CouponRepository
        from app.modules.coupons.service import CouponService
        from app.modules.inventory.service import InventoryService
        from app.modules.orders.schemas import CreateOrderRequest, OrderResponse
        from app.modules.profiles.repository import ProfileRepository

        user_id = uuid.uuid4()
        coupon_id = uuid.uuid4()
        cart_item = _make_cart_item(quantity=1)
        mock_cart = MagicMock()
        mock_cart.id = uuid.uuid4()
        mock_cart.items = [cart_item]

        mock_addr = _make_address()
        # low price so shipping charge would apply (< 999)
        prod_row = _make_prod_row(base_price=200.0, tax_rate=0.0, stock_quantity=5)
        prod_result = MagicMock()
        prod_result.fetchone.return_value = prod_row
        db = AsyncMock()
        db.execute = AsyncMock(return_value=prod_result)

        mock_order = MagicMock()
        mock_order.id = uuid.uuid4()
        mock_order.items = []
        # coupon_type = free_shipping
        mock_coupon = MagicMock()
        mock_coupon.coupon_type = "free_shipping"
        mock_response = MagicMock()
        mock_profile = MagicMock()
        mock_profile.email = "t@t.com"
        mock_profile.phone = None

        with (
            patch.object(CartRepository, "get_for_user", AsyncMock(return_value=mock_cart)),
            patch.object(AddressRepository, "get", AsyncMock(return_value=mock_addr)),
            patch(
                "app.modules.orders.service._repo.generate_order_number",
                AsyncMock(return_value="ORD-2026-0004"),
            ),
            patch("app.modules.orders.service._repo.create", AsyncMock(return_value=mock_order)),
            patch("app.modules.orders.service._repo.add_item", AsyncMock()),
            patch.object(
                CouponService, "apply_and_reserve", AsyncMock(return_value=(0.0, coupon_id))
            ),
            patch.object(CouponRepository, "get_by_id", AsyncMock(return_value=mock_coupon)),
            patch.object(CouponService, "finalize_usage", AsyncMock()),
            patch.object(InventoryService, "record_movement", AsyncMock()),
            patch.object(CartRepository, "clear_items", AsyncMock()),
            patch.object(ProfileRepository, "get_by_id", AsyncMock(return_value=mock_profile)),
            patch("app.core.events.event_bus.publish", AsyncMock()),
            patch(
                "app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=MagicMock())
            ),
            patch.object(OrderResponse, "model_validate", return_value=mock_response),
        ):
            result = await self.svc.create_from_cart(
                db,
                user_id=user_id,
                payload=CreateOrderRequest(
                    shipping_address_id=uuid.uuid4(),
                    payment_method="cod",
                    coupon_code="FREESHIP",
                ),
            )
        assert result is mock_response

    async def test_create_from_cart_no_inventory_tracking(self):
        """track_inventory=False skips stock check."""
        from app.modules.addresses.repository import AddressRepository
        from app.modules.cart.repository import CartRepository
        from app.modules.inventory.service import InventoryService
        from app.modules.orders.schemas import CreateOrderRequest, OrderResponse
        from app.modules.profiles.repository import ProfileRepository

        user_id = uuid.uuid4()
        # Requesting 100, only 1 in stock, but tracking disabled
        cart_item = _make_cart_item(quantity=100)
        mock_cart = MagicMock()
        mock_cart.id = uuid.uuid4()
        mock_cart.items = [cart_item]

        mock_addr = _make_address()
        prod_row = _make_prod_row(stock_quantity=1, track_inventory=False)
        prod_result = MagicMock()
        prod_result.fetchone.return_value = prod_row
        db = AsyncMock()
        db.execute = AsyncMock(return_value=prod_result)

        mock_order = MagicMock()
        mock_order.id = uuid.uuid4()
        mock_order.items = []
        mock_response = MagicMock()
        mock_profile = MagicMock()
        mock_profile.email = "a@b.com"
        mock_profile.phone = None

        with (
            patch.object(CartRepository, "get_for_user", AsyncMock(return_value=mock_cart)),
            patch.object(AddressRepository, "get", AsyncMock(return_value=mock_addr)),
            patch(
                "app.modules.orders.service._repo.generate_order_number",
                AsyncMock(return_value="ORD-2026-0005"),
            ),
            patch("app.modules.orders.service._repo.create", AsyncMock(return_value=mock_order)),
            patch("app.modules.orders.service._repo.add_item", AsyncMock()),
            patch.object(InventoryService, "record_movement", AsyncMock()),
            patch.object(CartRepository, "clear_items", AsyncMock()),
            patch.object(ProfileRepository, "get_by_id", AsyncMock(return_value=mock_profile)),
            patch("app.core.events.event_bus.publish", AsyncMock()),
            patch(
                "app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=MagicMock())
            ),
            patch.object(OrderResponse, "model_validate", return_value=mock_response),
        ):
            result = await self.svc.create_from_cart(
                db,
                user_id=user_id,
                payload=CreateOrderRequest(
                    shipping_address_id=uuid.uuid4(), payment_method="razorpay"
                ),
            )
        assert result is mock_response

    async def test_create_from_cart_address_not_found_raises(self):
        from app.core.exceptions import NotFoundError
        from app.modules.addresses.repository import AddressRepository
        from app.modules.cart.repository import CartRepository
        from app.modules.orders.schemas import CreateOrderRequest

        user_id = uuid.uuid4()
        mock_cart = MagicMock()
        mock_cart.items = [_make_cart_item()]

        db = AsyncMock()

        with (
            patch.object(CartRepository, "get_for_user", AsyncMock(return_value=mock_cart)),
            patch.object(AddressRepository, "get", AsyncMock(return_value=None)),
        ):
            with pytest.raises(NotFoundError, match="Address not found"):
                await self.svc.create_from_cart(
                    db,
                    user_id=user_id,
                    payload=CreateOrderRequest(
                        shipping_address_id=uuid.uuid4(), payment_method="razorpay"
                    ),
                )

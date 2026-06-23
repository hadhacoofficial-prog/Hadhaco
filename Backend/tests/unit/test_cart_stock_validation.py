"""Tests for CartService stock-validation logic added in the reservation refactor.

Cart validates available stock on add/update but does NOT reserve it.
Stock formula: available = stock_quantity - reserved_quantity - sold_quantity.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _stock_row(
    available: int, track: bool = True, backorder: bool = False
) -> MagicMock:
    """Build a fake fetchone() row for _fetch_available_stock."""
    row = MagicMock()
    # row[0] = available, row[1] = track_inventory, row[2] = allow_backorder
    row.__getitem__ = lambda self, i: [available, track, backorder][i]
    return row


def _fetch_result(row) -> MagicMock:
    result = MagicMock()
    result.fetchone.return_value = row
    return result


# ── TestFetchAvailableStock ───────────────────────────────────────────────────


class TestFetchAvailableStock:
    def setup_method(self):
        from app.modules.cart.service import CartService

        self.svc = CartService()

    async def test_returns_computed_available(self):
        product_id = uuid.uuid4()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_fetch_result(_stock_row(7)))

        result = await self.svc._fetch_available_stock(db, product_id)

        assert result == 7

    async def test_returns_large_number_when_track_inventory_false(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_fetch_result(_stock_row(0, track=False)))

        result = await self.svc._fetch_available_stock(db, uuid.uuid4())

        assert result == 999_999

    async def test_returns_large_number_when_backorder_allowed(self):
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=_fetch_result(_stock_row(0, backorder=True))
        )

        result = await self.svc._fetch_available_stock(db, uuid.uuid4())

        assert result == 999_999

    async def test_product_not_found_raises_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_fetch_result(None))

        with pytest.raises(NotFoundError):
            await self.svc._fetch_available_stock(db, uuid.uuid4())


# ── TestAddItemStockValidation ────────────────────────────────────────────────


class TestAddItemStockValidation:
    def setup_method(self):
        from app.modules.cart.service import CartService

        self.svc = CartService()

    def _payload(self, product_id: uuid.UUID | None = None, quantity: int = 1):
        p = MagicMock()
        p.product_id = product_id or uuid.uuid4()
        p.quantity = quantity
        p.variant_id = None
        return p

    async def test_out_of_stock_raises_inventory_error(self):
        from app.core.exceptions import InventoryError

        db = AsyncMock()
        payload = self._payload(quantity=1)

        with patch.object(
            self.svc, "_fetch_available_stock", AsyncMock(return_value=0)
        ):
            with pytest.raises(InventoryError, match="out of stock"):
                await self.svc.add_item(db, payload, user_id=uuid.uuid4())

    async def test_quantity_exceeds_available_raises_inventory_error(self):
        from app.core.exceptions import InventoryError

        db = AsyncMock()
        payload = self._payload(quantity=5)

        with patch.object(
            self.svc, "_fetch_available_stock", AsyncMock(return_value=3)
        ):
            with pytest.raises(InventoryError, match="3 item"):
                await self.svc.add_item(db, payload, user_id=uuid.uuid4())

    async def test_quantity_within_available_proceeds(self):
        db = AsyncMock()
        product_id = uuid.uuid4()
        payload = self._payload(product_id=product_id, quantity=2)

        mock_cart = MagicMock()
        mock_cart.id = uuid.uuid4()
        mock_cart.items = []
        mock_cart.discount = 0.0
        mock_cart.coupon_code = None
        mock_cart.expires_at = datetime.now(UTC) + timedelta(days=30)

        with patch.object(
            self.svc, "_fetch_available_stock", AsyncMock(return_value=10)
        ):
            with patch.object(
                self.svc, "_get_or_create", AsyncMock(return_value=mock_cart)
            ):
                with patch.object(
                    self.svc, "_fetch_product_price", AsyncMock(return_value=500.0)
                ):
                    with patch(
                        "app.modules.cart.service._repo.upsert_item", AsyncMock()
                    ):
                        with patch(
                            "app.modules.cart.service._repo.get_by_id",
                            AsyncMock(return_value=mock_cart),
                        ):
                            result = await self.svc.add_item(
                                db, payload, user_id=uuid.uuid4()
                            )

        assert result is not None

    async def test_exactly_available_quantity_is_accepted(self):
        """Boundary: qty == available should be accepted (no InventoryError raised)."""
        db = AsyncMock()
        payload = self._payload(quantity=5)

        mock_cart = MagicMock()
        mock_cart.id = uuid.uuid4()
        mock_cart.items = []
        mock_cart.discount = 0.0
        mock_cart.coupon_code = None
        mock_cart.expires_at = datetime.now(UTC) + timedelta(days=30)

        with patch.object(
            self.svc, "_fetch_available_stock", AsyncMock(return_value=5)
        ):
            with patch.object(
                self.svc, "_get_or_create", AsyncMock(return_value=mock_cart)
            ):
                with patch.object(
                    self.svc, "_fetch_product_price", AsyncMock(return_value=100.0)
                ):
                    with patch(
                        "app.modules.cart.service._repo.upsert_item", AsyncMock()
                    ):
                        with patch(
                            "app.modules.cart.service._repo.get_by_id",
                            AsyncMock(return_value=mock_cart),
                        ):
                            # Should not raise
                            await self.svc.add_item(db, payload, user_id=uuid.uuid4())


# ── TestUpdateItemStockValidation ─────────────────────────────────────────────


class TestUpdateItemStockValidation:
    def setup_method(self):
        from app.modules.cart.service import CartService

        self.svc = CartService()

    def _make_cart_with_item(self, item_id: uuid.UUID, product_id: uuid.UUID, qty: int):
        item = MagicMock()
        item.id = item_id
        item.product_id = product_id
        item.quantity = qty
        item.unit_price = 100.0

        cart = MagicMock()
        cart.id = uuid.uuid4()
        cart.user_id = uuid.uuid4()
        cart.items = [item]
        cart.discount = 0.0
        cart.coupon_code = None
        cart.expires_at = None
        return cart

    async def test_increase_quantity_above_available_raises(self):
        from app.core.exceptions import InventoryError

        item_id = uuid.uuid4()
        product_id = uuid.uuid4()
        cart = self._make_cart_with_item(item_id, product_id, qty=2)
        user_id = cart.user_id

        db = AsyncMock()
        payload = MagicMock()
        payload.quantity = 10  # increasing from 2 to 10

        with patch(
            "app.modules.cart.service._repo.get_by_id", AsyncMock(return_value=cart)
        ):
            with patch.object(
                self.svc, "_fetch_available_stock", AsyncMock(return_value=5)
            ):
                with pytest.raises(InventoryError, match="5 item"):
                    await self.svc.update_item(
                        db, cart.id, item_id, payload, user_id=user_id
                    )

    async def test_decrease_quantity_skips_stock_check(self):
        """Decreasing quantity never triggers a stock check."""
        item_id = uuid.uuid4()
        product_id = uuid.uuid4()
        cart = self._make_cart_with_item(item_id, product_id, qty=5)
        user_id = cart.user_id

        db = AsyncMock()
        payload = MagicMock()
        payload.quantity = 2  # decreasing from 5 to 2

        updated_cart = MagicMock()
        updated_cart.id = cart.id
        updated_cart.items = []
        updated_cart.discount = 0.0
        updated_cart.coupon_code = None
        updated_cart.expires_at = datetime.now(UTC) + timedelta(days=30)

        with patch(
            "app.modules.cart.service._repo.get_by_id",
            AsyncMock(side_effect=[cart, updated_cart]),
        ):
            with patch(
                "app.modules.cart.service._repo.update_item_quantity", AsyncMock()
            ):
                with patch.object(
                    self.svc, "_fetch_available_stock", AsyncMock(return_value=3)
                ) as mock_fetch:
                    await self.svc.update_item(
                        db, cart.id, item_id, payload, user_id=user_id
                    )
                    # Stock check should NOT have been called (quantity decreased)
                    mock_fetch.assert_not_called()

    async def test_same_quantity_no_stock_check(self):
        """Setting the same quantity as current — no stock check needed."""
        item_id = uuid.uuid4()
        product_id = uuid.uuid4()
        cart = self._make_cart_with_item(item_id, product_id, qty=3)
        user_id = cart.user_id

        db = AsyncMock()
        payload = MagicMock()
        payload.quantity = 3  # no change

        updated_cart = MagicMock()
        updated_cart.id = cart.id
        updated_cart.items = []
        updated_cart.discount = 0.0
        updated_cart.coupon_code = None
        updated_cart.expires_at = datetime.now(UTC) + timedelta(days=30)

        with patch(
            "app.modules.cart.service._repo.get_by_id",
            AsyncMock(side_effect=[cart, updated_cart]),
        ):
            with patch(
                "app.modules.cart.service._repo.update_item_quantity", AsyncMock()
            ):
                with patch.object(
                    self.svc, "_fetch_available_stock", AsyncMock(return_value=5)
                ) as mock_fetch:
                    await self.svc.update_item(
                        db, cart.id, item_id, payload, user_id=user_id
                    )
                    mock_fetch.assert_not_called()

    async def test_cart_not_found_raises_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        payload = MagicMock()
        payload.quantity = 1

        with patch(
            "app.modules.cart.service._repo.get_by_id", AsyncMock(return_value=None)
        ):
            with pytest.raises(NotFoundError, match="Cart not found"):
                await self.svc.update_item(
                    db, uuid.uuid4(), uuid.uuid4(), payload, user_id=uuid.uuid4()
                )

    async def test_item_not_found_raises_not_found(self):
        from app.core.exceptions import NotFoundError

        cart = MagicMock()
        cart.id = uuid.uuid4()
        cart.user_id = uuid.uuid4()
        cart.items = []  # empty — item not in cart

        db = AsyncMock()
        payload = MagicMock()
        payload.quantity = 1

        with patch(
            "app.modules.cart.service._repo.get_by_id", AsyncMock(return_value=cart)
        ):
            with pytest.raises(NotFoundError, match="Cart item not found"):
                await self.svc.update_item(
                    db, cart.id, uuid.uuid4(), payload, user_id=cart.user_id
                )

"""Tests for CartService.replace_items (PUT /cart/items).

Replaces the checkout's DELETE /cart + one POST per line with a single call,
so it must keep add_item's per-line validation and never write a partial cart.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.cart.schemas import AddToCartRequest, ReplaceCartItemsRequest


def _cart() -> MagicMock:
    cart = MagicMock()
    cart.id = uuid.uuid4()
    cart.items = []
    cart.discount = 0.0
    cart.coupon_code = None
    cart.expires_at = datetime.now(UTC) + timedelta(days=30)
    return cart


class TestReplaceItems:
    def setup_method(self):
        from app.modules.cart.service import CartService

        self.svc = CartService()
        self.svc._own_active_reserved_qty = AsyncMock(return_value=0)
        self.cart = _cart()
        self.svc._get_or_create = AsyncMock(return_value=self.cart)
        self.clear_items = AsyncMock()
        self.update_cart = AsyncMock()
        self.upsert_item = AsyncMock()
        self._patches = [
            patch("app.modules.cart.service._repo.clear_items", self.clear_items),
            patch("app.modules.cart.service._repo.update_cart", self.update_cart),
            patch("app.modules.cart.service._repo.upsert_item", self.upsert_item),
            patch(
                "app.modules.cart.service._repo.get_by_id",
                AsyncMock(return_value=self.cart),
            ),
        ]
        for p in self._patches:
            p.start()

    def teardown_method(self):
        for p in self._patches:
            p.stop()

    async def test_replaces_cart_with_validated_lines(self):
        p1, v1, p2, v2 = (uuid.uuid4() for _ in range(4))
        payload = ReplaceCartItemsRequest(
            items=[
                AddToCartRequest(product_id=p1, variant_id=v1, quantity=2),
                AddToCartRequest(product_id=p2, variant_id=v2, quantity=1),
            ]
        )
        self.svc._fetch_add_item_validations = AsyncMock(
            side_effect=[(10, True, False, 0, 500.0), (10, True, False, 0, 250.0)]
        )

        result = await self.svc.replace_items(
            AsyncMock(), payload, user_id=uuid.uuid4()
        )

        assert result is not None
        self.clear_items.assert_awaited_once()
        assert self.clear_items.await_args.args[1] == self.cart.id
        self.update_cart.assert_awaited_once()
        assert [c.args[2:] for c in self.upsert_item.await_args_list] == [
            (p1, v1, 2, 500.0),
            (p2, v2, 1, 250.0),
        ]

    async def test_invalid_line_leaves_cart_untouched(self):
        from app.core.exceptions import InventoryError

        payload = ReplaceCartItemsRequest(
            items=[
                AddToCartRequest(
                    product_id=uuid.uuid4(), variant_id=uuid.uuid4(), quantity=1
                ),
                AddToCartRequest(
                    product_id=uuid.uuid4(), variant_id=uuid.uuid4(), quantity=5
                ),
            ]
        )
        self.svc._fetch_add_item_validations = AsyncMock(
            side_effect=[(10, True, False, 0, 100.0), (2, True, False, 0, 100.0)]
        )

        with pytest.raises(InventoryError):
            await self.svc.replace_items(AsyncMock(), payload, user_id=uuid.uuid4())

        self.clear_items.assert_not_awaited()
        self.upsert_item.assert_not_awaited()

    async def test_max_order_quantity_enforced(self):
        from app.core.exceptions import ValidationError

        payload = ReplaceCartItemsRequest(
            items=[
                AddToCartRequest(
                    product_id=uuid.uuid4(), variant_id=uuid.uuid4(), quantity=3
                )
            ]
        )
        self.svc._fetch_add_item_validations = AsyncMock(
            return_value=(10, True, False, 2, 100.0)
        )

        with pytest.raises(ValidationError, match="Maximum 2"):
            await self.svc.replace_items(AsyncMock(), payload, user_id=uuid.uuid4())

        self.clear_items.assert_not_awaited()

    async def test_duplicate_lines_rejected(self):
        """upsert_item sums quantities, so duplicates would bypass per-line limits."""
        from app.core.exceptions import ValidationError

        pid, vid = uuid.uuid4(), uuid.uuid4()
        payload = ReplaceCartItemsRequest(
            items=[
                AddToCartRequest(product_id=pid, variant_id=vid, quantity=2),
                AddToCartRequest(product_id=pid, variant_id=vid, quantity=2),
            ]
        )
        self.svc._fetch_add_item_validations = AsyncMock(
            return_value=(10, True, False, 2, 100.0)
        )

        with pytest.raises(ValidationError, match="Duplicate"):
            await self.svc.replace_items(AsyncMock(), payload, user_id=uuid.uuid4())

        self.clear_items.assert_not_awaited()

    async def test_duplicate_detected_after_default_variant_resolution(self):
        pid, default_vid = uuid.uuid4(), uuid.uuid4()
        self.svc._resolve_default_variant_id = AsyncMock(return_value=default_vid)
        payload = ReplaceCartItemsRequest(
            items=[
                AddToCartRequest(product_id=pid, variant_id=None, quantity=1),
                AddToCartRequest(product_id=pid, variant_id=default_vid, quantity=1),
            ]
        )
        self.svc._fetch_add_item_validations = AsyncMock(
            return_value=(10, True, False, 0, 100.0)
        )

        from app.core.exceptions import ValidationError

        with pytest.raises(ValidationError, match="Duplicate"):
            await self.svc.replace_items(AsyncMock(), payload, user_id=uuid.uuid4())

    async def test_empty_items_clears_cart(self):
        payload = ReplaceCartItemsRequest(items=[])

        await self.svc.replace_items(AsyncMock(), payload, user_id=uuid.uuid4())

        self.clear_items.assert_awaited_once()
        self.upsert_item.assert_not_awaited()


def test_rejects_more_than_50_items():
    from pydantic import ValidationError

    item = {"product_id": str(uuid.uuid4()), "quantity": 1}
    with pytest.raises(ValidationError):
        ReplaceCartItemsRequest.model_validate({"items": [item] * 51})

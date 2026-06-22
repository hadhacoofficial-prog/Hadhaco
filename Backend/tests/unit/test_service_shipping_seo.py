"""Tests for ShippingService (pure function + error paths) and SeoService."""

import uuid
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─── _map_do_status pure function ────────────────────────────────────────────


class TestMapDoStatus:
    def _fn(self, s):
        from app.modules.shipping.service import _map_do_status

        return _map_do_status(s)

    def test_created(self):
        assert self._fn("CREATED") == "created"

    def test_pickup_scheduled(self):
        assert self._fn("PICKUP_SCHEDULED") == "created"

    def test_picked_up(self):
        assert self._fn("PICKED_UP") == "picked_up"

    def test_in_transit(self):
        assert self._fn("IN_TRANSIT") == "in_transit"

    def test_out_for_delivery(self):
        assert self._fn("OUT_FOR_DELIVERY") == "out_for_delivery"

    def test_delivered(self):
        assert self._fn("DELIVERED") == "delivered"

    def test_cancelled(self):
        assert self._fn("CANCELLED") == "cancelled"

    def test_failed(self):
        assert self._fn("FAILED") == "failed"

    def test_rto_maps_to_failed(self):
        assert self._fn("RTO") == "failed"

    def test_unknown_defaults_to_in_transit(self):
        assert self._fn("MYSTERY_STATUS") == "in_transit"

    def test_lowercase_input_accepted(self):
        assert self._fn("delivered") == "delivered"


# ─── ShippingService error paths ──────────────────────────────────────────────


class TestShippingServiceCreateShipment:
    def setup_method(self):
        from app.modules.shipping.service import ShippingService

        self.svc = ShippingService()

    def _payload(self):
        from app.modules.shipping.schemas import CreateShipmentRequest

        return CreateShipmentRequest(order_id=uuid.uuid4(), weight_grams=500)

    async def test_raises_conflict_when_active_shipment_exists(self):
        from app.core.exceptions import ConflictError

        db = AsyncMock()
        mock_existing = MagicMock()
        mock_existing.status = "created"  # not failed/cancelled
        with patch(
            "app.modules.shipping.service._repo.get_for_order",
            AsyncMock(return_value=mock_existing),
        ):
            with pytest.raises(ConflictError):
                await self.svc.create_shipment(db, uuid.uuid4(), self._payload())

    async def test_allows_retry_when_shipment_is_failed(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        mock_existing = MagicMock()
        mock_existing.status = "failed"
        from app.modules.orders.repository import OrderRepository

        with (
            patch(
                "app.modules.shipping.service._repo.get_for_order",
                AsyncMock(return_value=mock_existing),
            ),
            patch.object(OrderRepository, "get_by_id", AsyncMock(return_value=None)),
        ):
            with pytest.raises(NotFoundError):  # fails at next guard
                await self.svc.create_shipment(db, uuid.uuid4(), self._payload())

    async def test_raises_not_found_when_order_missing(self):
        from app.core.exceptions import NotFoundError
        from app.modules.orders.repository import OrderRepository

        db = AsyncMock()
        with (
            patch(
                "app.modules.shipping.service._repo.get_for_order",
                AsyncMock(return_value=None),
            ),
            patch.object(OrderRepository, "get_by_id", AsyncMock(return_value=None)),
        ):
            with pytest.raises(NotFoundError):
                await self.svc.create_shipment(db, uuid.uuid4(), self._payload())

    async def test_raises_validation_error_for_wrong_order_status(self):
        from app.core.exceptions import ValidationError
        from app.modules.orders.repository import OrderRepository

        db = AsyncMock()
        mock_order = MagicMock()
        mock_order.status = "delivered"  # not confirmed or processing
        with (
            patch(
                "app.modules.shipping.service._repo.get_for_order",
                AsyncMock(return_value=None),
            ),
            patch.object(
                OrderRepository, "get_by_id", AsyncMock(return_value=mock_order)
            ),
        ):
            with pytest.raises(ValidationError):
                await self.svc.create_shipment(db, uuid.uuid4(), self._payload())

    async def test_raises_validation_error_for_cancelled_order(self):
        from app.core.exceptions import ValidationError
        from app.modules.orders.repository import OrderRepository

        db = AsyncMock()
        mock_order = MagicMock()
        mock_order.status = "cancelled"
        with (
            patch(
                "app.modules.shipping.service._repo.get_for_order",
                AsyncMock(return_value=None),
            ),
            patch.object(
                OrderRepository, "get_by_id", AsyncMock(return_value=mock_order)
            ),
        ):
            with pytest.raises(ValidationError):
                await self.svc.create_shipment(db, uuid.uuid4(), self._payload())


class TestShippingServiceGetShipment:
    def setup_method(self):
        from app.modules.shipping.service import ShippingService

        self.svc = ShippingService()

    async def test_raises_404_when_order_not_found_for_user(self):
        from app.core.exceptions import NotFoundError
        from app.modules.orders.repository import OrderRepository

        db = AsyncMock()
        with patch.object(OrderRepository, "get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.get_shipment(db, uuid.uuid4(), user_id=uuid.uuid4())

    async def test_raises_404_when_wrong_user(self):
        from app.core.exceptions import NotFoundError
        from app.modules.orders.repository import OrderRepository

        db = AsyncMock()
        mock_order = MagicMock()
        mock_order.user_id = uuid.uuid4()  # different from caller
        with patch.object(
            OrderRepository, "get_by_id", AsyncMock(return_value=mock_order)
        ):
            with pytest.raises(NotFoundError):
                await self.svc.get_shipment(db, uuid.uuid4(), user_id=uuid.uuid4())

    async def test_raises_404_when_no_shipment_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch(
            "app.modules.shipping.service._repo.get_for_order",
            AsyncMock(return_value=None),
        ):
            with pytest.raises(NotFoundError):
                await self.svc.get_shipment(db, uuid.uuid4(), user_id=None)


class TestShippingServiceTrack:
    def setup_method(self):
        from app.modules.shipping.service import ShippingService

        self.svc = ShippingService()

    async def test_raises_404_when_shipment_not_found_by_awb(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch(
            "app.modules.shipping.service._repo.get_by_awb",
            AsyncMock(return_value=None),
        ):
            with pytest.raises(NotFoundError):
                await self.svc.track(db, "AWB-NOT-FOUND")

    async def test_returns_cached_events_when_client_fails(self):
        db = AsyncMock()
        mock_shipment = MagicMock()
        mock_shipment.status = "in_transit"
        mock_shipment.estimated_delivery = None
        mock_shipment.events = []
        with (
            patch(
                "app.modules.shipping.service._repo.get_by_awb",
                AsyncMock(return_value=mock_shipment),
            ),
            patch(
                "app.modules.shipping.service._client.track",
                AsyncMock(side_effect=Exception("network error")),
            ),
        ):
            result = await self.svc.track(db, "AWB-123")
        assert result.awb_number == "AWB-123"
        assert result.status == "in_transit"
        assert result.events == []


# ─── SeoService ──────────────────────────────────────────────────────────────


class TestSeoService:
    def setup_method(self):
        from app.modules.seo.service import SeoService

        self.svc = SeoService()

    def _mock_execute(self, fetchone_return=None, fetchall_return=None):
        mock_result = MagicMock()
        mock_result.fetchone.return_value = fetchone_return
        mock_result.fetchall.return_value = fetchall_return or []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)
        return db

    async def test_get_page_returns_none_when_no_row(self):
        db = self._mock_execute(fetchone_return=None)
        result = await self.svc.get_page(db, "/products/ring")
        assert result is None

    async def test_get_page_returns_dict_when_row_found(self):
        mock_row = MagicMock()
        mock_row._mapping = {
            "path": "/products/ring",
            "title": "Silver Ring",
            "description": "A beautiful ring",
            "canonical_url": None,
            "og_image": None,
            "og_title": None,
            "og_description": None,
            "structured_data": None,
            "noindex": False,
        }
        db = self._mock_execute(fetchone_return=mock_row)
        result = await self.svc.get_page(db, "/products/ring")
        assert result["path"] == "/products/ring"
        assert result["title"] == "Silver Ring"

    async def test_get_redirect_returns_none_when_no_row(self):
        db = self._mock_execute(fetchone_return=None)
        result = await self.svc.get_redirect(db, "/old-path")
        assert result is None

    async def test_get_redirect_returns_target_path(self):
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, i: "/new-path"
        db = self._mock_execute(fetchone_return=mock_row)
        result = await self.svc.get_redirect(db, "/old-path")
        assert result == "/new-path"

    async def test_create_redirect_executes_sql(self):
        db = AsyncMock()
        await self.svc.create_redirect(db, "/from", "/to", 301)
        db.execute.assert_awaited_once()

    async def test_upsert_page_returns_dict(self):
        mock_row = MagicMock()
        mock_row._mapping = {"path": "/test", "title": "Test"}
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)
        result = await self.svc.upsert_page(
            db,
            {
                "path": "/test",
                "title": "Test",
                "description": None,
                "canonical_url": None,
                "og_image": None,
                "og_title": None,
                "og_description": None,
                "structured_data": None,
                "noindex": False,
            },
        )
        assert result["path"] == "/test"

    async def test_generate_sitemap_contains_static_pages(self):
        mock_products_result = MagicMock()
        mock_products_result.fetchall.return_value = []
        mock_cats_result = MagicMock()
        mock_cats_result.fetchall.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[mock_products_result, mock_cats_result])

        result = await self.svc.generate_sitemap(db)
        assert '<?xml version="1.0"' in result
        assert "<urlset" in result
        assert "/collections" in result
        assert "/categories" in result

    async def test_generate_sitemap_includes_product_slugs(self):
        from datetime import datetime

        now = datetime.now(UTC)
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, i: "silver-ring" if i == 0 else now

        mock_products_result = MagicMock()
        mock_products_result.fetchall.return_value = [mock_row]
        mock_cats_result = MagicMock()
        mock_cats_result.fetchall.return_value = []

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[mock_products_result, mock_cats_result])
        result = await self.svc.generate_sitemap(db)
        assert "silver-ring" in result

    async def test_generate_sitemap_includes_category_slugs(self):
        mock_cat_row = MagicMock()
        mock_cat_row.__getitem__ = lambda self, i: "rings"

        mock_products_result = MagicMock()
        mock_products_result.fetchall.return_value = []
        mock_cats_result = MagicMock()
        mock_cats_result.fetchall.return_value = [mock_cat_row]

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[mock_products_result, mock_cats_result])
        result = await self.svc.generate_sitemap(db)
        assert "/categories/rings" in result

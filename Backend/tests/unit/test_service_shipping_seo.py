"""Tests for ShippingService (error paths) and SeoService."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─── ShippingService error paths ──────────────────────────────────────────────


class TestShippingServiceCreateShipment:
    def setup_method(self):
        from app.modules.shipping.service import ShippingService

        self.svc = ShippingService()

    def _payload(self):
        from app.modules.shipping.schemas import CreateShipmentRequest

        return CreateShipmentRequest(courier="BlueDart", tracking_number="BD123")

    async def test_raises_conflict_when_active_shipment_exists(self):
        from app.core.exceptions import ConflictError

        db = AsyncMock()
        mock_existing = MagicMock()
        mock_existing.status = "created"
        with patch(
            "app.modules.shipping.service._repo.get_for_order",
            AsyncMock(return_value=mock_existing),
        ):
            with pytest.raises(ConflictError):
                await self.svc.create_shipment(db, uuid.uuid4(), self._payload())

    async def test_allows_retry_when_shipment_is_failed(self):
        from app.core.exceptions import NotFoundError
        from app.modules.orders.repository import OrderRepository

        db = AsyncMock()
        mock_existing = MagicMock()
        mock_existing.status = "failed"
        with (
            patch(
                "app.modules.shipping.service._repo.get_for_order",
                AsyncMock(return_value=mock_existing),
            ),
            patch.object(OrderRepository, "get_by_id", AsyncMock(return_value=None)),
        ):
            with pytest.raises(NotFoundError):
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
        mock_order.status = "delivered"
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
        mock_order.user_id = uuid.uuid4()
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


class TestShippingServiceGetTracking:
    def setup_method(self):
        from app.modules.shipping.service import ShippingService

        self.svc = ShippingService()

    async def test_raises_404_when_shipment_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch(
            "app.modules.shipping.service._repo.get_for_order",
            AsyncMock(return_value=None),
        ):
            with pytest.raises(NotFoundError):
                await self.svc.get_tracking(db, uuid.uuid4())

    async def test_returns_tracking_from_db(self):
        from app.modules.shipping.schemas import TrackingResponse

        db = AsyncMock()
        import datetime

        mock_shipment = MagicMock()
        mock_shipment.provider = "BlueDart"
        mock_shipment.awb_number = "BD-999"
        mock_shipment.tracking_url = "https://bluedart.com/track/BD-999"
        mock_shipment.status = "in_transit"
        mock_shipment.estimated_delivery = None
        mock_shipment.created_at = datetime.datetime.now(datetime.UTC)
        with patch(
            "app.modules.shipping.service._repo.get_for_order",
            AsyncMock(return_value=mock_shipment),
        ):
            result = await self.svc.get_tracking(db, uuid.uuid4())
        assert isinstance(result, TrackingResponse)
        assert result.courier == "BlueDart"
        assert result.tracking_number == "BD-999"
        assert result.status == "in_transit"

    async def test_raises_404_when_wrong_user(self):
        from app.core.exceptions import NotFoundError
        from app.modules.orders.repository import OrderRepository

        db = AsyncMock()
        mock_order = MagicMock()
        mock_order.user_id = uuid.uuid4()
        with patch.object(
            OrderRepository, "get_by_id", AsyncMock(return_value=mock_order)
        ):
            with pytest.raises(NotFoundError):
                await self.svc.get_tracking(db, uuid.uuid4(), user_id=uuid.uuid4())


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

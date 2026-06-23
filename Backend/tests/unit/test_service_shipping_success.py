"""Tests for ShippingService success paths (manual workflow)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestShippingServiceCreateShipmentSuccess:
    def setup_method(self):
        from app.modules.shipping.service import ShippingService

        self.svc = ShippingService()

    def _payload(self):
        from app.modules.shipping.schemas import CreateShipmentRequest

        return CreateShipmentRequest(
            courier="BlueDart",
            tracking_number="BD-001",
            tracking_url="https://bluedart.com/track/BD-001",
        )

    def _mock_order(self):
        order = MagicMock()
        order.status = "confirmed"
        order.order_number = "ORD-202406-000001"
        order.user_id = uuid.uuid4()
        return order

    async def test_create_shipment_success_path(self):
        from app.core.events import event_bus
        from app.modules.orders.repository import OrderRepository
        from app.modules.profiles.repository import ProfileRepository

        db = AsyncMock()
        mock_order = self._mock_order()
        mock_shipment = MagicMock()
        mock_shipment.id = uuid.uuid4()
        mock_profile = MagicMock()
        mock_profile.email = "alice@example.com"

        with (
            patch(
                "app.modules.shipping.service._repo.get_for_order",
                AsyncMock(return_value=None),
            ),
            patch.object(
                OrderRepository, "get_by_id", AsyncMock(return_value=mock_order)
            ),
            patch(
                "app.modules.shipping.service._repo.create",
                AsyncMock(return_value=mock_shipment),
            ),
            patch.object(OrderRepository, "update", AsyncMock()),
            patch.object(
                ProfileRepository, "get_by_id", AsyncMock(return_value=mock_profile)
            ),
            patch.object(event_bus, "publish", AsyncMock()),
            patch(
                "app.modules.shipping.service.ShipmentResponse.model_validate",
                return_value=MagicMock(),
            ),
        ):
            result = await self.svc.create_shipment(db, uuid.uuid4(), self._payload())
        assert result is not None

    async def test_create_shipment_allows_retry_on_failed_existing(self):
        from app.core.events import event_bus
        from app.modules.orders.repository import OrderRepository
        from app.modules.profiles.repository import ProfileRepository

        db = AsyncMock()
        mock_order = self._mock_order()
        mock_existing = MagicMock()
        mock_existing.status = "failed"
        mock_shipment = MagicMock()
        mock_shipment.id = uuid.uuid4()

        with (
            patch(
                "app.modules.shipping.service._repo.get_for_order",
                AsyncMock(return_value=mock_existing),
            ),
            patch.object(
                OrderRepository, "get_by_id", AsyncMock(return_value=mock_order)
            ),
            patch(
                "app.modules.shipping.service._repo.create",
                AsyncMock(return_value=mock_shipment),
            ),
            patch.object(OrderRepository, "update", AsyncMock()),
            patch.object(
                ProfileRepository, "get_by_id", AsyncMock(return_value=MagicMock())
            ),
            patch.object(event_bus, "publish", AsyncMock()),
            patch(
                "app.modules.shipping.service.ShipmentResponse.model_validate",
                return_value=MagicMock(),
            ),
        ):
            result = await self.svc.create_shipment(db, uuid.uuid4(), self._payload())
        assert result is not None

    async def test_create_shipment_publishes_shipped_event(self):
        from app.core.events import OrderShippedEvent, event_bus
        from app.modules.orders.repository import OrderRepository
        from app.modules.profiles.repository import ProfileRepository

        db = AsyncMock()
        mock_order = self._mock_order()
        mock_shipment = MagicMock()
        mock_shipment.id = uuid.uuid4()

        with (
            patch(
                "app.modules.shipping.service._repo.get_for_order",
                AsyncMock(return_value=None),
            ),
            patch.object(
                OrderRepository, "get_by_id", AsyncMock(return_value=mock_order)
            ),
            patch(
                "app.modules.shipping.service._repo.create",
                AsyncMock(return_value=mock_shipment),
            ),
            patch.object(OrderRepository, "update", AsyncMock()),
            patch.object(
                ProfileRepository, "get_by_id", AsyncMock(return_value=MagicMock())
            ),
            patch.object(event_bus, "publish", AsyncMock()) as mock_pub,
            patch(
                "app.modules.shipping.service.ShipmentResponse.model_validate",
                return_value=MagicMock(),
            ),
        ):
            await self.svc.create_shipment(db, uuid.uuid4(), self._payload())
        mock_pub.assert_awaited_once()
        args = mock_pub.call_args[0]
        assert isinstance(args[0], OrderShippedEvent)


class TestShippingServiceUpdateShipment:
    def setup_method(self):
        from app.modules.shipping.service import ShippingService

        self.svc = ShippingService()

    async def test_update_shipment_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError
        from app.modules.shipping.schemas import UpdateShipmentRequest

        db = AsyncMock()
        with patch(
            "app.modules.shipping.service._repo.get_for_order",
            AsyncMock(return_value=None),
        ):
            with pytest.raises(NotFoundError):
                await self.svc.update_shipment(
                    db, uuid.uuid4(), UpdateShipmentRequest()
                )

    async def test_update_shipment_sets_delivered_at_on_delivered_status(self):
        from app.core.events import event_bus
        from app.modules.orders.repository import OrderRepository
        from app.modules.profiles.repository import ProfileRepository
        from app.modules.shipping.schemas import UpdateShipmentRequest

        db = AsyncMock()
        mock_shipment = MagicMock()
        mock_shipment.id = uuid.uuid4()
        mock_shipment.status = "in_transit"
        mock_updated = MagicMock()
        mock_updated.status = "delivered"
        mock_order = MagicMock()
        mock_order.user_id = uuid.uuid4()
        mock_order.status = "shipped"
        mock_order.order_number = "ORD-001"

        with (
            patch(
                "app.modules.shipping.service._repo.get_for_order",
                AsyncMock(return_value=mock_shipment),
            ),
            patch(
                "app.modules.shipping.service._repo.update",
                AsyncMock(return_value=mock_updated),
            ),
            patch.object(
                OrderRepository, "get_by_id", AsyncMock(return_value=mock_order)
            ),
            patch.object(OrderRepository, "update", AsyncMock()),
            patch.object(
                ProfileRepository, "get_by_id", AsyncMock(return_value=MagicMock())
            ),
            patch.object(event_bus, "publish", AsyncMock()) as mock_pub,
            patch(
                "app.modules.shipping.service.ShipmentResponse.model_validate",
                return_value=MagicMock(),
            ),
        ):
            await self.svc.update_shipment(
                db,
                uuid.uuid4(),
                UpdateShipmentRequest(status="delivered"),
            )
        mock_pub.assert_awaited_once()

    async def test_update_shipment_no_op_when_empty_payload(self):
        from app.modules.shipping.schemas import UpdateShipmentRequest

        db = AsyncMock()
        mock_shipment = MagicMock()
        mock_shipment.id = uuid.uuid4()

        with (
            patch(
                "app.modules.shipping.service._repo.get_for_order",
                AsyncMock(return_value=mock_shipment),
            ),
            patch(
                "app.modules.shipping.service.ShipmentResponse.model_validate",
                return_value=MagicMock(),
            ),
        ):
            result = await self.svc.update_shipment(
                db, uuid.uuid4(), UpdateShipmentRequest()
            )
        assert result is not None


class TestShippingServiceCancelAndRates:
    def setup_method(self):
        from app.modules.shipping.service import ShippingService

        self.svc = ShippingService()

    async def test_cancel_shipment_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        with patch(
            "app.modules.shipping.service._repo.get_for_order",
            AsyncMock(return_value=None),
        ):
            with pytest.raises(NotFoundError):
                await self.svc.cancel_shipment(db, uuid.uuid4())

    async def test_cancel_shipment_raises_validation_error_when_delivered(self):
        from app.core.exceptions import ValidationError

        db = AsyncMock()
        mock_shipment = MagicMock()
        mock_shipment.status = "delivered"
        with patch(
            "app.modules.shipping.service._repo.get_for_order",
            AsyncMock(return_value=mock_shipment),
        ):
            with pytest.raises(ValidationError):
                await self.svc.cancel_shipment(db, uuid.uuid4())

    async def test_cancel_shipment_success(self):
        db = AsyncMock()
        mock_shipment = MagicMock()
        mock_shipment.status = "created"
        mock_updated = MagicMock()
        with (
            patch(
                "app.modules.shipping.service._repo.get_for_order",
                AsyncMock(return_value=mock_shipment),
            ),
            patch(
                "app.modules.shipping.service._repo.update",
                AsyncMock(return_value=mock_updated),
            ),
            patch(
                "app.modules.shipping.service.ShipmentResponse.model_validate",
                return_value=MagicMock(),
            ),
        ):
            result = await self.svc.cancel_shipment(
                db, uuid.uuid4(), reason="Customer request"
            )
        assert result is not None

    async def test_get_rates_returns_flat_rate(self):
        result = await self.svc.get_rates(500, "400001")
        assert len(result) == 1
        assert result[0].service_name == "Standard Delivery"
        assert result[0].charge == 99.0
        assert result[0].is_recommended is True

    async def test_get_shipment_success_without_user(self):
        db = AsyncMock()
        mock_shipment = MagicMock()
        with (
            patch(
                "app.modules.shipping.service._repo.get_for_order",
                AsyncMock(return_value=mock_shipment),
            ),
            patch(
                "app.modules.shipping.service.ShipmentResponse.model_validate",
                return_value=MagicMock(),
            ),
        ):
            result = await self.svc.get_shipment(db, uuid.uuid4(), user_id=None)
        assert result is not None

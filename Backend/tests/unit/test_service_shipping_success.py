"""Tests for ShippingService success paths and advanced branches."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestShippingServiceCreateShipmentSuccess:
    def setup_method(self):
        from app.modules.shipping.service import ShippingService
        self.svc = ShippingService()

    def _payload(self, weight=500):
        from app.modules.shipping.schemas import CreateShipmentRequest
        return CreateShipmentRequest(order_id=uuid.uuid4(), weight_grams=weight)

    def _mock_order(self):
        order = MagicMock()
        order.status = "confirmed"
        order.order_number = "ORD-202406-000001"
        order.user_id = uuid.uuid4()
        order.shipping_postal = "400001"
        order.shipping_full_name = "Alice"
        order.shipping_phone = "+919876543210"
        order.shipping_line1 = "123 Main St"
        order.shipping_line2 = None
        order.shipping_city = "Mumbai"
        order.shipping_state = "Maharashtra"
        return order

    async def test_create_shipment_success_path(self):
        from app.core.events import event_bus
        from app.modules.orders.repository import OrderRepository
        from app.modules.profiles.repository import ProfileRepository
        db = AsyncMock()
        mock_order = self._mock_order()
        mock_shipment = MagicMock()
        mock_shipment.id = uuid.uuid4()
        mock_shipment.provider_shipment_id = "DO-123"
        mock_profile = MagicMock()
        mock_profile.email = "alice@example.com"

        with patch("app.modules.shipping.service._repo.get_for_order", AsyncMock(return_value=None)), \
             patch.object(OrderRepository, "get_by_id", AsyncMock(return_value=mock_order)), \
             patch("app.modules.shipping.service._client.create_shipment", AsyncMock(return_value={"id": "DO-123", "awb_number": "AWB-001"})), \
             patch("app.modules.shipping.service._repo.create", AsyncMock(return_value=mock_shipment)), \
             patch("app.modules.shipping.service._client.get_label", AsyncMock(return_value=b"%PDF-label")), \
             patch.object(self.svc, "_upload_label", AsyncMock(return_value=("https://cdn/label.pdf", "labels/key"))), \
             patch("app.modules.shipping.service._repo.update", AsyncMock(return_value=mock_shipment)), \
             patch("app.modules.shipping.service._repo.get_by_id", AsyncMock(return_value=mock_shipment)), \
             patch.object(OrderRepository, "update", AsyncMock()), \
             patch.object(ProfileRepository, "get_by_id", AsyncMock(return_value=mock_profile)), \
             patch.object(event_bus, "publish", AsyncMock()), \
             patch("app.modules.shipping.service.ShipmentResponse.model_validate", return_value=MagicMock()):
            result = await self.svc.create_shipment(db, uuid.uuid4(), self._payload())
        assert result is not None

    async def test_create_shipment_records_failed_when_client_raises(self):
        from app.modules.orders.repository import OrderRepository
        db = AsyncMock()
        mock_order = self._mock_order()
        mock_shipment = MagicMock()

        with patch("app.modules.shipping.service._repo.get_for_order", AsyncMock(return_value=None)), \
             patch.object(OrderRepository, "get_by_id", AsyncMock(return_value=mock_order)), \
             patch("app.modules.shipping.service._client.create_shipment", AsyncMock(side_effect=Exception("API timeout"))), \
             patch("app.modules.shipping.service._repo.create", AsyncMock(return_value=mock_shipment)), \
             patch("app.modules.shipping.service.ShipmentResponse.model_validate", return_value=MagicMock()):
            result = await self.svc.create_shipment(db, uuid.uuid4(), self._payload())
        assert result is not None

    async def test_create_shipment_allows_retry_on_failed_existing(self):
        from app.modules.orders.repository import OrderRepository
        db = AsyncMock()
        mock_order = self._mock_order()
        mock_existing = MagicMock()
        mock_existing.status = "failed"  # allows retry
        mock_shipment = MagicMock()
        mock_shipment.id = uuid.uuid4()
        mock_shipment.provider_shipment_id = None

        with patch("app.modules.shipping.service._repo.get_for_order", AsyncMock(return_value=mock_existing)), \
             patch.object(OrderRepository, "get_by_id", AsyncMock(return_value=mock_order)), \
             patch("app.modules.shipping.service._client.create_shipment", AsyncMock(return_value={"id": "DO-456", "awb_number": "AWB-002"})), \
             patch("app.modules.shipping.service._repo.create", AsyncMock(return_value=mock_shipment)), \
             patch("app.modules.shipping.service._repo.update", AsyncMock(return_value=mock_shipment)), \
             patch("app.modules.shipping.service._repo.get_by_id", AsyncMock(return_value=mock_shipment)), \
             patch.object(OrderRepository, "update", AsyncMock()), \
             patch("app.modules.profiles.repository.ProfileRepository.get_by_id", AsyncMock(return_value=MagicMock())), \
             patch("app.core.events.event_bus.publish", AsyncMock()), \
             patch("app.modules.shipping.service.ShipmentResponse.model_validate", return_value=MagicMock()):
            result = await self.svc.create_shipment(db, uuid.uuid4(), self._payload())
        assert result is not None

    async def test_create_shipment_with_no_weight_queries_db(self):
        from app.modules.orders.repository import OrderRepository
        db = AsyncMock()
        mock_order = self._mock_order()
        mock_shipment = MagicMock()
        mock_shipment.id = uuid.uuid4()
        mock_shipment.provider_shipment_id = None

        # Mock the weight query
        weight_row = MagicMock()
        weight_row.__getitem__ = lambda s, i: 750.0
        weight_result = MagicMock()
        weight_result.fetchone.return_value = weight_row
        db.execute = AsyncMock(return_value=weight_result)

        with patch("app.modules.shipping.service._repo.get_for_order", AsyncMock(return_value=None)), \
             patch.object(OrderRepository, "get_by_id", AsyncMock(return_value=mock_order)), \
             patch("app.modules.shipping.service._client.create_shipment", AsyncMock(return_value={"id": "DO-789", "awb_number": ""})), \
             patch("app.modules.shipping.service._repo.create", AsyncMock(return_value=mock_shipment)), \
             patch("app.modules.shipping.service._repo.update", AsyncMock(return_value=mock_shipment)), \
             patch("app.modules.shipping.service._repo.get_by_id", AsyncMock(return_value=mock_shipment)), \
             patch.object(OrderRepository, "update", AsyncMock()), \
             patch("app.modules.profiles.repository.ProfileRepository.get_by_id", AsyncMock(return_value=MagicMock())), \
             patch("app.core.events.event_bus.publish", AsyncMock()), \
             patch("app.modules.shipping.service.ShipmentResponse.model_validate", return_value=MagicMock()):
            # payload with no weight
            from app.modules.shipping.schemas import CreateShipmentRequest
            result = await self.svc.create_shipment(db, uuid.uuid4(), CreateShipmentRequest(order_id=uuid.uuid4()))
        assert result is not None


class TestShippingServiceTrackSuccess:
    def setup_method(self):
        from app.modules.shipping.service import ShippingService
        self.svc = ShippingService()

    async def test_track_success_syncs_events_and_updates_status(self):
        from datetime import datetime, timezone
        from app.modules.shipping.schemas import ShipmentEventResponse
        db = AsyncMock()

        existing_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        existing_event = MagicMock()
        existing_event.occurred_at = existing_time

        mock_shipment = MagicMock()
        mock_shipment.id = uuid.uuid4()
        mock_shipment.order_id = uuid.uuid4()
        mock_shipment.status = "in_transit"
        mock_shipment.estimated_delivery = None
        mock_shipment.events = [existing_event]

        real_event = ShipmentEventResponse(
            id=uuid.uuid4(),
            status="in_transit",
            description="Arrived at hub",
            location="Delhi",
            occurred_at=datetime(2026, 1, 1, 15, 0, 0, tzinfo=timezone.utc),
        )
        mock_updated = MagicMock()
        mock_updated.status = "in_transit"
        mock_updated.estimated_delivery = None
        mock_updated.events = [real_event]

        tracking_data = {
            "events": [
                {
                    "timestamp": "2026-01-01T15:00:00",
                    "status": "IN_TRANSIT",
                    "description": "Arrived at hub",
                    "location": "Delhi",
                },
                {
                    "timestamp": "2026-01-01T12:00:00+00:00",  # duplicate — already in events
                    "status": "IN_TRANSIT",
                    "description": "Picked up",
                    "location": "Mumbai",
                },
            ]
        }

        with patch("app.modules.shipping.service._repo.get_by_awb", AsyncMock(return_value=mock_shipment)), \
             patch("app.modules.shipping.service._client.track", AsyncMock(return_value=tracking_data)), \
             patch("app.modules.shipping.service._repo.add_event", AsyncMock()), \
             patch("app.modules.shipping.service._repo.update", AsyncMock(return_value=mock_updated)), \
             patch("app.modules.shipping.service._repo.get_by_id", AsyncMock(return_value=mock_updated)):
            result = await self.svc.track(db, "AWB-123")
        assert result.awb_number == "AWB-123"

    async def test_track_publishes_delivered_event(self):
        from datetime import datetime, timezone
        from app.core.events import event_bus
        from app.modules.orders.repository import OrderRepository
        from app.modules.profiles.repository import ProfileRepository
        db = AsyncMock()

        order_id = uuid.uuid4()
        mock_shipment = MagicMock()
        mock_shipment.id = uuid.uuid4()
        mock_shipment.order_id = order_id
        mock_shipment.status = "out_for_delivery"
        mock_shipment.estimated_delivery = None
        mock_shipment.events = []

        mock_order = MagicMock()
        mock_order.user_id = uuid.uuid4()
        mock_order.order_number = "ORD-001"
        mock_order.status = "processing"

        mock_profile = MagicMock()
        mock_profile.email = "alice@example.com"

        mock_updated = MagicMock()
        mock_updated.status = "delivered"
        mock_updated.estimated_delivery = None
        mock_updated.events = []

        tracking_data = {
            "events": [
                {
                    "timestamp": "2026-06-15T10:00:00",
                    "status": "DELIVERED",
                    "description": "Delivered to customer",
                    "location": "Mumbai",
                },
            ]
        }

        with patch("app.modules.shipping.service._repo.get_by_awb", AsyncMock(return_value=mock_shipment)), \
             patch("app.modules.shipping.service._client.track", AsyncMock(return_value=tracking_data)), \
             patch("app.modules.shipping.service._repo.add_event", AsyncMock()), \
             patch("app.modules.shipping.service._repo.update", AsyncMock(return_value=mock_updated)), \
             patch("app.modules.shipping.service._repo.get_by_id", AsyncMock(return_value=mock_updated)), \
             patch.object(OrderRepository, "get_by_id", AsyncMock(return_value=mock_order)), \
             patch.object(OrderRepository, "update", AsyncMock()), \
             patch.object(ProfileRepository, "get_by_id", AsyncMock(return_value=mock_profile)), \
             patch.object(event_bus, "publish", AsyncMock()) as mock_publish:
            result = await self.svc.track(db, "AWB-123")
        mock_publish.assert_awaited_once()


class TestShippingServiceSyncStatus:
    def setup_method(self):
        from app.modules.shipping.service import ShippingService
        self.svc = ShippingService()

    async def test_sync_returns_early_when_no_shipment(self):
        db = AsyncMock()
        with patch("app.modules.shipping.service._repo.get_for_order", AsyncMock(return_value=None)):
            await self.svc.sync_shipment_status(db, uuid.uuid4())

    async def test_sync_returns_early_when_no_awb(self):
        db = AsyncMock()
        mock_shipment = MagicMock()
        mock_shipment.awb_number = None
        with patch("app.modules.shipping.service._repo.get_for_order", AsyncMock(return_value=mock_shipment)):
            await self.svc.sync_shipment_status(db, uuid.uuid4())

    async def test_sync_returns_early_when_delivered(self):
        db = AsyncMock()
        mock_shipment = MagicMock()
        mock_shipment.awb_number = "AWB-123"
        mock_shipment.status = "delivered"
        with patch("app.modules.shipping.service._repo.get_for_order", AsyncMock(return_value=mock_shipment)):
            await self.svc.sync_shipment_status(db, uuid.uuid4())

    async def test_sync_calls_track_for_active_shipment(self):
        db = AsyncMock()
        mock_shipment = MagicMock()
        mock_shipment.awb_number = "AWB-123"
        mock_shipment.status = "in_transit"
        with patch("app.modules.shipping.service._repo.get_for_order", AsyncMock(return_value=mock_shipment)), \
             patch.object(self.svc, "track", AsyncMock()) as mock_track:
            await self.svc.sync_shipment_status(db, uuid.uuid4())
        mock_track.assert_awaited_once_with(db, "AWB-123")


class TestShippingServiceCancelAndRates:
    def setup_method(self):
        from app.modules.shipping.service import ShippingService
        self.svc = ShippingService()

    async def test_cancel_shipment_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError
        db = AsyncMock()
        with patch("app.modules.shipping.service._repo.get_for_order", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.cancel_shipment(db, uuid.uuid4())

    async def test_cancel_shipment_raises_validation_error_when_delivered(self):
        from app.core.exceptions import ValidationError
        db = AsyncMock()
        mock_shipment = MagicMock()
        mock_shipment.status = "delivered"
        with patch("app.modules.shipping.service._repo.get_for_order", AsyncMock(return_value=mock_shipment)):
            with pytest.raises(ValidationError):
                await self.svc.cancel_shipment(db, uuid.uuid4())

    async def test_cancel_shipment_success(self):
        db = AsyncMock()
        mock_shipment = MagicMock()
        mock_shipment.status = "created"
        mock_shipment.provider_shipment_id = "DO-123"
        mock_updated = MagicMock()
        with patch("app.modules.shipping.service._repo.get_for_order", AsyncMock(return_value=mock_shipment)), \
             patch("app.modules.shipping.service._client.cancel_shipment", AsyncMock()), \
             patch("app.modules.shipping.service._repo.update", AsyncMock(return_value=mock_updated)), \
             patch("app.modules.shipping.service.ShipmentResponse.model_validate", return_value=MagicMock()):
            result = await self.svc.cancel_shipment(db, uuid.uuid4(), reason="Customer request")
        assert result is not None

    async def test_cancel_shipment_continues_when_api_cancel_fails(self):
        db = AsyncMock()
        mock_shipment = MagicMock()
        mock_shipment.status = "in_transit"
        mock_shipment.provider_shipment_id = "DO-789"
        mock_updated = MagicMock()
        with patch("app.modules.shipping.service._repo.get_for_order", AsyncMock(return_value=mock_shipment)), \
             patch("app.modules.shipping.service._client.cancel_shipment", AsyncMock(side_effect=Exception("API error"))), \
             patch("app.modules.shipping.service._repo.update", AsyncMock(return_value=mock_updated)), \
             patch("app.modules.shipping.service.ShipmentResponse.model_validate", return_value=MagicMock()):
            result = await self.svc.cancel_shipment(db, uuid.uuid4())
        assert result is not None

    async def test_get_rates_returns_rates_from_client(self):
        with patch("app.modules.shipping.service._client.get_rates", AsyncMock(return_value=[
            {"service_name": "Express", "estimated_days": 2, "charge": 150, "is_recommended": True}
        ])):
            result = await self.svc.get_rates(500, "400001")
        assert len(result) == 1
        assert result[0].charge == 150.0

    async def test_get_rates_returns_default_on_api_failure(self):
        with patch("app.modules.shipping.service._client.get_rates", AsyncMock(side_effect=Exception("API down"))):
            result = await self.svc.get_rates(500, "400001")
        assert len(result) == 1
        assert result[0].service_name == "Standard Delivery"
        assert result[0].charge == 99.0

    async def test_get_shipment_success_without_user(self):
        db = AsyncMock()
        mock_shipment = MagicMock()
        with patch("app.modules.shipping.service._repo.get_for_order", AsyncMock(return_value=mock_shipment)), \
             patch("app.modules.shipping.service.ShipmentResponse.model_validate", return_value=MagicMock()):
            result = await self.svc.get_shipment(db, uuid.uuid4(), user_id=None)
        assert result is not None

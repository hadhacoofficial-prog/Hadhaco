"""OrderService mock-based tests — no real DB needed."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.orders.schemas import CancelOrderRequest, UpdateOrderStatusRequest


class TestOrderServiceGetOrder:
    def setup_method(self):
        from app.modules.orders.service import OrderService
        self.svc = OrderService()

    async def test_get_order_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError
        db = AsyncMock()
        with patch("app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.get_order(db, uuid.uuid4())

    async def test_get_order_raises_404_for_wrong_owner(self):
        from app.core.exceptions import NotFoundError
        db = AsyncMock()
        mock_order = MagicMock()
        mock_order.user_id = uuid.uuid4()
        with patch("app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=mock_order)):
            with pytest.raises(NotFoundError):
                await self.svc.get_order(db, uuid.uuid4(), user_id=uuid.uuid4())

    async def test_get_order_no_user_check_for_admin(self):
        db = AsyncMock()
        user_id = uuid.uuid4()
        mock_order = MagicMock()
        mock_order.user_id = user_id
        mock_order.id = uuid.uuid4()
        with patch("app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=mock_order)):
            with patch("app.modules.orders.schemas.OrderResponse.model_validate", return_value=MagicMock()):
                result = await self.svc.get_order(db, mock_order.id)
        assert result is not None


class TestOrderServiceList:
    def setup_method(self):
        from app.modules.orders.service import OrderService
        self.svc = OrderService()

    async def test_list_my_orders_empty(self):
        db = AsyncMock()
        with patch("app.modules.orders.service._repo.list_for_user", AsyncMock(return_value=([], 0))):
            result = await self.svc.list_my_orders(db, uuid.uuid4())
        assert result.total == 0
        assert result.total_pages == 0
        assert result.items == []

    async def test_list_my_orders_with_results(self):
        db = AsyncMock()
        mock_order = MagicMock()
        mock_order.id = uuid.uuid4()
        mock_order.order_number = "ORD-001"
        mock_order.status = "pending"
        mock_order.payment_status = "pending"
        mock_order.total = Decimal("1500.00")
        mock_order.created_at = datetime.now(timezone.utc)
        mock_order.items = []
        with patch("app.modules.orders.service._repo.list_for_user", AsyncMock(return_value=([mock_order], 1))):
            result = await self.svc.list_my_orders(db, uuid.uuid4(), page=1, page_size=10)
        assert result.total == 1
        assert len(result.items) == 1
        assert result.total_pages == 1

    async def test_list_my_orders_pagination(self):
        db = AsyncMock()
        with patch("app.modules.orders.service._repo.list_for_user", AsyncMock(return_value=([], 25))):
            result = await self.svc.list_my_orders(db, uuid.uuid4(), page=2, page_size=10)
        assert result.page == 2
        assert result.page_size == 10
        assert result.total == 25
        assert result.total_pages == 3

    async def test_admin_list_orders_empty(self):
        db = AsyncMock()
        with patch("app.modules.orders.service._repo.list_all", AsyncMock(return_value=([], 0))):
            result = await self.svc.admin_list_orders(db)
        assert result.total == 0

    async def test_admin_list_orders_with_results(self):
        db = AsyncMock()
        mock_order = MagicMock()
        mock_order.id = uuid.uuid4()
        mock_order.order_number = "ORD-002"
        mock_order.status = "confirmed"
        mock_order.payment_status = "paid"
        mock_order.total = Decimal("500.00")
        mock_order.created_at = datetime.now(timezone.utc)
        with patch("app.modules.orders.service._repo.list_all", AsyncMock(return_value=([mock_order], 1))):
            result = await self.svc.admin_list_orders(db)
        assert result.total == 1


class TestOrderServiceCancel:
    def setup_method(self):
        from app.modules.orders.service import OrderService
        self.svc = OrderService()

    async def test_cancel_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError
        db = AsyncMock()
        with patch("app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.cancel_order(db, uuid.uuid4(), uuid.uuid4(), CancelOrderRequest(reason="changed mind"))

    async def test_cancel_raises_404_for_wrong_user(self):
        from app.core.exceptions import NotFoundError
        db = AsyncMock()
        owner = uuid.uuid4()
        caller = uuid.uuid4()
        mock_order = MagicMock()
        mock_order.user_id = owner
        with patch("app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=mock_order)):
            with pytest.raises(NotFoundError):
                await self.svc.cancel_order(db, uuid.uuid4(), caller, CancelOrderRequest(reason="x"))

    async def test_cancel_raises_validation_for_shipped_status(self):
        from app.core.exceptions import ValidationError
        db = AsyncMock()
        user_id = uuid.uuid4()
        mock_order = MagicMock()
        mock_order.user_id = user_id
        mock_order.status = "shipped"
        with patch("app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=mock_order)):
            with pytest.raises(ValidationError):
                await self.svc.cancel_order(db, uuid.uuid4(), user_id, CancelOrderRequest(reason="x"))

    async def test_cancel_raises_validation_for_delivered_status(self):
        from app.core.exceptions import ValidationError
        db = AsyncMock()
        user_id = uuid.uuid4()
        mock_order = MagicMock()
        mock_order.user_id = user_id
        mock_order.status = "delivered"
        with patch("app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=mock_order)):
            with pytest.raises(ValidationError):
                await self.svc.cancel_order(db, uuid.uuid4(), user_id, CancelOrderRequest(reason="x"))


class TestOrderServiceUpdateStatus:
    def setup_method(self):
        from app.modules.orders.service import OrderService
        self.svc = OrderService()

    async def test_update_status_raises_404_when_not_found(self):
        from app.core.exceptions import NotFoundError
        db = AsyncMock()
        with patch("app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=None)):
            with pytest.raises(NotFoundError):
                await self.svc.update_status(db, uuid.uuid4(), UpdateOrderStatusRequest(status="confirmed"))

    async def test_update_status_success(self):
        db = AsyncMock()
        order_id = uuid.uuid4()
        mock_order = MagicMock()
        mock_order.id = order_id
        mock_order.user_id = uuid.uuid4()
        mock_order.status = "pending"
        mock_updated = MagicMock()
        with patch("app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=mock_order)), \
             patch("app.modules.orders.service._repo.update", AsyncMock(return_value=mock_updated)), \
             patch("app.modules.orders.service.event_bus.publish", AsyncMock()), \
             patch("app.modules.orders.schemas.OrderResponse.model_validate", return_value=MagicMock()):
            result = await self.svc.update_status(db, order_id, UpdateOrderStatusRequest(status="confirmed"))
        assert result is not None

    async def test_update_status_to_cancelled_sets_cancelled_at(self):
        db = AsyncMock()
        order_id = uuid.uuid4()
        captured_data = {}
        mock_order = MagicMock()
        mock_order.status = "confirmed"
        mock_order.user_id = uuid.uuid4()

        async def capture_update(db, oid, data):
            captured_data.update(data)
            return MagicMock()

        with patch("app.modules.orders.service._repo.get_by_id", AsyncMock(return_value=mock_order)), \
             patch("app.modules.orders.service._repo.update", capture_update), \
             patch("app.modules.orders.service.event_bus.publish", AsyncMock()), \
             patch("app.modules.orders.schemas.OrderResponse.model_validate", return_value=MagicMock()):
            await self.svc.update_status(db, order_id, UpdateOrderStatusRequest(status="cancelled"))
        assert "cancelled_at" in captured_data
        assert captured_data["status"] == "cancelled"

"""Tests for WebhookService — Razorpay and Delivery One webhook handling."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch


class TestWebhookServiceRecordEvent:
    def setup_method(self):
        from app.modules.webhooks.service import WebhookService

        self.svc = WebhookService()

    async def test_record_event_with_no_event_id(self):
        db = AsyncMock()
        db.add = MagicMock()
        result = await self.svc._record_event(
            db, "razorpay", "payment.captured", None, '{"event":"test"}'
        )
        db.add.assert_called_once()
        assert result is not None

    async def test_record_event_returns_none_when_duplicate(self):
        db = AsyncMock()
        mock_existing = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_existing
        db.execute = AsyncMock(return_value=mock_result)
        result = await self.svc._record_event(db, "razorpay", "payment.captured", "evt_abc", "{}")
        assert result is None

    async def test_record_event_creates_new_when_no_duplicate(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        result = await self.svc._record_event(db, "razorpay", "payment.captured", "evt_new", "{}")
        db.add.assert_called_once()
        assert result is not None

    async def test_mark_processed_executes_update(self):
        db = AsyncMock()
        await self.svc._mark_processed(db, uuid.uuid4())
        db.execute.assert_awaited_once()

    async def test_mark_failed_executes_update(self):
        db = AsyncMock()
        await self.svc._mark_failed(db, uuid.uuid4(), "Something went wrong")
        db.execute.assert_awaited_once()


class TestWebhookServiceRazorpay:
    def setup_method(self):
        from app.modules.webhooks.service import WebhookService

        self.svc = WebhookService()

    async def test_handle_razorpay_rejects_invalid_signature(self):
        db = AsyncMock()
        with patch(
            "app.modules.webhooks.service.verify_razorpay_webhook_signature", return_value=False
        ):
            result = await self.svc.handle_razorpay(db, b"{}", "bad_sig")
        assert result == {"status": "invalid_signature"}

    async def test_handle_razorpay_rejects_invalid_json(self):
        db = AsyncMock()
        with patch(
            "app.modules.webhooks.service.verify_razorpay_webhook_signature", return_value=True
        ):
            result = await self.svc.handle_razorpay(db, b"not-json", "sig")
        assert result == {"status": "invalid_payload"}

    async def test_handle_razorpay_returns_already_processed_on_duplicate(self):
        db = AsyncMock()
        body = json.dumps({"event": "payment.captured", "id": "evt_dup"}).encode()
        with (
            patch(
                "app.modules.webhooks.service.verify_razorpay_webhook_signature", return_value=True
            ),
            patch.object(self.svc, "_record_event", AsyncMock(return_value=None)),
        ):
            result = await self.svc.handle_razorpay(db, body, "sig")
        assert result == {"status": "already_processed"}

    async def test_handle_razorpay_payment_captured(self):
        db = AsyncMock()
        body = json.dumps({"event": "payment.captured", "id": "evt_001"}).encode()
        mock_event_row = MagicMock()
        mock_event_row.id = uuid.uuid4()
        with (
            patch(
                "app.modules.webhooks.service.verify_razorpay_webhook_signature", return_value=True
            ),
            patch.object(self.svc, "_record_event", AsyncMock(return_value=mock_event_row)),
            patch.object(self.svc, "_on_payment_captured", AsyncMock()) as mock_captured,
            patch.object(self.svc, "_mark_processed", AsyncMock()),
        ):
            result = await self.svc.handle_razorpay(db, body, "sig")
        mock_captured.assert_awaited_once()
        assert result == {"status": "ok"}

    async def test_handle_razorpay_payment_failed(self):
        db = AsyncMock()
        body = json.dumps({"event": "payment.failed", "id": "evt_002"}).encode()
        mock_event_row = MagicMock()
        mock_event_row.id = uuid.uuid4()
        with (
            patch(
                "app.modules.webhooks.service.verify_razorpay_webhook_signature", return_value=True
            ),
            patch.object(self.svc, "_record_event", AsyncMock(return_value=mock_event_row)),
            patch.object(self.svc, "_on_payment_failed", AsyncMock()) as mock_failed,
            patch.object(self.svc, "_mark_processed", AsyncMock()),
        ):
            await self.svc.handle_razorpay(db, body, "sig")
        mock_failed.assert_awaited_once()

    async def test_handle_razorpay_refund_event(self):
        db = AsyncMock()
        body = json.dumps({"event": "refund.created", "id": "evt_003"}).encode()
        mock_event_row = MagicMock()
        mock_event_row.id = uuid.uuid4()
        with (
            patch(
                "app.modules.webhooks.service.verify_razorpay_webhook_signature", return_value=True
            ),
            patch.object(self.svc, "_record_event", AsyncMock(return_value=mock_event_row)),
            patch.object(self.svc, "_on_refund_event", AsyncMock()) as mock_refund,
            patch.object(self.svc, "_mark_processed", AsyncMock()),
        ):
            await self.svc.handle_razorpay(db, body, "sig")
        mock_refund.assert_awaited_once()

    async def test_handle_razorpay_unknown_event_marks_ignored(self):
        db = AsyncMock()
        body = json.dumps({"event": "order.paid", "id": "evt_004"}).encode()
        mock_event_row = MagicMock()
        mock_event_row.id = uuid.uuid4()
        with (
            patch(
                "app.modules.webhooks.service.verify_razorpay_webhook_signature", return_value=True
            ),
            patch.object(self.svc, "_record_event", AsyncMock(return_value=mock_event_row)),
        ):
            result = await self.svc.handle_razorpay(db, body, "sig")
        assert result == {"status": "ignored"}

    async def test_handle_razorpay_marks_failed_on_handler_exception(self):
        db = AsyncMock()
        body = json.dumps({"event": "payment.captured", "id": "evt_005"}).encode()
        mock_event_row = MagicMock()
        mock_event_row.id = uuid.uuid4()
        with (
            patch(
                "app.modules.webhooks.service.verify_razorpay_webhook_signature", return_value=True
            ),
            patch.object(self.svc, "_record_event", AsyncMock(return_value=mock_event_row)),
            patch.object(
                self.svc, "_on_payment_captured", AsyncMock(side_effect=Exception("DB error"))
            ),
            patch.object(self.svc, "_mark_failed", AsyncMock()) as mock_failed,
        ):
            result = await self.svc.handle_razorpay(db, body, "sig")
        mock_failed.assert_awaited_once()
        assert result == {"status": "ok"}


class TestWebhookServiceOnPaymentCaptured:
    def setup_method(self):
        from app.modules.webhooks.service import WebhookService

        self.svc = WebhookService()

    async def test_on_payment_captured_skips_when_no_payment(self):
        db = AsyncMock()
        payload = {
            "payload": {
                "payment": {"entity": {"id": "pay_abc", "order_id": "order_abc", "method": "upi"}}
            }
        }
        from app.modules.payments.repository import PaymentRepository

        with patch.object(
            PaymentRepository, "get_by_razorpay_order_id", AsyncMock(return_value=None)
        ):
            await self.svc._on_payment_captured(db, payload)

    async def test_on_payment_captured_skips_when_already_captured(self):
        db = AsyncMock()
        payload = {
            "payload": {
                "payment": {"entity": {"id": "pay_abc", "order_id": "order_abc", "method": "upi"}}
            }
        }
        from app.modules.payments.repository import PaymentRepository

        mock_payment = MagicMock()
        mock_payment.status = "captured"
        with patch.object(
            PaymentRepository, "get_by_razorpay_order_id", AsyncMock(return_value=mock_payment)
        ):
            await self.svc._on_payment_captured(db, payload)

    async def test_on_payment_captured_updates_payment_and_order(self):
        db = AsyncMock()
        payload = {
            "payload": {
                "payment": {"entity": {"id": "pay_xyz", "order_id": "order_xyz", "method": "card"}}
            }
        }
        from app.core.events import event_bus
        from app.modules.invoices.service import InvoiceService
        from app.modules.orders.repository import OrderRepository
        from app.modules.payments.repository import PaymentRepository

        mock_payment = MagicMock()
        mock_payment.status = "created"
        mock_payment.id = uuid.uuid4()
        mock_payment.order_id = uuid.uuid4()
        mock_payment.amount = 999.0
        mock_order = MagicMock()

        with (
            patch.object(
                PaymentRepository, "get_by_razorpay_order_id", AsyncMock(return_value=mock_payment)
            ),
            patch.object(PaymentRepository, "update", AsyncMock()),
            patch.object(OrderRepository, "update", AsyncMock()),
            patch.object(OrderRepository, "get_by_id", AsyncMock(return_value=mock_order)),
            patch.object(InvoiceService, "generate_and_store", AsyncMock()),
            patch.object(event_bus, "publish", AsyncMock()),
        ):
            await self.svc._on_payment_captured(db, payload)


class TestWebhookServiceOnPaymentFailed:
    def setup_method(self):
        from app.modules.webhooks.service import WebhookService

        self.svc = WebhookService()

    async def test_on_payment_failed_skips_when_no_payment(self):
        db = AsyncMock()
        payload = {
            "payload": {
                "payment": {
                    "entity": {"order_id": "no_order", "error_description": "Card declined"}
                }
            }
        }
        from app.modules.payments.repository import PaymentRepository

        with patch.object(
            PaymentRepository, "get_by_razorpay_order_id", AsyncMock(return_value=None)
        ):
            await self.svc._on_payment_failed(db, payload)

    async def test_on_payment_failed_updates_and_publishes_event(self):
        db = AsyncMock()
        payload = {
            "payload": {
                "payment": {
                    "entity": {"order_id": "order_abc", "error_description": "Card declined"}
                }
            }
        }
        from app.core.events import event_bus
        from app.modules.payments.repository import PaymentRepository

        mock_payment = MagicMock()
        mock_payment.id = uuid.uuid4()
        mock_payment.order_id = uuid.uuid4()
        with (
            patch.object(
                PaymentRepository, "get_by_razorpay_order_id", AsyncMock(return_value=mock_payment)
            ),
            patch.object(PaymentRepository, "update", AsyncMock()),
            patch.object(event_bus, "publish", AsyncMock()) as mock_pub,
        ):
            await self.svc._on_payment_failed(db, payload)
        mock_pub.assert_awaited_once()


class TestWebhookServiceOnRefundEvent:
    def setup_method(self):
        from app.modules.webhooks.service import WebhookService

        self.svc = WebhookService()

    async def test_on_refund_event_skips_when_no_refund(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        payload = {"payload": {"refund": {"entity": {"id": "ref_abc", "amount": 50000}}}}
        await self.svc._on_refund_event(db, payload, "refund.processed")

    async def test_on_refund_processed_updates_and_publishes_event(self):
        from app.core.events import event_bus
        from app.modules.payments.repository import PaymentRepository

        db = AsyncMock()
        mock_refund = MagicMock()
        mock_refund.id = uuid.uuid4()
        mock_refund.order_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_refund
        db.execute = AsyncMock(return_value=mock_result)
        payload = {"payload": {"refund": {"entity": {"id": "ref_xyz", "amount": 50000}}}}
        with (
            patch.object(PaymentRepository, "update_refund", AsyncMock()),
            patch.object(event_bus, "publish", AsyncMock()) as mock_pub,
        ):
            await self.svc._on_refund_event(db, payload, "refund.processed")
        mock_pub.assert_awaited_once()

    async def test_on_refund_created_skips_update(self):
        db = AsyncMock()
        mock_refund = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_refund
        db.execute = AsyncMock(return_value=mock_result)
        payload = {"payload": {"refund": {"entity": {"id": "ref_xyz", "amount": 50000}}}}
        # refund.created event should NOT update or publish
        from app.core.events import event_bus

        with patch.object(event_bus, "publish", AsyncMock()) as mock_pub:
            await self.svc._on_refund_event(db, payload, "refund.created")
        mock_pub.assert_not_awaited()


class TestWebhookServiceDeliveryOne:
    def setup_method(self):
        from app.modules.webhooks.service import WebhookService

        self.svc = WebhookService()

    async def test_handle_delivery_one_rejects_invalid_signature(self):
        db = AsyncMock()
        with patch(
            "app.modules.webhooks.service.verify_delivery_one_webhook_signature", return_value=False
        ):
            result = await self.svc.handle_delivery_one(db, b"{}", "bad_sig")
        assert result == {"status": "invalid_signature"}

    async def test_handle_delivery_one_rejects_invalid_json(self):
        db = AsyncMock()
        with patch(
            "app.modules.webhooks.service.verify_delivery_one_webhook_signature", return_value=True
        ):
            result = await self.svc.handle_delivery_one(db, b"not-json", "sig")
        assert result == {"status": "invalid_payload"}

    async def test_handle_delivery_one_returns_already_processed(self):
        db = AsyncMock()
        body = json.dumps({"event": "shipment.dispatched", "id": "evt_dup"}).encode()
        with (
            patch(
                "app.modules.webhooks.service.verify_delivery_one_webhook_signature",
                return_value=True,
            ),
            patch.object(self.svc, "_record_event", AsyncMock(return_value=None)),
        ):
            result = await self.svc.handle_delivery_one(db, body, "sig")
        assert result == {"status": "already_processed"}

    async def test_handle_delivery_one_success(self):
        db = AsyncMock()
        body = json.dumps({"event": "shipment.dispatched", "id": "evt_010"}).encode()
        mock_event_row = MagicMock()
        mock_event_row.id = uuid.uuid4()
        with (
            patch(
                "app.modules.webhooks.service.verify_delivery_one_webhook_signature",
                return_value=True,
            ),
            patch.object(self.svc, "_record_event", AsyncMock(return_value=mock_event_row)),
            patch.object(self.svc, "_on_shipment_event", AsyncMock()),
            patch.object(self.svc, "_mark_processed", AsyncMock()) as mock_proc,
        ):
            result = await self.svc.handle_delivery_one(db, body, "sig")
        mock_proc.assert_awaited_once()
        assert result == {"status": "ok"}

    async def test_handle_delivery_one_marks_failed_on_error(self):
        db = AsyncMock()
        body = json.dumps({"event": "shipment.delivered", "id": "evt_011"}).encode()
        mock_event_row = MagicMock()
        mock_event_row.id = uuid.uuid4()
        with (
            patch(
                "app.modules.webhooks.service.verify_delivery_one_webhook_signature",
                return_value=True,
            ),
            patch.object(self.svc, "_record_event", AsyncMock(return_value=mock_event_row)),
            patch.object(
                self.svc, "_on_shipment_event", AsyncMock(side_effect=Exception("DB error"))
            ),
            patch.object(self.svc, "_mark_failed", AsyncMock()) as mock_failed,
        ):
            await self.svc.handle_delivery_one(db, body, "sig")
        mock_failed.assert_awaited_once()


class TestWebhookServiceOnShipmentEvent:
    def setup_method(self):
        from app.modules.webhooks.service import WebhookService

        self.svc = WebhookService()

    async def test_on_shipment_event_skips_when_no_order_number(self):
        db = AsyncMock()
        payload = {"data": {}}
        await self.svc._on_shipment_event(db, payload, "shipment.dispatched")

    async def test_on_shipment_event_skips_when_order_not_found(self):
        from app.modules.orders.repository import OrderRepository

        db = AsyncMock()
        payload = {"data": {"order_reference": "ORD-NOT-FOUND", "tracking_number": "AWB-123"}}
        with patch.object(OrderRepository, "get_by_order_number", AsyncMock(return_value=None)):
            await self.svc._on_shipment_event(db, payload, "shipment.dispatched")

    async def test_on_shipment_dispatched_updates_order(self):
        from app.core.events import event_bus
        from app.modules.orders.repository import OrderRepository

        db = AsyncMock()
        payload = {"data": {"order_reference": "ORD-001", "tracking_number": "AWB-555"}}
        mock_order = MagicMock()
        mock_order.id = uuid.uuid4()
        mock_order.user_id = uuid.uuid4()
        mock_order.status = "processing"
        with (
            patch.object(
                OrderRepository, "get_by_order_number", AsyncMock(return_value=mock_order)
            ),
            patch.object(OrderRepository, "update", AsyncMock()) as mock_upd,
            patch.object(event_bus, "publish", AsyncMock()),
        ):
            await self.svc._on_shipment_event(db, payload, "shipment.dispatched")
        mock_upd.assert_awaited_once()

    async def test_on_shipment_delivered_sets_delivered_at(self):
        from app.core.events import event_bus
        from app.modules.orders.repository import OrderRepository

        db = AsyncMock()
        payload = {"data": {"order_reference": "ORD-002", "tracking_number": ""}}
        mock_order = MagicMock()
        mock_order.id = uuid.uuid4()
        mock_order.user_id = uuid.uuid4()
        mock_order.status = "processing"
        update_call_data = {}

        async def capture_update(self_repo, db, oid, data):
            update_call_data.update(data)

        with (
            patch.object(
                OrderRepository, "get_by_order_number", AsyncMock(return_value=mock_order)
            ),
            patch.object(OrderRepository, "update", capture_update),
            patch.object(event_bus, "publish", AsyncMock()),
        ):
            await self.svc._on_shipment_event(db, payload, "shipment.delivered")
        assert "delivered_at" in update_call_data

    async def test_on_unknown_shipment_event_does_not_update(self):
        from app.modules.orders.repository import OrderRepository

        db = AsyncMock()
        payload = {"data": {"order_reference": "ORD-003"}}
        mock_order = MagicMock()
        mock_order.id = uuid.uuid4()
        with (
            patch.object(
                OrderRepository, "get_by_order_number", AsyncMock(return_value=mock_order)
            ),
            patch.object(OrderRepository, "update", AsyncMock()) as mock_upd,
        ):
            await self.svc._on_shipment_event(db, payload, "shipment.created")
        mock_upd.assert_not_awaited()

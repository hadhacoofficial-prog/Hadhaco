"""
Webhook idempotency stress tests.

Validates that sending the same Razorpay webhook event N times (5x, 10x, 50x)
produces exactly one state change:

  - Order confirmed only once
  - Reservation completed/released only once
  - Invoice generated only once
  - Domain event returned (for the dispatcher to publish) only once
  - Payment row updated only once

Two idempotency layers are exercised:
  1. _get_or_create_event: an event_id already status="processed" short-circuits
     handle_razorpay to "already_processed" before any handler runs.
  2. Handler-level guards: payment.status == "captured"/"failed" and
     refund.status == "processed"/"failed" make repeated handler invocations
     no-ops even if the outer idempotency layer were somehow bypassed.
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

# ── Helpers ───────────────────────────────────────────────────────────────────


def _captured_payload(
    rzp_payment_id: str = "pay_ABC", rzp_order_id: str = "rzp_ord_XYZ"
) -> dict:
    return {
        "event": "payment.captured",
        "id": "evt_idem_001",
        "payload": {
            "payment": {
                "entity": {
                    "id": rzp_payment_id,
                    "order_id": rzp_order_id,
                    "method": "upi",
                }
            }
        },
    }


def _failed_payload(rzp_order_id: str = "rzp_ord_FAIL") -> dict:
    return {
        "event": "payment.failed",
        "id": "evt_fail_001",
        "payload": {
            "payment": {
                "entity": {
                    "order_id": rzp_order_id,
                    "error_description": "Insufficient funds",
                }
            }
        },
    }


class _SharedPaymentState:
    """Tracks payment status across repeated webhook calls so mocks can
    simulate state transitions correctly."""

    def __init__(self, initial_status: str = "pending"):
        self.status = initial_status
        self.update_count = 0
        self.complete_count = 0
        self.release_count = 0
        self.invoice_count = 0
        self.id = uuid.uuid4()
        self.order_id = uuid.uuid4()
        self.amount = 1030.0


# ── Layer 1: _get_or_create_event duplicate detection ──────────────────────


class TestRecordEventIdempotency:
    """handle_razorpay returns 'already_processed' for an event_id whose
    webhook_events row already has status='processed'."""

    def setup_method(self):
        from app.modules.webhooks.service import WebhookService

        self.svc = WebhookService()

    async def _send_n_times(self, n: int, body: bytes) -> list[dict]:
        existing = MagicMock()
        existing.status = "processed"
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing

        results = []
        for _ in range(n):
            db = AsyncMock()
            db.execute = AsyncMock(return_value=result_mock)
            with patch(
                "app.modules.webhooks.service.verify_razorpay_webhook_signature",
                return_value=True,
            ):
                result = await self.svc.handle_razorpay(db, body, "sig")
                results.append(result)
        return results

    async def test_five_duplicate_events_all_skipped(self):
        body = json.dumps(_captured_payload()).encode()
        results = await self._send_n_times(5, body)
        assert all(r == {"status": "already_processed"} for r in results)

    async def test_fifty_duplicate_events_all_skipped(self):
        body = json.dumps(_captured_payload()).encode()
        results = await self._send_n_times(50, body)
        assert all(r == {"status": "already_processed"} for r in results)


# ── Layer 2: payment.status == "captured" guard ────────────────────────────


class TestPaymentCapturedIdempotency:
    """_on_payment_captured: after the first call sets payment.status to
    'captured', all subsequent calls short-circuit and return event=None
    without touching the reservation/invoice/order services again."""

    def setup_method(self):
        import app.modules.invoices.service  # noqa: F401 — pre-load to avoid import-under-patch
        from app.modules.webhooks.service import WebhookService

        self.svc = WebhookService()

    async def _call_n_times(self, state: _SharedPaymentState, payload: dict, n: int):
        from app.modules.audit.service import AuditService
        from app.modules.inventory.reservation_service import ReservationService
        from app.modules.invoices.service import InvoiceService
        from app.modules.orders.repository import OrderRepository
        from app.modules.payments.repository import PaymentRepository
        from app.modules.profiles.repository import ProfileRepository

        order = MagicMock()
        order.id = state.order_id
        order.total = state.amount
        order.user_id = uuid.uuid4()
        order.order_number = "HDH-202607-000001"
        order.payment_status = "pending"  # not "paid" — let processing continue

        async def _get_payment(_, db, rzp_oid):
            p = MagicMock()
            p.id = state.id
            p.order_id = state.order_id
            p.amount = state.amount
            p.status = state.status
            return p

        async def _update_payment(_, db, pid, data):
            state.update_count += 1
            if "status" in data:
                state.status = data["status"]

        async def _complete_reservations(_, db, oid):
            state.complete_count += 1

        async def _generate_invoice(_, db, ord):
            state.invoice_count += 1

        results = []
        for _ in range(n):
            db = AsyncMock()
            with (
                patch.object(
                    PaymentRepository, "get_by_razorpay_order_id", _get_payment
                ),
                patch.object(PaymentRepository, "update", _update_payment),
                patch.object(
                    OrderRepository, "get_by_id", AsyncMock(return_value=order)
                ),
                patch.object(OrderRepository, "update", AsyncMock()),
                patch.object(
                    ReservationService,
                    "complete_order_reservations",
                    _complete_reservations,
                ),
                patch.object(InvoiceService, "generate_and_store", _generate_invoice),
                patch.object(AuditService, "log", AsyncMock()),
                patch.object(
                    ProfileRepository, "get_by_id", AsyncMock(return_value=None)
                ),
            ):
                result = await self.svc._on_payment_captured(db, payload)
                results.append(result)
        return results

    async def test_five_calls_complete_once(self):
        state = _SharedPaymentState(initial_status="pending")
        results = await self._call_n_times(state, _captured_payload(), 5)

        assert (
            state.complete_count == 1
        ), f"complete_order_reservations called {state.complete_count}x (expected 1)"
        assert (
            state.update_count == 1
        ), f"payment updated {state.update_count}x (expected 1)"
        assert state.invoice_count == 1
        events_returned = sum(1 for r in results if r.event is not None)
        assert events_returned == 1

    async def test_ten_calls_complete_once(self):
        state = _SharedPaymentState(initial_status="pending")
        results = await self._call_n_times(state, _captured_payload(), 10)

        assert state.complete_count == 1
        assert state.invoice_count == 1
        events_returned = sum(1 for r in results if r.event is not None)
        assert events_returned == 1

    async def test_fifty_calls_complete_once(self):
        state = _SharedPaymentState(initial_status="pending")
        results = await self._call_n_times(state, _captured_payload(), 50)

        assert state.complete_count == 1
        assert state.update_count == 1
        assert state.invoice_count == 1
        events_returned = sum(1 for r in results if r.event is not None)
        assert events_returned == 1

    async def test_status_captured_after_first_call(self):
        """Payment status becomes 'captured' after the first successful call."""
        state = _SharedPaymentState(initial_status="pending")
        results = await self._call_n_times(state, _captured_payload(), 1)
        assert state.status == "captured"
        assert results[0].event is not None


# ── Payment failed idempotency ─────────────────────────────────────────────


class TestPaymentFailedIdempotency:
    """_on_payment_failed: release_order_reservations, the order-status
    update, and the returned domain event all happen exactly once — the
    payment.status == 'failed' guard short-circuits every repeat call."""

    def setup_method(self):
        from app.modules.webhooks.service import WebhookService

        self.svc = WebhookService()

    async def _call_n_times(self, state: _SharedPaymentState, payload: dict, n: int):
        from app.modules.audit.service import AuditService
        from app.modules.inventory.reservation_service import ReservationService
        from app.modules.orders.repository import OrderRepository
        from app.modules.payments.repository import PaymentRepository

        order = MagicMock()
        order.id = state.order_id
        order.user_id = uuid.uuid4()
        order.payment_status = "pending"

        async def _get_payment(_, db, rzp_oid):
            p = MagicMock()
            p.id = state.id
            p.order_id = state.order_id
            p.status = state.status
            return p

        async def _update_payment(_, db, pid, data):
            state.update_count += 1
            if "status" in data:
                state.status = data["status"]

        async def _release(_, db, oid, reason="RELEASED"):
            state.release_count += 1

        results = []
        for _ in range(n):
            db = AsyncMock()
            with (
                patch.object(
                    PaymentRepository, "get_by_razorpay_order_id", _get_payment
                ),
                patch.object(PaymentRepository, "update", _update_payment),
                patch.object(
                    OrderRepository, "get_by_id", AsyncMock(return_value=order)
                ),
                patch.object(OrderRepository, "update", AsyncMock()),
                patch.object(
                    ReservationService, "release_order_reservations", _release
                ),
                patch.object(AuditService, "log", AsyncMock()),
            ):
                result = await self.svc._on_payment_failed(db, payload)
                results.append(result)
        return results

    async def test_five_calls_release_once(self):
        state = _SharedPaymentState(initial_status="created")
        results = await self._call_n_times(state, _failed_payload(), 5)
        assert state.release_count == 1
        assert state.update_count == 1
        events_returned = sum(1 for r in results if r.event is not None)
        assert events_returned == 1

    async def test_fifty_calls_release_once(self):
        state = _SharedPaymentState(initial_status="created")
        results = await self._call_n_times(state, _failed_payload(), 50)
        assert state.release_count == 1
        assert state.update_count == 1
        events_returned = sum(1 for r in results if r.event is not None)
        assert events_returned == 1


# ── Full handle_razorpay idempotency with event_id deduplication ──────────


class TestFullWebhookIdempotency:
    """Combines both idempotency layers end-to-end through handle_razorpay:
    - First delivery: event_id not yet processed -> handler runs, event
      row is marked processed.
    - Every subsequent delivery of the same event_id: short-circuits to
      'already_processed' without re-invoking the handler.
    """

    def setup_method(self):
        import app.modules.invoices.service  # noqa: F401
        from app.modules.webhooks.service import WebhookService

        self.svc = WebhookService()

    async def test_first_call_processes_remaining_return_already_processed(self):
        from app.modules.webhooks.service import WebhookService, _HandlerResult

        body = json.dumps(_captured_payload()).encode()
        state = {"processed": False}

        async def _fake_get_or_create(self_, db, **kwargs):
            event_row = MagicMock()
            event_row.id = uuid.uuid4()
            return event_row, state["processed"]

        async def _fake_mark_processed(self_, db, event_id, *, order_id):
            state["processed"] = True

        mock_handler = AsyncMock(return_value=_HandlerResult(order_id=None, event=None))
        self.svc._handlers["payment.captured"] = mock_handler

        results = []
        for _ in range(10):
            db = AsyncMock()
            nested_cm = AsyncMock()
            nested_cm.__aenter__ = AsyncMock(return_value=None)
            nested_cm.__aexit__ = AsyncMock(return_value=False)
            db.begin_nested = MagicMock(return_value=nested_cm)
            with (
                patch(
                    "app.modules.webhooks.service.verify_razorpay_webhook_signature",
                    return_value=True,
                ),
                patch.object(
                    WebhookService, "_get_or_create_event", _fake_get_or_create
                ),
                patch.object(WebhookService, "_mark_processed", _fake_mark_processed),
            ):
                result = await self.svc.handle_razorpay(db, body, "sig")
                results.append(result)

        assert results[0] == {"status": "ok"}
        assert all(r == {"status": "already_processed"} for r in results[1:])
        mock_handler.assert_awaited_once()

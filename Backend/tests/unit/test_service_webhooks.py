"""Tests for WebhookService — Razorpay webhook dispatcher, idempotency store,
and each event handler (payment.captured, payment.failed, order.paid,
refund.created, refund.processed, refund.failed).
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _db_with_nested() -> AsyncMock:
    """handle_razorpay wraps each event dispatch in db.begin_nested() (a
    SAVEPOINT), so tests exercising that path need it mocked as an async
    context manager, not the AsyncMock default (a plain coroutine)."""
    db = AsyncMock()
    nested_cm = AsyncMock()
    nested_cm.__aenter__ = AsyncMock(return_value=None)
    nested_cm.__aexit__ = AsyncMock(return_value=False)
    db.begin_nested = MagicMock(return_value=nested_cm)
    db.add = MagicMock()  # db.add() is sync in real SQLAlchemy
    return db


def _payment_captured_payload(
    event_id="evt_001",
    rzp_payment_id="pay_ABC",
    rzp_order_id="order_XYZ",
    amount=100000,
):
    return {
        "event": "payment.captured",
        "id": event_id,
        "payload": {
            "payment": {
                "entity": {
                    "id": rzp_payment_id,
                    "order_id": rzp_order_id,
                    "amount": amount,
                    "currency": "INR",
                    "method": "upi",
                }
            }
        },
    }


def _payment_failed_payload(event_id="evt_002", rzp_order_id="order_XYZ"):
    return {
        "event": "payment.failed",
        "id": event_id,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_FAIL",
                    "order_id": rzp_order_id,
                    "error_description": "Insufficient funds",
                }
            }
        },
    }


def _order_paid_payload(event_id="evt_003", rzp_order_id="order_XYZ", amount=100000):
    return {
        "event": "order.paid",
        "id": event_id,
        "payload": {
            "order": {"entity": {"id": rzp_order_id}},
            "payment": {
                "entity": {
                    "id": "pay_ABC",
                    "order_id": rzp_order_id,
                    "amount": amount,
                    "currency": "INR",
                    "method": "netbanking",
                }
            },
        },
    }


def _refund_created_payload(
    event_id="evt_004", rzp_refund_id="rfnd_1", rzp_payment_id="pay_ABC"
):
    return {
        "event": "refund.created",
        "id": event_id,
        "payload": {
            "refund": {
                "entity": {
                    "id": rzp_refund_id,
                    "payment_id": rzp_payment_id,
                    "amount": 50000,
                }
            }
        },
    }


def _refund_processed_payload(event_id="evt_005", rzp_refund_id="rfnd_1"):
    return {
        "event": "refund.processed",
        "id": event_id,
        "payload": {"refund": {"entity": {"id": rzp_refund_id, "amount": 50000}}},
    }


def _refund_failed_payload(event_id="evt_006", rzp_refund_id="rfnd_1"):
    return {
        "event": "refund.failed",
        "id": event_id,
        "payload": {
            "refund": {
                "entity": {
                    "id": rzp_refund_id,
                    "error_description": "Bank rejected the refund",
                }
            }
        },
    }


def _mock_order(order_id=None, user_id=None, total=1000.0, payment_status="pending"):
    order = MagicMock()
    order.id = order_id or uuid.uuid4()
    order.user_id = user_id or uuid.uuid4()
    order.total = total
    order.payment_status = payment_status
    order.status = "stock_reserved"
    order.order_number = "HDH-202607-000001"
    order.coupon_id = None
    return order


def _mock_payment(payment_id=None, order_id=None, amount=1000.0, status="created"):
    payment = MagicMock()
    payment.id = payment_id or uuid.uuid4()
    payment.order_id = order_id or uuid.uuid4()
    payment.amount = amount
    payment.status = status
    return payment


def _mock_refund(
    refund_id=None, order_id=None, payment_id=None, amount=500.0, status="pending"
):
    refund = MagicMock()
    refund.id = refund_id or uuid.uuid4()
    refund.order_id = order_id or uuid.uuid4()
    refund.payment_id = payment_id or uuid.uuid4()
    refund.amount = amount
    refund.status = status
    return refund


# ── Signature / payload validation ────────────────────────────────────────────


class TestSignatureAndPayloadValidation:
    def setup_method(self):
        from app.modules.webhooks.service import WebhookService

        self.svc = WebhookService()

    async def test_invalid_signature_rejected(self):
        db = AsyncMock()
        with patch(
            "app.modules.webhooks.service.verify_razorpay_webhook_signature",
            return_value=False,
        ):
            result = await self.svc.handle_razorpay(db, b"{}", "bad_sig")
        assert result == {"status": "invalid_signature"}
        db.execute.assert_not_awaited()

    async def test_invalid_json_rejected(self):
        db = AsyncMock()
        with patch(
            "app.modules.webhooks.service.verify_razorpay_webhook_signature",
            return_value=True,
        ):
            result = await self.svc.handle_razorpay(db, b"not-json", "sig")
        assert result == {"status": "invalid_payload"}

    async def test_unknown_event_marks_ignored(self):
        db = AsyncMock()
        db.add = MagicMock()  # db.add() is sync in real SQLAlchemy
        body = json.dumps({"event": "subscription.charged", "id": "evt_999"}).encode()
        no_existing = MagicMock()
        no_existing.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=no_existing)
        with patch(
            "app.modules.webhooks.service.verify_razorpay_webhook_signature",
            return_value=True,
        ):
            result = await self.svc.handle_razorpay(db, body, "sig")
        assert result == {"status": "ignored"}


# ── Idempotency ────────────────────────────────────────────────────────────────


class TestIdempotency:
    def setup_method(self):
        from app.modules.webhooks.service import WebhookService

        self.svc = WebhookService()

    async def test_already_processed_event_skipped(self):
        db = AsyncMock()
        existing = MagicMock()
        existing.status = "processed"
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        db.execute = AsyncMock(return_value=result_mock)

        body = json.dumps(_payment_captured_payload()).encode()
        with patch(
            "app.modules.webhooks.service.verify_razorpay_webhook_signature",
            return_value=True,
        ):
            result = await self.svc.handle_razorpay(db, body, "sig")
        assert result == {"status": "already_processed"}
        # No further processing attempted — no savepoint opened.
        db.begin_nested.assert_not_called()

    async def test_duplicate_delivery_ten_times_processes_once(self):
        """A truly-processed event returns 'already_processed' on every
        subsequent delivery, however many times it's retried."""
        db = AsyncMock()
        existing = MagicMock()
        existing.status = "processed"
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        db.execute = AsyncMock(return_value=result_mock)

        body = json.dumps(_payment_captured_payload()).encode()
        results = []
        with patch(
            "app.modules.webhooks.service.verify_razorpay_webhook_signature",
            return_value=True,
        ):
            for _ in range(10):
                results.append(await self.svc.handle_razorpay(db, body, "sig"))
        assert all(r == {"status": "already_processed"} for r in results)

    async def test_retry_of_previously_failed_event_is_reprocessed(self):
        """A Razorpay retry of an event we previously failed to process must
        NOT be silently skipped — it should be attempted again."""
        db = _db_with_nested()
        existing = MagicMock()
        existing.status = "failed"
        existing.processing_attempts = 1
        existing.id = uuid.uuid4()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        db.execute = AsyncMock(return_value=result_mock)

        body = json.dumps(_payment_captured_payload()).encode()
        from app.modules.webhooks.service import _HandlerResult

        # The dispatch table binds handler methods at __init__ time, so
        # patch.object on the instance attribute afterward would not be
        # seen by the already-built self._handlers dict — override the
        # dispatch entry directly instead.
        mock_handler = AsyncMock(return_value=_HandlerResult(order_id=None, event=None))
        self.svc._handlers["payment.captured"] = mock_handler
        with patch(
            "app.modules.webhooks.service.verify_razorpay_webhook_signature",
            return_value=True,
        ):
            result = await self.svc.handle_razorpay(db, body, "sig")

        mock_handler.assert_awaited_once()
        assert existing.processing_attempts == 2
        assert result == {"status": "ok"}


# ── DB / handler-exception rollback ────────────────────────────────────────────


class TestHandlerFailure:
    def setup_method(self):
        from app.modules.webhooks.service import WebhookService

        self.svc = WebhookService()

    async def test_handler_exception_marks_failed_and_returns_processing_failed(self):
        db = _db_with_nested()
        no_existing = MagicMock()
        no_existing.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=no_existing)

        body = json.dumps(_payment_captured_payload()).encode()
        with (
            patch(
                "app.modules.webhooks.service.verify_razorpay_webhook_signature",
                return_value=True,
            ),
            patch.object(
                self.svc,
                "_on_payment_captured",
                AsyncMock(side_effect=RuntimeError("boom")),
            ),
        ):
            result = await self.svc.handle_razorpay(db, body, "sig")

        assert result == {"status": "processing_failed"}
        # Two commits: one for the failure record after mark_failed.
        assert db.commit.await_count >= 1

    async def test_inventory_failure_during_payment_captured_marks_failed(self):
        """If ReservationService.complete_order_reservations raises, the
        whole payment.captured handler must fail (order never gets marked
        paid without stock actually being decremented from reserved)."""
        from app.modules.inventory.reservation_service import ReservationService
        from app.modules.orders.repository import OrderRepository
        from app.modules.payments.repository import PaymentRepository

        db = _db_with_nested()
        no_existing = MagicMock()
        no_existing.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=no_existing)

        order = _mock_order(payment_status="pending")
        with (
            patch(
                "app.modules.webhooks.service.verify_razorpay_webhook_signature",
                return_value=True,
            ),
            patch.object(
                PaymentRepository,
                "get_by_razorpay_order_id",
                AsyncMock(return_value=None),
            ),
            patch.object(
                OrderRepository,
                "get_by_razorpay_order_id",
                AsyncMock(return_value=order),
            ),
            patch.object(PaymentRepository, "create", AsyncMock()),
            patch.object(
                ReservationService,
                "complete_order_reservations",
                AsyncMock(side_effect=RuntimeError("lock timeout")),
            ),
        ):
            body = json.dumps(
                _payment_captured_payload(amount=int(order.total * 100))
            ).encode()
            result = await self.svc.handle_razorpay(db, body, "sig")

        assert result == {"status": "processing_failed"}


# ── payment.captured ─────────────────────────────────────────────────────────


class TestPaymentCaptured:
    def setup_method(self):
        from app.modules.webhooks.service import WebhookService

        self.svc = WebhookService()

    async def test_idempotent_when_already_captured(self):
        db = AsyncMock()
        payment = _mock_payment(status="captured")
        from app.modules.payments.repository import PaymentRepository

        with patch.object(
            PaymentRepository,
            "get_by_razorpay_order_id",
            AsyncMock(return_value=payment),
        ):
            result = await self.svc._on_payment_captured(
                db, _payment_captured_payload()
            )
        assert result.event is None
        assert result.order_id == payment.order_id

    async def test_happy_path_completes_reservation_and_publishes_event(self):
        from app.modules.audit.service import AuditService
        from app.modules.inventory.reservation_service import ReservationService
        from app.modules.invoices.service import InvoiceService
        from app.modules.orders.repository import OrderRepository
        from app.modules.payments.repository import PaymentRepository
        from app.modules.profiles.repository import ProfileRepository

        db = AsyncMock()
        no_expired = MagicMock()
        no_expired.fetchone.return_value = None
        db.execute = AsyncMock(return_value=no_expired)
        payment = _mock_payment(status="created", amount=1000.0)
        order = _mock_order(
            order_id=payment.order_id, total=1000.0, payment_status="pending"
        )

        with (
            patch.object(
                PaymentRepository,
                "get_by_razorpay_order_id",
                AsyncMock(return_value=payment),
            ),
            patch.object(PaymentRepository, "update", AsyncMock()),
            patch.object(OrderRepository, "get_by_id", AsyncMock(return_value=order)),
            patch.object(OrderRepository, "update", AsyncMock()) as mock_order_update,
            patch.object(
                ReservationService, "complete_order_reservations", AsyncMock()
            ) as mock_complete,
            patch.object(
                InvoiceService, "generate_and_store", AsyncMock()
            ) as mock_invoice,
            patch.object(AuditService, "log", AsyncMock()) as mock_audit,
            patch.object(ProfileRepository, "get_by_id", AsyncMock(return_value=None)),
        ):
            result = await self.svc._on_payment_captured(
                db, _payment_captured_payload(amount=100000)
            )

        mock_complete.assert_awaited_once()
        mock_invoice.assert_awaited_once()
        mock_audit.assert_awaited_once()
        mock_order_update.assert_awaited_once()
        assert result.event is not None
        assert result.event.event_type == "PaymentCapturedEvent"
        assert result.order_id == order.id

    async def test_creates_payment_row_when_none_exists(self):
        """Webhook arrives before verify_and_fulfill ever created a Payment
        row — the handler must create one so refunds/invoices can reference it."""
        from app.modules.audit.service import AuditService
        from app.modules.inventory.reservation_service import ReservationService
        from app.modules.invoices.service import InvoiceService
        from app.modules.orders.repository import OrderRepository
        from app.modules.payments.repository import PaymentRepository
        from app.modules.profiles.repository import ProfileRepository

        db = AsyncMock()
        no_expired = MagicMock()
        no_expired.fetchone.return_value = None
        db.execute = AsyncMock(return_value=no_expired)
        order = _mock_order(total=1000.0, payment_status="pending")

        with (
            patch.object(
                PaymentRepository,
                "get_by_razorpay_order_id",
                AsyncMock(return_value=None),
            ),
            patch.object(
                OrderRepository,
                "get_by_razorpay_order_id",
                AsyncMock(return_value=order),
            ),
            patch.object(PaymentRepository, "create", AsyncMock()) as mock_create,
            patch.object(OrderRepository, "get_by_id", AsyncMock(return_value=order)),
            patch.object(OrderRepository, "update", AsyncMock()),
            patch.object(
                ReservationService, "complete_order_reservations", AsyncMock()
            ),
            patch.object(InvoiceService, "generate_and_store", AsyncMock()),
            patch.object(AuditService, "log", AsyncMock()),
            patch.object(ProfileRepository, "get_by_id", AsyncMock(return_value=None)),
        ):
            result = await self.svc._on_payment_captured(
                db, _payment_captured_payload(amount=100000)
            )

        mock_create.assert_awaited_once()
        assert result.order_id == order.id

    async def test_amount_mismatch_raises(self):
        from app.modules.orders.repository import OrderRepository
        from app.modules.payments.repository import PaymentRepository

        db = AsyncMock()
        order = _mock_order(total=1000.0, payment_status="pending")

        with (
            patch.object(
                PaymentRepository,
                "get_by_razorpay_order_id",
                AsyncMock(return_value=None),
            ),
            patch.object(
                OrderRepository,
                "get_by_razorpay_order_id",
                AsyncMock(return_value=order),
            ),
        ):
            with pytest.raises(ValueError, match="Amount mismatch"):
                await self.svc._on_payment_captured(
                    db, _payment_captured_payload(amount=1)
                )

    async def test_currency_mismatch_raises(self):
        from app.modules.orders.repository import OrderRepository
        from app.modules.payments.repository import PaymentRepository

        db = AsyncMock()
        order = _mock_order(total=1000.0, payment_status="pending")
        payload = _payment_captured_payload(amount=100000)
        payload["payload"]["payment"]["entity"]["currency"] = "USD"

        with (
            patch.object(
                PaymentRepository,
                "get_by_razorpay_order_id",
                AsyncMock(return_value=None),
            ),
            patch.object(
                OrderRepository,
                "get_by_razorpay_order_id",
                AsyncMock(return_value=order),
            ),
        ):
            with pytest.raises(ValueError, match="Currency mismatch"):
                await self.svc._on_payment_captured(db, payload)

    async def test_no_matching_order_raises(self):
        from app.modules.orders.repository import OrderRepository
        from app.modules.payments.repository import PaymentRepository

        db = AsyncMock()
        with (
            patch.object(
                PaymentRepository,
                "get_by_razorpay_order_id",
                AsyncMock(return_value=None),
            ),
            patch.object(
                OrderRepository,
                "get_by_razorpay_order_id",
                AsyncMock(return_value=None),
            ),
        ):
            with pytest.raises(ValueError, match="No order found"):
                await self.svc._on_payment_captured(
                    db, _payment_captured_payload(amount=100000)
                )

    async def test_already_paid_order_is_idempotent(self):
        from app.modules.orders.repository import OrderRepository
        from app.modules.payments.repository import PaymentRepository

        db = AsyncMock()
        payment = _mock_payment(status="created")
        order = _mock_order(order_id=payment.order_id, payment_status="paid")

        with (
            patch.object(
                PaymentRepository,
                "get_by_razorpay_order_id",
                AsyncMock(return_value=payment),
            ),
            patch.object(OrderRepository, "get_by_id", AsyncMock(return_value=order)),
        ):
            result = await self.svc._on_payment_captured(
                db, _payment_captured_payload(amount=int(order.total * 100))
            )
        assert result.event is None


# ── order.paid ───────────────────────────────────────────────────────────────


class TestOrderPaid:
    def setup_method(self):
        from app.modules.webhooks.service import WebhookService

        self.svc = WebhookService()

    async def test_already_paid_order_ignored_safely(self):
        from app.modules.orders.repository import OrderRepository

        db = AsyncMock()
        order = _mock_order(payment_status="paid")
        with patch.object(
            OrderRepository, "get_by_razorpay_order_id", AsyncMock(return_value=order)
        ):
            result = await self.svc._on_order_paid(db, _order_paid_payload())
        assert result.event is None
        assert result.order_id == order.id

    async def test_not_yet_paid_processes_like_payment_captured(self):
        from app.modules.audit.service import AuditService
        from app.modules.inventory.reservation_service import ReservationService
        from app.modules.invoices.service import InvoiceService
        from app.modules.orders.repository import OrderRepository
        from app.modules.payments.repository import PaymentRepository
        from app.modules.profiles.repository import ProfileRepository

        db = AsyncMock()
        no_expired = MagicMock()
        no_expired.fetchone.return_value = None
        db.execute = AsyncMock(return_value=no_expired)
        order = _mock_order(total=1000.0, payment_status="pending")

        with (
            patch.object(
                OrderRepository,
                "get_by_razorpay_order_id",
                AsyncMock(return_value=order),
            ),
            patch.object(
                PaymentRepository,
                "get_by_razorpay_order_id",
                AsyncMock(return_value=None),
            ),
            patch.object(PaymentRepository, "create", AsyncMock()),
            patch.object(OrderRepository, "get_by_id", AsyncMock(return_value=order)),
            patch.object(OrderRepository, "update", AsyncMock()),
            patch.object(
                ReservationService, "complete_order_reservations", AsyncMock()
            ) as mock_complete,
            patch.object(InvoiceService, "generate_and_store", AsyncMock()),
            patch.object(AuditService, "log", AsyncMock()),
            patch.object(ProfileRepository, "get_by_id", AsyncMock(return_value=None)),
        ):
            result = await self.svc._on_order_paid(
                db, _order_paid_payload(amount=100000)
            )

        mock_complete.assert_awaited_once()
        assert result.event is not None


# ── payment.failed ───────────────────────────────────────────────────────────


class TestPaymentFailed:
    def setup_method(self):
        from app.modules.webhooks.service import WebhookService

        self.svc = WebhookService()

    async def test_idempotent_when_already_failed(self):
        from app.modules.payments.repository import PaymentRepository

        db = AsyncMock()
        payment = _mock_payment(status="failed")
        with patch.object(
            PaymentRepository,
            "get_by_razorpay_order_id",
            AsyncMock(return_value=payment),
        ):
            result = await self.svc._on_payment_failed(db, _payment_failed_payload())
        assert result.event is None

    async def test_happy_path_releases_reservation_and_publishes_event(self):
        from app.modules.audit.service import AuditService
        from app.modules.inventory.reservation_service import ReservationService
        from app.modules.orders.repository import OrderRepository
        from app.modules.payments.repository import PaymentRepository

        db = AsyncMock()
        payment = _mock_payment(status="created")
        order = _mock_order(order_id=payment.order_id, payment_status="pending")

        with (
            patch.object(
                PaymentRepository,
                "get_by_razorpay_order_id",
                AsyncMock(return_value=payment),
            ),
            patch.object(PaymentRepository, "update", AsyncMock()),
            patch.object(OrderRepository, "get_by_id", AsyncMock(return_value=order)),
            patch.object(OrderRepository, "update", AsyncMock()) as mock_order_update,
            patch.object(
                ReservationService, "release_order_reservations", AsyncMock()
            ) as mock_release,
            patch.object(AuditService, "log", AsyncMock()),
        ):
            result = await self.svc._on_payment_failed(db, _payment_failed_payload())

        mock_release.assert_awaited_once()
        mock_order_update.assert_awaited_once()
        assert result.event is not None
        assert result.event.event_type == "PaymentFailedEvent"

    async def test_already_paid_order_never_downgraded(self):
        from app.modules.inventory.reservation_service import ReservationService
        from app.modules.orders.repository import OrderRepository
        from app.modules.payments.repository import PaymentRepository

        db = AsyncMock()
        payment = _mock_payment(status="created")
        order = _mock_order(order_id=payment.order_id, payment_status="paid")

        with (
            patch.object(
                PaymentRepository,
                "get_by_razorpay_order_id",
                AsyncMock(return_value=payment),
            ),
            patch.object(PaymentRepository, "update", AsyncMock()),
            patch.object(OrderRepository, "get_by_id", AsyncMock(return_value=order)),
            patch.object(
                ReservationService, "release_order_reservations", AsyncMock()
            ) as mock_release,
        ):
            result = await self.svc._on_payment_failed(db, _payment_failed_payload())

        mock_release.assert_not_awaited()
        assert result.event is None

    async def test_no_order_or_payment_raises(self):
        from app.modules.orders.repository import OrderRepository
        from app.modules.payments.repository import PaymentRepository

        db = AsyncMock()
        with (
            patch.object(
                PaymentRepository,
                "get_by_razorpay_order_id",
                AsyncMock(return_value=None),
            ),
            patch.object(
                OrderRepository,
                "get_by_razorpay_order_id",
                AsyncMock(return_value=None),
            ),
        ):
            with pytest.raises(ValueError, match="No order/payment found"):
                await self.svc._on_payment_failed(db, _payment_failed_payload())


# ── refund.created ───────────────────────────────────────────────────────────


class TestRefundCreated:
    def setup_method(self):
        from app.modules.webhooks.service import WebhookService

        self.svc = WebhookService()

    async def test_idempotent_when_refund_already_exists(self):
        """Covers the admin-initiated-refund race: initiate_refund already
        created this exact razorpay_refund_id row before the webhook arrived."""
        from app.modules.payments.repository import PaymentRepository

        db = AsyncMock()
        existing = _mock_refund()
        with patch.object(
            PaymentRepository,
            "get_refund_by_razorpay_id",
            AsyncMock(return_value=existing),
        ):
            result = await self.svc._on_refund_created(db, _refund_created_payload())
        assert result.event is None
        assert result.order_id == existing.order_id

    async def test_happy_path_creates_refund_and_publishes_event(self):
        from app.modules.audit.service import AuditService
        from app.modules.orders.repository import OrderRepository
        from app.modules.payments.repository import PaymentRepository
        from app.modules.profiles.repository import ProfileRepository

        db = AsyncMock()
        payment = _mock_payment(status="captured")
        order = _mock_order(order_id=payment.order_id)
        new_refund = _mock_refund(order_id=payment.order_id, payment_id=payment.id)

        with (
            patch.object(
                PaymentRepository,
                "get_refund_by_razorpay_id",
                AsyncMock(return_value=None),
            ),
            patch.object(
                PaymentRepository,
                "get_by_razorpay_payment_id",
                AsyncMock(return_value=payment),
            ),
            patch.object(
                PaymentRepository, "create_refund", AsyncMock(return_value=new_refund)
            ) as mock_create,
            patch.object(OrderRepository, "get_by_id", AsyncMock(return_value=order)),
            patch.object(OrderRepository, "update", AsyncMock()),
            patch.object(AuditService, "log", AsyncMock()),
            patch.object(ProfileRepository, "get_by_id", AsyncMock(return_value=None)),
        ):
            result = await self.svc._on_refund_created(db, _refund_created_payload())

        mock_create.assert_awaited_once()
        assert result.event is not None
        assert result.event.event_type == "RefundCreatedEvent"

    async def test_no_matching_payment_raises(self):
        from app.modules.payments.repository import PaymentRepository

        db = AsyncMock()
        with (
            patch.object(
                PaymentRepository,
                "get_refund_by_razorpay_id",
                AsyncMock(return_value=None),
            ),
            patch.object(
                PaymentRepository,
                "get_by_razorpay_payment_id",
                AsyncMock(return_value=None),
            ),
        ):
            with pytest.raises(ValueError, match="No payment found"):
                await self.svc._on_refund_created(db, _refund_created_payload())


# ── refund.processed ─────────────────────────────────────────────────────────


class TestRefundProcessed:
    def setup_method(self):
        from app.modules.webhooks.service import WebhookService

        self.svc = WebhookService()

    async def test_idempotent_when_already_processed(self):
        from app.modules.payments.repository import PaymentRepository

        db = AsyncMock()
        refund = _mock_refund(status="processed")
        with patch.object(
            PaymentRepository,
            "get_refund_by_razorpay_id",
            AsyncMock(return_value=refund),
        ):
            result = await self.svc._on_refund_processed(
                db, _refund_processed_payload()
            )
        assert result.event is None

    async def test_full_refund_marks_payment_and_order_refunded(self):
        from app.modules.audit.service import AuditService
        from app.modules.orders.repository import OrderRepository
        from app.modules.payments.repository import PaymentRepository
        from app.modules.profiles.repository import ProfileRepository

        db = AsyncMock()
        payment = _mock_payment(amount=500.0, status="captured")
        refund = _mock_refund(
            payment_id=payment.id,
            order_id=payment.order_id,
            amount=500.0,
            status="pending",
        )
        order = _mock_order(order_id=payment.order_id)

        with (
            patch.object(
                PaymentRepository,
                "get_refund_by_razorpay_id",
                AsyncMock(return_value=refund),
            ),
            patch.object(PaymentRepository, "update_refund", AsyncMock()),
            patch.object(
                PaymentRepository, "get_by_id", AsyncMock(return_value=payment)
            ),
            patch.object(
                PaymentRepository,
                "get_refunds_for_order",
                AsyncMock(
                    return_value=[_mock_refund(amount=500.0, status="processed")]
                ),
            ),
            patch.object(PaymentRepository, "update", AsyncMock()) as mock_pay_update,
            patch.object(OrderRepository, "get_by_id", AsyncMock(return_value=order)),
            patch.object(OrderRepository, "update", AsyncMock()) as mock_order_update,
            patch.object(AuditService, "log", AsyncMock()),
            patch.object(ProfileRepository, "get_by_id", AsyncMock(return_value=None)),
        ):
            result = await self.svc._on_refund_processed(
                db, _refund_processed_payload()
            )

        mock_pay_update.assert_awaited_once_with(db, payment.id, {"status": "refunded"})
        mock_order_update.assert_awaited_once()
        assert result.event is not None
        assert result.event.event_type == "RefundProcessedEvent"

    async def test_creates_then_processes_when_refund_created_never_arrived(self):
        from app.modules.audit.service import AuditService
        from app.modules.orders.repository import OrderRepository
        from app.modules.payments.repository import PaymentRepository
        from app.modules.profiles.repository import ProfileRepository

        db = AsyncMock()
        payment = _mock_payment(amount=500.0, status="captured")
        order = _mock_order(order_id=payment.order_id)
        new_refund = _mock_refund(
            payment_id=payment.id, order_id=payment.order_id, amount=500.0
        )

        with (
            patch.object(
                PaymentRepository,
                "get_refund_by_razorpay_id",
                AsyncMock(return_value=None),
            ),
            patch.object(
                PaymentRepository,
                "get_by_razorpay_payment_id",
                AsyncMock(return_value=payment),
            ),
            patch.object(
                PaymentRepository,
                "create_refund",
                AsyncMock(return_value=new_refund),
            ) as mock_create,
            patch.object(PaymentRepository, "update_refund", AsyncMock()),
            patch.object(
                PaymentRepository, "get_by_id", AsyncMock(return_value=payment)
            ),
            patch.object(
                PaymentRepository, "get_refunds_for_order", AsyncMock(return_value=[])
            ),
            patch.object(PaymentRepository, "update", AsyncMock()),
            patch.object(OrderRepository, "get_by_id", AsyncMock(return_value=order)),
            patch.object(OrderRepository, "update", AsyncMock()),
            patch.object(AuditService, "log", AsyncMock()),
            patch.object(ProfileRepository, "get_by_id", AsyncMock(return_value=None)),
        ):
            result = await self.svc._on_refund_processed(
                db, _refund_processed_payload()
            )

        mock_create.assert_awaited_once()
        assert result.order_id == payment.order_id


# ── refund.failed ────────────────────────────────────────────────────────────


class TestRefundFailed:
    def setup_method(self):
        from app.modules.webhooks.service import WebhookService

        self.svc = WebhookService()

    async def test_unknown_refund_logs_and_no_ops(self):
        from app.modules.payments.repository import PaymentRepository

        db = AsyncMock()
        with patch.object(
            PaymentRepository,
            "get_refund_by_razorpay_id",
            AsyncMock(return_value=None),
        ):
            result = await self.svc._on_refund_failed(db, _refund_failed_payload())
        assert result.event is None
        assert result.order_id is None

    async def test_idempotent_when_already_failed(self):
        from app.modules.payments.repository import PaymentRepository

        db = AsyncMock()
        refund = _mock_refund(status="failed")
        with patch.object(
            PaymentRepository,
            "get_refund_by_razorpay_id",
            AsyncMock(return_value=refund),
        ):
            result = await self.svc._on_refund_failed(db, _refund_failed_payload())
        assert result.event is None

    async def test_happy_path_marks_failed_and_publishes_event(self):
        from app.modules.audit.service import AuditService
        from app.modules.orders.repository import OrderRepository
        from app.modules.payments.repository import PaymentRepository

        db = AsyncMock()
        refund = _mock_refund(status="pending")
        order = _mock_order(order_id=refund.order_id)

        with (
            patch.object(
                PaymentRepository,
                "get_refund_by_razorpay_id",
                AsyncMock(return_value=refund),
            ),
            patch.object(
                PaymentRepository, "update_refund", AsyncMock()
            ) as mock_update,
            patch.object(AuditService, "log", AsyncMock()),
            patch.object(OrderRepository, "get_by_id", AsyncMock(return_value=order)),
        ):
            result = await self.svc._on_refund_failed(db, _refund_failed_payload())

        mock_update.assert_awaited_once_with(
            db,
            refund.id,
            {"status": "failed", "failure_reason": "Bank rejected the refund"},
        )
        assert result.event is not None
        assert result.event.event_type == "RefundFailedEvent"


# ── End-to-end dispatcher wiring (all 6 event types) ──────────────────────────


class TestDispatcherRouting:
    """Confirms handle_razorpay routes each event_type to the correct
    handler and that a successful run commits, publishes, and marks
    processed."""

    def setup_method(self):
        from app.modules.webhooks.service import WebhookService

        self.svc = WebhookService()

    async def _run(self, payload: dict, event_type: str):
        db = _db_with_nested()
        no_existing = MagicMock()
        no_existing.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=no_existing)

        from app.modules.webhooks.service import _HandlerResult

        # The dispatch table is built once in __init__ from bound methods,
        # so overriding self.svc._on_x afterward wouldn't be seen by
        # self._handlers — replace the dispatch entry directly instead.
        mock_handler = AsyncMock(return_value=_HandlerResult(order_id=None, event=None))
        self.svc._handlers[event_type] = mock_handler
        with patch(
            "app.modules.webhooks.service.verify_razorpay_webhook_signature",
            return_value=True,
        ):
            result = await self.svc.handle_razorpay(
                db, json.dumps(payload).encode(), "sig"
            )
        mock_handler.assert_awaited_once()
        assert result == {"status": "ok"}

    async def test_payment_captured_routes_correctly(self):
        await self._run(_payment_captured_payload(), "payment.captured")

    async def test_payment_failed_routes_correctly(self):
        await self._run(_payment_failed_payload(), "payment.failed")

    async def test_order_paid_routes_correctly(self):
        await self._run(_order_paid_payload(), "order.paid")

    async def test_refund_created_routes_correctly(self):
        await self._run(_refund_created_payload(), "refund.created")

    async def test_refund_processed_routes_correctly(self):
        await self._run(_refund_processed_payload(), "refund.processed")

    async def test_refund_failed_routes_correctly(self):
        await self._run(_refund_failed_payload(), "refund.failed")

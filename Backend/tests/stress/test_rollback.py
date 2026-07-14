"""
Transaction rollback and error-path validation tests.

These tests verify that the reservation system fails safely:

  1. InventoryError during reserve_items — partial work is not committed
  2. reserve_items fails mid-loop — stock not double-counted
  3. complete_order_reservations with no active rows — idempotent no-op
  4. release_order_reservations with no active rows — idempotent no-op
  5. DB exception during complete propagates — not silently swallowed
  6. HMAC failure in handle_razorpay — zero DB writes
  7. Payment failure path — release always called even if order update fails
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import InventoryError, NotFoundError

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_product_row(
    stock: int = 10,
    reserved: int = 0,
    sold: int = 0,
    allow_backorder: bool = False,
    name: str = "Test Ring",
    sku: str = "SKU-001",
) -> MagicMock:
    row = MagicMock()
    row._mapping = {
        "id": str(uuid.uuid4()),
        "name": name,
        "sku": sku,
        "stock_quantity": stock,
        "reserved_quantity": reserved,
        "sold_quantity": sold,
        "track_inventory": True,
        "allow_backorder": allow_backorder,
    }
    return row


def _exec_returning_row(row: MagicMock) -> MagicMock:
    result = MagicMock()
    result.fetchone.return_value = row
    return result


def _exec_returning_rows(rows: list) -> MagicMock:
    result = MagicMock()
    result.fetchall.return_value = rows
    return result


def _exec_noop() -> MagicMock:
    return MagicMock()


def _exec_scalar(value: int) -> MagicMock:
    result = MagicMock()
    result.scalar_one.return_value = value
    return result


# ── 1. InventoryError stops early — no partial commit ─────────────────────


class TestReserveItemsRollback:
    """
    When reserve_items raises InventoryError, the caller owns the transaction.
    Inside the service, no explicit rollback is needed because the caller's
    `async with db.begin()` context manager handles it.  These tests verify
    the service raises correctly and does not suppress the error.
    """

    async def test_insufficient_stock_raises_inventory_error(self):
        from app.modules.inventory.reservation_service import ReservationService

        product_id = uuid.uuid4()
        prod_row = _make_product_row(stock=5, reserved=4, sold=0)  # only 1 available

        # SELECT FOR UPDATE returns the product row
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_exec_returning_row(prod_row))
        db.add = MagicMock()
        db.flush = AsyncMock()

        svc = ReservationService()
        with pytest.raises(InventoryError, match=r"item\(s\) available"):
            await svc.reserve_items(
                db,
                user_id=uuid.uuid4(),
                items=[{"product_id": product_id, "quantity": 3}],
            )

        # One extra execute for get_user_active_reservations + the SELECT FOR UPDATE
        assert db.execute.await_count == 2

    async def test_product_not_found_raises_not_found(self):
        from app.modules.inventory.reservation_service import ReservationService

        db = AsyncMock()
        # SELECT FOR UPDATE returns no row
        no_result = MagicMock()
        no_result.fetchone.return_value = None
        db.execute = AsyncMock(return_value=no_result)
        db.add = MagicMock()
        db.flush = AsyncMock()

        svc = ReservationService()
        with pytest.raises(NotFoundError):
            await svc.reserve_items(
                db,
                user_id=uuid.uuid4(),
                items=[{"product_id": uuid.uuid4(), "quantity": 1}],
            )

    async def test_second_item_fails_first_item_update_already_issued(self):
        """
        If the first item succeeds but the second fails, the caller must rollback.
        The service does not rollback internally — this test confirms the exception
        propagates so the caller can handle it.
        """
        from app.modules.inventory.reservation_service import ReservationService

        # Fixed, lexicographically-ordered UUIDs — reserve_items sorts by
        # (product_id, variant_id) before locking (deadlock prevention), so
        # the mocked side_effect sequence below must be stable across runs
        # rather than depending on random uuid4() insertion order.
        p1_id = uuid.UUID(int=1)
        p2_id = uuid.UUID(int=2)

        p1_row = _make_product_row(stock=10, name="Ring A")
        p2_row = _make_product_row(stock=2, reserved=2, name="Ring B")  # 0 available

        reservation_mock = MagicMock()
        reservation_mock.id = uuid.uuid4()
        reservation_mock.reservation_number = "RES-ABCD1234"

        # Sequence: get_user_active, SELECT p1, UPDATE p1, (flush), SELECT p2 → error
        execute_results = [
            _exec_returning_row(
                p1_row
            ),  # get_user_active_reservations (fetchall → empty)
            _exec_returning_row(p1_row),  # SELECT p1 FOR UPDATE
            _exec_noop(),  # UPDATE products (p1 reserved_quantity++)
            _exec_returning_row(p2_row),  # SELECT p2 FOR UPDATE
        ]

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=execute_results)
        db.add = MagicMock()
        db.flush = AsyncMock()

        svc = ReservationService()
        with pytest.raises(InventoryError, match=r"item\(s\) available"):
            await svc.reserve_items(
                db,
                user_id=uuid.uuid4(),
                items=[
                    {"product_id": p1_id, "quantity": 1},
                    {"product_id": p2_id, "quantity": 5},
                ],
            )

        # The second SELECT caused the error; no UPDATE for p2 was issued
        assert (
            db.execute.await_count == 4
        )  # get_user_active, SELECT p1, UPDATE p1, SELECT p2


# ── 2. complete_order_reservations — idempotency ──────────────────────────


class TestCompleteReservationsIdempotency:
    """
    complete_order_reservations is called after payment capture.
    If no ACTIVE reservations exist (already completed or none), it should
    not raise and should not corrupt stock.
    """

    async def test_already_completed_is_silent_no_op(self):
        """Second call: no ACTIVE rows → CHECK finds COMPLETED rows → returns."""
        from app.modules.inventory.reservation_service import ReservationService

        order_id = uuid.uuid4()
        # SELECT ACTIVE → empty; SELECT COUNT(COMPLETED) → 1
        active_result = MagicMock()
        active_result.fetchall.return_value = []

        completed_result = MagicMock()
        completed_result.scalar_one.return_value = 1  # already completed

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[active_result, completed_result])
        db.add = MagicMock()
        db.flush = AsyncMock()

        svc = ReservationService()
        # Must not raise
        await svc.complete_order_reservations(db, order_id)

        # Only 2 SQL calls: SELECT ACTIVE, SELECT COUNT(COMPLETED)
        assert db.execute.await_count == 2

    async def test_no_reservations_at_all_is_silent(self):
        """Order with zero reservations: no rows active or completed."""
        from app.modules.inventory.reservation_service import ReservationService

        order_id = uuid.uuid4()
        active_result = MagicMock()
        active_result.fetchall.return_value = []

        completed_result = MagicMock()
        completed_result.scalar_one.return_value = 0  # nothing at all

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[active_result, completed_result])
        db.add = MagicMock()

        svc = ReservationService()
        await svc.complete_order_reservations(db, order_id)

        assert db.execute.await_count == 2

    async def test_db_exception_during_product_lock_propagates(self):
        """If the product SELECT FOR UPDATE fails, exception must propagate."""
        from app.modules.inventory.reservation_service import ReservationService

        order_id = uuid.uuid4()
        res_row = (uuid.uuid4(), uuid.uuid4(), None, 2)

        active_result = MagicMock()
        active_result.fetchall.return_value = [res_row]

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                active_result,  # SELECT ACTIVE rows
                RuntimeError("DB connection lost"),  # SELECT product FOR UPDATE
            ]
        )
        db.add = MagicMock()

        svc = ReservationService()
        with pytest.raises(RuntimeError, match="DB connection lost"):
            await svc.complete_order_reservations(db, order_id)


# ── 3. release_order_reservations — idempotency ───────────────────────────


class TestReleaseReservationsIdempotency:
    """
    release_order_reservations is called on payment failure and order cancellation.
    If no ACTIVE reservations exist, it should be a safe no-op.
    """

    async def test_no_active_reservations_is_no_op(self):
        from app.modules.inventory.reservation_service import ReservationService

        order_id = uuid.uuid4()
        empty_result = MagicMock()
        empty_result.fetchall.return_value = []

        db = AsyncMock()
        db.execute = AsyncMock(return_value=empty_result)
        db.add = MagicMock()

        svc = ReservationService()
        await svc.release_order_reservations(db, order_id)

        # Only one SQL call: SELECT ACTIVE FOR UPDATE
        assert db.execute.await_count == 1

    async def test_second_release_is_no_op(self):
        """
        After the first release sets status='RELEASED', the second release
        finds no ACTIVE rows and returns early.
        """
        from app.modules.inventory.reservation_service import ReservationService

        order_id = uuid.uuid4()
        res_id = uuid.uuid4()
        product_id = uuid.uuid4()

        prod_row = _make_product_row(stock=10, reserved=1)

        # First call: 1 ACTIVE row → processes it
        active_result = MagicMock()
        active_result.fetchall.return_value = [(res_id, product_id, None, 1)]

        # Second call: no ACTIVE rows
        empty_result = MagicMock()
        empty_result.fetchall.return_value = []

        # First call sequence: SELECT ACTIVE, SELECT product, UPDATE products, UPDATE reservation
        db_first = AsyncMock()
        db_first.execute = AsyncMock(
            side_effect=[
                active_result,
                _exec_returning_row(prod_row),
                _exec_noop(),  # UPDATE products
                _exec_noop(),  # UPDATE reservations
            ]
        )
        db_first.add = MagicMock()
        db_first.flush = AsyncMock()

        db_second = AsyncMock()
        db_second.execute = AsyncMock(return_value=empty_result)
        db_second.add = MagicMock()

        svc = ReservationService()
        await svc.release_order_reservations(db_first, order_id)
        await svc.release_order_reservations(db_second, order_id)

        # Second call: only 1 execute (the SELECT ACTIVE)
        assert db_second.execute.await_count == 1

    async def test_release_decrements_reserved_quantity(self):
        """
        After release, the correct UPDATE products SQL is issued with the right qty.
        """
        from app.modules.inventory.reservation_service import ReservationService

        order_id = uuid.uuid4()
        res_id = uuid.uuid4()
        product_id = uuid.uuid4()
        quantity = 5

        prod_row = _make_product_row(stock=20, reserved=5)

        active_result = MagicMock()
        active_result.fetchall.return_value = [(res_id, product_id, None, quantity)]

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                active_result,
                _exec_returning_row(prod_row),
                _exec_noop(),  # UPDATE products
                _exec_noop(),  # UPDATE reservations
            ]
        )
        db.add = MagicMock()
        db.flush = AsyncMock()

        svc = ReservationService()
        await svc.release_order_reservations(db, order_id)

        # Verify UPDATE products was called with qty=5
        update_call = db.execute.await_args_list[2]
        sql_params = update_call.args[1] if len(update_call.args) > 1 else {}
        assert sql_params.get("qty") == quantity


# ── 4. HMAC failure — no DB writes ────────────────────────────────────────


class TestHmacFailureNoDbWrites:
    """
    If verify_razorpay_webhook_signature raises/returns False, handle_razorpay
    must return an error immediately without touching the DB at all.
    """

    def setup_method(self):
        from app.modules.webhooks.service import WebhookService

        self.svc = WebhookService()

    async def test_invalid_signature_raises_before_db(self):
        import json

        from app.core.exceptions import ValidationError as AppValidationError

        body = json.dumps({"event": "payment.captured"}).encode()
        db = AsyncMock()

        with patch(
            "app.modules.webhooks.service.verify_razorpay_webhook_signature",
            side_effect=AppValidationError("Invalid HMAC"),
        ):
            with pytest.raises(AppValidationError):
                await self.svc.handle_razorpay(db, body, "bad_signature")

        # No DB access should have occurred
        db.execute.assert_not_awaited()

    async def test_invalid_json_returns_error_before_db(self):
        db = AsyncMock()

        with patch(
            "app.modules.webhooks.service.verify_razorpay_webhook_signature",
            return_value=True,
        ):
            result = await self.svc.handle_razorpay(db, b"not-json", "sig")

        assert result == {"status": "invalid_payload"}
        db.execute.assert_not_awaited()


# ── 5. Payment failure path — release always called ───────────────────────


class TestPaymentFailureRelease:
    """
    _on_payment_failed must call release_order_reservations even if the
    order UPDATE itself fails.
    """

    def setup_method(self):
        from app.modules.webhooks.service import WebhookService

        self.svc = WebhookService()

    async def test_release_called_even_if_order_update_raises(self):
        from app.modules.inventory.reservation_service import ReservationService
        from app.modules.orders.repository import OrderRepository
        from app.modules.payments.repository import PaymentRepository

        order_id = uuid.uuid4()
        payment_id = uuid.uuid4()

        payment = MagicMock()
        payment.id = payment_id
        payment.order_id = order_id

        order = MagicMock()
        order.id = order_id
        order.payment_status = "pending"
        order.coupon_id = None

        release_called = {"n": 0}

        async def _release(_, db, oid, reason="RELEASED"):
            release_called["n"] += 1

        no_row = MagicMock(fetchone=MagicMock(return_value=None))
        db = AsyncMock()
        db.execute = AsyncMock(return_value=no_row)

        payload = {
            "event": "payment.failed",
            "payload": {
                "payment": {
                    "entity": {
                        "order_id": "rzp_ord_XYZ",
                        "error_description": "Card declined",
                    }
                }
            },
        }

        with (
            patch.object(
                PaymentRepository,
                "get_by_razorpay_order_id",
                AsyncMock(return_value=payment),
            ),
            patch.object(PaymentRepository, "update", AsyncMock()),
            patch.object(ReservationService, "release_order_reservations", _release),
            patch.object(
                OrderRepository,
                "get_by_id",
                AsyncMock(return_value=order),
            ),
            patch.object(
                OrderRepository,
                "update",
                AsyncMock(side_effect=RuntimeError("DB error")),
            ),
            patch("app.core.events.event_bus.publish", AsyncMock()),
        ):
            # The RuntimeError from OrderRepository.update should propagate
            with pytest.raises(RuntimeError, match="DB error"):
                await self.svc._on_payment_failed(db, payload)

        # But release was still called before the order update
        assert release_called["n"] == 1

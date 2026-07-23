"""Unit tests for ReservationService — all paths, all branches."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

# ── helpers ────────────────────────────────────────────────────────────────────


def _prod_mapping(
    *,
    product_id: uuid.UUID | None = None,
    name: str = "Silver Ring",
    sku: str = "RING-001",
    stock: int = 10,
    reserved: int = 0,
    sold: int = 0,
    allow_backorder: bool = False,
    track_inventory: bool = True,
) -> dict:
    return {
        "id": str(product_id or uuid.uuid4()),
        "name": name,
        "sku": sku,
        "stock_quantity": stock,
        "reserved_quantity": reserved,
        "sold_quantity": sold,
        "allow_backorder": allow_backorder,
        "track_inventory": track_inventory,
    }


def _variant_mapping(
    *,
    variant_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    variant_name: str = "Ring Size 20",
    product_name: str = "Silver Ring",
    stock: int = 10,
    reserved: int = 0,
    sold: int = 0,
    allow_backorder: bool = False,
    track_inventory: bool = True,
) -> dict:
    """Mapping returned by the JOIN query in _lock_stock_target for variant path."""
    return {
        "target_id": str(variant_id or uuid.uuid4()),
        "product_id": str(product_id or uuid.uuid4()),
        "variant_name": variant_name,
        "product_name": product_name,
        "stock_quantity": stock,
        "reserved_quantity": reserved,
        "sold_quantity": sold,
        "allow_backorder": allow_backorder,
        "track_inventory": track_inventory,
    }


def _lock_result(mapping: dict | None) -> MagicMock:
    """Simulate a SELECT...FOR UPDATE result whose .fetchone() returns a row with ._mapping."""
    row = MagicMock()
    row._mapping = mapping
    result = MagicMock()
    result.fetchone.return_value = row if mapping is not None else None
    return result


def _scalar_result(value: int) -> MagicMock:
    """Simulate a result whose .scalar_one() returns an integer."""
    result = MagicMock()
    result.scalar_one.return_value = value
    return result


def _fetchone_result(row) -> MagicMock:
    """Simulate a result whose .fetchone() returns the given row."""
    result = MagicMock()
    result.fetchone.return_value = row
    return result


def _fetchall_result(rows: list) -> MagicMock:
    """Simulate a result whose .fetchall() returns the given rows."""
    result = MagicMock()
    result.fetchall.return_value = rows
    return result


def _noop_result() -> MagicMock:
    """Simulate an UPDATE result with rowcount=1 (successful update)."""
    r = MagicMock()
    r.rowcount = 1
    return r


# ── TestReserveItems ───────────────────────────────────────────────────────────


class TestReserveItems:
    def setup_method(self):
        from app.modules.inventory.reservation_service import ReservationService

        self.svc = ReservationService()

    async def test_empty_items_returns_empty_list(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_fetchall_result([]))
        result = await self.svc.reserve_items(db, user_id=uuid.uuid4(), items=[])
        assert result == []
        # get_user_active_reservations makes one execute call
        assert db.execute.call_count == 1
        db.add.assert_not_called()

    async def test_reserve_single_item_success(self):
        product_id = uuid.uuid4()
        user_id = uuid.uuid4()
        mapping = _prod_mapping(product_id=product_id, stock=10, reserved=0, sold=0)

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([]),  # get_user_active_reservations
                _lock_result(mapping),  # SELECT FOR UPDATE (lock_product)
                _noop_result(),  # UPDATE products SET reserved_quantity += qty
            ]
        )
        db.add = MagicMock()
        db.flush = AsyncMock()

        items = [{"product_id": product_id, "variant_id": None, "quantity": 3}]
        reservations = await self.svc.reserve_items(db, user_id=user_id, items=items)

        assert len(reservations) == 1
        r = reservations[0]
        assert r.quantity == 3
        assert r.status == "ACTIVE"
        assert r.user_id == user_id
        assert r.product_id == product_id
        assert r.order_id is None
        assert r.reservation_number.startswith("RES-")
        assert r.expires_at > datetime.now(UTC)

        db.flush.assert_called_once()
        # add called twice: InventoryReservation + InventoryTransaction
        assert db.add.call_count == 2

    async def test_reserve_reuses_existing_reservation_binds_datetime(self):
        """When the customer already holds an ACTIVE reservation, reserve_items
        reuses it via a raw UPDATE. The expires_at bind MUST be a datetime, not
        an isoformat string, or asyncpg raises DataError against the timestamptz
        column (regression: the reuse path 500'd on every checkout retry)."""
        product_id = uuid.uuid4()
        user_id = uuid.uuid4()

        existing_row = MagicMock()
        existing_row._mapping = {
            "id": uuid.uuid4(),
            "reservation_number": "RES-DEADBEEF",
            "product_id": product_id,
            "variant_id": None,
            "quantity": 2,
            "expires_at": datetime.now(UTC),
            "order_id": None,
        }

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([existing_row]),  # get_user_active_reservations
                _noop_result(),  # reuse UPDATE inventory_reservations
            ]
        )
        db.add = MagicMock()
        db.flush = AsyncMock()

        items = [{"product_id": product_id, "variant_id": None, "quantity": 2}]
        reservations = await self.svc.reserve_items(db, user_id=user_id, items=items)

        # Reused, not newly created: no ORM add, no stock re-lock/increment.
        assert len(reservations) == 1
        assert reservations[0].quantity == 2
        db.add.assert_not_called()

        # The UPDATE (2nd execute) must bind a datetime for expires_at.
        update_call = db.execute.call_args_list[1]
        bound_params = update_call.args[1]
        assert isinstance(bound_params["expires"], datetime)

    async def test_reserve_multiple_items_success(self):
        # Fixed, lexicographically-ordered UUIDs: reserve_items sorts by
        # (product_id, variant_id) before locking (deadlock prevention), so
        # the mocked db.execute side_effect sequence below must match that
        # order rather than random uuid4() insertion order.
        pid1, pid2 = uuid.UUID(int=1), uuid.UUID(int=2)
        user_id = uuid.uuid4()
        m1 = _prod_mapping(product_id=pid1, stock=5, reserved=0, sold=0)
        m2 = _prod_mapping(product_id=pid2, stock=8, reserved=1, sold=1)

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([]),  # get_user_active_reservations
                _lock_result(m1),  # lock item 1
                _noop_result(),  # update item 1
                _lock_result(m2),  # lock item 2
                _noop_result(),  # update item 2
            ]
        )
        db.add = MagicMock()
        db.flush = AsyncMock()

        items = [
            {"product_id": pid1, "variant_id": None, "quantity": 2},
            {"product_id": pid2, "variant_id": None, "quantity": 3},
        ]
        reservations = await self.svc.reserve_items(db, user_id=user_id, items=items)

        assert len(reservations) == 2
        assert reservations[0].quantity == 2
        assert reservations[1].quantity == 3
        # 2 flushes (one per item), 4 add calls (reservation + txn per item)
        assert db.flush.call_count == 2
        assert db.add.call_count == 4

    async def test_reserve_insufficient_stock_raises_inventory_error(self):
        from app.core.exceptions import InventoryError

        product_id = uuid.uuid4()
        # available = 5 - 3 - 1 = 1, requesting 3
        mapping = _prod_mapping(
            product_id=product_id, stock=5, reserved=3, sold=1, allow_backorder=False
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([]),  # get_user_active_reservations
                _lock_result(mapping),
            ]
        )

        items = [{"product_id": product_id, "variant_id": None, "quantity": 3}]
        with pytest.raises(InventoryError, match="1 item"):
            await self.svc.reserve_items(db, user_id=uuid.uuid4(), items=items)

        # get_user_active_reservations + the lock SELECT
        assert db.execute.call_count == 2

    async def test_reserve_zero_available_raises_inventory_error(self):
        from app.core.exceptions import InventoryError

        product_id = uuid.uuid4()
        mapping = _prod_mapping(
            product_id=product_id, stock=5, reserved=3, sold=2, allow_backorder=False
        )
        # available = 0

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([]),  # get_user_active_reservations
                _lock_result(mapping),
            ]
        )

        items = [{"product_id": product_id, "variant_id": None, "quantity": 1}]
        with pytest.raises(InventoryError, match="0 item"):
            await self.svc.reserve_items(db, user_id=uuid.uuid4(), items=items)

    async def test_reserve_product_not_found_raises_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([]),  # get_user_active_reservations
                _lock_result(None),  # fetchone returns None
            ]
        )

        items = [{"product_id": uuid.uuid4(), "variant_id": None, "quantity": 1}]
        with pytest.raises(NotFoundError):
            await self.svc.reserve_items(db, user_id=uuid.uuid4(), items=items)

    async def test_reserve_backorder_allowed_succeeds_with_zero_stock(self):
        product_id = uuid.uuid4()
        # available = 2 - 2 - 0 = 0, but allow_backorder=True
        mapping = _prod_mapping(
            product_id=product_id,
            stock=2,
            reserved=2,
            sold=0,
            allow_backorder=True,
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([]),  # get_user_active_reservations
                _lock_result(mapping),  # lock product
                _noop_result(),  # update product
            ]
        )
        db.add = MagicMock()
        db.flush = AsyncMock()

        items = [{"product_id": product_id, "variant_id": None, "quantity": 5}]
        reservations = await self.svc.reserve_items(
            db, user_id=uuid.uuid4(), items=items
        )

        assert len(reservations) == 1
        assert reservations[0].quantity == 5

    async def test_reserve_with_variant_id(self):
        product_id = uuid.uuid4()
        variant_id = uuid.uuid4()
        mapping = _variant_mapping(
            variant_id=variant_id, product_id=product_id, stock=10
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([]),  # get_user_active_reservations
                _lock_result(mapping),  # lock variant
                _noop_result(),  # update variant
            ]
        )
        db.add = MagicMock()
        db.flush = AsyncMock()

        items = [{"product_id": product_id, "variant_id": variant_id, "quantity": 1}]
        reservations = await self.svc.reserve_items(
            db, user_id=uuid.uuid4(), items=items
        )

        assert reservations[0].variant_id == variant_id
        assert reservations[0].product_id == product_id

    async def test_reserve_fails_on_second_item_does_not_rollback_first(self):
        """
        If the second item lacks stock, InventoryError is raised.
        The caller owns the transaction and must roll back both reservations.
        This test verifies the error propagates correctly.
        """
        from app.core.exceptions import InventoryError

        # Fixed, lexicographically-ordered UUIDs — reserve_items sorts by
        # (product_id, variant_id) before locking (deadlock prevention), so
        # the mocked side_effect order below must be stable across runs.
        pid1, pid2 = uuid.UUID(int=1), uuid.UUID(int=2)
        m1 = _prod_mapping(product_id=pid1, stock=10)
        m2 = _prod_mapping(
            product_id=pid2, stock=2, reserved=2, sold=0, allow_backorder=False
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([]),  # get_user_active_reservations
                _lock_result(m1),  # lock pid1 — ok
                _noop_result(),  # update pid1
                _lock_result(m2),  # lock pid2 — available=0, qty=1
            ]
        )
        db.add = MagicMock()
        db.flush = AsyncMock()

        items = [
            {"product_id": pid1, "variant_id": None, "quantity": 1},
            {"product_id": pid2, "variant_id": None, "quantity": 1},
        ]
        with pytest.raises(InventoryError):
            await self.svc.reserve_items(db, user_id=uuid.uuid4(), items=items)

    async def test_reservation_ttl_is_ten_minutes(self):
        product_id = uuid.uuid4()
        mapping = _prod_mapping(product_id=product_id, stock=10)

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([]),  # get_user_active_reservations
                _lock_result(mapping),  # lock product
                _noop_result(),  # update product
            ]
        )
        db.add = MagicMock()
        db.flush = AsyncMock()

        before = datetime.now(UTC)
        items = [{"product_id": product_id, "variant_id": None, "quantity": 1}]
        reservations = await self.svc.reserve_items(
            db, user_id=uuid.uuid4(), items=items
        )
        after = datetime.now(UTC)

        expires_at = reservations[0].expires_at
        assert expires_at > before + timedelta(minutes=9, seconds=50)
        assert expires_at < after + timedelta(minutes=10, seconds=10)


# ── TestLinkReservationsToOrder ────────────────────────────────────────────────


class TestLinkReservationsToOrder:
    def setup_method(self):
        from app.modules.inventory.reservation_service import ReservationService

        self.svc = ReservationService()

    async def test_empty_reservations_skips_db(self):
        db = AsyncMock()
        await self.svc.link_reservations_to_order(db, [], uuid.uuid4())
        db.execute.assert_not_called()

    async def test_links_reservations_and_transactions(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_noop_result())

        order_id = uuid.uuid4()
        r1 = MagicMock()
        r1.id = uuid.uuid4()
        r2 = MagicMock()
        r2.id = uuid.uuid4()

        await self.svc.link_reservations_to_order(db, [r1, r2], order_id)

        # Two UPDATE calls: inventory_reservations + inventory_transactions
        assert db.execute.call_count == 2
        # Both calls should include order_id in params
        for c in db.execute.call_args_list:
            args, kwargs = c
            params = args[1] if len(args) > 1 else {}
            assert "order_id" in params
            assert params["order_id"] == str(order_id)


# ── TestCompleteOrderReservations ─────────────────────────────────────────────


class TestCompleteOrderReservations:
    def setup_method(self):
        from app.modules.inventory.reservation_service import ReservationService

        self.svc = ReservationService()

    async def test_complete_single_reservation_success(self):
        order_id = uuid.uuid4()
        res_id = uuid.uuid4()
        product_id = uuid.uuid4()

        # active reservation row: (id, product_id, variant_id, quantity)
        active_row = (res_id, product_id, None, 2)

        # product state after lock
        prod_mapping = {
            "stock_quantity": 10,
            "reserved_quantity": 2,
            "sold_quantity": 0,
        }
        prod_row = MagicMock()
        prod_row._mapping = prod_mapping

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([active_row]),  # SELECT ACTIVE reservations
                _fetchone_result(prod_row),  # SELECT product FOR UPDATE
                _noop_result(),  # UPDATE products (reserved→sold)
                _noop_result(),  # UPDATE reservations SET status='COMPLETED'
            ]
        )
        db.add = MagicMock()

        await self.svc.complete_order_reservations(db, order_id)

        # The transaction log was added
        db.add.assert_called_once()
        added = db.add.call_args[0][0]
        from app.modules.inventory.models import InventoryTransaction

        assert isinstance(added, InventoryTransaction)
        assert added.transaction_type == "SALE"
        assert added.quantity == 2
        assert added.order_id == order_id

    async def test_complete_already_completed_is_idempotent(self):
        order_id = uuid.uuid4()

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([]),  # no ACTIVE reservations
                _scalar_result(2),  # 2 already COMPLETED
            ]
        )
        db.add = MagicMock()

        await self.svc.complete_order_reservations(db, order_id)

        # No inventory transaction should be logged
        db.add.assert_not_called()

    async def test_complete_no_reservations_at_all_warns_and_returns(self):
        order_id = uuid.uuid4()

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([]),  # no ACTIVE
                _scalar_result(0),  # no COMPLETED either
            ]
        )
        db.add = MagicMock()

        await self.svc.complete_order_reservations(db, order_id)

        db.add.assert_not_called()

    async def test_complete_skips_missing_product(self):
        order_id = uuid.uuid4()
        active_row = (uuid.uuid4(), uuid.uuid4(), None, 1)

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([active_row]),
                _fetchone_result(None),  # product missing
            ]
        )
        db.add = MagicMock()

        await self.svc.complete_order_reservations(db, order_id)

        db.add.assert_not_called()

    async def test_complete_multiple_reservations(self):
        order_id = uuid.uuid4()
        pid1, pid2 = uuid.uuid4(), uuid.uuid4()
        row1 = (uuid.uuid4(), pid1, None, 2)
        row2 = (uuid.uuid4(), pid2, None, 3)

        def _prod_row(stock=10, reserved=2, sold=0):
            row = MagicMock()
            row._mapping = {
                "stock_quantity": stock,
                "reserved_quantity": reserved,
                "sold_quantity": sold,
            }
            return row

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([row1, row2]),  # SELECT ACTIVE
                _fetchone_result(_prod_row()),  # product for row1
                _noop_result(),  # UPDATE products row1
                _noop_result(),  # UPDATE reservations row1
                _fetchone_result(_prod_row(reserved=3)),  # product for row2
                _noop_result(),  # UPDATE products row2
                _noop_result(),  # UPDATE reservations row2
            ]
        )
        db.add = MagicMock()

        await self.svc.complete_order_reservations(db, order_id)

        # Two transaction records added
        assert db.add.call_count == 2


# ── TestCompleteReservationsForOrder ──────────────────────────────────────────
#
# This orchestration (complete -> detect EXPIRED -> late-payment fallback) used
# to be duplicated inline in orders/service.py::verify_and_fulfill and
# webhooks/service.py::_process_payment_captured. It now lives in exactly one
# place, so these are the only tests for that sequencing.


class TestCompleteReservationsForOrder:
    def setup_method(self):
        from app.modules.inventory.reservation_service import ReservationService

        self.svc = ReservationService()

    async def test_no_expired_reservations_skips_late_payment_fallback(self):
        order_id = uuid.uuid4()

        db = AsyncMock()
        # Only the EXPIRED-detection query hits db.execute directly here;
        # the two sub-methods are patched out to isolate orchestration.
        db.execute = AsyncMock(return_value=_fetchone_result(None))

        self.svc.complete_order_reservations = AsyncMock()
        self.svc.complete_expired_order_reservations = AsyncMock()

        await self.svc.complete_reservations_for_order(db, order_id)

        self.svc.complete_order_reservations.assert_awaited_once_with(db, order_id)
        self.svc.complete_expired_order_reservations.assert_not_awaited()

    async def test_expired_reservations_trigger_late_payment_fallback(self):
        order_id = uuid.uuid4()

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_fetchone_result((1,)))

        self.svc.complete_order_reservations = AsyncMock()
        self.svc.complete_expired_order_reservations = AsyncMock()

        await self.svc.complete_reservations_for_order(db, order_id)

        self.svc.complete_order_reservations.assert_awaited_once_with(db, order_id)
        self.svc.complete_expired_order_reservations.assert_awaited_once_with(
            db, order_id
        )

    async def test_complete_runs_before_expired_check(self):
        """The EXPIRED check must run after complete_order_reservations, not
        before — otherwise a reservation completed by this same call could
        never be observed as EXPIRED, which is fine, but the reverse
        ordering bug (checking EXPIRED before completing) would still be a
        regression worth catching."""
        order_id = uuid.uuid4()
        call_order: list[str] = []

        async def _fake_complete(db, oid):
            call_order.append("complete")

        db = AsyncMock()

        async def _fake_execute(*args, **kwargs):
            call_order.append("expired_check")
            return _fetchone_result(None)

        db.execute = AsyncMock(side_effect=_fake_execute)
        self.svc.complete_order_reservations = AsyncMock(side_effect=_fake_complete)
        self.svc.complete_expired_order_reservations = AsyncMock()

        await self.svc.complete_reservations_for_order(db, order_id)

        assert call_order == ["complete", "expired_check"]


# ── TestReleaseOrderReservations ──────────────────────────────────────────────


class TestReleaseOrderReservations:
    def setup_method(self):
        from app.modules.inventory.reservation_service import ReservationService

        self.svc = ReservationService()

    async def test_release_single_reservation_success(self):
        order_id = uuid.uuid4()
        res_id = uuid.uuid4()
        product_id = uuid.uuid4()
        active_row = (res_id, product_id, None, 3)

        prod_row = MagicMock()
        prod_row._mapping = {
            "stock_quantity": 10,
            "reserved_quantity": 3,
            "sold_quantity": 0,
        }

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([active_row]),  # SELECT ACTIVE
                _fetchone_result(prod_row),  # SELECT product FOR UPDATE
                _noop_result(),  # UPDATE products reserved -= qty
                _noop_result(),  # UPDATE reservations status='RELEASED'
            ]
        )
        db.add = MagicMock()

        await self.svc.release_order_reservations(db, order_id, reason="RELEASED")

        db.add.assert_called_once()
        txn = db.add.call_args[0][0]
        assert txn.transaction_type == "RELEASE"
        assert txn.quantity == 3

    async def test_release_with_expired_reason(self):
        order_id = uuid.uuid4()
        active_row = (uuid.uuid4(), uuid.uuid4(), None, 1)

        prod_row = MagicMock()
        prod_row._mapping = {
            "stock_quantity": 5,
            "reserved_quantity": 1,
            "sold_quantity": 0,
        }

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([active_row]),
                _fetchone_result(prod_row),
                _noop_result(),
                _noop_result(),
            ]
        )
        db.add = MagicMock()

        await self.svc.release_order_reservations(db, order_id, reason="EXPIRED")

        txn = db.add.call_args[0][0]
        assert txn.transaction_type == "RELEASE"

    async def test_release_no_active_reservations_is_noop(self):
        order_id = uuid.uuid4()

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_fetchall_result([]))
        db.add = MagicMock()

        await self.svc.release_order_reservations(db, order_id)

        # Only one execute: the SELECT ACTIVE
        assert db.execute.call_count == 1
        db.add.assert_not_called()

    async def test_release_skips_missing_product(self):
        order_id = uuid.uuid4()
        active_row = (uuid.uuid4(), uuid.uuid4(), None, 2)

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([active_row]),
                _fetchone_result(None),  # product gone
            ]
        )
        db.add = MagicMock()

        await self.svc.release_order_reservations(db, order_id)

        db.add.assert_not_called()


# ── TestExpireStaleReservations ───────────────────────────────────────────────


class TestExpireStaleReservations:
    def setup_method(self):
        from app.modules.inventory.reservation_service import ReservationService

        self.svc = ReservationService()

    async def test_no_candidates_returns_empty(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_fetchall_result([]))

        result = await self.svc.expire_stale_reservations(db)

        assert result == []
        assert db.execute.call_count == 1

    async def test_expire_single_reservation_without_order(self):
        res_id = uuid.uuid4()
        product_id = uuid.uuid4()
        candidate_row = (res_id, product_id, None, None, 2)  # no order_id

        locked_row = MagicMock()
        locked_row.__getitem__ = lambda self, i: "ACTIVE" if i == 0 else None

        prod_row = MagicMock()
        prod_row._mapping = {
            "stock_quantity": 5,
            "reserved_quantity": 2,
            "sold_quantity": 0,
        }

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([candidate_row]),  # candidates
                _fetchone_result(locked_row),  # SKIP LOCKED re-lock
                _fetchone_result(prod_row),  # product lock
                _noop_result(),  # UPDATE products
                _noop_result(),  # UPDATE reservations EXPIRED
                # no UPDATE orders (no order_id)
            ]
        )
        db.add = MagicMock()

        result = await self.svc.expire_stale_reservations(db)

        assert len(result) == 0  # no order_id, so no order IDs returned
        db.add.assert_called_once()  # RELEASE transaction logged

    async def test_expire_single_reservation_with_order_transitions_order(self):
        res_id = uuid.uuid4()
        product_id = uuid.uuid4()
        order_id = uuid.uuid4()
        candidate_row = (res_id, product_id, None, order_id, 1)

        locked_row = MagicMock()
        locked_row.__getitem__ = lambda self, i: "ACTIVE" if i == 0 else None

        prod_row = MagicMock()
        prod_row._mapping = {
            "stock_quantity": 5,
            "reserved_quantity": 1,
            "sold_quantity": 0,
        }

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([candidate_row]),
                _fetchone_result(locked_row),  # SKIP LOCKED
                _fetchone_result(prod_row),  # product
                _noop_result(),  # UPDATE products
                _noop_result(),  # UPDATE reservations
                _noop_result(),  # UPDATE orders (rowcount=1 → transitioned)
            ]
        )
        db.add = MagicMock()

        result = await self.svc.expire_stale_reservations(db)

        assert len(result) == 1
        assert result[0] == order_id
        assert db.execute.call_count == 6

    async def test_expire_order_already_terminal_not_returned(self):
        """Order already in a terminal state → rowcount=0 → not in result."""
        res_id = uuid.uuid4()
        product_id = uuid.uuid4()
        order_id = uuid.uuid4()
        candidate_row = (res_id, product_id, None, order_id, 1)

        locked_row = MagicMock()
        locked_row.__getitem__ = lambda self, i: "ACTIVE" if i == 0 else None

        prod_row = MagicMock()
        prod_row._mapping = {
            "stock_quantity": 5,
            "reserved_quantity": 1,
            "sold_quantity": 0,
        }

        order_update = MagicMock()
        order_update.rowcount = 0  # order was already terminal

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([candidate_row]),
                _fetchone_result(locked_row),  # SKIP LOCKED
                _fetchone_result(prod_row),  # product
                _noop_result(),  # UPDATE products
                _noop_result(),  # UPDATE reservations
                order_update,  # UPDATE orders (rowcount=0 → not transitioned)
            ]
        )
        db.add = MagicMock()

        result = await self.svc.expire_stale_reservations(db)

        assert result == []  # reservation expired but order not transitioned

    async def test_skip_locked_already_processed_skips_row(self):
        """If SKIP LOCKED returns None (row locked by another worker), skip."""
        res_id = uuid.uuid4()
        product_id = uuid.uuid4()
        candidate_row = (res_id, product_id, None, None, 1)

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([candidate_row]),
                _fetchone_result(None),  # SKIP LOCKED — row locked elsewhere
            ]
        )
        db.add = MagicMock()

        result = await self.svc.expire_stale_reservations(db)

        assert result == []
        db.add.assert_not_called()

    async def test_skip_locked_row_not_active_skips(self):
        """If SKIP LOCKED returns a row with status != ACTIVE, skip."""
        res_id = uuid.uuid4()
        product_id = uuid.uuid4()
        candidate_row = (res_id, product_id, None, None, 1)

        locked_row = MagicMock()
        locked_row.__getitem__ = lambda self, i: "COMPLETED" if i == 0 else None

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([candidate_row]),
                _fetchone_result(locked_row),  # status='COMPLETED'
            ]
        )
        db.add = MagicMock()

        result = await self.svc.expire_stale_reservations(db)

        assert result == []
        db.add.assert_not_called()

    async def test_expire_multiple_candidates(self):
        r1_id, r2_id = uuid.uuid4(), uuid.uuid4()
        p1_id, p2_id = uuid.uuid4(), uuid.uuid4()
        rows = [
            (r1_id, p1_id, None, None, 2),
            (r2_id, p2_id, None, None, 1),
        ]

        def _locked():
            row = MagicMock()
            row.__getitem__ = lambda self, i: "ACTIVE"
            return row

        def _prod():
            row = MagicMock()
            row._mapping = {
                "stock_quantity": 10,
                "reserved_quantity": 3,
                "sold_quantity": 0,
            }
            return row

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result(rows),  # candidates
                _fetchone_result(_locked()),  # row1 skip-locked
                _fetchone_result(_prod()),  # row1 product
                _noop_result(),  # row1 UPDATE products
                _noop_result(),  # row1 UPDATE reservations
                _fetchone_result(_locked()),  # row2 skip-locked
                _fetchone_result(_prod()),  # row2 product
                _noop_result(),  # row2 UPDATE products
                _noop_result(),  # row2 UPDATE reservations
            ]
        )
        db.add = MagicMock()

        result = await self.svc.expire_stale_reservations(db)

        assert len(result) == 0  # no order_ids in candidates
        assert db.add.call_count == 2  # one RELEASE txn per expired reservation

    async def test_expire_skips_missing_product(self):
        res_id = uuid.uuid4()
        product_id = uuid.uuid4()
        candidate_row = (res_id, product_id, None, None, 1)

        locked_row = MagicMock()
        locked_row.__getitem__ = lambda self, i: "ACTIVE"

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([candidate_row]),
                _fetchone_result(locked_row),
                _fetchone_result(None),  # product not found
            ]
        )
        db.add = MagicMock()

        result = await self.svc.expire_stale_reservations(db)

        assert result == []


# ── TestGetAvailableStock ─────────────────────────────────────────────────────


class TestGetAvailableStock:
    def setup_method(self):
        from app.modules.inventory.reservation_service import ReservationService

        self.svc = ReservationService()

    async def test_returns_computed_available(self):
        product_id = uuid.uuid4()
        # stock=10, reserved=2, sold=3 → available=5
        row = MagicMock()
        row.__getitem__ = lambda self, i: 5  # available column

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_fetchone_result(row))

        result = await self.svc.get_available_stock(db, product_id)

        assert result == 5

    async def test_clamps_negative_to_zero(self):
        row = MagicMock()
        row.__getitem__ = lambda self, i: -1  # DB formula went negative

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_fetchone_result(row))

        result = await self.svc.get_available_stock(db, uuid.uuid4())

        assert result == 0

    async def test_product_not_found_raises_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_fetchone_result(None))

        with pytest.raises(NotFoundError):
            await self.svc.get_available_stock(db, uuid.uuid4())


# ── TestRecordRestock ─────────────────────────────────────────────────────────


class TestRecordRestock:
    def setup_method(self):
        from app.modules.inventory.reservation_service import ReservationService

        self.svc = ReservationService()

    async def test_restock_success(self):
        product_id = uuid.uuid4()
        prod_row = MagicMock()
        prod_row._mapping = {
            "stock_quantity": 10,
            "reserved_quantity": 0,
            "sold_quantity": 0,
        }

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchone_result(prod_row),  # SELECT FOR UPDATE
                _noop_result(),  # UPDATE stock_quantity
            ]
        )
        db.add = MagicMock()

        await self.svc.record_restock(
            db, product_id=product_id, variant_id=None, quantity=20, reference="PO-001"
        )

        db.add.assert_called_once()
        txn = db.add.call_args[0][0]
        assert txn.transaction_type == "RESTOCK"
        assert txn.quantity == 20
        assert txn.reference == "PO-001"

    async def test_restock_zero_quantity_raises_validation_error(self):
        from app.core.exceptions import ValidationError

        db = AsyncMock()
        with pytest.raises(ValidationError, match="positive"):
            await self.svc.record_restock(
                db, product_id=uuid.uuid4(), variant_id=None, quantity=0
            )
        db.execute.assert_not_called()

    async def test_restock_negative_quantity_raises_validation_error(self):
        from app.core.exceptions import ValidationError

        db = AsyncMock()
        with pytest.raises(ValidationError, match="positive"):
            await self.svc.record_restock(
                db, product_id=uuid.uuid4(), variant_id=None, quantity=-5
            )

    async def test_restock_product_not_found_raises_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_fetchone_result(None))

        with pytest.raises(NotFoundError):
            await self.svc.record_restock(
                db, product_id=uuid.uuid4(), variant_id=None, quantity=10
            )


# ── TestRecordReturn ──────────────────────────────────────────────────────────


class TestRecordReturn:
    def setup_method(self):
        from app.modules.inventory.reservation_service import ReservationService

        self.svc = ReservationService()

    async def test_return_success(self):
        product_id = uuid.uuid4()
        order_id = uuid.uuid4()
        prod_row = MagicMock()
        prod_row._mapping = {
            "stock_quantity": 10,
            "reserved_quantity": 0,
            "sold_quantity": 5,
        }

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchone_result(prod_row),  # SELECT FOR UPDATE
                _noop_result(),  # UPDATE sold_quantity
            ]
        )
        db.add = MagicMock()

        await self.svc.record_return(
            db,
            product_id=product_id,
            variant_id=None,
            quantity=2,
            order_id=order_id,
            reference="RTN-001",
        )

        db.add.assert_called_once()
        txn = db.add.call_args[0][0]
        assert txn.transaction_type == "RETURN"
        assert txn.quantity == 2
        assert txn.after_sold == 3  # 5 - 2 = 3

    async def test_return_clamps_sold_to_zero(self):
        """Returning more than sold_quantity is clamped to 0, not negative."""
        product_id = uuid.uuid4()
        prod_row = MagicMock()
        prod_row._mapping = {
            "stock_quantity": 10,
            "reserved_quantity": 0,
            "sold_quantity": 1,
        }

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[_fetchone_result(prod_row), _noop_result()])
        db.add = MagicMock()

        await self.svc.record_return(
            db, product_id=product_id, variant_id=None, quantity=5
        )

        txn = db.add.call_args[0][0]
        assert txn.after_sold == 0  # max(1 - 5, 0) = 0

    async def test_return_zero_quantity_raises_validation_error(self):
        from app.core.exceptions import ValidationError

        db = AsyncMock()
        with pytest.raises(ValidationError, match="positive"):
            await self.svc.record_return(
                db, product_id=uuid.uuid4(), variant_id=None, quantity=0
            )
        db.execute.assert_not_called()

    async def test_return_product_not_found_raises_not_found(self):
        from app.core.exceptions import NotFoundError

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_fetchone_result(None))

        with pytest.raises(NotFoundError):
            await self.svc.record_return(
                db, product_id=uuid.uuid4(), variant_id=None, quantity=1
            )


# ── TestLogTransaction ────────────────────────────────────────────────────────


class TestLogTransaction:
    def setup_method(self):
        from app.modules.inventory.reservation_service import ReservationService

        self.svc = ReservationService()

    async def test_log_computes_correct_before_after_available(self):
        db = AsyncMock()
        db.add = MagicMock()

        product_id = uuid.uuid4()
        before_stock = {
            "stock_quantity": 10,
            "reserved_quantity": 2,
            "sold_quantity": 1,
        }
        # before_available = 10 - 2 - 1 = 7
        # after_reserved=5, after_sold=1 → after_available = 10 - 5 - 1 = 4

        await self.svc._log_transaction(
            db,
            product_id=product_id,
            variant_id=None,
            reservation_id=None,
            order_id=None,
            transaction_type="RESERVE",
            quantity=3,
            before_stock=before_stock,
            after_reserved=5,
            after_sold=1,
            reference="RES-ABCD1234",
        )

        db.add.assert_called_once()
        from app.modules.inventory.models import InventoryTransaction

        txn = db.add.call_args[0][0]
        assert isinstance(txn, InventoryTransaction)
        assert txn.before_available == 7
        assert txn.after_available == 4
        assert txn.before_reserved == 2
        assert txn.after_reserved == 5
        assert txn.before_sold == 1
        assert txn.after_sold == 1
        assert txn.quantity == 3
        assert txn.reference == "RES-ABCD1234"


# ── TestVariantLevelInventory ─────────────────────────────────────────────────


class TestVariantLevelInventory:
    """Variant purchases must update product_variants, not products."""

    def setup_method(self):
        from app.modules.inventory.reservation_service import ReservationService

        self.svc = ReservationService()

    # 1. Variant reserve hits product_variants table
    async def test_reserve_variant_uses_product_variants_table(self):
        product_id = uuid.uuid4()
        variant_id = uuid.uuid4()
        mapping = _variant_mapping(
            variant_id=variant_id, product_id=product_id, stock=5, reserved=0, sold=0
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([]),  # get_user_active_reservations
                _lock_result(mapping),  # lock variant
                _noop_result(),  # update variant
            ]
        )
        db.add = MagicMock()
        db.flush = AsyncMock()

        items = [{"product_id": product_id, "variant_id": variant_id, "quantity": 2}]
        reservations = await self.svc.reserve_items(
            db, user_id=uuid.uuid4(), items=items
        )

        assert len(reservations) == 1
        assert reservations[0].variant_id == variant_id
        assert reservations[0].product_id == product_id

        # The UPDATE must target product_variants, not products
        # Index 2: [0]=get_user_active_reservations, [1]=lock, [2]=update
        update_call = db.execute.call_args_list[2]
        sql = str(update_call[0][0])
        assert "product_variants" in sql
        assert "products" not in sql

    # 2. Parent product row is untouched when variant is bought
    async def test_reserve_variant_does_not_touch_product_row(self):
        product_id = uuid.uuid4()
        variant_id = uuid.uuid4()
        mapping = _variant_mapping(
            variant_id=variant_id, product_id=product_id, stock=5
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([]),  # get_user_active_reservations
                _lock_result(mapping),  # lock variant
                _noop_result(),  # update variant
            ]
        )
        db.add = MagicMock()
        db.flush = AsyncMock()

        items = [{"product_id": product_id, "variant_id": variant_id, "quantity": 1}]
        await self.svc.reserve_items(db, user_id=uuid.uuid4(), items=items)

        all_sqls = [str(c[0][0]) for c in db.execute.call_args_list]
        update_sqls = [s for s in all_sqls if "UPDATE" in s.upper()]
        # The only UPDATE is against product_variants
        for sql in update_sqls:
            assert "product_variants" in sql
            assert "UPDATE products" not in sql

    # 3. Non-variant products still update the products table
    async def test_reserve_no_variant_updates_products_table(self):
        product_id = uuid.uuid4()
        mapping = _prod_mapping(product_id=product_id, stock=10)

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([]),  # get_user_active_reservations
                _lock_result(mapping),  # lock product
                _noop_result(),  # update product
            ]
        )
        db.add = MagicMock()
        db.flush = AsyncMock()

        items = [{"product_id": product_id, "variant_id": None, "quantity": 2}]
        await self.svc.reserve_items(db, user_id=uuid.uuid4(), items=items)

        update_call = db.execute.call_args_list[2]
        sql = str(update_call[0][0])
        assert "UPDATE products" in sql

    # 4. Completing a variant reservation moves stock in product_variants
    async def test_complete_variant_reservation_updates_product_variants(self):
        order_id = uuid.uuid4()
        product_id = uuid.uuid4()
        variant_id = uuid.uuid4()
        active_row = (uuid.uuid4(), product_id, variant_id, 3)

        var_row = MagicMock()
        var_row._mapping = _variant_mapping(
            variant_id=variant_id, product_id=product_id, stock=10, reserved=3, sold=0
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([active_row]),  # SELECT ACTIVE
                _fetchone_result(var_row),  # SELECT variant FOR UPDATE
                _noop_result(),  # UPDATE product_variants reserved→sold
                _noop_result(),  # UPDATE reservations COMPLETED
            ]
        )
        db.add = MagicMock()

        await self.svc.complete_order_reservations(db, order_id)

        db.add.assert_called_once()
        txn = db.add.call_args[0][0]
        assert txn.transaction_type == "SALE"
        assert txn.variant_id == variant_id

        update_sql = str(db.execute.call_args_list[2][0][0])
        assert "product_variants" in update_sql

    # 5. Releasing a variant reservation updates product_variants
    async def test_release_variant_reservation_updates_product_variants(self):
        order_id = uuid.uuid4()
        product_id = uuid.uuid4()
        variant_id = uuid.uuid4()
        active_row = (uuid.uuid4(), product_id, variant_id, 2)

        var_row = MagicMock()
        var_row._mapping = _variant_mapping(
            variant_id=variant_id, product_id=product_id, stock=5, reserved=2, sold=0
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([active_row]),
                _fetchone_result(var_row),
                _noop_result(),  # UPDATE product_variants reserved -= 2
                _noop_result(),  # UPDATE reservations RELEASED
            ]
        )
        db.add = MagicMock()

        await self.svc.release_order_reservations(db, order_id)

        update_sql = str(db.execute.call_args_list[2][0][0])
        assert "product_variants" in update_sql

        txn = db.add.call_args[0][0]
        assert txn.transaction_type == "RELEASE"
        assert txn.variant_id == variant_id

    # 6. Expiry of a variant reservation updates product_variants
    async def test_expire_variant_reservation_updates_product_variants(self):
        res_id = uuid.uuid4()
        product_id = uuid.uuid4()
        variant_id = uuid.uuid4()
        candidate_row = (res_id, product_id, variant_id, None, 1)

        locked_row = MagicMock()
        locked_row.__getitem__ = lambda self, i: "ACTIVE" if i == 0 else None

        var_row = MagicMock()
        var_row._mapping = _variant_mapping(
            variant_id=variant_id, product_id=product_id, stock=5, reserved=1, sold=0
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([candidate_row]),
                _fetchone_result(locked_row),  # SKIP LOCKED
                _fetchone_result(var_row),  # variant lock
                _noop_result(),  # UPDATE product_variants
                _noop_result(),  # UPDATE reservations EXPIRED
            ]
        )
        db.add = MagicMock()

        result = await self.svc.expire_stale_reservations(db)

        assert len(result) == 0  # no order_id → no order IDs returned
        update_sql = str(db.execute.call_args_list[3][0][0])
        assert "product_variants" in update_sql

    # 7. Variant restock updates product_variants
    async def test_restock_variant_updates_product_variants(self):
        product_id = uuid.uuid4()
        variant_id = uuid.uuid4()

        var_row = MagicMock()
        var_row._mapping = _variant_mapping(
            variant_id=variant_id, product_id=product_id, stock=5
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchone_result(var_row),
                _noop_result(),
            ]
        )
        db.add = MagicMock()

        await self.svc.record_restock(
            db, product_id=product_id, variant_id=variant_id, quantity=10
        )

        update_sql = str(db.execute.call_args_list[1][0][0])
        assert "product_variants" in update_sql
        txn = db.add.call_args[0][0]
        assert txn.transaction_type == "RESTOCK"
        assert txn.variant_id == variant_id

    # 8. Variant return updates product_variants
    async def test_return_variant_updates_product_variants(self):
        product_id = uuid.uuid4()
        variant_id = uuid.uuid4()

        var_row = MagicMock()
        var_row._mapping = _variant_mapping(
            variant_id=variant_id, product_id=product_id, stock=10, reserved=0, sold=3
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchone_result(var_row),
                _noop_result(),
            ]
        )
        db.add = MagicMock()

        await self.svc.record_return(
            db, product_id=product_id, variant_id=variant_id, quantity=2
        )

        update_sql = str(db.execute.call_args_list[1][0][0])
        assert "product_variants" in update_sql
        txn = db.add.call_args[0][0]
        assert txn.transaction_type == "RETURN"
        assert txn.variant_id == variant_id
        assert txn.after_sold == 1  # max(3 - 2, 0) = 1

    # 9. Variant with zero stock raises InventoryError
    async def test_reserve_variant_out_of_stock_raises_inventory_error(self):
        from app.core.exceptions import InventoryError

        product_id = uuid.uuid4()
        variant_id = uuid.uuid4()
        mapping = _variant_mapping(
            variant_id=variant_id,
            product_id=product_id,
            stock=3,
            reserved=2,
            sold=1,
            allow_backorder=False,
        )  # available = 3 - 2 - 1 = 0

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchall_result([]),  # get_user_active_reservations
                _lock_result(mapping),  # lock variant
            ]
        )

        items = [{"product_id": product_id, "variant_id": variant_id, "quantity": 1}]
        with pytest.raises(InventoryError, match="0 item"):
            await self.svc.reserve_items(db, user_id=uuid.uuid4(), items=items)

        # get_user_active_reservations + the lock SELECT
        assert db.execute.call_count == 2

    # 10. Variant adjustment updates product_variants
    async def test_adjustment_variant_updates_product_variants(self):
        product_id = uuid.uuid4()
        variant_id = uuid.uuid4()

        var_row = MagicMock()
        var_row._mapping = _variant_mapping(
            variant_id=variant_id, product_id=product_id, stock=10, reserved=0, sold=0
        )

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _fetchone_result(var_row),
                _noop_result(),
            ]
        )
        db.add = MagicMock()

        new_stock = await self.svc.record_adjustment(
            db, product_id=product_id, variant_id=variant_id, delta=5
        )

        assert new_stock == 15
        update_sql = str(db.execute.call_args_list[1][0][0])
        assert "product_variants" in update_sql
        txn = db.add.call_args[0][0]
        assert txn.transaction_type == "ADJUSTMENT"
        assert txn.variant_id == variant_id

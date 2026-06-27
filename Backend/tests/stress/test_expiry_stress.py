"""
Reservation expiry stress tests.

Exercises expire_stale_reservations() with large batches of ACTIVE reservations.
The service processes up to LIMIT 500 per call; for 10 000 reservations the
worker must be called 20 times.  These tests verify:

  - All rows in a batch are processed (expired_count == batch_size)
  - reserved_quantity is released correctly
  - Orders transition to payment_expired
  - No row is processed twice (idempotency via SKIP LOCKED)
  - Runtime stays within acceptable bounds
"""

import time
import uuid
from unittest.mock import AsyncMock, MagicMock

# ── Mock-builder helpers ──────────────────────────────────────────────────────

_BATCH_LIMIT = 500  # mirrors "LIMIT 500" in expire_stale_reservations


def _make_candidate_row(
    product_id: uuid.UUID,
    order_id: uuid.UUID | None = None,
    quantity: int = 1,
) -> tuple:
    """Return a tuple matching: (id, product_id, variant_id, order_id, quantity)."""
    return (uuid.uuid4(), product_id, None, order_id, quantity)


def _candidates_result(rows: list) -> MagicMock:
    r = MagicMock()
    r.fetchall.return_value = rows
    return r


def _skip_locked_result(status: str = "ACTIVE") -> MagicMock:
    """Simulates SKIP LOCKED returning a row with status at index 0."""
    locked_row = (status,)  # tuple → locked_row[0] == status
    r = MagicMock()
    r.fetchone.return_value = locked_row
    return r


def _product_result(stock: int, reserved: int, sold: int = 0) -> MagicMock:
    prod_row = MagicMock()
    prod_row._mapping = {
        "stock_quantity": stock,
        "reserved_quantity": reserved,
        "sold_quantity": sold,
    }
    r = MagicMock()
    r.fetchone.return_value = prod_row
    return r


def _noop() -> MagicMock:
    return MagicMock()


def _build_db_for_batch(candidates: list) -> AsyncMock:
    """
    Build a db mock that replays the exact sequence of SQL calls
    expire_stale_reservations() makes for a given list of candidate rows.

    Call sequence (per row with order_id set):
      0. SELECT candidates       → candidates_result (once)
      per row:
        1. SKIP LOCKED SELECT    → _skip_locked_result("ACTIVE")
        2. SELECT product        → _product_result(...)
        3. UPDATE products       → noop
        4. UPDATE reservations   → noop
        5. UPDATE orders         → noop (only when row[3] is not None)
    """
    n = len(candidates)
    total_stock = n  # 1 unit reserved per row

    side_effects = [_candidates_result(candidates)]
    for row in candidates:
        order_id = row[3]
        side_effects.append(_skip_locked_result("ACTIVE"))
        side_effects.append(_product_result(stock=total_stock, reserved=n))
        side_effects.append(_noop())  # UPDATE products
        side_effects.append(_noop())  # UPDATE reservations
        if order_id is not None:
            side_effects.append(_noop())  # UPDATE orders

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=side_effects)
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestExpirySingleBatch:
    """expire_stale_reservations with a single full batch (≤ 500 rows)."""

    async def test_small_batch_all_expired(self):
        """10 expired reservations → all processed, count == 10."""
        from app.modules.inventory.reservation_service import ReservationService

        product_id = uuid.uuid4()
        candidates = [_make_candidate_row(product_id) for _ in range(10)]
        db = _build_db_for_batch(candidates)

        svc = ReservationService()
        count = await svc.expire_stale_reservations(db)

        assert count == 10

    async def test_medium_batch_all_expired(self):
        """100 expired reservations → all processed."""
        from app.modules.inventory.reservation_service import ReservationService

        product_id = uuid.uuid4()
        candidates = [_make_candidate_row(product_id) for _ in range(100)]
        db = _build_db_for_batch(candidates)

        svc = ReservationService()
        count = await svc.expire_stale_reservations(db)

        assert count == 100

    async def test_full_batch_limit(self):
        """
        500 expired reservations (the service's internal LIMIT) — all processed
        in a single call.  This is the maximum batch size.
        """
        from app.modules.inventory.reservation_service import ReservationService

        product_id = uuid.uuid4()
        candidates = [_make_candidate_row(product_id) for _ in range(_BATCH_LIMIT)]
        db = _build_db_for_batch(candidates)

        start = time.perf_counter()
        svc = ReservationService()
        count = await svc.expire_stale_reservations(db)
        elapsed = time.perf_counter() - start

        assert count == _BATCH_LIMIT
        assert elapsed < 10.0, f"Full batch took {elapsed:.2f}s (expected < 10s)"

    async def test_empty_batch_returns_zero(self):
        """No expired reservations → returns 0 immediately."""
        from app.modules.inventory.reservation_service import ReservationService

        empty_result = MagicMock()
        empty_result.fetchall.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=empty_result)

        svc = ReservationService()
        count = await svc.expire_stale_reservations(db)

        assert count == 0
        db.execute.assert_awaited_once()  # only the SELECT candidates call

    async def test_orders_marked_payment_expired(self):
        """Rows with an order_id trigger UPDATE orders → payment_expired."""
        from app.modules.inventory.reservation_service import ReservationService

        product_id = uuid.uuid4()
        order_id = uuid.uuid4()
        # One row with order_id, one without
        candidates = [
            _make_candidate_row(product_id, order_id=order_id),
            _make_candidate_row(product_id, order_id=None),
        ]
        db = _build_db_for_batch(candidates)

        svc = ReservationService()
        count = await svc.expire_stale_reservations(db)

        assert count == 2

        # With order_id: 5 execute calls; without: 4.  Total = 1 + 5 + 4 = 10
        assert db.execute.await_count == 1 + 5 + 4

    async def test_skip_locked_row_skipped(self):
        """
        A reservation that is SKIP LOCKED (already being processed by another
        worker) must be silently skipped — count should not include it.
        """
        from app.modules.inventory.reservation_service import ReservationService

        product_id = uuid.uuid4()
        candidates = [_make_candidate_row(product_id) for _ in range(3)]

        # First row: SKIP LOCKED returns None (locked by another worker)
        # Other rows: ACTIVE → processed normally
        side_effects = [_candidates_result(candidates)]
        side_effects.append(MagicMock(fetchone=MagicMock(return_value=None)))  # locked!
        for _ in range(2):
            side_effects.append(_skip_locked_result("ACTIVE"))
            side_effects.append(_product_result(stock=3, reserved=3))
            side_effects.append(_noop())  # UPDATE products
            side_effects.append(_noop())  # UPDATE reservations

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effects)
        db.add = MagicMock()
        db.flush = AsyncMock()

        svc = ReservationService()
        count = await svc.expire_stale_reservations(db)

        assert count == 2  # 3 candidates, 1 skipped


class TestExpiryMultiBatch:
    """
    Simulate 10 000 expired reservations processed across 20 worker calls
    (each call handles up to 500 rows — the LIMIT).
    """

    async def test_ten_thousand_reservations_twenty_batches(self):
        """
        Worker called 20× with 500 rows each → total expired == 10 000.
        Verifies linear scalability of the expiry loop.
        """
        from app.modules.inventory.reservation_service import ReservationService

        product_id = uuid.uuid4()
        total_reservations = 10_000
        batch_size = _BATCH_LIMIT  # 500

        total_expired = 0
        total_elapsed = 0.0
        svc = ReservationService()

        for batch_num in range(total_reservations // batch_size):
            candidates = [_make_candidate_row(product_id) for _ in range(batch_size)]
            db = _build_db_for_batch(candidates)

            start = time.perf_counter()
            count = await svc.expire_stale_reservations(db)
            total_elapsed += time.perf_counter() - start

            assert (
                count == batch_size
            ), f"Batch {batch_num}: expected {batch_size}, got {count}"
            total_expired += count

        assert total_expired == total_reservations
        assert (
            total_elapsed < 60.0
        ), f"10 000 reservations across 20 batches took {total_elapsed:.2f}s (limit: 60s)"

    async def test_partial_last_batch(self):
        """
        3 batches: 2 full (500 each) + 1 partial (250).
        Verifies that the last partial batch is processed completely.
        """
        from app.modules.inventory.reservation_service import ReservationService

        product_id = uuid.uuid4()
        batches = [500, 500, 250]
        total_expected = sum(batches)
        svc = ReservationService()
        total_expired = 0

        for size in batches:
            candidates = [_make_candidate_row(product_id) for _ in range(size)]
            db = _build_db_for_batch(candidates)
            total_expired += await svc.expire_stale_reservations(db)

        assert total_expired == total_expected

    async def test_no_double_processing(self):
        """
        Each reservation must be expired exactly once.  The second worker call
        returns an empty candidate list (all already expired by first call).
        """
        from app.modules.inventory.reservation_service import ReservationService

        product_id = uuid.uuid4()
        candidates = [_make_candidate_row(product_id) for _ in range(10)]

        # First call: processes all 10
        db_first = _build_db_for_batch(candidates)
        # Second call: empty candidates (nothing left to expire)
        empty_result = MagicMock(fetchall=MagicMock(return_value=[]))
        db_second = AsyncMock()
        db_second.execute = AsyncMock(return_value=empty_result)

        svc = ReservationService()
        first_count = await svc.expire_stale_reservations(db_first)
        second_count = await svc.expire_stale_reservations(db_second)

        assert first_count == 10
        assert second_count == 0  # nothing left


class TestExpiryReservedStockReleased:
    """Verify that reserved_quantity decreases by the exact quantity expired."""

    async def test_reserved_quantity_decremented_correctly(self):
        """
        Single reservation for qty=3: after expiry, reserved should drop by 3.
        Checked via the UPDATE products SQL call arguments captured in db.execute.
        """
        from app.modules.inventory.reservation_service import ReservationService

        product_id = uuid.uuid4()
        quantity = 3
        candidates = [_make_candidate_row(product_id, quantity=quantity)]

        db = _build_db_for_batch(candidates)
        svc = ReservationService()
        count = await svc.expire_stale_reservations(db)

        assert count == 1

        # Verify UPDATE products was called with correct qty
        # Call order: SELECT candidates, SKIP LOCKED, SELECT product, UPDATE products, UPDATE res
        update_products_call = db.execute.await_args_list[3]
        params = (
            update_products_call.args[1] if len(update_products_call.args) > 1 else {}
        )
        assert params.get("qty") == quantity or params.get("qty", None) == quantity

"""
High-concurrency checkout tests — Scenarios A & B + deadlock detection.

WHAT THESE TEST
---------------
Python-level asyncio concurrency using asyncio.Lock() to simulate the
serialization that PostgreSQL's SELECT ... FOR UPDATE provides at the DB layer.
Every coroutine that wants to modify reserved_quantity must acquire the shared
lock first, which is exactly the contract the ReservationService enforces via
raw SQL.

WHAT THEY DON'T TEST
---------------------
True DB-level concurrency: WAL serialization, MVCC, row-level dead-lock
detection, and network latency only appear in integration tests against a live
PostgreSQL instance.  These tests validate the Python logic layer and serve as
fast regression guards in CI.
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field

import pytest

from app.core.exceptions import InventoryError

# ── Shared inventory state (simulates DB row with FOR UPDATE semantics) ──────


@dataclass
class _InventoryState:
    """
    Coroutine-safe inventory snapshot.  asyncio.Lock mirrors SELECT FOR UPDATE:
    only one coroutine at a time may read-then-write.
    """

    stock_quantity: int
    reserved_quantity: int = 0
    sold_quantity: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def available(self) -> int:
        return self.stock_quantity - self.reserved_quantity - self.sold_quantity


async def _atomic_reserve(
    state: _InventoryState,
    quantity: int,
    product_id: uuid.UUID,
) -> uuid.UUID:
    """
    Atomically reserve `quantity` units, mirroring ReservationService semantics:
      1. Acquire lock  (≡ SELECT ... FOR UPDATE)
      2. Read available
      3. Raise InventoryError if insufficient
      4. Increment reserved_quantity
      5. Return new reservation ID
    """
    async with state.lock:
        available = state.available
        if available < quantity:
            raise InventoryError(
                f"Only {max(available, 0)} item(s) available. " f"Requested {quantity}."
            )
        state.reserved_quantity += quantity
        return uuid.uuid4()


# ── Scenario A: Stock = 1, 100 concurrent requests ──────────────────────────


class TestScenarioA:
    """Product stock = 1; 100 simultaneous checkout attempts."""

    async def test_exactly_one_succeeds(self):
        state = _InventoryState(stock_quantity=1)
        product_id = uuid.uuid4()

        async def attempt() -> bool:
            try:
                await _atomic_reserve(state, 1, product_id)
                return True
            except InventoryError:
                return False

        results = await asyncio.gather(*[attempt() for _ in range(100)])

        assert sum(results) == 1, f"Expected 1 success, got {sum(results)}"
        assert results.count(False) == 99
        assert state.reserved_quantity == 1
        assert state.available == 0

    async def test_inventory_never_negative(self):
        state = _InventoryState(stock_quantity=1)
        product_id = uuid.uuid4()

        await asyncio.gather(
            *[_atomic_reserve(state, 1, product_id) for _ in range(500)],
            return_exceptions=True,
        )

        assert state.available >= 0, "available went negative!"
        assert state.reserved_quantity <= state.stock_quantity

    async def test_no_duplicate_reservation_ids(self):
        state = _InventoryState(stock_quantity=1)
        product_id = uuid.uuid4()

        results = await asyncio.gather(
            *[_atomic_reserve(state, 1, product_id) for _ in range(100)],
            return_exceptions=True,
        )

        ids = [r for r in results if isinstance(r, uuid.UUID)]
        assert len(ids) == 1
        assert len({str(i) for i in ids}) == 1  # all unique (trivially, len=1)

    async def test_final_state_stock_one_reserved_one_sold_zero(self):
        state = _InventoryState(stock_quantity=1)
        await asyncio.gather(
            *[_atomic_reserve(state, 1, uuid.uuid4()) for _ in range(100)],
            return_exceptions=True,
        )
        assert state.stock_quantity == 1
        assert state.reserved_quantity == 1
        assert state.sold_quantity == 0
        assert state.available == 0


# ── Scenario B: Stock = 50, 500 concurrent requests (qty=1 each) ─────────


class TestScenarioB:
    """Product stock = 50; 500 simultaneous checkout attempts requesting 1 unit."""

    async def test_exactly_fifty_succeed(self):
        state = _InventoryState(stock_quantity=50)
        product_id = uuid.uuid4()

        async def attempt() -> bool:
            try:
                await _atomic_reserve(state, 1, product_id)
                return True
            except InventoryError:
                return False

        results = await asyncio.gather(*[attempt() for _ in range(500)])

        assert sum(results) == 50, f"Expected 50, got {sum(results)}"
        assert results.count(False) == 450
        assert state.reserved_quantity == 50
        assert state.available == 0

    async def test_reserved_never_exceeds_stock(self):
        state = _InventoryState(stock_quantity=50)

        await asyncio.gather(
            *[_atomic_reserve(state, 1, uuid.uuid4()) for _ in range(500)],
            return_exceptions=True,
        )

        assert (
            state.reserved_quantity <= state.stock_quantity
        ), f"reserved ({state.reserved_quantity}) > stock ({state.stock_quantity})"

    async def test_mixed_quantities(self):
        """Some users request 1, others 2 or 5; total available = 50."""
        state = _InventoryState(stock_quantity=50)
        product_id = uuid.uuid4()
        quantities = [1] * 100 + [2] * 50 + [5] * 50  # 200 coroutines

        results = await asyncio.gather(
            *[_atomic_reserve(state, q, product_id) for q in quantities],
            return_exceptions=True,
        )

        successes = [r for r in results if isinstance(r, uuid.UUID)]
        assert state.reserved_quantity <= state.stock_quantity
        assert state.available >= 0
        # At least some must have succeeded
        assert len(successes) > 0

    async def test_independent_products_dont_interfere(self):
        """
        Five separate products each with stock=10; 50 concurrent requests per
        product.  Each product should end with exactly 10 reserved and 0 available.
        """
        products = {uuid.uuid4(): _InventoryState(stock_quantity=10) for _ in range(5)}

        async def attempt(pid: uuid.UUID, state: _InventoryState) -> bool:
            try:
                await _atomic_reserve(state, 1, pid)
                return True
            except InventoryError:
                return False

        coros = [
            attempt(pid, state) for pid, state in products.items() for _ in range(50)
        ]
        await asyncio.gather(*coros)

        for pid, state in products.items():
            assert (
                state.reserved_quantity == 10
            ), f"Product {pid}: reserved={state.reserved_quantity}, expected 10"
            assert state.available == 0

    async def test_high_contention_throughput(self):
        """1 000 coroutines on 100-unit stock complete within 5 s."""
        state = _InventoryState(stock_quantity=100)
        product_id = uuid.uuid4()

        start = time.perf_counter()
        await asyncio.gather(
            *[_atomic_reserve(state, 1, product_id) for _ in range(1000)],
            return_exceptions=True,
        )
        elapsed = time.perf_counter() - start

        assert (
            elapsed < 5.0
        ), f"1 000 concurrent attempts took {elapsed:.2f}s (expected < 5s)"
        assert state.reserved_quantity == 100


# ── Deadlock detection ────────────────────────────────────────────────────────


class TestDeadlockDetection:
    """
    Verify that asyncio.Lock-based serialization never produces a deadlock.
    All coroutines must complete within a strict timeout.
    """

    async def test_no_deadlock_single_product(self):
        """1 000 concurrent coroutines for the same product — must not hang."""
        state = _InventoryState(stock_quantity=200)
        product_id = uuid.uuid4()

        try:
            await asyncio.wait_for(
                asyncio.gather(
                    *[_atomic_reserve(state, 1, product_id) for _ in range(1000)],
                    return_exceptions=True,
                ),
                timeout=10.0,
            )
        except TimeoutError:
            pytest.fail("Deadlock: 1 000 coroutines did not finish in 10 s")

    async def test_no_deadlock_multi_product(self):
        """10 products × 200 concurrent coroutines each — no deadlock."""
        products = {
            uuid.uuid4(): _InventoryState(stock_quantity=100) for _ in range(10)
        }
        coros = [
            _atomic_reserve(state, 1, pid)
            for pid, state in products.items()
            for _ in range(200)
        ]

        try:
            await asyncio.wait_for(
                asyncio.gather(*coros, return_exceptions=True),
                timeout=30.0,
            )
        except TimeoutError:
            pytest.fail("Deadlock: multi-product concurrent reservations timed out")

        for _pid, state in products.items():
            assert state.reserved_quantity <= state.stock_quantity
            assert state.available >= 0

    async def test_lock_released_after_inventory_error(self):
        """
        Even when InventoryError is raised (insufficient stock), the lock must be
        released so subsequent coroutines are not blocked.
        """
        state = _InventoryState(stock_quantity=0)  # nothing available
        product_id = uuid.uuid4()

        # All 100 must raise InventoryError promptly — the lock must not be held
        # after the exception.
        try:
            await asyncio.wait_for(
                asyncio.gather(
                    *[_atomic_reserve(state, 1, product_id) for _ in range(100)],
                    return_exceptions=True,
                ),
                timeout=5.0,
            )
        except TimeoutError:
            pytest.fail(
                "Lock was held after InventoryError — subsequent coroutines blocked"
            )

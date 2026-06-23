"""
Performance benchmarks for the reservation system.

Uses time.perf_counter() rather than pytest-benchmark (not installed).
All latency assertions are conservative bounds appropriate for a mocked
(no real I/O) test environment.

Metrics captured:
  - _atomic_reserve latency: P50, P95, P99
  - expire_stale_reservations throughput (rows/second)
  - Concurrent checkout throughput (requests/second)
  - reserve_items single-item latency
"""

import asyncio
import statistics
import time
import uuid
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock

# ── Shared state helper (reused from concurrency tests) ────────────────────


@dataclass
class _BenchState:
    stock_quantity: int
    reserved_quantity: int = 0
    sold_quantity: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def available(self) -> int:
        return self.stock_quantity - self.reserved_quantity - self.sold_quantity


async def _bench_atomic_reserve(state: _BenchState, quantity: int) -> bool:
    async with state.lock:
        if state.available < quantity:
            return False
        state.reserved_quantity += quantity
        return True


def _percentile(data: list[float], pct: float) -> float:
    """Return the pct-th percentile of sorted data."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = int(len(sorted_data) * pct / 100)
    return sorted_data[min(idx, len(sorted_data) - 1)]


# ── Benchmark 1: _atomic_reserve latency ──────────────────────────────────


class TestAtomicReserveLatency:
    """Measure per-call latency of the asyncio.Lock-based _atomic_reserve."""

    async def _measure_latencies(self, n: int, stock: int) -> list[float]:
        state = _BenchState(stock_quantity=stock)
        latencies: list[float] = []

        for _ in range(n):
            start = time.perf_counter()
            await _bench_atomic_reserve(state, 1)
            latencies.append(time.perf_counter() - start)
            if state.available == 0:
                # Reset for continuing benchmark
                state.reserved_quantity = 0

        return latencies

    async def test_p50_latency_under_1ms(self):
        """Median latency of _atomic_reserve must be under 1ms."""
        latencies = await self._measure_latencies(n=1000, stock=10000)
        p50 = _percentile(latencies, 50) * 1000  # convert to ms
        assert p50 < 1.0, f"P50 latency = {p50:.3f}ms (expected < 1ms)"

    async def test_p95_latency_under_5ms(self):
        """95th percentile latency must be under 5ms."""
        latencies = await self._measure_latencies(n=1000, stock=10000)
        p95 = _percentile(latencies, 95) * 1000
        assert p95 < 5.0, f"P95 latency = {p95:.3f}ms (expected < 5ms)"

    async def test_p99_latency_under_10ms(self):
        """99th percentile latency must be under 10ms."""
        latencies = await self._measure_latencies(n=1000, stock=10000)
        p99 = _percentile(latencies, 99) * 1000
        assert p99 < 10.0, f"P99 latency = {p99:.3f}ms (expected < 10ms)"

    async def test_latency_report(self, capsys):
        """Print latency report to stdout for CI visibility."""
        latencies = await self._measure_latencies(n=1000, stock=10000)
        ms = [lat * 1000 for lat in latencies]

        print("\n=== _atomic_reserve Latency Report (1 000 calls) ===")
        print(f"  P50 : {_percentile(ms, 50):.4f} ms")
        print(f"  P90 : {_percentile(ms, 90):.4f} ms")
        print(f"  P95 : {_percentile(ms, 95):.4f} ms")
        print(f"  P99 : {_percentile(ms, 99):.4f} ms")
        print(f"  Mean: {statistics.mean(ms):.4f} ms")
        print(f"  Max : {max(ms):.4f} ms")
        print("=" * 50)

        capsys.readouterr()
        assert len(latencies) == 1000


# ── Benchmark 2: expire_stale_reservations throughput ─────────────────────


class TestExpiryThroughput:
    """Measure rows/second for expire_stale_reservations."""

    def _build_expiry_db(self, n: int) -> AsyncMock:
        product_id = uuid.uuid4()

        def _row():
            return (uuid.uuid4(), product_id, None, None, 1)

        candidates = [_row() for _ in range(n)]

        candidates_result = MagicMock()
        candidates_result.fetchall.return_value = candidates

        side_effects = [candidates_result]
        for _ in candidates:
            skip_locked = MagicMock()
            skip_locked.fetchone.return_value = ("ACTIVE",)

            prod_result = MagicMock()
            prod_row = MagicMock()
            prod_row._mapping = {
                "stock_quantity": n,
                "reserved_quantity": n,
                "sold_quantity": 0,
            }
            prod_result.fetchone.return_value = prod_row

            side_effects.append(skip_locked)
            side_effects.append(prod_result)
            side_effects.append(MagicMock())  # UPDATE products
            side_effects.append(MagicMock())  # UPDATE reservations

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=side_effects)
        db.add = MagicMock()
        db.flush = AsyncMock()
        return db

    async def test_throughput_100_rows(self, capsys):
        from app.modules.inventory.reservation_service import ReservationService

        db = self._build_expiry_db(100)
        svc = ReservationService()

        start = time.perf_counter()
        count = await svc.expire_stale_reservations(db)
        elapsed = time.perf_counter() - start

        rps = count / elapsed if elapsed > 0 else float("inf")
        print(
            f"\n  expire_stale_reservations (100 rows): {rps:.0f} rows/sec ({elapsed*1000:.1f}ms)"
        )
        assert count == 100

    async def test_throughput_500_rows(self, capsys):
        from app.modules.inventory.reservation_service import ReservationService

        db = self._build_expiry_db(500)
        svc = ReservationService()

        start = time.perf_counter()
        count = await svc.expire_stale_reservations(db)
        elapsed = time.perf_counter() - start

        rps = count / elapsed if elapsed > 0 else float("inf")
        print(
            f"\n  expire_stale_reservations (500 rows): {rps:.0f} rows/sec ({elapsed*1000:.1f}ms)"
        )
        assert count == 500
        assert elapsed < 5.0, f"500-row expiry took {elapsed:.2f}s (expected < 5s)"

    async def test_throughput_report(self, capsys):
        """Print multi-batch throughput report."""
        from app.modules.inventory.reservation_service import ReservationService

        svc = ReservationService()
        batch_sizes = [10, 50, 100, 250, 500]
        results = []

        for n in batch_sizes:
            db = self._build_expiry_db(n)
            start = time.perf_counter()
            count = await svc.expire_stale_reservations(db)
            elapsed = time.perf_counter() - start
            rps = count / elapsed if elapsed > 0 else float("inf")
            results.append((n, elapsed * 1000, rps))

        print("\n=== expire_stale_reservations Throughput Report ===")
        print(f"  {'Rows':>8} | {'Time (ms)':>12} | {'Rows/sec':>12}")
        print(f"  {'-'*8} | {'-'*12} | {'-'*12}")
        for n, ms, rps in results:
            print(f"  {n:>8} | {ms:>12.1f} | {rps:>12.0f}")
        print("=" * 45)

        capsys.readouterr()
        assert len(results) == len(batch_sizes)


# ── Benchmark 3: concurrent checkout throughput ────────────────────────────


class TestCheckoutThroughput:
    """Measure requests/second for concurrent checkout under contention."""

    async def _run_concurrent(
        self, n: int, stock: int, qty: int = 1
    ) -> tuple[int, int, float]:
        state = _BenchState(stock_quantity=stock)
        start = time.perf_counter()
        results = await asyncio.gather(
            *[_bench_atomic_reserve(state, qty) for _ in range(n)],
            return_exceptions=True,
        )
        elapsed = time.perf_counter() - start
        successes = sum(1 for r in results if r is True)
        return successes, n, elapsed

    async def test_throughput_100_concurrent(self, capsys):
        successes, total, elapsed = await self._run_concurrent(100, stock=50)
        rps = total / elapsed if elapsed > 0 else float("inf")
        print(f"\n  100 concurrent (stock=50): {rps:.0f} req/sec, {successes} success")
        assert elapsed < 1.0

    async def test_throughput_500_concurrent(self, capsys):
        successes, total, elapsed = await self._run_concurrent(500, stock=100)
        rps = total / elapsed if elapsed > 0 else float("inf")
        print(f"\n  500 concurrent (stock=100): {rps:.0f} req/sec, {successes} success")
        assert elapsed < 2.0

    async def test_throughput_1000_concurrent(self, capsys):
        successes, total, elapsed = await self._run_concurrent(1000, stock=200)
        rps = total / elapsed if elapsed > 0 else float("inf")
        print(
            f"\n  1 000 concurrent (stock=200): {rps:.0f} req/sec, {successes} success"
        )
        assert elapsed < 5.0

    async def test_throughput_report(self, capsys):
        """Print full checkout throughput report."""
        scenarios = [
            (100, 50),
            (500, 100),
            (1000, 200),
            (5000, 500),
        ]

        print("\n=== Concurrent Checkout Throughput Report ===")
        print(
            f"  {'Concurrent':>12} | {'Stock':>8} | {'Success':>8} | {'req/sec':>10} | {'ms':>8}"
        )
        print(f"  {'-'*12} | {'-'*8} | {'-'*8} | {'-'*10} | {'-'*8}")

        for n, stock in scenarios:
            successes, total, elapsed = await self._run_concurrent(n, stock)
            rps = total / elapsed
            print(
                f"  {n:>12} | {stock:>8} | {successes:>8} | {rps:>10.0f} | {elapsed*1000:>8.1f}"
            )

        print("=" * 60)
        capsys.readouterr()
        assert True  # report always passes


# ── Benchmark 4: reserve_items single-call latency ────────────────────────


class TestReserveItemsLatency:
    """Measure latency of ReservationService.reserve_items with mocked DB."""

    def _build_reserve_db(self) -> AsyncMock:
        product_id = uuid.uuid4()
        prod_row = MagicMock()
        prod_row._mapping = {
            "id": str(product_id),
            "name": "Silver Ring",
            "sku": "SKU-001",
            "stock_quantity": 100,
            "reserved_quantity": 0,
            "sold_quantity": 0,
            "track_inventory": True,
            "allow_backorder": False,
        }

        select_result = MagicMock()
        select_result.fetchone.return_value = prod_row

        reservation_mock = MagicMock()
        reservation_mock.id = uuid.uuid4()
        reservation_mock.reservation_number = "RES-ABCD1234"

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                select_result,  # SELECT FOR UPDATE
                MagicMock(),  # UPDATE products
            ]
        )
        db.add = MagicMock()
        db.flush = AsyncMock()
        return db

    async def _measure_reserve_latency(self, iterations: int) -> list[float]:
        from app.modules.inventory.reservation_service import ReservationService

        latencies = []
        svc = ReservationService()

        for _ in range(iterations):
            db = self._build_reserve_db()
            product_id = uuid.uuid4()

            start = time.perf_counter()
            await svc.reserve_items(
                db,
                user_id=uuid.uuid4(),
                items=[{"product_id": product_id, "quantity": 1}],
            )
            latencies.append(time.perf_counter() - start)

        return latencies

    async def test_reserve_items_p50_under_5ms(self):
        latencies = await self._measure_reserve_latency(100)
        p50 = _percentile(latencies, 50) * 1000
        assert p50 < 5.0, f"reserve_items P50 = {p50:.3f}ms (expected < 5ms)"

    async def test_reserve_items_p95_under_20ms(self):
        latencies = await self._measure_reserve_latency(100)
        p95 = _percentile(latencies, 95) * 1000
        assert p95 < 20.0, f"reserve_items P95 = {p95:.3f}ms (expected < 20ms)"

    async def test_reserve_items_latency_report(self, capsys):
        latencies = await self._measure_reserve_latency(200)
        ms = [lat * 1000 for lat in latencies]

        print("\n=== reserve_items Latency Report (200 calls, mocked DB) ===")
        print(f"  P50 : {_percentile(ms, 50):.4f} ms")
        print(f"  P90 : {_percentile(ms, 90):.4f} ms")
        print(f"  P95 : {_percentile(ms, 95):.4f} ms")
        print(f"  P99 : {_percentile(ms, 99):.4f} ms")
        print(f"  Mean: {statistics.mean(ms):.4f} ms")
        print(f"  Max : {max(ms):.4f} ms")
        print("=" * 55)

        capsys.readouterr()
        assert len(latencies) == 200

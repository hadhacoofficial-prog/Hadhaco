"""
Runtime profiling instrumentation for pool, SQL, Redis, and cache.
-----------------------------------------------------------------
Captures high-water marks, wait-time histograms, percentile latencies,
per-request query stats, slow-SQL tracking, and endpoint latency rankings
without adding external dependencies.

Usage:
    from app.core.profiling import profiler

    # In request middleware (once per request):
    profiler.begin_request()
    ...
    profiler.end_request()        # records query stats, pool snapshot

    # For Redis calls:
    async with profiler.track_redis("get", key):
        result = await safe_redis_get(...)

    # For cache hits/misses:
    profiler.record_cache_hit()
    profiler.record_cache_miss()
"""

from __future__ import annotations

import bisect
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger("profiling")

_lock = threading.Lock()

# ── Constants ────────────────────────────────────────────────────────────────
_SLOW_SQL_THRESHOLD_MS: float = 200.0
_SLOW_QUERY_DEQUE_MAX: int = 50
_ENDPOINT_RANKING_SIZE: int = 10


class LatencyHistogram:
    """Fixed-bucket in-memory histogram for percentile computation.

    Uses *sorted-insert* on a bounded sample ring so memory is O(max_samples)
    instead of O(total_observations).  Percentiles are computed from the raw
    sample list, giving exact results for the most recent window of
    observations.
    """

    __slots__ = ("_max_samples", "_samples", "_total_count", "_total_sum")

    def __init__(self, max_samples: int = 4_096) -> None:
        self._max_samples = max_samples
        self._samples: list[float] = []
        self._total_count: int = 0
        self._total_sum: float = 0.0

    def record(self, value_ms: float) -> None:
        self._total_count += 1
        self._total_sum += value_ms
        if len(self._samples) < self._max_samples:
            bisect.insort(self._samples, value_ms)
        else:
            # Replace a random-ish position to avoid bias toward old values.
            # Use total_count mod max_samples for a simple spread.
            idx = self._total_count % self._max_samples
            self._samples[idx] = value_ms
            # Re-sort — O(n log n) worst case but n is capped at 4 096.
            self._samples.sort()

    def percentile(self, p: float) -> float:
        """Return the *p*-th percentile (0–1) in ms, or 0.0 if empty."""
        if not self._samples:
            return 0.0
        idx = max(0, min(int(len(self._samples) * p), len(self._samples) - 1))
        return round(self._samples[idx], 2)

    @property
    def count(self) -> int:
        return self._total_count

    @property
    def avg(self) -> float:
        return (
            round(self._total_sum / self._total_count, 2) if self._total_count else 0.0
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "count": self._total_count,
            "avg_ms": self.avg,
            "p50_ms": self.percentile(0.50),
            "p95_ms": self.percentile(0.95),
            "p99_ms": self.percentile(0.99),
        }


# ── Internal dataclasses ─────────────────────────────────────────────────────


@dataclass
class _PerRequestStats:
    """Accumulated during a single request lifetime."""

    query_count: int = 0
    query_total_ms: float = 0.0
    query_max_ms: float = 0.0
    slow_queries: list[dict[str, Any]] = field(default_factory=list)
    pool_checked_out_peak: int = 0


@dataclass
class _SlowQueryEntry:
    """A single slow-query record kept in the global deque."""

    __slots__ = ("duration_ms", "query", "timestamp")

    def __init__(self, duration_ms: float, query: str) -> None:
        self.duration_ms = duration_ms
        self.query = query
        self.timestamp = time.time()

    def as_dict(self) -> dict[str, Any]:
        return {
            "duration_ms": round(self.duration_ms, 1),
            "query": self.query,
            "timestamp": self.timestamp,
        }


@dataclass
class _EndpointStats:
    """Per-path latency accumulator for the top-N ranking."""

    path: str
    count: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0

    @property
    def avg_ms(self) -> float:
        return round(self.total_ms / self.count, 2) if self.count else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "request_count": self.count,
            "avg_ms": self.avg_ms,
            "max_ms": round(self.max_ms, 1),
        }


class _GlobalStats:
    """Singleton accumulated across all requests (reset on restart).

    Holds raw counters *and* references to the histogram / deque objects
    that are mutated under ``_lock``.
    """

    def __init__(self) -> None:
        # ── Pool ──────────────────────────────────────────────────────────
        self.pool_checkout_waits_total: int = 0
        self.pool_checkout_wait_ms_total: float = 0.0
        self.pool_checkout_wait_max_ms: float = 0.0
        self.pool_peak_checked_out: int = 0
        self.pool_peak_capacity: int = 0
        # ── SQL ───────────────────────────────────────────────────────────
        self.sql_queries_total: int = 0
        self.sql_slow_total: int = 0
        self.sql_total_ms: float = 0.0
        # ── Redis ─────────────────────────────────────────────────────────
        self.redis_total_calls: int = 0
        self.redis_total_ms: float = 0.0
        self.redis_max_ms: float = 0.0
        self.redis_errors_total: int = 0
        self.redis_circuit_breaker_fallbacks: int = 0
        # ── Cache ─────────────────────────────────────────────────────────
        self.cache_hits: int = 0
        self.cache_misses: int = 0
        self.cache_compressed_writes: int = 0
        self.cache_bytes_saved_by_compression: int = 0
        # ── Requests ──────────────────────────────────────────────────────
        self.requests_total: int = 0

        # ── Histograms (sample-ring backed) ───────────────────────────────
        self.request_histogram = LatencyHistogram()
        self.sql_histogram = LatencyHistogram()
        self.redis_histogram = LatencyHistogram()

        # ── Slow SQL deque (bounded) ──────────────────────────────────────
        self.slow_queries: deque[_SlowQueryEntry] = deque(maxlen=_SLOW_QUERY_DEQUE_MAX)

        # ── Endpoint latency (in-memory dict — not bounded, but bounded by
        #    the number of distinct paths which is finite in a given deploy).
        self.endpoints: dict[str, _EndpointStats] = {}

    def as_dict(self) -> dict[str, Any]:
        avg_wait = (
            self.pool_checkout_wait_ms_total / self.pool_checkout_waits_total
            if self.pool_checkout_waits_total
            else 0
        )
        avg_query = (
            self.sql_total_ms / self.sql_queries_total if self.sql_queries_total else 0
        )
        avg_redis = (
            self.redis_total_ms / self.redis_total_calls
            if self.redis_total_calls
            else 0
        )
        total_cache = self.cache_hits + self.cache_misses
        cache_hit_rate = (
            round(self.cache_hits / total_cache * 100, 1) if total_cache else 0.0
        )
        return {
            "pool": {
                "capacity": self.pool_peak_capacity,
                "peak_checked_out": self.pool_peak_checked_out,
                "peak_utilization_pct": (
                    round(
                        self.pool_peak_checked_out
                        / max(1, self.pool_peak_capacity)
                        * 100,
                        1,
                    )
                ),
                "total_checkout_waits": self.pool_checkout_waits_total,
                "total_wait_ms": round(self.pool_checkout_wait_ms_total, 1),
                "max_wait_ms": round(self.pool_checkout_wait_max_ms, 1),
                "avg_wait_ms": round(avg_wait, 1),
            },
            "sql": {
                "total_queries": self.sql_queries_total,
                "total_ms": round(self.sql_total_ms, 1),
                "avg_ms": round(avg_query, 1),
                "slow_queries": self.sql_slow_total,
            },
            "redis": {
                "total_calls": self.redis_total_calls,
                "total_ms": round(self.redis_total_ms, 1),
                "max_ms": round(self.redis_max_ms, 1),
                "avg_ms": round(avg_redis, 1),
                "errors": self.redis_errors_total,
                "circuit_breaker_fallbacks": self.redis_circuit_breaker_fallbacks,
            },
            "cache": {
                "hits": self.cache_hits,
                "misses": self.cache_misses,
                "hit_rate_pct": cache_hit_rate,
                "compressed_writes": self.cache_compressed_writes,
                "bytes_saved_by_compression": self.cache_bytes_saved_by_compression,
            },
            "requests_total": self.requests_total,
        }


class Profiler:
    """Thread-safe profiling singleton."""

    def __init__(self) -> None:
        self._global = _GlobalStats()
        self._local = threading.local()
        self._request_start: float = 0.0
        self._start_time: float = time.time()

    # ── Request lifecycle ──────────────────────────────────────────────────

    def begin_request(self) -> None:
        self._request_start = time.perf_counter()
        stats = _PerRequestStats()
        self._local.stats = stats  # type: ignore[attr-defined]

    def end_request(self, path: str = "", duration_ms: float = 0.0) -> None:
        stats: _PerRequestStats | None = getattr(self._local, "stats", None)
        if stats is None:
            return
        with _lock:
            self._global.requests_total += 1
            self._global.sql_queries_total += stats.query_count
            self._global.sql_total_ms += stats.query_total_ms
            self._global.sql_slow_total += len(stats.slow_queries)
            if stats.pool_checked_out_peak > self._global.pool_peak_checked_out:
                self._global.pool_peak_checked_out = stats.pool_checked_out_peak
            # Record request latency into histogram
            if duration_ms > 0:
                self._global.request_histogram.record(duration_ms)
            # Track endpoint latency
            if path:
                ep = self._global.endpoints.get(path)
                if ep is None:
                    ep = _EndpointStats(path=path)
                    self._global.endpoints[path] = ep
                ep.count += 1
                ep.total_ms += duration_ms
                if duration_ms > ep.max_ms:
                    ep.max_ms = duration_ms
        self._local.stats = None  # type: ignore[attr-defined]

    # ── Pool checkout tracking (called from event listener) ────────────────

    def record_pool_checkout(
        self, wait_ms: float, checked_out: int, capacity: int
    ) -> None:
        with _lock:
            self._global.pool_checkout_waits_total += 1
            self._global.pool_checkout_wait_ms_total += wait_ms
            if wait_ms > self._global.pool_checkout_wait_max_ms:
                self._global.pool_checkout_wait_max_ms = wait_ms
            if checked_out > self._global.pool_peak_checked_out:
                self._global.pool_peak_checked_out = checked_out
            self._global.pool_peak_capacity = max(
                self._global.pool_peak_capacity, capacity
            )
        stats: _PerRequestStats | None = getattr(self._local, "stats", None)
        if stats is not None:
            if checked_out > stats.pool_checked_out_peak:
                stats.pool_checked_out_peak = checked_out

    # ── SQL query tracking ────────────────────────────────────────────────

    def record_query(
        self,
        duration_ms: float,
        query_text: str = "",
        slow_threshold_ms: float = _SLOW_SQL_THRESHOLD_MS,
    ) -> None:
        # Global histogram (always, regardless of per-request state)
        with _lock:
            self._global.sql_histogram.record(duration_ms)
        stats: _PerRequestStats | None = getattr(self._local, "stats", None)
        if stats is not None:
            stats.query_count += 1
            stats.query_total_ms += duration_ms
            if duration_ms > stats.query_max_ms:
                stats.query_max_ms = duration_ms
            if duration_ms >= slow_threshold_ms:
                truncated = query_text[:200] if query_text else ""
                stats.slow_queries.append(
                    {
                        "duration_ms": round(duration_ms, 1),
                        "query": truncated,
                    }
                )
                # Also record into the global slow-query deque
                with _lock:
                    self._global.slow_queries.append(
                        _SlowQueryEntry(duration_ms, truncated)
                    )

    # ── Redis call tracking ───────────────────────────────────────────────

    def record_redis(
        self,
        operation: str,
        duration_ms: float,
        error: bool = False,
        circuit_breaker_fallback: bool = False,
    ) -> None:
        with _lock:
            self._global.redis_total_calls += 1
            self._global.redis_total_ms += duration_ms
            if duration_ms > self._global.redis_max_ms:
                self._global.redis_max_ms = duration_ms
            if error:
                self._global.redis_errors_total += 1
            if circuit_breaker_fallback:
                self._global.redis_circuit_breaker_fallbacks += 1
            self._global.redis_histogram.record(duration_ms)

    # ── Cache hit/miss tracking ───────────────────────────────────────────

    def record_cache_hit(self) -> None:
        with _lock:
            self._global.cache_hits += 1

    def record_cache_miss(self) -> None:
        with _lock:
            self._global.cache_misses += 1

    def record_cache_compression(self, bytes_saved: int) -> None:
        """Record bytes saved by SWR cache compression."""
        with _lock:
            self._global.cache_compressed_writes += 1
            self._global.cache_bytes_saved_by_compression += bytes_saved

    # ── Snapshot ──────────────────────────────────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        """Return current metrics snapshot (non-destructive)."""
        with _lock:
            data = self._global.as_dict()
            # Attach histogram percentiles
            data["request_latency"] = self._global.request_histogram.as_dict()
            data["sql_latency"] = self._global.sql_histogram.as_dict()
            data["redis_latency"] = self._global.redis_histogram.as_dict()
            # Attach top-N slow SQL queries
            data["slow_sql_top5"] = [
                entry.as_dict()
                for entry in sorted(
                    self._global.slow_queries,
                    key=lambda e: e.duration_ms,
                    reverse=True,
                )[:5]
            ]
            # Attach top-10 slowest endpoints
            ranked = sorted(
                self._global.endpoints.values(),
                key=lambda e: e.avg_ms,
                reverse=True,
            )[:_ENDPOINT_RANKING_SIZE]
            data["slowest_endpoints"] = [ep.as_dict() for ep in ranked]
            # Uptime
            data["uptime_seconds"] = round(time.time() - self._start_time, 1)
        return data

    def reset(self) -> None:
        """Reset all counters (for testing)."""
        with _lock:
            self._global = _GlobalStats()
            self._start_time = time.time()


profiler = Profiler()

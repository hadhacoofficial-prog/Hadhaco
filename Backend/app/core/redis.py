import asyncio
import json
import time
from collections.abc import AsyncGenerator
from enum import Enum
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings

_redis_pool: aioredis.Redis | None = None

# ── Circuit breaker ───────────────────────────────────────────────────────────
# Three-state circuit breaker for Redis:
#   CLOSED  → normal operation, requests pass through
#   OPEN    → Redis down, requests fail fast with fallback
#   HALF_OPEN → one probe allowed through; success → CLOSED, failure → OPEN
#
# Uses exponential backoff when transitioning OPEN → HALF_OPEN:
#   30s → 60s → 120s → 300s (max). Resets on success.


class _CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


_circuit_state: _CircuitState = _CircuitState.CLOSED
_circuit_failed_at: float = 0.0
_circuit_consecutive_failures: int = 0
_CIRCUIT_INITIAL_BACKOFF: float = 30.0  # seconds
_CIRCUIT_MAX_BACKOFF: float = 300.0  # 5 minutes max
_CIRCUIT_BACKOFF_MULTIPLIER: float = 2.0
_REDIS_OP_TIMEOUT: float = 0.3  # max seconds per cache operation


def _circuit_backoff() -> float:
    """Compute exponential backoff for the current failure count."""
    backoff = _CIRCUIT_INITIAL_BACKOFF * (
        _CIRCUIT_BACKOFF_MULTIPLIER ** min(_circuit_consecutive_failures, 5)
    )
    return min(backoff, _CIRCUIT_MAX_BACKOFF)


def redis_available() -> bool:
    """Return False if Redis is known down and the retry window hasn't elapsed.

    Transitions OPEN → HALF_OPEN when the backoff elapses, allowing a
    single probe request through.
    """
    if _circuit_state == _CircuitState.CLOSED:
        return True
    if _circuit_state == _CircuitState.HALF_OPEN:
        return True  # Allow probe requests through
    # OPEN state — check if backoff has elapsed, transition to HALF_OPEN
    if (time.monotonic() - _circuit_failed_at) >= _circuit_backoff():
        _try_half_open()
        return True
    return False


def mark_redis_ok() -> None:
    """Redis responded successfully — close the circuit breaker."""
    global _circuit_state, _circuit_consecutive_failures
    if _circuit_state != _CircuitState.CLOSED:
        import structlog

        structlog.get_logger("redis.circuit").info(
            "circuit_closed",
            prev_state=_circuit_state.value,
            consecutive_failures=_circuit_consecutive_failures,
        )
    _circuit_state = _CircuitState.CLOSED
    _circuit_consecutive_failures = 0


def mark_redis_error() -> None:
    """Redis operation failed — open the circuit or stay open."""
    global _circuit_state, _circuit_failed_at, _circuit_consecutive_failures

    _circuit_consecutive_failures += 1

    if _circuit_state == _CircuitState.HALF_OPEN:
        # Probe failed — stay open with increased backoff
        _circuit_failed_at = time.monotonic()
        _circuit_state = _CircuitState.OPEN
        import structlog

        structlog.get_logger("redis.circuit").warning(
            "circuit_probe_failed",
            consecutive_failures=_circuit_consecutive_failures,
            backoff_s=round(_circuit_backoff(), 1),
        )
    elif _circuit_state == _CircuitState.CLOSED:
        # First failure — transition to OPEN
        _circuit_failed_at = time.monotonic()
        _circuit_state = _CircuitState.OPEN
        import structlog

        structlog.get_logger("redis.circuit").warning(
            "circuit_opened",
            consecutive_failures=_circuit_consecutive_failures,
            backoff_s=round(_circuit_backoff(), 1),
        )
    # If already OPEN, just keep the state (backoff timer is running)


def _try_half_open() -> bool:
    """If in OPEN state and backoff elapsed, transition to HALF_OPEN.

    Returns True if the probe is allowed through.
    """
    global _circuit_state
    if _circuit_state != _CircuitState.OPEN:
        return (
            _circuit_state == _CircuitState.CLOSED
            or _circuit_state == _CircuitState.HALF_OPEN
        )
    if (time.monotonic() - _circuit_failed_at) >= _circuit_backoff():
        _circuit_state = _CircuitState.HALF_OPEN
        import structlog

        structlog.get_logger("redis.circuit").info(
            "circuit_half_open",
            consecutive_failures=_circuit_consecutive_failures,
        )
        return True
    return False


def get_circuit_state() -> dict[str, Any]:
    """Return circuit breaker status for observability."""
    return {
        "state": _circuit_state.value,
        "consecutive_failures": _circuit_consecutive_failures,
        "backoff_s": round(_circuit_backoff(), 1),
        "time_since_failure_s": (
            round(time.monotonic() - _circuit_failed_at, 1) if _circuit_failed_at else 0
        ),
    }


async def safe_redis_get(redis: aioredis.Redis, key: str) -> str | None:
    """
    Get a Redis key with a hard timeout and circuit-breaker guard.
    Returns None on any failure — callers fall through to the source of truth.
    """
    if not redis_available():
        from app.core.profiling import profiler

        profiler.record_redis("get", 0.0, circuit_breaker_fallback=True)
        return None
    try:
        t0 = time.perf_counter()
        value = await asyncio.wait_for(redis.get(key), timeout=_REDIS_OP_TIMEOUT)
        from app.core.profiling import profiler

        profiler.record_redis("get", (time.perf_counter() - t0) * 1000)
        mark_redis_ok()
        return value
    except Exception:
        from app.core.profiling import profiler

        profiler.record_redis("get", 0.0, error=True)
        mark_redis_error()
        return None


async def safe_redis_setex(
    redis: aioredis.Redis, key: str, ttl: int, value: str
) -> None:
    """Set a Redis key with a hard timeout and circuit-breaker guard. Fire-and-forget."""
    if not redis_available():
        from app.core.profiling import profiler

        profiler.record_redis("setex", 0.0, circuit_breaker_fallback=True)
        return
    try:
        t0 = time.perf_counter()
        await asyncio.wait_for(redis.setex(key, ttl, value), timeout=_REDIS_OP_TIMEOUT)
        from app.core.profiling import profiler

        profiler.record_redis("setex", (time.perf_counter() - t0) * 1000)
        mark_redis_ok()
    except Exception:
        from app.core.profiling import profiler

        profiler.record_redis("setex", 0.0, error=True)
        mark_redis_error()


async def safe_redis_delete(redis: aioredis.Redis, *keys: str) -> None:
    """Delete Redis keys with a hard timeout and circuit-breaker guard."""
    if not redis_available() or not keys:
        if not redis_available() and keys:
            from app.core.profiling import profiler

            profiler.record_redis("delete", 0.0, circuit_breaker_fallback=True)
        return
    try:
        t0 = time.perf_counter()
        await asyncio.wait_for(redis.delete(*keys), timeout=_REDIS_OP_TIMEOUT)
        from app.core.profiling import profiler

        profiler.record_redis("delete", (time.perf_counter() - t0) * 1000)
        mark_redis_ok()
    except Exception:
        from app.core.profiling import profiler

        profiler.record_redis("delete", 0.0, error=True)
        mark_redis_error()


# Must match catalog/router.py's `_PRODUCT_LIST_TTL` (the `ttl` *and*
# `swr_window` passed to `cache_swr` for the product-list cache — both are
# 300s there). Duplicated here rather than imported to avoid a cycle
# (app.core.cache imports bust_product_list_cache from this module already).
_PRODUCT_LIST_SWR_TTL_SECONDS = 300


async def bust_product_list_cache(redis: aioredis.Redis) -> None:
    """Soft-invalidate every cached storefront product-list page
    (`products:list:v1:*`) — rewrites each entry's cache_swr staleness
    timestamp to "just expired" instead of deleting the key outright.

    Called after any mutation that changes what a product listing renders —
    not just catalog field edits, but also product image crop/replace/
    set-primary/delete/upload via the media module, since those change the
    thumbnail a `ProductListItem` serves without touching the `products`
    table row itself.

    Previously this did a hard DELETE. cache_swr (app/core/cache.py) only
    serves stale-while-revalidating when *some* cached value exists — a
    fully deleted key is a hard miss, and cache_swr's hard-miss path blocks
    every reader on a fresh DB round-trip. In production, a single admin
    session doing a product image upload followed by a crop (two busts
    seconds apart) turned every /api/v1/products request in between into a
    ~2.3-2.7s synchronous fetch, repeatedly — confirmed via Loki correlation
    post-deploy. Rewriting the timestamp instead keeps the still-valid
    cached page servable instantly (slightly stale — acceptable, same
    tradeoff cache_swr already makes on every normal TTL expiry) while
    triggering exactly one coalesced background refresh.
    """
    if not redis_available():
        return
    try:

        async def _collect() -> list[str]:
            return [
                str(key)
                async for key in redis.scan_iter(match="products:list:v1:*", count=500)
            ]

        keys = await asyncio.wait_for(_collect(), timeout=1.0)
        for key in keys:
            await _soft_expire_swr_entry(
                redis, key, ttl_seconds=_PRODUCT_LIST_SWR_TTL_SECONDS
            )
    except Exception:
        mark_redis_error()


async def _soft_expire_swr_entry(
    redis: aioredis.Redis, key: str, *, ttl_seconds: int
) -> None:
    """Rewrite one `cache_swr`-format entry's `"t"` field so the next read
    lands on cache_swr's soft-expired (stale-serve + background-refresh)
    branch instead of fresh or hard-miss. Falls back to a hard DELETE if the
    stored value isn't in the expected `{"d": ..., "t": ...}` wrapper shape
    (legacy/foreign entry) — the same defensive fallback cache_swr's own
    read path uses for unparseable values, so an entry this can't safely
    rewrite is still invalidated, just via the old (correct, if blocking)
    path rather than silently left fresh.
    """
    from app.core.cache import _compress_value, _decompress_value

    try:
        raw = await safe_redis_get(redis, key)
        if not raw:
            return
        wrapper = json.loads(_decompress_value(raw))
        # Must have the {"d", "t"} shape cache_swr writes — KeyError below
        # falls through to the hard-delete fallback for anything else.
        wrapper["d"]
        wrapper["t"] = time.time() - ttl_seconds
        rewritten = _compress_value(json.dumps(wrapper, default=str))
        # cache_swr always stores at Redis TTL = ttl + swr_window; for the
        # product list both are ttl_seconds, so 2x here reproduces that.
        await safe_redis_setex(redis, key, ttl_seconds * 2, rewritten)
    except (json.JSONDecodeError, KeyError, TypeError):
        await safe_redis_delete(redis, key)


def get_redis_pool() -> aioredis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
            # Defense-in-depth for the long-lived pub/sub subscriber
            # (app/core/pubsub.py): OS-level TCP keepalive helps the kernel
            # notice a half-open connection sooner, and health_check_interval
            # makes get_message()'s periodic health probing (not .listen(),
            # which has no timeout and can't self-check) more robust. Neither
            # changes behavior for the short-lived cache calls in this module,
            # which already bound themselves via asyncio.wait_for.
            socket_keepalive=True,
            health_check_interval=30,
        )
    return _redis_pool


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """FastAPI dependency — yields a Redis connection."""
    pool = get_redis_pool()
    try:
        yield pool
    finally:
        pass  # pool is shared; do not close per-request


async def close_redis() -> None:
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None


class RedisCache:
    """
    Thin wrapper for cache-aside pattern.
    Serializes/deserializes JSON automatically.
    """

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    async def get(self, key: str) -> Any | None:
        import json

        value = await self._redis.get(key)
        if value is None:
            return None
        return json.loads(value)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        import json

        serialized = json.dumps(value, default=str)
        await self._redis.set(key, serialized, ex=ttl or settings.REDIS_CACHE_TTL)

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)

    async def delete_pattern(self, pattern: str) -> int:
        # KEYS blocks the whole Redis event loop for the duration of the
        # scan on a large keyspace — SCAN (via scan_iter) walks it
        # incrementally instead, same tradeoff bust_product_list_cache
        # already makes above. Docs audit LP-10.
        keys = [
            str(key) async for key in self._redis.scan_iter(match=pattern, count=500)
        ]
        if keys:
            return await self._redis.delete(*keys)
        return 0

    async def exists(self, key: str) -> bool:
        return bool(await self._redis.exists(key))

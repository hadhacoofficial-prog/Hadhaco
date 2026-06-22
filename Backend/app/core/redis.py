import asyncio
import time
from collections.abc import AsyncGenerator
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings

_redis_pool: aioredis.Redis | None = None

# ── Circuit breaker ───────────────────────────────────────────────────────────
# When Redis is unreachable, skip cache calls rather than waiting on TCP timeout.
# Each uvicorn worker maintains its own state independently.

_circuit_ok: bool = True
_circuit_failed_at: float = 0.0
_CIRCUIT_RETRY_AFTER: float = 30.0  # seconds before retrying a down Redis
_REDIS_OP_TIMEOUT: float = 0.3  # max seconds per cache operation


def redis_available() -> bool:
    """Return False if Redis is known down and the retry window hasn't elapsed."""
    if _circuit_ok:
        return True
    return (time.monotonic() - _circuit_failed_at) >= _CIRCUIT_RETRY_AFTER


def mark_redis_ok() -> None:
    global _circuit_ok
    _circuit_ok = True


def mark_redis_error() -> None:
    global _circuit_ok, _circuit_failed_at
    if _circuit_ok:
        _circuit_failed_at = time.monotonic()
    _circuit_ok = False


async def safe_redis_get(redis: aioredis.Redis, key: str) -> str | None:
    """
    Get a Redis key with a hard timeout and circuit-breaker guard.
    Returns None on any failure — callers fall through to the source of truth.
    """
    if not redis_available():
        return None
    try:
        value = await asyncio.wait_for(redis.get(key), timeout=_REDIS_OP_TIMEOUT)
        mark_redis_ok()
        return value
    except Exception:
        mark_redis_error()
        return None


async def safe_redis_setex(redis: aioredis.Redis, key: str, ttl: int, value: str) -> None:
    """Set a Redis key with a hard timeout and circuit-breaker guard. Fire-and-forget."""
    if not redis_available():
        return
    try:
        await asyncio.wait_for(redis.setex(key, ttl, value), timeout=_REDIS_OP_TIMEOUT)
        mark_redis_ok()
    except Exception:
        mark_redis_error()


async def safe_redis_delete(redis: aioredis.Redis, *keys: str) -> None:
    """Delete Redis keys with a hard timeout and circuit-breaker guard."""
    if not redis_available() or not keys:
        return
    try:
        await asyncio.wait_for(redis.delete(*keys), timeout=_REDIS_OP_TIMEOUT)
        mark_redis_ok()
    except Exception:
        mark_redis_error()


def get_redis_pool() -> aioredis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
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
        keys = await self._redis.keys(pattern)
        if keys:
            return await self._redis.delete(*keys)
        return 0

    async def exists(self, key: str) -> bool:
        return bool(await self._redis.exists(key))

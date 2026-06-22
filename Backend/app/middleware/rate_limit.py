"""
Redis-backed sliding window rate limiter.

Usage in routers:
    @router.post("/login")
    async def login(
        request: Request,
        redis: aioredis.Redis = Depends(get_redis),
    ):
        await check_rate_limit(request, redis, limit=settings.RATE_LIMIT_AUTH, window=60)
        ...

Or as a middleware for blanket API limiting (applied in main.py).
"""

import time

import redis.asyncio as aioredis
import structlog
from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.redis import get_redis_pool

log = structlog.get_logger(__name__)


async def check_rate_limit(
    request: Request,
    redis: aioredis.Redis,
    *,
    limit: int,
    window: int = 60,
    key_prefix: str = "rl",
) -> None:
    """
    Sliding window rate limiter.
    key  = <prefix>:<ip>:<path>
    Uses a Redis sorted set: members are timestamps, scored by timestamp.

    Fails OPEN: a Redis outage must degrade rate limiting, not take the
    API down with it.
    """
    ip = _get_client_ip(request)
    path = request.url.path
    key = f"{key_prefix}:{ip}:{path}"
    now = time.time()
    window_start = now - window

    try:
        pipe = redis.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, window)
        results = await pipe.execute()
    except Exception as exc:
        log.warning("rate_limit_redis_unavailable", error=str(exc), key=key)
        return

    count: int = results[2]
    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please slow down.",
            headers={
                "Retry-After": str(window),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(now + window)),
            },
        )


def _get_client_ip(request: Request) -> str:
    """Respects X-Forwarded-For from trusted reverse proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


async def rate_limit_auth(request: Request) -> None:
    """Dependency for auth endpoints."""
    redis = get_redis_pool()
    await check_rate_limit(
        request, redis,
        limit=settings.RATE_LIMIT_AUTH,
        window=60,
        key_prefix="rl:auth",
    )


async def rate_limit_upload(request: Request) -> None:
    """Dependency for file upload endpoints."""
    redis = get_redis_pool()
    await check_rate_limit(
        request, redis,
        limit=settings.RATE_LIMIT_UPLOAD,
        window=60,
        key_prefix="rl:upload",
    )


async def rate_limit_webhook(request: Request) -> None:
    """Dependency for webhook endpoints."""
    redis = get_redis_pool()
    await check_rate_limit(
        request, redis,
        limit=settings.RATE_LIMIT_WEBHOOK,
        window=60,
        key_prefix="rl:webhook",
    )

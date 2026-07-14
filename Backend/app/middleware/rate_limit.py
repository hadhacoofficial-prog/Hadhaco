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

Named policies provide endpoint-specific limits while sharing the same
sliding-window implementation.  Import and use as FastAPI dependencies:

    @router.post("/verify-token", dependencies=[Depends(rate_limit_verify_token)])
    async def verify_token(...):
        ...
"""

import time
from dataclasses import dataclass

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
    """
    Extract the real client IP.

    Strategy (defense in depth):
    1. X-Real-IP — set by Nginx, always the true client IP (preferred).
    2. X-Forwarded-For — only used when behind a trusted proxy.
       Without a trusted-proxy allowlist we take the *last* non-private IP
       in the chain (closest to the internet), not the first (which the
       client controls).
    3. request.client.host — direct connection IP.

    IMPORTANT: This implementation assumes Nginx/Cloudflare is always in front.
    If the API can be reached directly (bypassing the reverse proxy), rate-limit
    bypass via spoofed headers is possible.  Mitigation: restrict network access
    to the API port at the infrastructure level (firewall / security group).
    """
    # Prefer X-Real-IP (set by Nginx's proxy_set_header).
    real_ip = request.headers.get("X-Real-IP", "").strip()
    if real_ip:
        return real_ip

    # Fall back to X-Forwarded-For — take the rightmost untrusted IP.
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        # Per RFC 7239: client, proxy1, proxy2, ...
        # The rightmost address that is NOT a private/reserved IP is the
        # true client.  For simplicity, take the last entry (which is the
        # the proxy's view of the client IP).
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            return parts[-1]

    if request.client:
        return request.client.host
    return "unknown"


# ── Named rate-limit policies ────────────────────────────────────────────────
# Each policy is a thin dependency that calls check_rate_limit with
# endpoint-appropriate limits.  Import and use in router declarations:
#
#   @router.post("/auth/verify-token", dependencies=[Depends(rate_limit_verify_token)])
#
@dataclass(frozen=True)
class _RateLimitPolicy:
    limit: int
    window: int
    key_prefix: str


def _make_policy_dependency(policy: _RateLimitPolicy):
    """Create a FastAPI dependency from a rate-limit policy."""

    async def dependency(request: Request) -> None:
        redis = get_redis_pool()
        await check_rate_limit(
            request,
            redis,
            limit=policy.limit,
            window=policy.window,
            key_prefix=policy.key_prefix,
        )

    return dependency


# ── Auth-specific policies ───────────────────────────────────────────────────
# verify-token: called on every page load — generous limit
rate_limit_verify_token = _make_policy_dependency(
    _RateLimitPolicy(limit=60, window=60, key_prefix="rl:auth:verify")
)
# logout: user-initiated, moderate frequency
rate_limit_logout = _make_policy_dependency(
    _RateLimitPolicy(limit=20, window=60, key_prefix="rl:auth:logout")
)
# force-logout: admin action, low frequency
rate_limit_force_logout = _make_policy_dependency(
    _RateLimitPolicy(limit=10, window=60, key_prefix="rl:auth:force-logout")
)
# 2FA setup: generates TOTP secrets — sensitive
rate_limit_2fa_setup = _make_policy_dependency(
    _RateLimitPolicy(limit=5, window=60, key_prefix="rl:auth:2fa-setup")
)
# 2FA verify: activates 2FA — brute-force target
rate_limit_2fa_verify = _make_policy_dependency(
    _RateLimitPolicy(limit=5, window=60, key_prefix="rl:auth:2fa-verify")
)
# 2FA validate: login TOTP check — most sensitive brute-force target
rate_limit_2fa_validate = _make_policy_dependency(
    _RateLimitPolicy(limit=5, window=60, key_prefix="rl:auth:2fa-validate")
)
# Dev login: dev-only but still needs brute-force protection
rate_limit_dev_login = _make_policy_dependency(
    _RateLimitPolicy(limit=5, window=60, key_prefix="rl:auth:dev-login")
)


# ── Generic policies (kept for non-auth endpoints) ───────────────────────────
async def rate_limit_auth(request: Request) -> None:
    """Legacy dependency — prefer named policies above for new code."""
    redis = get_redis_pool()
    await check_rate_limit(
        request,
        redis,
        limit=settings.RATE_LIMIT_AUTH,
        window=60,
        key_prefix="rl:auth",
    )


async def rate_limit_upload(request: Request) -> None:
    """Dependency for file upload endpoints."""
    redis = get_redis_pool()
    await check_rate_limit(
        request,
        redis,
        limit=settings.RATE_LIMIT_UPLOAD,
        window=60,
        key_prefix="rl:upload",
    )


async def rate_limit_webhook(request: Request) -> None:
    """Dependency for webhook endpoints."""
    redis = get_redis_pool()
    await check_rate_limit(
        request,
        redis,
        limit=settings.RATE_LIMIT_WEBHOOK,
        window=60,
        key_prefix="rl:webhook",
    )


async def rate_limit_enquiry(request: Request) -> None:
    """Dependency for public enquiry submission — 5 requests per minute per IP."""
    redis = get_redis_pool()
    await check_rate_limit(
        request,
        redis,
        limit=5,
        window=60,
        key_prefix="rl:enquiry",
    )

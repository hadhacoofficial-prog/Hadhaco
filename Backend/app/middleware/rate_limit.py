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

import ipaddress
import time
from dataclasses import dataclass

import redis.asyncio as aioredis
import structlog
from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.redis import get_redis_pool

log = structlog.get_logger(__name__)


def _is_trusted_proxy_peer(peer_ip: str) -> bool:
    """
    True if *peer_ip* — the actual TCP connection's source address, not
    anything header-supplied — is allowed to set X-Real-IP/X-Forwarded-For.

    Private/loopback ranges are always trusted (covers the common case: a
    reverse proxy on the same Docker network or internal VPC) plus anything
    explicitly listed in TRUSTED_PROXY_IPS (e.g. a public-IP load balancer).
    If the request's direct peer isn't trusted, forwarding headers are
    attacker-controlled input and must be ignored — otherwise any client
    that can reach the API directly could spoof its own rate-limit key,
    audit-log IP, and new-device/location detection.
    """
    if peer_ip in settings.trusted_proxy_ips_list:
        return True
    try:
        addr = ipaddress.ip_address(peer_ip)
    except ValueError:
        return False
    return addr.is_private or addr.is_loopback


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
    ip = get_client_ip(request)
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
        log.warning(
            "rate_limit_exceeded",
            key_prefix=key_prefix,
            path=path,
            ip=ip,
            count=count,
            limit=limit,
        )
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


def get_client_ip(request: Request) -> str:
    """
    Extract the real client IP.

    X-Real-IP/X-Forwarded-For are trusted *only* when the request's direct
    TCP peer is itself a trusted reverse proxy (private/loopback range, or
    explicitly listed in TRUSTED_PROXY_IPS) — see _is_trusted_proxy_peer.
    If the API is reachable directly (bypassing the reverse proxy) from an
    untrusted address, these headers are attacker-controlled input and are
    ignored entirely, falling back to the actual socket peer address.

    Strategy once the peer is trusted:
    1. X-Real-IP — set by Nginx, always the true client IP (preferred).
    2. X-Forwarded-For — take the *last* entry (the proxy's own view of the
       client, per RFC 7239: client, proxy1, proxy2, ...).
    3. request.client.host — direct connection IP.
    """
    direct_ip = request.client.host if request.client else "unknown"

    if not _is_trusted_proxy_peer(direct_ip):
        return direct_ip

    # Prefer X-Real-IP (set by Nginx's proxy_set_header).
    real_ip = request.headers.get("X-Real-IP", "").strip()
    if real_ip:
        return real_ip

    # Fall back to X-Forwarded-For — take the rightmost entry.
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            return parts[-1]

    return direct_ip


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
# Admin session list/revoke: security-dashboard traffic, moderate frequency.
rate_limit_admin_sessions = _make_policy_dependency(
    _RateLimitPolicy(limit=30, window=60, key_prefix="rl:auth:admin-sessions")
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

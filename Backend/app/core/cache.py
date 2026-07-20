"""
Reusable caching helpers for the Hadha storefront.

Provides:
- CacheHelper: cache-aside pattern with TTL, tags, invalidation
- ETag / Cache-Control / Last-Modified header helpers
- Graceful fallback to DB when Redis is unavailable
- Stale-While-Revalidate (SWR) + request coalescing
- Transparent zlib compression for large cached values
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import zlib
from collections.abc import Callable
from typing import Any

import redis.asyncio as aioredis
from fastapi import Request, Response
from pydantic import BaseModel

from app.core.redis import (
    bust_product_list_cache,
    mark_redis_error,
    redis_available,
    safe_redis_delete,
    safe_redis_get,
    safe_redis_setex,
)

# ── Transparent compression for SWR cache values ────────────────────────────
# Large payloads (product lists, CMS homepages) are compressed with zlib
# before storing in Redis, reducing memory usage by 5-8x for repetitive JSON.
#
# Format: if the first byte is b"\\x01", the rest is zlib-compressed data.
# Otherwise the value is plain JSON (backward-compatible with existing data).

_COMPRESS_THRESHOLD_BYTES = 2048  # Only compress payloads >2KB
_ZLIB_LEVEL = 6  # Balanced speed/ratio (1-9; 6 is ~70% of max ratio at 2x speed)


def _compress_value(payload: str) -> str:
    """Compress a payload string if it exceeds the threshold."""
    raw = payload.encode("utf-8")
    if len(raw) <= _COMPRESS_THRESHOLD_BYTES:
        return payload
    compressed = zlib.compress(raw, level=_ZLIB_LEVEL)
    # Only use compression if it actually saves space
    if len(compressed) >= len(raw):
        return payload
    # Record compression savings for observability
    try:
        from app.core.profiling import profiler

        profiler.record_cache_compression(len(raw) - len(compressed))
    except Exception:
        pass
    # Prefix with \x01 to mark as compressed
    return "\x01" + compressed.decode("latin-1")


def _decompress_value(raw: str) -> str:
    """Decompress a value if it was compressed (starts with \\x01 prefix)."""
    if not raw or raw[0] != "\x01":
        return raw
    compressed = raw[1:].encode("latin-1")
    try:
        return zlib.decompress(compressed).decode("utf-8")
    except zlib.error:
        return raw  # Corrupted — return as-is, caller handles


# ── Generic serialization ─────────────────────────────────────────────────────


def _safe_json_dumps(obj: Any) -> str:
    """Serialize to JSON string. Handles Pydantic, dicts, lists, primitives."""
    if isinstance(obj, BaseModel):
        return obj.model_dump_json()
    try:
        return json.dumps(obj)
    except (TypeError, ValueError):
        return json.dumps(obj, default=str)


# ── Cache key builders ────────────────────────────────────────────────────────


def make_cache_key(prefix: str, **params: Any) -> str:
    """Build a deterministic cache key from a prefix and query parameters."""
    filtered = {k: v for k, v in params.items() if v is not None}
    if not filtered:
        return prefix
    h = hashlib.sha256(
        json.dumps(filtered, sort_keys=True, default=str).encode()
    ).hexdigest()[:12]
    return f"{prefix}:{h}"


def make_etag(data: str | bytes) -> str:
    """Generate an ETag from response content."""
    if isinstance(data, str):
        data = data.encode()
    return f'"{hashlib.md5(data, usedforsecurity=False).hexdigest()}"'


# ── Cache TTL constants ──────────────────────────────────────────────────────

# Category A — Read-only, cache first (public storefront)
TTL_PRODUCT_DETAIL = 600  # 10 min
TTL_PRODUCT_LIST = 300  # 5 min (already in catalog router)
TTL_CATEGORY_TREE = 3600  # 1 hour
TTL_CATEGORY_NAVBAR = 86400  # 24 hours (already in categories router)
TTL_CATEGORY_NAVIGATION = 86400  # 24 hours (already in categories router)
TTL_COLLECTION_LIST = 900  # 15 min (already in collections router)
TTL_COLLECTION_DETAIL = 900  # 15 min
TTL_CMS_HOMEPAGE = 86400  # 24 hours (already in CMS service)
TTL_CMS_HOME_LEGACY = 3600  # 1 hour
TTL_CMS_PAGE = 3600  # 1 hour
TTL_SEO_PAGE = 3600  # 1 hour
TTL_SITEMAP = 3600  # 1 hour
TTL_SEARCH_RESULTS = 120  # 2 min
TTL_AUTOCOMPLETE = 60  # 1 min
TTL_TRENDING = 300  # 5 min
TTL_REVIEW_LIST = 300  # 5 min
TTL_REVIEW_SUMMARY = 600  # 10 min
TTL_FEATURE_FLAG = 300  # 5 min
TTL_SHIPPING_RATES = 600  # 10 min
TTL_RATINGS_AGGREGATE = 600  # 10 min (product ratings stored on product row)

# Category B — Cache with invalidation (shorter TTLs)
TTL_SEARCH_RESULTS_B = 120  # 2 min
TTL_COLLECTION_DETAIL_B = 300  # 5 min
TTL_CATEGORY_TREE_B = 600  # 10 min

# Cache key prefixes
PREFIX_PRODUCT_DETAIL = "product:detail:v1"
PREFIX_PRODUCT_LIST = "products:list:v1"
PREFIX_CATEGORY_TREE = "categories:tree:v1"
PREFIX_COLLECTION_DETAIL = "collection:detail:v1"
PREFIX_CMS_HOME_LEGACY = "cms:home:v1"
PREFIX_CMS_PAGE = "cms:page:v1"
PREFIX_SEO_PAGE = "seo:page:v1"
PREFIX_SITEMAP = "sitemap:v1"
PREFIX_SEARCH = "search:v1"
PREFIX_AUTOCOMPLETE = "autocomplete:v1"
PREFIX_TRENDING = "trending:v1"
PREFIX_REVIEW_LIST = "reviews:list:v1"
PREFIX_REVIEW_SUMMARY = "reviews:summary:v1"
PREFIX_FEATURE_FLAG = "flag:v1"
PREFIX_SHIPPING_RATES = "shipping:rates:v1"


# ── Cache invalidation helpers ────────────────────────────────────────────────


async def bust_product_detail_cache(
    redis: aioredis.Redis, slug: str | None = None, product_id: str | None = None
) -> None:
    """Invalidate cached product detail page."""
    if slug:
        await safe_redis_delete(redis, f"{PREFIX_PRODUCT_DETAIL}:{slug}")
    if product_id:
        # Also try to invalidate by ID (some callers may only have the ID)
        await safe_redis_delete(redis, f"{PREFIX_PRODUCT_DETAIL}:{product_id}")


async def bust_collection_detail_cache(
    redis: aioredis.Redis, slug: str | None = None
) -> None:
    """Invalidate cached collection detail page."""
    if slug:
        await safe_redis_delete(redis, f"{PREFIX_COLLECTION_DETAIL}:{slug}")


async def bust_cms_page_cache(redis: aioredis.Redis, slug: str) -> None:
    """Invalidate cached CMS page."""
    await safe_redis_delete(redis, f"{PREFIX_CMS_PAGE}:{slug}")


async def bust_seo_page_cache(redis: aioredis.Redis, path: str) -> None:
    """Invalidate cached SEO page data."""
    await safe_redis_delete(redis, f"{PREFIX_SEO_PAGE}:{path}")


async def bust_sitemap_cache(redis: aioredis.Redis) -> None:
    """Invalidate cached sitemap."""
    await safe_redis_delete(redis, PREFIX_SITEMAP)


async def bust_search_cache(redis: aioredis.Redis) -> None:
    """Invalidate search-related caches (autocomplete, trending)."""
    if not redis_available():
        return
    try:
        # Delete autocomplete cache keys
        keys: list[str] = [
            str(key)
            async for key in redis.scan_iter(
                match=f"{PREFIX_AUTOCOMPLETE}:*", count=200
            )
        ]
        # Delete trending cache
        keys.append(PREFIX_TRENDING)
        # Delete search result cache keys
        search_keys = [
            str(key)
            async for key in redis.scan_iter(match=f"{PREFIX_SEARCH}:*", count=200)
        ]
        keys.extend(search_keys)
        if keys:
            await safe_redis_delete(redis, *keys)
    except Exception:
        mark_redis_error()


async def bust_review_cache(redis: aioredis.Redis, product_id: str) -> None:
    """Invalidate review caches for a product."""
    await safe_redis_delete(
        redis,
        f"{PREFIX_REVIEW_LIST}:{product_id}",
        f"{PREFIX_REVIEW_SUMMARY}:{product_id}",
    )


async def bust_feature_flag_cache(redis: aioredis.Redis, key: str) -> None:
    """Invalidate cached feature flag."""
    await safe_redis_delete(redis, f"{PREFIX_FEATURE_FLAG}:{key}")


async def bust_category_tree_cache(redis: aioredis.Redis) -> None:
    """Invalidate category tree cache."""
    if not redis_available():
        return
    try:
        keys = [
            str(key)
            async for key in redis.scan_iter(
                match=f"{PREFIX_CATEGORY_TREE}*", count=100
            )
        ]
        if keys:
            await safe_redis_delete(redis, *keys)
    except Exception:
        mark_redis_error()


async def bust_all_product_caches(redis: aioredis.Redis) -> None:
    """Bust all product-related caches (list + detail + search + sitemap)."""
    await bust_product_list_cache(redis)
    if not redis_available():
        return
    try:
        detail_keys = [
            str(key)
            async for key in redis.scan_iter(
                match=f"{PREFIX_PRODUCT_DETAIL}:*", count=500
            )
        ]
        if detail_keys:
            await safe_redis_delete(redis, *detail_keys)
    except Exception:
        mark_redis_error()
    await bust_sitemap_cache(redis)
    await bust_search_cache(redis)


async def bust_all_caches(redis: aioredis.Redis) -> None:
    """Full cache invalidation — use sparingly (e.g. admin "purge all")."""
    if not redis_available():
        return
    try:
        await redis.flushdb()
    except Exception:
        mark_redis_error()


# ── HTTP cache header helpers ────────────────────────────────────────────────


def add_cache_headers(
    response: Response,
    max_age: int,
    *,
    stale_while_revalidate: int = 0,
    stale_if_error: int = 0,
    private: bool = False,
    immutable: bool = False,
    etag: str | None = None,
    last_modified: str | None = None,
    vary: str = "Accept, Authorization",
) -> None:
    """Add Cache-Control and optional ETag/Last-Modified headers to a response."""
    directives = []
    if private:
        directives.append("private")
    else:
        directives.append("public")
    directives.append(f"max-age={max_age}")
    if stale_while_revalidate:
        directives.append(f"stale-while-revalidate={stale_while_revalidate}")
    if stale_if_error:
        directives.append(f"stale-if-error={stale_if_error}")
    if immutable:
        directives.append("immutable")
    response.headers["Cache-Control"] = ", ".join(directives)
    if etag:
        response.headers["ETag"] = etag
    if last_modified:
        response.headers["Last-Modified"] = last_modified
    if vary:
        response.headers["Vary"] = vary


def check_not_modified(request: Request, etag: str | None = None) -> bool:
    """Check If-None-Match / If-Modified-Since headers for conditional GET."""
    if etag:
        if_none_match = request.headers.get("if-none-match")
        if if_none_match and if_none_match.strip() == etag:
            return True
    # Last-Modified / If-Modified-Since can be added per-endpoint when needed.
    return False


def not_modified_response() -> Response:
    """Return a 304 Not Modified response."""
    return Response(status_code=304)


# ── Cache-aside helper for storefront reads ──────────────────────────────────


async def cache_get_or_fetch(
    redis: aioredis.Redis,
    cache_key: str,
    ttl: int,
    fetch_fn: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Cache-aside pattern: try Redis first, fall back to fetch_fn.

    Returns (data, from_cache: bool).
    """
    from app.core.profiling import profiler

    cached = await safe_redis_get(redis, cache_key)
    if cached:
        profiler.record_cache_hit()
        return json.loads(cached), True

    profiler.record_cache_miss()
    data = await fetch_fn(*args, **kwargs)
    # Cache the serialized result
    serialized = json.dumps(data, default=str)
    await safe_redis_setex(redis, cache_key, ttl, serialized)
    return data, False


# ── Stale-While-Revalidate + Request Coalescing ──────────────────────────────
#
# SWR solves two problems:
# 1. **Stampede prevention**: When a popular cache key expires, many concurrent
#    requests hit the DB simultaneously.  SWR serves the stale response while a
#    single background refresh populates the new value.
# 2. **Zero-downtime revalidation**: Users never see a slow DB-backed response;
#    they always get a fast cached response (stale or fresh).
#
# Request coalescing ensures that even if multiple coroutines start a refresh
# at the same time, only ONE actually hits the database — the others await
# the first result.

_coalesce_locks: dict[str, asyncio.Lock] = {}
_coalesce_lock_last_used: dict[str, float] = {}
_LOCK_IDLE_TTL: float = 300.0  # 5 minutes


def _get_coalesce_lock(key: str) -> asyncio.Lock:
    """Return (and lazily create) a per-key asyncio lock for coalescing."""
    _coalesce_lock_last_used[key] = time.monotonic()
    lock = _coalesce_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _coalesce_locks[key] = lock
    return lock


def _evict_stale_locks() -> None:
    now = time.monotonic()
    stale = [
        k
        for k, last_used in _coalesce_lock_last_used.items()
        if now - last_used > _LOCK_IDLE_TTL and k in _coalesce_locks
    ]
    for k in stale:
        lock = _coalesce_locks.get(k)
        if lock is not None and not lock.locked():
            del _coalesce_locks[k]
            del _coalesce_lock_last_used[k]


_MAX_SWR_TASKS = 32
_swr_refresh_tasks: set[asyncio.Task[None]] = set()


def _on_swr_task_done(task: asyncio.Task[None]) -> None:
    _swr_refresh_tasks.discard(task)


def _maybe_start_swr_refresh(
    redis: aioredis.Redis,
    cache_key: str,
    ttl: int,
    swr_window: int,
    fetch_fn: Callable[..., Any],
    args: tuple,
    kwargs: dict,
) -> None:
    if len(_swr_refresh_tasks) >= _MAX_SWR_TASKS:
        return
    lock = _get_coalesce_lock(cache_key)
    if lock.locked():
        return
    task = asyncio.ensure_future(
        _swr_refresh(redis, cache_key, ttl, swr_window, fetch_fn, args, kwargs)
    )
    _swr_refresh_tasks.add(task)
    task.add_done_callback(_on_swr_task_done)


async def cache_swr(
    redis: aioredis.Redis,
    cache_key: str,
    ttl: int,
    swr_window: int,
    fetch_fn: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Cache-aside with Stale-While-Revalidate and request coalescing.

    Parameters
    ----------
    redis : Redis connection
    cache_key : Redis key for the cached value
    ttl : Seconds after which the value is considered "soft expired"
    swr_window : Extra seconds beyond TTL where stale data is still served
                 while a background refresh runs.  After ttl + swr_window,
                 the value is a hard miss and callers block on fetch_fn.
    fetch_fn : Async callable that returns the fresh value on cache miss
    *args, **kwargs : forwarded to fetch_fn

    Returns the cached or freshly-fetched value.  The first caller on a
    miss blocks on fetch_fn; concurrent callers for the same key await
    the same lock and get the same result (request coalescing).
    """
    from app.core.profiling import profiler

    _evict_stale_locks()

    now = time.time()
    cached_raw = await safe_redis_get(redis, cache_key)

    if cached_raw:
        # Decompress if the value was compressed by the write path.
        cached_raw = _decompress_value(cached_raw)
        try:
            wrapper = json.loads(cached_raw)
            data = wrapper["d"]
            ts = wrapper["t"]
        except (json.JSONDecodeError, KeyError, TypeError):
            # Legacy plain-value cache entries (no wrapper) — treat as fresh
            profiler.record_cache_hit()
            return json.loads(cached_raw)

        age = now - ts
        if age < ttl:
            # Fresh — return immediately
            profiler.record_cache_hit()
            return data
        elif age < ttl + swr_window:
            # Soft-expired: return stale data, trigger background refresh.
            # Only one coroutine refreshes (coalesced via lock).
            profiler.record_cache_hit()
            _maybe_start_swr_refresh(
                redis, cache_key, ttl, swr_window, fetch_fn, args, kwargs
            )
            return data
        # else: hard miss — fall through to blocking fetch below

    profiler.record_cache_miss()

    # Cache miss or hard-expired: coalesce concurrent requests
    lock = _get_coalesce_lock(cache_key)
    async with lock:
        # Double-check: another coroutine may have refreshed while we waited
        cached_raw = await safe_redis_get(redis, cache_key)
        if cached_raw:
            cached_raw = _decompress_value(cached_raw)
            try:
                wrapper = json.loads(cached_raw)
                data = wrapper["d"]
                ts = wrapper["t"]
                if (now - ts) < ttl:
                    profiler.record_cache_hit()
                    return data
            except (json.JSONDecodeError, KeyError, TypeError):
                profiler.record_cache_hit()
                return json.loads(cached_raw)

        data = await fetch_fn(*args, **kwargs)
        wrapper = _safe_json_dumps({"d": data, "t": time.time()})
        # Compress large payloads transparently before storing in Redis.
        compressed = _compress_value(wrapper)
        # Store with hard TTL = ttl + swr_window so the stale value is
        # still in Redis during the SWR window (readable via safe_redis_get).
        await safe_redis_setex(redis, cache_key, ttl + swr_window, compressed)
        return data


async def _swr_refresh(
    redis: aioredis.Redis,
    cache_key: str,
    ttl: int,
    swr_window: int,
    fetch_fn: Callable[..., Any],
    args: tuple,
    kwargs: dict,
) -> None:
    """Background refresh — runs as a fire-and-forget task."""
    lock = _get_coalesce_lock(cache_key)
    if lock.locked():
        # Another coroutine is already refreshing — skip
        return
    async with lock:
        try:
            data = await fetch_fn(*args, **kwargs)
            wrapper = _safe_json_dumps({"d": data, "t": time.time()})
            compressed = _compress_value(wrapper)
            await safe_redis_setex(redis, cache_key, ttl + swr_window, compressed)
        except Exception:
            # Refresh failed — stale data remains valid until hard expiry.
            # Log but don't crash the background task.
            pass

"""Cache warming — pre-populates Redis for high-traffic storefront endpoints.

Strategy (Phase 2 redesign):
  1. **Startup-only** — run once at process start; SWR handles refresh after.
  2. **Distributed lock** — only one worker warms at a time (SET NX).
  3. **Invalidation hooks** — bust_*_cache functions can optionally re-warm
     after invalidation so the next visitor gets a warm cache.

Uses direct service/DB calls instead of HTTP requests, eliminating
server-dependency and network overhead.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Callable, Coroutine
from typing import Any

import redis.asyncio as aioredis
import structlog

logger = structlog.get_logger("cache.warmer")

# Distributed-lock key and TTL (seconds).
# Only one worker warms at a time; the lock expires after 5 minutes as a
# safety net in case the holder crashes mid-warm.
_WARM_LOCK_KEY = "cache:warmer:lock"
_WARM_LOCK_TTL = 300
# Set (not deleted) at the start of each periodic pass so only one worker in
# the cluster runs a pass per interval.
_WARM_TICK_KEY = "cache:warmer:tick"

# How long to wait between re-warm attempts triggered by invalidation.
# Prevents burst re-warming when multiple invalidations arrive in a short window.
_MIN_REWARM_INTERVAL = 10  # seconds
_last_warm_at: float = 0.0

# Redis expiry for product-list / facets entries: soft TTL + SWR window, the
# same total cache_swr stores them with (see catalog/router.py).
_PRODUCT_LIST_HARD_TTL = 300 + 3600


def _product_list_cache_key(**params: object) -> str:
    """Build product list cache key — mirrors the catalog router's logic."""
    h = hashlib.sha256(
        json.dumps(params, sort_keys=True, default=str).encode()
    ).hexdigest()[:12]
    return f"products:list:v1:{h}"


async def _warm_one(
    name: str,
    cache_key: str,
    fetch_fn: Callable[..., Coroutine[Any, Any, Any]],
    ttl: int,
    redis: aioredis.Redis,
    *,
    wrap_swr: bool = True,
    hard_ttl: int | None = None,
) -> bool:
    """Warm a single cache entry.

    *ttl* drives the freshness skip; *hard_ttl* (default: *ttl*) is the Redis
    expiry — pass ``ttl + swr_window`` to match what ``cache_swr`` stores.

    Always re-warms (skips only if the current value was written less than
    half the TTL ago — this avoids redundant warming under high traffic
    while still refreshing stale entries).

    Returns True if warmed, False if skipped.
    """
    from app.core.cache import _compress_value, _decompress_value, _safe_json_dumps
    from app.core.redis import safe_redis_get, safe_redis_setex

    try:
        existing = await safe_redis_get(redis, cache_key)
        if existing and not wrap_swr:
            # Raw (non-SWR) entries carry no timestamp, so judge freshness by
            # the Redis TTL left. Without this they were regenerated on every
            # tick (trending + sitemap showed warm_ok 12/12 ticks in prod logs).
            try:
                left = int(await asyncio.wait_for(redis.ttl(cache_key), timeout=0.5))
            except Exception:
                left = -1
            total = hard_ttl or ttl
            if left > 0 and (total - left) < ttl * 0.5:
                logger.debug("warm_skip", endpoint=name, cache_key=cache_key)
                return False
        if existing:
            # Decompress if needed, then parse the SWR wrapper to check age.
            existing = _decompress_value(existing)
            try:
                wrapper = json.loads(existing)
                age = time.time() - wrapper.get("t", 0)
                if age < ttl * 0.5:
                    logger.debug(
                        "warm_skip",
                        endpoint=name,
                        cache_key=cache_key,
                        age_s=round(age, 1),
                    )
                    return False
            except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
                pass  # unparseable or non-SWR raw value — re-warm anyway

        raw = await fetch_fn()
        if wrap_swr:
            payload = _safe_json_dumps({"d": raw, "t": time.time()})
        else:
            payload = raw if isinstance(raw, str) else _safe_json_dumps(raw)
        compressed = _compress_value(payload)
        await safe_redis_setex(redis, cache_key, hard_ttl or ttl, compressed)
        logger.info("warm_ok", endpoint=name, cache_key=cache_key)
        return True
    except Exception as exc:
        logger.warning("warm_error", endpoint=name, error=str(exc))
        return False


def _facets_cache_key(spec_params: dict[str, Any]) -> str:
    """Build the product-facets cache key — mirrors the catalog router."""
    h = hashlib.sha256(
        json.dumps(spec_params, sort_keys=True, default=str).encode()
    ).hexdigest()[:12]
    return f"products:list:v1:facets:{h}"


async def _warm_default_facets(redis: aioredis.Redis) -> bool:
    """Warm the unfiltered facets entry (``GET /products/facets`` with no params)."""
    from app.core.database import AsyncSessionLocal
    from app.modules.catalog.repository import ProductFilterSpec
    from app.modules.catalog.service import CatalogService

    spec = ProductFilterSpec(status="active")

    async def _fetch_facets() -> dict:
        async with AsyncSessionLocal() as db:
            facets = await CatalogService().get_facets(db, spec)
            return facets.model_dump(mode="json")

    return await _warm_one(
        "products:facets",
        _facets_cache_key(spec.cache_params()),
        _fetch_facets,
        600,
        redis,
        hard_ttl=_PRODUCT_LIST_HARD_TTL,
    )


async def warm_once(
    *, force: bool = False, rate_limit_seconds: int | None = None
) -> dict[str, object]:
    """Populate Redis for each warm-target endpoint.

    Uses a Redis distributed lock so only one worker warms at a time.
    Pass *force=True* to bypass the freshness check and always re-warm.
    *rate_limit_seconds* makes the pass cluster-wide at-most-once per window:
    the lock above is released when a pass ends, so with 2 uvicorn workers
    each looping on the same cadence both used to run back to back.
    """
    from app.core.redis import get_redis_pool, redis_available

    if not redis_available():
        logger.warning("warm_skip_all", reason="redis_unavailable")
        return {"ok": 0, "fail": 0, "skipped": 0, "elapsed_ms": 0}

    redis = get_redis_pool()

    if rate_limit_seconds:
        try:
            first = await asyncio.wait_for(
                redis.set(_WARM_TICK_KEY, "1", nx=True, ex=rate_limit_seconds),
                timeout=0.5,
            )
            if not first:
                return {"ok": 0, "fail": 0, "skipped": 0, "elapsed_ms": 0}
        except Exception:
            pass  # Redis hiccup - fall through to the normal lock

    # ── Distributed lock ─────────────────────────────────────────────────
    lock_key = _WARM_LOCK_KEY
    try:
        acquired = await asyncio.wait_for(
            redis.set(lock_key, "1", nx=True, ex=_WARM_LOCK_TTL),
            timeout=0.5,
        )
        if not acquired and not force:
            logger.info("warm_skip_all", reason="another_worker_warming")
            return {"ok": 0, "fail": 0, "skipped": 0, "elapsed_ms": 0}
    except Exception:
        pass  # Redis down or timeout — proceed anyway (best-effort)

    t0 = time.perf_counter()
    ok_count = 0
    fail_count = 0
    skip_count = 0

    try:
        skip_count, ok_count, fail_count = await _warm_all_targets(redis, force)
    finally:
        # Release the lock
        try:
            await asyncio.wait_for(redis.delete(lock_key), timeout=0.5)
        except Exception:
            pass

    elapsed = (time.perf_counter() - t0) * 1000
    logger.info(
        "cache_warm_done",
        endpoints_ok=ok_count,
        endpoints_fail=fail_count,
        endpoints_skipped=skip_count,
        elapsed_ms=round(elapsed, 1),
    )
    return {
        "ok": ok_count,
        "fail": fail_count,
        "skipped": skip_count,
        "elapsed_ms": round(elapsed, 1),
    }


async def _warm_all_targets(redis: aioredis.Redis, force: bool) -> tuple[int, int, int]:
    """Warm all targets. Returns (skip_count, ok_count, fail_count)."""
    skip_count = 0
    ok_count = 0
    fail_count = 0

    async def _track(result: bool) -> None:
        nonlocal ok_count, skip_count, fail_count
        if result:
            ok_count += 1
        else:
            skip_count += 1

    # 1. Product list — default page (page=1, page_size=20, active only)
    try:
        from app.modules.catalog.service import CatalogService

        async def _warm_products() -> dict:
            from app.core.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                result = await CatalogService().list_products(
                    db, page=1, page_size=20, status="active"
                )
                return result.model_dump(mode="json")

        from app.modules.catalog.repository import ProductFilterSpec

        cache_key = _product_list_cache_key(
            page=1,
            page_size=20,
            sort_by="created_at",
            sort_dir="desc",
            include_collections=True,
            **ProductFilterSpec(status="active").cache_params(),
        )
        await _track(
            await _warm_one(
                "products",
                cache_key,
                _warm_products,
                600,
                redis,
                hard_ttl=_PRODUCT_LIST_HARD_TTL,
            )
        )
    except Exception as exc:
        fail_count += 1
        logger.warning("warm_error", endpoint="products", error=str(exc))

    # 1b. Default (unfiltered) product facets — the filter panel requests this
    # on every /products page load.
    try:
        await _track(await _warm_default_facets(redis))
    except Exception as exc:
        fail_count += 1
        logger.warning("warm_error", endpoint="products:facets", error=str(exc))

    # 2. Categories tree
    try:
        from app.modules.categories.service import CategoryService

        async def _warm_category_tree() -> list[dict]:
            from app.core.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                result = await CategoryService().get_tree(db)
                return [n.model_dump(mode="json") for n in result]

        await _track(
            await _warm_one(
                "categories:tree",
                "categories:tree:v1:all",
                _warm_category_tree,
                7200,
                redis,
            )
        )
    except Exception as exc:
        fail_count += 1
        logger.warning("warm_error", endpoint="categories:tree", error=str(exc))

    # 3. Categories navbar
    try:
        from app.modules.categories.service import CategoryService

        async def _warm_navbar() -> dict:
            from app.core.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                result = await CategoryService().get_navbar(db)
                return result.model_dump(mode="json")

        await _track(
            await _warm_one(
                "categories:navbar",
                "categories:navbar:v1",
                _warm_navbar,
                172_800,
                redis,
            )
        )
    except Exception as exc:
        fail_count += 1
        logger.warning("warm_error", endpoint="categories:navbar", error=str(exc))

    # 4. Categories navigation
    try:
        from app.modules.categories.service import CategoryService

        async def _warm_navigation() -> dict:
            from app.core.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                result = await CategoryService().get_navigation(db)
                return result.model_dump(mode="json")

        await _track(
            await _warm_one(
                "navigation:categories",
                "navigation:categories:v2",
                _warm_navigation,
                172_800,
                redis,
            )
        )
    except Exception as exc:
        fail_count += 1
        logger.warning("warm_error", endpoint="navigation:categories", error=str(exc))

    # 5. Collections list
    try:
        from app.modules.collections.service import CollectionService

        async def _warm_collections() -> list[dict]:
            from app.core.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                result = await CollectionService().list_active(db)
                return [c.model_dump(mode="json") for c in result]

        await _track(
            await _warm_one(
                "collections",
                "collections:list:v1",
                _warm_collections,
                1800,
                redis,
            )
        )
    except Exception as exc:
        fail_count += 1
        logger.warning("warm_error", endpoint="collections", error=str(exc))

    # 6. CMS home (legacy)
    try:
        from app.modules.cms.service import CMSService

        async def _warm_cms_home() -> dict:
            from app.core.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                data = await CMSService().get_home_data(db)
                return {
                    "success": True,
                    "code": "CMS_HOME_FETCHED",
                    "message": "Home page data fetched",
                    "data": data,
                }

        await _track(
            await _warm_one("cms:home", "cms:home:v1", _warm_cms_home, 7200, redis)
        )
    except Exception as exc:
        fail_count += 1
        logger.warning("warm_error", endpoint="cms:home", error=str(exc))

    # 7. CMS homepage (new rich endpoint)
    try:
        from app.modules.cms.schemas import HomepageDataOut
        from app.modules.cms.service import CMSService

        async def _warm_cms_homepage() -> dict:
            from app.core.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                data = await CMSService()._build_homepage(db)
                from app.common.response_codes import ResponseCode
                from app.common.responses import ok

                return ok(
                    HomepageDataOut(**data),
                    ResponseCode.CMS_HOMEPAGE_FETCHED,
                    "Homepage data fetched",
                ).model_dump(mode="json")

        await _track(
            await _warm_one(
                "cms:homepage", "cms:homepage", _warm_cms_homepage, 172_800, redis
            )
        )
    except Exception as exc:
        fail_count += 1
        logger.warning("warm_error", endpoint="cms:homepage", error=str(exc))

    # 8. Search trending
    try:
        from app.core.cache import _safe_json_dumps
        from app.modules.search.service import SearchService

        async def _warm_trending() -> str:
            from app.core.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                result = await SearchService().trending_searches(db, limit=10)
                return _safe_json_dumps(result)

        await _track(
            await _warm_one(
                "search:trending",
                "trending:v1",
                _warm_trending,
                600,
                redis,
                wrap_swr=False,
            )
        )
    except Exception as exc:
        fail_count += 1
        logger.warning("warm_error", endpoint="search:trending", error=str(exc))

    # 9. Sitemap
    try:
        from app.modules.seo.service import SeoService

        async def _warm_sitemap() -> str:
            from app.core.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                return await SeoService().generate_sitemap(db)

        await _track(
            await _warm_one(
                "sitemap", "sitemap:v1", _warm_sitemap, 3600, redis, wrap_swr=False
            )
        )
    except Exception as exc:
        fail_count += 1
        logger.warning("warm_error", endpoint="sitemap", error=str(exc))

    return skip_count, ok_count, fail_count


# SWR only refreshes an entry when a request arrives for it. On a low-traffic
# site an entry idles past its hard TTL (600s for the product list, 1h for the
# sitemap) and the next visitor pays the full DB miss (~1.5s measured in
# production). Re-checking every 150s keeps each target refreshed at its
# soft-TTL boundary (``_warm_one`` skips entries younger than half the hard
# TTL, so most ticks are a cheap Redis GET) and never lets one hard-expire.
_WARM_INTERVAL_SECONDS = 150


async def start_warm_loop() -> None:
    """Warm at startup, then keep targets from hard-expiring while idle.

    The Redis lock in ``warm_once`` makes concurrent workers collapse to one
    warmer per tick. Runs until cancelled at shutdown.
    """
    first = True
    while True:
        try:
            await warm_once(
                rate_limit_seconds=None if first else _WARM_INTERVAL_SECONDS - 15
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("warm_loop_failed", error=str(exc))
        first = False
        await asyncio.sleep(_WARM_INTERVAL_SECONDS)


async def rewarm_after_invalidation(
    targets: list[str] | None = None,
) -> dict[str, object]:
    """Re-warm specific cache keys after invalidation.

    Called by bust_*_cache functions to ensure the next visitor gets a
    warm cache instead of paying the cold-cache penalty.

    *targets* is a list of target names (e.g. ["products", "collections"]).
    If None, re-warms all targets. Rate-limited to prevent burst re-warming.
    """
    global _last_warm_at

    now = time.time()
    if now - _last_warm_at < _MIN_REWARM_INTERVAL:
        logger.debug("rewarm_throttled", interval=now - _last_warm_at)
        return {"throttled": True}

    _last_warm_at = now

    if targets is None:
        return await warm_once(force=True)

    # Targeted re-warming — only refresh specified endpoints.
    from app.core.redis import get_redis_pool, redis_available

    if not redis_available():
        return {"error": "redis_unavailable"}

    redis = get_redis_pool()
    ok_count = 0
    fail_count = 0

    for target in targets:
        try:
            warmed = await _warm_target(redis, target)
            if warmed:
                ok_count += 1
            else:
                fail_count += 1
        except Exception as exc:
            fail_count += 1
            logger.warning("rewarm_error", target=target, error=str(exc))

    return {"ok": ok_count, "fail": fail_count}


async def _warm_target(redis: aioredis.Redis, target: str) -> bool:
    """Warm a specific named target. Returns True on success."""
    if target == "products":
        from app.core.database import AsyncSessionLocal
        from app.modules.catalog.service import CatalogService

        async def _fetch_products() -> dict:
            async with AsyncSessionLocal() as db:
                result = await CatalogService().list_products(
                    db, page=1, page_size=20, status="active"
                )
                return result.model_dump(mode="json")

        from app.modules.catalog.repository import ProductFilterSpec

        cache_key = _product_list_cache_key(
            page=1,
            page_size=20,
            sort_by="created_at",
            sort_dir="desc",
            include_collections=True,
            **ProductFilterSpec(status="active").cache_params(),
        )
        warmed = await _warm_one(
            "products",
            cache_key,
            _fetch_products,
            600,
            redis,
            hard_ttl=_PRODUCT_LIST_HARD_TTL,
        )
        # Facets share the products:list:v1:* prefix, so the same bust that
        # soft-expired the list also soft-expired them.
        facets_warmed = await _warm_default_facets(redis)
        return warmed or facets_warmed

    if target == "collections":
        from app.core.database import AsyncSessionLocal
        from app.modules.collections.service import CollectionService

        async def _fetch_collections() -> list[dict]:
            async with AsyncSessionLocal() as db:
                result = await CollectionService().list_active(db)
                return [c.model_dump(mode="json") for c in result]

        return await _warm_one(
            "collections", "collections:list:v1", _fetch_collections, 1800, redis
        )

    if target == "categories":
        from app.core.database import AsyncSessionLocal
        from app.modules.categories.service import CategoryService

        async def _fetch_categories() -> list[dict]:
            async with AsyncSessionLocal() as db:
                result = await CategoryService().get_tree(db)
                return [n.model_dump(mode="json") for n in result]

        return await _warm_one(
            "categories:tree", "categories:tree:v1:all", _fetch_categories, 7200, redis
        )

    logger.warning("rewarm_unknown_target", target=target)
    return False

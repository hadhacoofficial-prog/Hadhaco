"""Cache warmer: periodic re-warm loop and warmer/router cache-key parity.

Production measurement (2026-10-10): the first request to /products after an
idle period took ~1.5s because warming was startup-only and the list entry
hard-expired (600s) with no traffic to trigger an SWR refresh.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.core.cache_warmer as warmer
from app.modules.catalog.repository import ProductFilterSpec


async def test_warm_loop_rewarms_until_cancelled(monkeypatch):
    warm = AsyncMock(return_value={"ok": 1})
    monkeypatch.setattr(warmer, "warm_once", warm)

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) >= 3:
            raise asyncio.CancelledError

    monkeypatch.setattr(warmer.asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await warmer.start_warm_loop()

    assert warm.await_count == 3
    assert sleeps == [warmer._WARM_INTERVAL_SECONDS] * 3


async def test_warm_loop_survives_a_failed_tick(monkeypatch):
    warm = AsyncMock(side_effect=[RuntimeError("boom"), {"ok": 1}])
    monkeypatch.setattr(warmer, "warm_once", warm)

    calls = 0

    async def fake_sleep(_seconds: float) -> None:
        nonlocal calls
        calls += 1
        if calls >= 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(warmer.asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await warmer.start_warm_loop()

    assert warm.await_count == 2


async def test_warmer_product_key_matches_router_default_request():
    """The default /products request must hit the key the warmer fills."""
    from app.modules.catalog.router import (
        _product_list_cache_key,
        public_product_filters,
    )

    spec = await public_product_filters(
        category_id=None,
        category_slug=None,
        collection_id=None,
        collection_slug=None,
        metal_type=None,
        purity=None,
        gender=None,
        is_featured=None,
        is_new_arrival=None,
        is_best_seller=None,
        min_price=None,
        max_price=None,
        in_stock=None,
        on_sale=None,
        min_rating=None,
        search=None,
        db=MagicMock(),
    )
    router_key = _product_list_cache_key(
        page=1,
        page_size=20,
        sort_by="created_at",
        sort_dir="desc",
        include_collections=True,
        **spec.cache_params(),
    )
    warmer_key = warmer._product_list_cache_key(
        page=1,
        page_size=20,
        sort_by="created_at",
        sort_dir="desc",
        include_collections=True,
        **ProductFilterSpec(status="active").cache_params(),
    )
    assert router_key == warmer_key


def test_facets_key_matches_router_formula():
    params = ProductFilterSpec(status="active").cache_params()
    expected = hashlib.sha256(
        json.dumps(params, sort_keys=True, default=str).encode()
    ).hexdigest()[:12]
    assert warmer._facets_cache_key(params) == f"products:list:v1:facets:{expected}"


def test_swr_window_constants_stay_in_sync():
    """redis.py duplicates the router's SWR constants (import cycle); keep equal."""
    import app.core.redis as redis_mod
    from app.modules.catalog import router

    assert redis_mod._PRODUCT_LIST_SWR_TTL_SECONDS == router._PRODUCT_LIST_TTL
    assert redis_mod._PRODUCT_LIST_SWR_WINDOW_SECONDS == router._PRODUCT_LIST_SWR_WINDOW
    assert warmer._PRODUCT_LIST_HARD_TTL == (
        router._PRODUCT_LIST_TTL + router._PRODUCT_LIST_SWR_WINDOW
    )


async def test_soft_expire_keeps_full_swr_window_in_redis_ttl():
    import time

    import app.core.redis as redis_mod

    stored = json.dumps({"d": {"x": 1}, "t": time.time()})
    r = MagicMock()
    r.get = AsyncMock(return_value=stored)
    r.setex = AsyncMock()

    await redis_mod._soft_expire_swr_entry(
        r, "products:list:v1:abc", ttl_seconds=300, swr_window_seconds=3600
    )

    r.setex.assert_awaited_once()
    assert r.setex.await_args.args[1] == 3900
    rewritten = json.loads(r.setex.await_args.args[2])
    assert time.time() - rewritten["t"] >= 300  # lands in the stale-serve window

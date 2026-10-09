import time
from unittest.mock import AsyncMock

import pytest

from app.core import jwks as jwks_mod
from app.core.jwks import JWKSCache


@pytest.mark.asyncio
async def test_unknown_kid_flood_triggers_at_most_one_fetch():
    cache = JWKSCache(ttl=3600)
    cache._keys = {"good": object()}
    cache._fetched_at = time.monotonic()
    cache._refresh = AsyncMock()  # type: ignore[method-assign]

    for i in range(25):
        with pytest.raises(ValueError):
            await cache.get_key(f"garbage-{i}")

    # One upstream fetch for the first unknown kid; the rest are cooled down.
    assert cache._refresh.await_count == 1


@pytest.mark.asyncio
async def test_known_kid_fast_path_never_fetches_or_locks():
    cache = JWKSCache(ttl=3600)
    key = object()
    cache._keys = {"good": key}
    cache._fetched_at = time.monotonic()
    cache._refresh = AsyncMock()  # type: ignore[method-assign]
    async with cache._lock:  # even with the lock held elsewhere
        assert await cache.get_key("good") is key
    cache._refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_rotation_is_picked_up_after_cooldown(monkeypatch):
    cache = JWKSCache(ttl=3600)
    cache._keys = {"old": object()}
    cache._fetched_at = time.monotonic()
    new_key = object()

    async def fake_refresh():
        cache._keys = {"old": cache._keys["old"], "new": new_key}
        cache._fetched_at = time.monotonic()

    cache._refresh = fake_refresh  # type: ignore[method-assign]
    cache._last_attempt = time.monotonic() - jwks_mod._MIN_REFETCH_INTERVAL - 1
    assert await cache.get_key("new") is new_key

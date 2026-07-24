"""Tests for the soft-bust fix in app.core.redis.bust_product_list_cache.

Production incident (Loki-confirmed, post-CPU-executor-fix deploy): a hard
DELETE turned every product image upload/crop into a cache stampede —
cache_swr's hard-miss path blocks every reader on a synchronous DB
round-trip, so /api/v1/products paid ~2.3-2.7s repeatedly whenever an admin
touched a product's images. The fix rewrites the cache_swr wrapper's
timestamp into the already-soft-expired window instead of deleting the key,
so readers get cache_swr's normal stale-serve + single-coalesced-refresh
path instead.

Uses a minimal in-memory stand-in for the tiny subset of the redis.asyncio
API this code actually calls (get/setex/delete/scan_iter) rather than a
mocked call-count check — this exercises the real GET/SETEX round-trip
cache_swr and bust_product_list_cache both depend on, not just "was this
method called"."""

from __future__ import annotations

import asyncio
import json
import time

import pytest

from app.core.cache import cache_swr
from app.core.redis import bust_product_list_cache, safe_redis_get, safe_redis_setex

pytestmark = pytest.mark.asyncio


class _FakeRedis:
    """In-memory stand-in for the get/setex/delete/scan_iter subset of
    redis.asyncio.Redis used by app.core.cache and app.core.redis. No TTL
    expiry simulation needed — these tests never wait past a TTL boundary,
    only past the cache_swr staleness math, which is timestamp-based, not
    Redis-TTL-based."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self._store[key] = value

    async def delete(self, *keys: str) -> None:
        for k in keys:
            self._store.pop(k, None)

    async def scan_iter(self, match: str, count: int = 500):
        # match is always "products:list:v1:*" in this module — good enough
        # to just prefix-match on the part before the trailing "*".
        prefix = match.rstrip("*")
        for key in list(self._store.keys()):
            if key.startswith(prefix):
                yield key


class _FlakyRedis(_FakeRedis):
    """Fails the Nth underlying call (1-indexed, across get/setex combined)
    with a connection-style error, then recovers — simulates a Redis
    restart/blip mid-rewrite across a multi-key bust."""

    def __init__(self, fail_on_call: int) -> None:
        super().__init__()
        self._fail_on_call = fail_on_call
        self._call_count = 0

    def _maybe_fail(self) -> None:
        self._call_count += 1
        if self._call_count == self._fail_on_call:
            raise ConnectionError("simulated Redis restart")

    async def get(self, key: str) -> str | None:
        self._maybe_fail()
        return await super().get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self._maybe_fail()
        await super().setex(key, ttl, value)


TEST_KEY = "products:list:v1:testkey"


def _wrapper(data, age_seconds: float = 0.0) -> str:
    return json.dumps({"d": data, "t": time.time() - age_seconds})


@pytest.fixture(autouse=True)
def _reset_redis_circuit_breaker():
    """app.core.redis's circuit breaker is module-global state. Without
    this, a test that deliberately triggers mark_redis_error() (the Redis
    restart / flaky-connection scenarios below) would leave the circuit
    OPEN for every test that runs after it in the same pytest process —
    their safe_redis_* calls would silently no-op against redis_available()
    == False instead of exercising _FakeRedis, producing confusing false
    failures unrelated to what each test actually checks."""
    import app.core.redis as redis_module

    redis_module._circuit_state = redis_module._CircuitState.CLOSED
    redis_module._circuit_consecutive_failures = 0
    redis_module._circuit_failed_at = 0.0
    yield
    redis_module._circuit_state = redis_module._CircuitState.CLOSED
    redis_module._circuit_consecutive_failures = 0
    redis_module._circuit_failed_at = 0.0


async def test_soft_bust_does_not_delete_the_key():
    """The core regression this fix closes: bust must NOT hard-delete."""
    redis = _FakeRedis()
    await safe_redis_setex(
        redis, TEST_KEY, 600, json.dumps({"d": {"call": 1}, "t": time.time()})
    )

    await bust_product_list_cache(redis)

    assert await safe_redis_get(redis, TEST_KEY) is not None, (
        "soft-bust deleted the key — this is the exact bug that caused the "
        "production cache stampede"
    )


async def test_soft_bust_rewrites_timestamp_into_soft_expired_window():
    redis = _FakeRedis()
    ttl = 300
    await safe_redis_setex(
        redis, TEST_KEY, ttl * 2, json.dumps({"d": {"call": 1}, "t": time.time()})
    )

    await bust_product_list_cache(redis)

    raw = await safe_redis_get(redis, TEST_KEY)
    wrapper = json.loads(raw)
    age = time.time() - wrapper["t"]
    assert ttl <= age < ttl * 2, (
        f"rewritten age {age:.2f}s not in cache_swr's soft-expired window "
        f"[{ttl}, {ttl * 2})"
    )


async def test_soft_bust_read_is_instant_not_a_blocking_refetch():
    """The actual production symptom: after a bust, does the next reader
    block on fetch_fn (old, broken) or get an instant stale response with a
    background refresh (new, fixed)?"""
    redis = _FakeRedis()
    ttl = 300
    calls = {"n": 0}

    async def fetch_fn():
        calls["n"] += 1
        if calls["n"] == 2:
            # Simulate the ~2.3s production DB round-trip this fix exists
            # to keep off the synchronous read path.
            await asyncio.sleep(0.05)
        return {"call": calls["n"]}

    await cache_swr(redis, TEST_KEY, ttl=ttl, swr_window=ttl, fetch_fn=fetch_fn)
    assert calls["n"] == 1

    await bust_product_list_cache(redis)

    t0 = time.perf_counter()
    result = await cache_swr(
        redis, TEST_KEY, ttl=ttl, swr_window=ttl, fetch_fn=fetch_fn
    )
    elapsed = time.perf_counter() - t0

    assert (
        result["call"] == 1
    ), "must serve the stale value instantly, not block on refetch"
    assert elapsed < 0.02, (
        f"read after bust took {elapsed * 1000:.1f}ms — should be near-instant "
        f"(cache_swr's soft-expired branch), not blocking on fetch_fn's simulated "
        f"50ms DB round-trip"
    )

    # Let the coalesced background refresh (fired by the read above) finish.
    await asyncio.sleep(0.15)
    assert calls["n"] == 2, "exactly one background refresh should have run"
    raw = await safe_redis_get(redis, TEST_KEY)
    assert (
        json.loads(raw)["d"]["call"] == 2
    ), "cache should now hold the refreshed value"


async def test_soft_bust_falls_back_to_delete_for_malformed_entries():
    """Legacy/foreign values that aren't {"d", "t"} wrappers must still be
    invalidated — via the old (safe) hard-delete path, not left fresh."""
    redis = _FakeRedis()
    await safe_redis_setex(redis, TEST_KEY, 60, "not-a-wrapper-at-all")

    await bust_product_list_cache(redis)

    assert await safe_redis_get(redis, TEST_KEY) is None


async def test_soft_bust_handles_no_matching_keys():
    """No products:list:v1:* keys cached — must not raise."""
    redis = _FakeRedis()
    await bust_product_list_cache(redis)  # should be a no-op, no exception


async def test_soft_bust_handles_multiple_keys():
    redis = _FakeRedis()
    keys = [f"products:list:v1:page{i}" for i in range(3)]
    for k in keys:
        await safe_redis_setex(
            redis, k, 600, json.dumps({"d": {"page": k}, "t": time.time()})
        )

    await bust_product_list_cache(redis)

    for k in keys:
        raw = await safe_redis_get(redis, k)
        assert raw is not None
        assert time.time() - json.loads(raw)["t"] >= 300


# ── 1. Cache consistency: eventual freshness, never permanently stale ─────────


async def test_edit_is_eventually_visible_not_permanently_stale():
    """Simulates: product listed (v1 thumbnail) -> admin edits image -> bust
    -> stale v1 still served briefly -> background refresh completes -> v2
    now served. Proves the storefront never serves the OLD thumbnail forever,
    only for one refresh cycle — same guarantee cache_swr already gives on
    every normal TTL expiry, now also true right after an edit."""
    redis = _FakeRedis()
    ttl = 300
    db_state = {"thumbnail": "v1.jpg"}

    async def fetch_fn():
        return {"thumbnail": db_state["thumbnail"]}

    result = await cache_swr(
        redis, TEST_KEY, ttl=ttl, swr_window=ttl, fetch_fn=fetch_fn
    )
    assert result["thumbnail"] == "v1.jpg"

    # Admin edits the image — DB changes, then the endpoint busts the cache.
    db_state["thumbnail"] = "v2.jpg"
    await bust_product_list_cache(redis)

    # Immediately after: still serving the old thumbnail (expected — SWR's
    # whole point), but NOT blocking, and a refresh is in flight.
    stale_result = await cache_swr(
        redis, TEST_KEY, ttl=ttl, swr_window=ttl, fetch_fn=fetch_fn
    )
    assert stale_result["thumbnail"] == "v1.jpg"

    await asyncio.sleep(0.1)  # let the background refresh land

    fresh_result = await cache_swr(
        redis, TEST_KEY, ttl=ttl, swr_window=ttl, fetch_fn=fetch_fn
    )
    assert fresh_result["thumbnail"] == "v2.jpg", (
        "edit never became visible — this would be an actual regression "
        "(permanently stale image URLs), not an acceptable SWR tradeoff"
    )


async def test_repeated_edits_each_individually_converge_to_fresh():
    """Rapid sequence of edits (upload, then crop seconds later — the exact
    production sequence from the incident) — each bust must still converge
    to the latest state, not get stuck on an intermediate one."""
    redis = _FakeRedis()
    ttl = 300
    db_state = {"v": 0}

    async def fetch_fn():
        return {"v": db_state["v"]}

    await cache_swr(redis, TEST_KEY, ttl=ttl, swr_window=ttl, fetch_fn=fetch_fn)

    for i in range(1, 4):
        db_state["v"] = i
        await bust_product_list_cache(redis)
        await asyncio.sleep(0.02)
        await cache_swr(redis, TEST_KEY, ttl=ttl, swr_window=ttl, fetch_fn=fetch_fn)
        await asyncio.sleep(0.05)  # let this edit's refresh land before the next

    final = await cache_swr(redis, TEST_KEY, ttl=ttl, swr_window=ttl, fetch_fn=fetch_fn)
    assert (
        final["v"] == 3
    ), "final read must reflect the LAST edit, not an intermediate one"


# ── 2. Background refresh behavior ─────────────────────────────────────────


async def test_refresh_failure_leaves_stale_cache_recoverable():
    """If the background refresh's DB fetch raises, the stale cache entry
    must survive untouched (not deleted, not corrupted) so the NEXT request
    still gets a servable (if older) value instead of a hard miss."""
    redis = _FakeRedis()
    ttl = 300
    attempt = {"n": 0}

    async def flaky_fetch_fn():
        attempt["n"] += 1
        if attempt["n"] == 2:  # the background refresh attempt
            raise RuntimeError("simulated DB error during refresh")
        return {"call": attempt["n"]}

    await cache_swr(redis, TEST_KEY, ttl=ttl, swr_window=ttl, fetch_fn=flaky_fetch_fn)
    await bust_product_list_cache(redis)

    result = await cache_swr(
        redis, TEST_KEY, ttl=ttl, swr_window=ttl, fetch_fn=flaky_fetch_fn
    )
    assert (
        result["call"] == 1
    ), "still serves stale data even though a refresh is about to fail"

    await asyncio.sleep(0.1)  # let the failing background refresh run and raise

    raw = await safe_redis_get(redis, TEST_KEY)
    assert raw is not None, "a failed refresh must not delete/corrupt the stale entry"
    assert (
        json.loads(raw)["d"]["call"] == 1
    ), "stale value must be unchanged after a failed refresh"

    # Recovery: next attempt (attempt 3) succeeds and the cache heals itself
    # on the next natural TTL/bust cycle — proving the entry wasn't corrupted
    # into some unrecoverable state.
    await bust_product_list_cache(redis)
    await cache_swr(redis, TEST_KEY, ttl=ttl, swr_window=ttl, fetch_fn=flaky_fetch_fn)
    await asyncio.sleep(0.1)
    raw2 = await safe_redis_get(redis, TEST_KEY)
    assert (
        json.loads(raw2)["d"]["call"] == 3
    ), "cache should recover once a refresh succeeds"


async def test_concurrent_readers_coalesce_to_a_bounded_number_of_refreshes():
    """The actual 'stampede' question: fire N concurrent readers immediately
    after a bust and count real DB fetches. cache_swr's coalescing lock is
    checked-then-fired without an intervening await inside a single call,
    but N *separate* concurrent cache_swr() calls can each pass the
    lock.locked() check before the first scheduled refresh task has had a
    chance to actually acquire the lock (asyncio.ensure_future schedules,
    it doesn't run synchronously) — so this asserts the REAL bound
    (small, single digits) rather than assuming exactly 1, and documents
    that every single one of the N readers still gets the instant stale
    response regardless."""
    redis = _FakeRedis()
    ttl = 300
    calls = {"n": 0}

    async def fetch_fn():
        calls["n"] += 1
        await asyncio.sleep(0.03)
        return {"call": calls["n"]}

    await cache_swr(redis, TEST_KEY, ttl=ttl, swr_window=ttl, fetch_fn=fetch_fn)
    await bust_product_list_cache(redis)

    N = 20
    t0 = time.perf_counter()
    results = await asyncio.gather(
        *(
            cache_swr(redis, TEST_KEY, ttl=ttl, swr_window=ttl, fetch_fn=fetch_fn)
            for _ in range(N)
        )
    )
    elapsed = time.perf_counter() - t0

    assert all(r["call"] == 1 for r in results), (
        "every one of the N concurrent readers must get the instant stale "
        "response — none should block on a fresh fetch"
    )
    assert elapsed < 0.02, (
        f"{N} concurrent readers took {elapsed * 1000:.1f}ms — should be near-instant, "
        f"proving none of them blocked on fetch_fn's 30ms simulated DB call"
    )

    await asyncio.sleep(0.2)
    refresh_count = calls["n"] - 1  # subtract the initial seed fetch
    print(
        f"\n  [stampede] {N} concurrent readers -> {refresh_count} background DB refresh(es)"
    )
    assert 1 <= refresh_count <= 3, (
        f"expected the coalescing lock to bound refreshes to a small number, got {refresh_count} "
        f"out of {N} concurrent readers — that would indicate coalescing isn't working at all"
    )


async def test_malformed_entry_falls_back_safely_during_concurrent_access():
    redis = _FakeRedis()
    await safe_redis_setex(redis, TEST_KEY, 60, "{garbage-not-valid-json")

    # Concurrent busts against the same malformed key must not raise.
    await asyncio.gather(*(bust_product_list_cache(redis) for _ in range(5)))

    assert await safe_redis_get(redis, TEST_KEY) is None


# ── 3. Redis failure scenarios ──────────────────────────────────────────────


async def test_redis_failure_partway_through_multi_key_bust_is_safe():
    """Simulates a Redis restart mid-rewrite: key 1 of 3 rewrites fine, then
    the connection drops on key 2. Must not raise into the caller (the
    upload/crop endpoint just does `await bust_product_list_cache(redis)`
    with no try/except of its own) and must not corrupt what was already
    written."""
    redis = _FlakyRedis(
        fail_on_call=3
    )  # succeeds through key1's get+setex, fails on key2's get
    keys = [f"products:list:v1:page{i}" for i in range(3)]
    for k in keys:
        redis._store[k] = _wrapper(
            {"page": k}
        )  # seed directly, bypassing the flaky wrapper

    await bust_product_list_cache(redis)  # must not raise

    raw0 = redis._store.get(keys[0])
    assert raw0 is not None
    assert (
        time.time() - json.loads(raw0)["t"] >= 300
    ), "key processed before the failure must be rewritten"

    # keys[1] and keys[2] were never reached (loop aborted on the exception)
    # — they remain in their pre-bust (fresh) state. Not corrupted, just not
    # yet invalidated; the next bust (or natural TTL expiry) will catch them.
    for k in keys[1:]:
        raw = redis._store.get(k)
        assert (
            raw is not None
        ), "an in-flight Redis failure must not delete unrelated keys"


async def test_expired_key_between_scan_and_get_is_a_safe_noop():
    """Key existed at SCAN time but is gone by GET time (natural TTL expiry
    racing the bust, or another process deleting it) — must be a no-op for
    that key, not an error."""
    redis = _FakeRedis()
    await safe_redis_setex(redis, TEST_KEY, 60, _wrapper({"call": 1}))

    # Simulate the key vanishing right after SCAN would have returned it —
    # verify the guard directly: _soft_expire_swr_entry must no-op when GET
    # returns None for a key SCAN found (the exact race this is testing).
    redis._store.pop(TEST_KEY, None)
    from app.core.redis import _soft_expire_swr_entry

    await _soft_expire_swr_entry(redis, TEST_KEY, ttl_seconds=300)  # must not raise
    assert await safe_redis_get(redis, TEST_KEY) is None


async def test_missing_key_bust_is_a_noop():
    """bust_product_list_cache called when nothing matches — e.g. cache
    already cold, or this product's list pages never got cached — must not
    raise or create phantom keys."""
    redis = _FakeRedis()
    await bust_product_list_cache(redis)
    assert redis._store == {}


async def test_concurrent_image_edits_do_not_corrupt_cache():
    """Two admins (or two rapid edits) busting the same key set at the same
    time — must not crash, must not corrupt the JSON, must end in a valid
    soft-expired state."""
    redis = _FakeRedis()
    keys = [f"products:list:v1:page{i}" for i in range(5)]
    for k in keys:
        redis._store[k] = _wrapper({"page": k})

    await asyncio.gather(*(bust_product_list_cache(redis) for _ in range(4)))

    for k in keys:
        raw = redis._store[k]
        wrapper = json.loads(raw)  # must still be valid JSON, not torn/corrupted
        assert "d" in wrapper and "t" in wrapper
        assert time.time() - wrapper["t"] >= 300

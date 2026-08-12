"""Tests for app.core.worker_leader.WorkerLeader.

Verifies the fail-open behavior (Redis down => assume leadership so startup
never stalls), the SET NX acquire semantics (first worker wins, followers
skip), the token-ownership guard (a stale leader can never refresh or
release a lock another process has since acquired), the heartbeat refresh,
the follower re-election loop (a crashed leader is replaced without a full
restart), and the shutdown release path. Uses an in-memory stand-in for the
tiny redis.asyncio API subset used, matching the _FakeRedis convention in
test_cache_swr_soft_bust.py.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core import worker_leader
from app.core.worker_leader import WorkerLeader


class _FakeRedis:
    """In-memory stand-in for set(nx/ex)/eval/delete on redis.asyncio.

    ``eval`` implements the two known Lua scripts by substring: an "expire"
    script only extends the TTL when the stored value matches the caller's
    token; a "del" script only removes the key on a token match.
    """

    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self.expire_calls: list[tuple[str, int]] = []

    async def set(
        self, key: str, value: str, *, nx: bool = False, ex: int | None = None
    ) -> bool:
        if nx and key in self._store:
            return False
        self._store[key] = value
        return True

    async def eval(self, script: str, numkeys: int, key: str, token: str, *rest) -> int:
        if "expire" in script:
            if self._store.get(key) == token:
                self.expire_calls.append((key, rest[0]))
                return 1
            return 0
        if "del" in script:
            if self._store.get(key) == token:
                self._store.pop(key, None)
                return 1
            return 0
        return 0

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


@pytest.fixture
def fake_redis(monkeypatch) -> _FakeRedis:
    redis = _FakeRedis()
    monkeypatch.setattr(worker_leader, "get_redis_pool", lambda: redis)
    monkeypatch.setattr(worker_leader, "redis_available", lambda: True)
    return redis


@pytest.fixture
def patch_redis_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(worker_leader, "redis_available", lambda: False)


@pytest.mark.asyncio
async def test_redis_unavailable_falls_back_to_leader(
    patch_redis_unavailable,
) -> None:
    """Fail-open: with Redis down the process assumes leadership so the
    queue still starts (a Redis outage must never disable background work)."""
    leader = WorkerLeader()
    assert await leader.try_acquire() is True
    # Nothing was written, but the process believes it is the leader.
    await leader.release()  # held=False -> no delete, must not raise


@pytest.mark.asyncio
async def test_first_worker_acquires_lock(fake_redis: _FakeRedis) -> None:
    leader = WorkerLeader()
    try:
        assert await leader.try_acquire() is True
        # The lock value is this process's random token, not a fixed string.
        assert worker_leader._LEADER_LOCK_KEY in fake_redis._store
        assert fake_redis._store[worker_leader._LEADER_LOCK_KEY] != "1"
    finally:
        await leader.release()


@pytest.mark.asyncio
async def test_second_worker_skips_when_lock_held(
    fake_redis: _FakeRedis,
) -> None:
    # Simulate another process already holding the lock.
    fake_redis._store[worker_leader._LEADER_LOCK_KEY] = "other-token"

    leader = WorkerLeader()
    assert await leader.try_acquire() is False
    # A follower must not release the leader's lock on shutdown.
    await leader.release()
    assert worker_leader._LEADER_LOCK_KEY in fake_redis._store
    assert fake_redis._store[worker_leader._LEADER_LOCK_KEY] == "other-token"


@pytest.mark.asyncio
async def test_release_removes_own_lock(fake_redis: _FakeRedis) -> None:
    leader = WorkerLeader()
    assert await leader.try_acquire() is True
    await leader.release()
    assert worker_leader._LEADER_LOCK_KEY not in fake_redis._store


@pytest.mark.asyncio
async def test_heartbeat_refresh_keeps_lock_alive(
    fake_redis: _FakeRedis, monkeypatch
) -> None:
    """The refresh loop re-expires the lock on a short cadence so a
    surviving worker can take over quickly after a leader crash."""
    monkeypatch.setattr(worker_leader, "_REFRESH_INTERVAL_SECONDS", 0.05)
    monkeypatch.setattr(worker_leader, "_LEADER_TTL_SECONDS", 30)

    leader = WorkerLeader()
    try:
        assert await leader.try_acquire() is True
        await asyncio.sleep(0.15)
        assert fake_redis.expire_calls, "refresh loop never ran"
        key, ttl = fake_redis.expire_calls[-1]
        assert key == worker_leader._LEADER_LOCK_KEY
        # TTL travels as a string through the Lua script.
        assert ttl == "30"
    finally:
        await leader.release()


@pytest.mark.asyncio
async def test_stale_leader_cannot_extend_new_leaders_lock(
    fake_redis: _FakeRedis, monkeypatch
) -> None:
    """Once the lock is re-acquired by another worker, the old leader's
    refresh loop must not extend the new leader's TTL."""
    monkeypatch.setattr(worker_leader, "_REFRESH_INTERVAL_SECONDS", 0.05)
    monkeypatch.setattr(worker_leader, "_LEADER_TTL_SECONDS", 30)

    leader = WorkerLeader()
    try:
        assert await leader.try_acquire() is True
        await asyncio.sleep(0.1)
        assert fake_redis.expire_calls, "owned refresh should have run"

        # The lock is stolen by a new leader (different token).
        fake_redis._store[worker_leader._LEADER_LOCK_KEY] = "new-leader-token"
        calls_before = len(fake_redis.expire_calls)
        await asyncio.sleep(0.15)
        assert (
            len(fake_redis.expire_calls) == calls_before
        ), "stale leader extended a lock it no longer owns"
    finally:
        await leader.release()


@pytest.mark.asyncio
async def test_stale_leader_cannot_release_new_leaders_lock(
    fake_redis: _FakeRedis,
) -> None:
    leader = WorkerLeader()
    assert await leader.try_acquire() is True
    # The lock is stolen by a new leader before this process shuts down.
    fake_redis._store[worker_leader._LEADER_LOCK_KEY] = "new-leader-token"
    await leader.release()
    assert worker_leader._LEADER_LOCK_KEY in fake_redis._store
    assert fake_redis._store[worker_leader._LEADER_LOCK_KEY] == "new-leader-token"


@pytest.mark.asyncio
async def test_follower_reacquires_after_leader_dies(
    fake_redis: _FakeRedis, monkeypatch
) -> None:
    """A follower polls for leadership; when the lock clears (leader crash
    + TTL expiry) it wins, fires on_elected, and stops polling."""
    monkeypatch.setattr(worker_leader, "_REACQUIRE_INTERVAL_SECONDS", 0.05)
    # Keep the refresh loop quiet so it can't interfere with the test.
    monkeypatch.setattr(worker_leader, "_REFRESH_INTERVAL_SECONDS", 3600)
    fake_redis._store[worker_leader._LEADER_LOCK_KEY] = "dead-leader-token"

    leader = WorkerLeader()
    assert await leader.try_acquire() is False

    elected: list[bool] = []
    leader.start_reacquire_loop(lambda: elected.append(True))

    # The old leader's lock expires; the next poll must win it.
    fake_redis._store.pop(worker_leader._LEADER_LOCK_KEY, None)
    await asyncio.sleep(0.2)

    assert elected == [True], "on_elected was never fired after lock expiry"
    assert leader._held is True
    await leader.release()
    assert worker_leader._LEADER_LOCK_KEY not in fake_redis._store


@pytest.mark.asyncio
async def test_redis_error_acquire_falls_back_to_leader(
    monkeypatch,
) -> None:
    """An exception from the SET NX call must not stall startup — assume
    leadership (same fail-open semantics as the cache warmer)."""

    class _BrokenRedis:
        async def set(self, *args, **kwargs) -> bool:
            raise ConnectionError("boom")

    monkeypatch.setattr(worker_leader, "get_redis_pool", lambda: _BrokenRedis())
    monkeypatch.setattr(worker_leader, "redis_available", lambda: True)

    leader = WorkerLeader()
    assert await leader.try_acquire() is True
    await leader.release()

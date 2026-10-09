"""Redis circuit breaker must tolerate isolated failures, and cache_swr must
keep serving a last-good copy while the circuit is open (no DB stampede)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import app.core.cache as cache_mod
import app.core.redis as redis_mod


@pytest.fixture(autouse=True)
def _reset_state():
    def reset() -> None:
        redis_mod._circuit_state = redis_mod._CircuitState.CLOSED
        redis_mod._circuit_failed_at = 0.0
        redis_mod._circuit_consecutive_failures = 0
        cache_mod._local_fallback.clear()

    reset()
    yield
    reset()


class TestCircuitBreakerThreshold:
    def test_single_failure_does_not_open(self) -> None:
        redis_mod.mark_redis_error()
        assert redis_mod.redis_available() is True
        assert redis_mod._circuit_state == redis_mod._CircuitState.CLOSED

    def test_success_resets_failure_count(self) -> None:
        for _ in range(redis_mod._CIRCUIT_FAILURE_THRESHOLD - 1):
            redis_mod.mark_redis_error()
        redis_mod.mark_redis_ok()
        redis_mod.mark_redis_error()
        assert redis_mod.redis_available() is True

    def test_opens_after_threshold_consecutive_failures(self) -> None:
        for _ in range(redis_mod._CIRCUIT_FAILURE_THRESHOLD):
            redis_mod.mark_redis_error()
        assert redis_mod._circuit_state == redis_mod._CircuitState.OPEN
        assert redis_mod.redis_available() is False

    def test_backoff_is_bounded(self) -> None:
        redis_mod._circuit_consecutive_failures = 1000
        assert redis_mod._circuit_backoff() == redis_mod._CIRCUIT_MAX_BACKOFF


class TestLocalFallback:
    @pytest.mark.asyncio
    async def test_serves_last_good_value_while_circuit_open(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fetch = AsyncMock(return_value={"items": [1, 2, 3]})
        redis = MagicMock()

        # Healthy: Redis miss -> fetch -> value remembered locally.
        redis_mod._circuit_state = redis_mod._CircuitState.CLOSED
        monkeypatch.setattr(cache_mod, "safe_redis_get", AsyncMock(return_value=None))
        monkeypatch.setattr(cache_mod, "safe_redis_setex", AsyncMock())
        first = await cache_mod.cache_swr(redis, "k", 300, 300, fetch)
        assert first == {"items": [1, 2, 3]}
        assert fetch.await_count == 1

        # Redis goes away: circuit open, GET yields nothing.
        redis_mod._circuit_state = redis_mod._CircuitState.OPEN
        redis_mod._circuit_failed_at = __import__("time").monotonic()
        second = await cache_mod.cache_swr(redis, "k", 300, 300, fetch)
        assert second == {"items": [1, 2, 3]}
        assert fetch.await_count == 1  # no second DB hit

    def test_local_fallback_is_bounded(self) -> None:
        for i in range(cache_mod._LOCAL_FALLBACK_MAX + 10):
            cache_mod._local_fallback_put(f"k{i}", i)
        assert len(cache_mod._local_fallback) == cache_mod._LOCAL_FALLBACK_MAX
        assert cache_mod._local_fallback_get("k0", 60) is None

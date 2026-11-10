"""check_rate_limit keyed by account identity instead of client IP."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.middleware.rate_limit import check_rate_limit, record_rate_limit_hit


def _request(path: str = "/api/v1/reviews") -> MagicMock:
    request = MagicMock()
    request.client = MagicMock(host="8.8.8.8")
    request.headers = {}
    request.url.path = path
    return request


def _redis(count: int, *, record: bool = True) -> tuple[MagicMock, MagicMock]:
    pipe = MagicMock()
    results = [0, 1, count, True] if record else [0, count]
    pipe.execute = AsyncMock(return_value=results)
    redis = MagicMock()
    redis.pipeline.return_value = pipe
    return redis, pipe


class TestCheckRateLimitIdentity:
    async def test_identity_replaces_ip_in_key(self):
        redis, pipe = _redis(count=1)
        await check_rate_limit(
            _request(),
            redis,
            limit=2,
            window=3600,
            key_prefix="rl:x",
            identity="user:42",
        )
        pipe.zadd.assert_called_once()
        assert pipe.zadd.call_args.args[0] == "rl:x:user:42:/api/v1/reviews"

    async def test_without_identity_keys_by_ip(self):
        redis, pipe = _redis(count=1)
        await check_rate_limit(_request(), redis, limit=2, key_prefix="rl:x")
        assert pipe.zadd.call_args.args[0] == "rl:x:8.8.8.8:/api/v1/reviews"

    async def test_over_limit_raises_429_with_custom_detail(self):
        redis, _ = _redis(count=3)
        with pytest.raises(HTTPException) as exc:
            await check_rate_limit(
                _request(),
                redis,
                limit=2,
                window=3600,
                identity="user:42",
                detail="Slow down on reviews.",
            )
        assert exc.value.status_code == 429
        assert exc.value.detail == "Slow down on reviews."
        assert exc.value.headers["Retry-After"] == "3600"

    async def test_at_limit_is_allowed(self):
        redis, _ = _redis(count=2)
        await check_rate_limit(_request(), redis, limit=2, identity="user:42")

    async def test_redis_failure_fails_open(self):
        redis = MagicMock()
        redis.pipeline.side_effect = ConnectionError("down")
        await check_rate_limit(_request(), redis, limit=2, identity="user:42")


class TestCheckRateLimitRecordOnSuccess:
    async def test_check_only_does_not_record(self):
        redis, pipe = _redis(count=1, record=False)
        await check_rate_limit(
            _request(), redis, limit=2, identity="user:42", record=False
        )
        pipe.zadd.assert_not_called()
        pipe.zcard.assert_called_once()

    async def test_check_only_blocks_when_quota_already_used(self):
        redis, _ = _redis(count=2, record=False)  # two successful posts in window
        with pytest.raises(HTTPException) as exc:
            await check_rate_limit(
                _request(), redis, limit=2, identity="user:42", record=False
            )
        assert exc.value.status_code == 429

    async def test_check_only_allows_last_slot(self):
        redis, _ = _redis(count=1, record=False)
        await check_rate_limit(
            _request(), redis, limit=2, identity="user:42", record=False
        )

    async def test_record_hit_adds_to_same_key(self):
        redis, pipe = _redis(count=0)
        await record_rate_limit_hit(
            _request(), redis, window=3600, key_prefix="rl:x", identity="user:42"
        )
        assert pipe.zadd.call_args.args[0] == "rl:x:user:42:/api/v1/reviews"
        pipe.expire.assert_called_once_with("rl:x:user:42:/api/v1/reviews", 3600)

    async def test_record_hit_fails_open(self):
        redis = MagicMock()
        redis.pipeline.side_effect = ConnectionError("down")
        await record_rate_limit_hit(_request(), redis, identity="user:42")

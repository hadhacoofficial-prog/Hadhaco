"""Public review endpoints use SWR so an idle product's reviews never cost a
cold DB fetch (~1.3s measured in production), and the X-Total-Count header
survives cache hits."""

from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.model_registry import import_all_models

import_all_models()

from app.modules.reviews import router as reviews_router  # noqa: E402


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = value

    async def delete(self, *keys: str) -> None:
        for k in keys:
            self.store.pop(k, None)


@pytest.fixture
def svc(monkeypatch):
    @asynccontextmanager
    async def fake_session():
        yield MagicMock()

    monkeypatch.setattr(reviews_router, "AsyncSessionLocal", fake_session)
    fake = SimpleNamespace(
        list_product_reviews=AsyncMock(return_value=([], 7)),
        rating_summary=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(reviews_router, "_svc", fake)
    return fake


async def _list(redis, user=None):
    return await reviews_router.list_product_reviews(
        product_id=uuid.UUID(int=1),
        offset=0,
        limit=20,
        sort="newest",
        rating=None,
        db=MagicMock(),
        redis=redis,
        user=user,
    )


async def test_anonymous_list_is_cached_and_keeps_total_header(svc):
    redis = FakeRedis()

    first = await _list(redis)
    second = await _list(redis)

    assert svc.list_product_reviews.await_count == 1
    assert first.headers["x-total-count"] == "7"
    assert second.headers["x-total-count"] == "7"  # was missing on cache hits
    assert json.loads(second.body)["data"] == []


async def test_logged_in_list_bypasses_cache(svc):
    redis = FakeRedis()
    user = SimpleNamespace(id=uuid.uuid4())

    await _list(redis, user=user)
    await _list(redis, user=user)

    assert svc.list_product_reviews.await_count == 2
    assert redis.store == {}


async def test_summary_cached_after_first_fetch(svc):
    redis = FakeRedis()
    pid = uuid.UUID(int=2)

    first = await reviews_router.product_rating_summary(
        product_id=pid, db=MagicMock(), redis=redis
    )
    second = await reviews_router.product_rating_summary(
        product_id=pid, db=MagicMock(), redis=redis
    )

    assert svc.rating_summary.await_count == 1
    assert json.loads(first.body) == json.loads(second.body)
    assert json.loads(second.body)["data"]["review_count"] == 0

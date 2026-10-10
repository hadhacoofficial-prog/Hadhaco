"""Search history is written off the response path, on its own session."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.core.model_registry import import_all_models

import_all_models()

from app.modules.search import router as search_router  # noqa: E402


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = value


async def test_search_miss_records_history_in_background(monkeypatch):
    session = MagicMock()
    session.commit = AsyncMock()

    @asynccontextmanager
    async def fake_session():
        yield session

    monkeypatch.setattr(search_router, "AsyncSessionLocal", fake_session)
    svc = SimpleNamespace(
        full_text_search=AsyncMock(
            return_value={
                "items": [],
                "total": 3,
                "page": 1,
                "page_size": 20,
                "total_pages": 1,
            }
        ),
        record_search=AsyncMock(),
    )
    monkeypatch.setattr(search_router, "_service", svc)

    request_db = MagicMock()
    request_db.execute = AsyncMock()
    resp = await search_router.search_products(
        q="ring",
        page=1,
        page_size=20,
        category_id=None,
        min_price=None,
        max_price=None,
        db=request_db,
        redis=_FakeRedis(),
        current_user=None,
    )
    assert resp.status_code == 200

    # the response did not wait for (or use) the history write ...
    request_db.execute.assert_not_awaited()
    # ... which completes on its own session shortly after.
    await asyncio.gather(*list(search_router._record_tasks))
    svc.record_search.assert_awaited_once_with(session, "ring", None, 3)
    session.commit.assert_awaited_once()


async def test_history_failure_never_breaks_search(monkeypatch):
    @asynccontextmanager
    async def boom():
        raise RuntimeError("db down")
        yield  # pragma: no cover

    monkeypatch.setattr(search_router, "AsyncSessionLocal", boom)
    await search_router._record_search_background("ring", None, 1)  # no raise

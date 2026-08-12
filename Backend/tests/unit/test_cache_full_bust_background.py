"""Tests for app.core.cache.schedule_all_product_caches_bust.

Catalog admin writes (create/update/delete/restore product, catalog/router.py)
used to `await bust_all_product_caches(redis)` inline, blocking the response
on the SCAN + per-key soft-expire + detail-key SCAN/DELETE + sitemap + search
busts (Docs/CURRENT_SLOW_SQL_ROOT_CAUSE_ANALYSIS.md §10 P1-B). This mirrors
the same fire-and-forget, single-flight, request-coalescing pattern the media
module already uses for schedule_product_list_bust (test_cache_swr_soft_bust.py)
so the fix is proven the same way: schedule must return immediately, and the
bust must still run to completion off the request path.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

import app.core.cache as cache_module
from app.core.cache import (
    cancel_pending_full_busts,
    schedule_all_product_caches_bust,
)

pytestmark = pytest.mark.asyncio


async def _await_idle(timeout: float = 2.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while cache_module._full_bust_in_flight or cache_module._full_bust_tasks:
        if asyncio.get_event_loop().time() > deadline:
            state = [
                f"{t!r} done={t.done()} cancelled={t.cancelled()}"
                for t in list(cache_module._full_bust_tasks)
            ]
            raise AssertionError(
                f"background full-bust task did not finish in time "
                f"(in_flight={cache_module._full_bust_in_flight} "
                f"requested={cache_module._full_bust_requested} tasks={state})"
            )
        await asyncio.sleep(0.01)


@pytest.fixture(autouse=True)
async def _cleanup():
    yield
    cancel_pending_full_busts()
    await _await_idle()


async def test_schedule_returns_immediately(monkeypatch):
    """schedule_all_product_caches_bust must not await the bust itself —
    the caller (an admin PATCH/POST/DELETE response) must not block on it.

    asyncio.create_task() schedules the coroutine for the *next* event-loop
    iteration; it never starts executing synchronously inside the call that
    creates it. So if schedule() returns and the underlying bust hasn't even
    started yet (no await in between), schedule() itself did not block on
    it — the P0-1 regression this guards against was an inline `await
    bust_all_product_caches(...)`, which by definition would have already
    run to completion by the time control returned here."""
    started = asyncio.Event()
    release = asyncio.Event()

    async def _slow_bust(redis):
        started.set()
        await release.wait()

    monkeypatch.setattr(cache_module, "bust_all_product_caches", _slow_bust)

    schedule_all_product_caches_bust(redis=object())

    assert not started.is_set(), (
        "schedule_all_product_caches_bust blocked on the bust — the admin "
        "write response must return immediately"
    )

    release.set()
    await _await_idle()


async def test_bust_actually_runs_in_background(monkeypatch):
    bust = AsyncMock()
    monkeypatch.setattr(cache_module, "bust_all_product_caches", bust)

    schedule_all_product_caches_bust(redis=object())
    await _await_idle()
    bust.assert_awaited_once()


async def test_concurrent_schedules_collapse_into_one_task(monkeypatch):
    bust = AsyncMock()
    monkeypatch.setattr(cache_module, "bust_all_product_caches", bust)

    schedule_all_product_caches_bust(redis=object())
    schedule_all_product_caches_bust(redis=object())
    schedule_all_product_caches_bust(redis=object())

    assert (
        len(cache_module._full_bust_tasks) == 1
    ), "concurrent schedules must collapse into a single in-flight task"

    await _await_idle()

    assert bust.await_count == 2, (
        "pending busts requested while one was running must be drained by "
        f"the running loop, got {bust.await_count} (expected initial + one drain)"
    )


async def test_cancel_pending_full_busts_stops_in_flight_task(monkeypatch):
    started = asyncio.Event()
    hang = asyncio.Event()

    async def _hanging_bust(redis):
        started.set()
        await hang.wait()

    monkeypatch.setattr(cache_module, "bust_all_product_caches", _hanging_bust)

    schedule_all_product_caches_bust(redis=object())
    await asyncio.wait_for(started.wait(), timeout=1.0)
    assert cache_module._full_bust_in_flight is True

    cancel_pending_full_busts()
    await _await_idle()

    assert cache_module._full_bust_in_flight is False
    assert cache_module._full_bust_tasks == set()

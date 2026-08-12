"""Regression tests for the per-process persistent event loop (app.celery_app
.get_worker_loop / app.tasks._common.run_async).

Root cause this guards against, confirmed against real production worker
logs: run_async used to call asyncio.run(coro_fn()) on every task invocation.
asyncio.run() creates a new event loop and destroys it when the coroutine
returns, but app.core.database's engine (and its pooled asyncpg connections)
is created once per *process* and reused across every task invocation in
that process. asyncpg connections are bound to the event loop that opened
them, so the second task's fresh loop tried to reuse a connection still
attached to the first task's already-destroyed loop:

    RuntimeError: Task ... got Future ... attached to a different loop
    asyncpg.exceptions.InterfaceError: cannot perform operation:
    another operation is in progress

This broke reservation_expiry, cms_publish, and notification_retry on the
second+ tick in the same worker process, and ultimately media.generate_variants
(observed in the UI as "Timed out waiting for variant generation").
"""

from __future__ import annotations

import asyncio

import app.celery_app as celery_app_module
from app.celery_app import get_worker_loop
from app.tasks._common import run_async


def _reset_worker_loop() -> None:
    celery_app_module._worker_loop = None


class TestRunAsyncReusesOneLoop:
    def setup_method(self) -> None:
        _reset_worker_loop()

    def teardown_method(self) -> None:
        _reset_worker_loop()

    def test_sequential_invocations_share_the_same_loop(self) -> None:
        """The exact shape of the bug: two Beat-triggered ticks of the same
        task in the same worker process must run on the same event loop, or
        pooled asyncpg connections opened by the first tick become unusable
        on the second.

        Compares actual loop object identity and open/closed state, not
        id() — id() can be reused once a garbage-collected loop's memory is
        freed, so two *different*, both-already-closed loop objects can
        report equal id()s and falsely look like the same loop. That gap
        would make this test pass against the old asyncio.run()-per-call bug
        just as easily as against the fix, which defeats the point of a
        regression test."""
        seen_loops: list[asyncio.AbstractEventLoop] = []

        async def _capture_loop() -> None:
            seen_loops.append(asyncio.get_running_loop())

        run_async(_capture_loop)
        run_async(_capture_loop)
        run_async(_capture_loop)

        first, second, third = seen_loops
        assert first is second is third
        assert not first.is_closed(), (
            "the loop must still be open after run_async returns — "
            "asyncio.run() closes it, which is exactly the bug"
        )


class TestGetWorkerLoop:
    def setup_method(self) -> None:
        _reset_worker_loop()

    def teardown_method(self) -> None:
        _reset_worker_loop()

    def test_creates_lazily_when_uninitialized(self) -> None:
        """Calling a task function directly (as tests do, outside a real
        Celery worker) must not require worker_process_init to have fired."""
        loop = get_worker_loop()
        assert isinstance(loop, asyncio.AbstractEventLoop)
        assert not loop.is_closed()

    def test_returns_the_same_loop_on_repeated_calls(self) -> None:
        loop1 = get_worker_loop()
        loop2 = get_worker_loop()
        assert loop1 is loop2

    def test_creates_a_new_loop_if_the_current_one_was_closed(self) -> None:
        loop1 = get_worker_loop()
        loop1.close()
        loop2 = get_worker_loop()
        assert loop2 is not loop1
        assert not loop2.is_closed()


class TestWorkerProcessInitResetsLoop:
    def setup_method(self) -> None:
        _reset_worker_loop()

    def teardown_method(self) -> None:
        _reset_worker_loop()

    def test_fork_hook_closes_old_loop_and_creates_a_fresh_one(self) -> None:
        old_loop = get_worker_loop()
        assert not old_loop.is_closed()

        celery_app_module._reinit_db_engine_after_fork()

        new_loop = get_worker_loop()
        assert old_loop.is_closed(), "the pre-fork loop must not leak"
        assert new_loop is not old_loop
        assert not new_loop.is_closed()
        assert asyncio.get_event_loop() is new_loop

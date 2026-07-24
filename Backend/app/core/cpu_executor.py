"""
Dedicated CPU-bound work executor — isolated from the default executor that
`asyncio.to_thread` uses for R2 network I/O (app/modules/media/storage.py's
`_run_bounded`).

Why a *separate* pool: `asyncio.to_thread()` always runs on the loop's
default executor. Mixing CPU-bound Pillow decode/resize/encode into that
same pool as R2 network I/O means a burst of image processing can starve
uploads/downloads waiting on nothing but network latency, and vice versa —
exactly the contention storage.py's own `_R2_CONCURRENCY` comment already
warns about for R2 calls alone. Giving CPU work its own bounded pool keeps
the two failure modes independent.

Sizing: the production container is capped at 1 CPU core (see
DEVOPS.md / docker-compose resource limits). More threads than cores buys
nothing for CPU-bound work — Pillow's C-level decode/resize/encode releases
the GIL, so 1-2 threads already let the event loop keep servicing requests
while one runs; beyond that it's just context-switch overhead competing for
the same core. `IMAGE_PROCESSING_WORKERS` (default 2) is deliberately small.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.core.config import settings

try:
    from prometheus_client import Gauge, Histogram

    cpu_executor_active_jobs: Any = Gauge(
        "cpu_executor_active_jobs",
        "CPU-bound jobs currently executing in the dedicated image-processing thread pool",
    )
    cpu_executor_queued_jobs: Any = Gauge(
        "cpu_executor_queued_jobs",
        "CPU-bound jobs submitted but not yet started (waiting for a free thread)",
    )
    cpu_executor_job_duration_seconds: Any = Histogram(
        "cpu_executor_job_duration_seconds",
        "Wall-clock time a CPU-bound job spent actually running in the thread pool "
        "(excludes queue wait)",
    )
    _METRICS_ENABLED = True
except ImportError:  # pragma: no cover - prometheus_client not installed

    class _NoOpMetric:
        def labels(self, *args: Any, **kwargs: Any) -> _NoOpMetric:
            return self

        def inc(self, *args: Any, **kwargs: Any) -> None:
            pass

        def dec(self, *args: Any, **kwargs: Any) -> None:
            pass

        def set(self, *args: Any, **kwargs: Any) -> None:
            pass

        def observe(self, *args: Any, **kwargs: Any) -> None:
            pass

    cpu_executor_active_jobs = _NoOpMetric()
    cpu_executor_queued_jobs = _NoOpMetric()
    cpu_executor_job_duration_seconds = _NoOpMetric()
    _METRICS_ENABLED = False

_executor: ThreadPoolExecutor | None = None


def get_cpu_executor() -> ThreadPoolExecutor:
    """Lazily create the process-wide dedicated CPU executor."""
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=settings.IMAGE_PROCESSING_WORKERS,
            thread_name_prefix="cpu-image",
        )
    return _executor


def _run_and_time[T](fn: Callable[[], T]) -> T:
    """Runs on the worker thread — records active/duration around the call.
    Queue-wait time is tracked separately by the caller (see run_cpu_bound),
    since it needs to straddle the submit-vs-start boundary the executor
    itself doesn't expose."""
    cpu_executor_queued_jobs.dec()
    cpu_executor_active_jobs.inc()
    start = time.perf_counter()
    try:
        return fn()
    finally:
        cpu_executor_job_duration_seconds.observe(time.perf_counter() - start)
        cpu_executor_active_jobs.dec()


async def run_cpu_bound[T](fn: Callable[[], T]) -> T:
    """
    Run a synchronous, CPU-bound, side-effect-free-of-asyncio callable on the
    dedicated executor, off the event loop.

    *fn* must not touch an AsyncSession, await anything, or call back into
    asyncio — it runs on a plain OS thread with no event loop of its own.
    Exceptions raised inside *fn* propagate to the caller unchanged (the
    executor Future re-raises on await), so existing try/except call sites
    around this function keep working exactly as before.
    """
    loop = asyncio.get_running_loop()
    cpu_executor_queued_jobs.inc()
    # No except/finally here that also touches the queued gauge: once
    # submission succeeds, _run_and_time (running on the worker thread) owns
    # the matching dec() as its very first action, even if fn raises. The
    # only leak is a task that's submitted but never dequeued at all (e.g.
    # executor torn down mid-submit during shutdown) — acceptable drift on
    # an already-terminal path, not worth a double-decrement bug to avoid.
    return await loop.run_in_executor(get_cpu_executor(), _run_and_time, fn)


def shutdown_cpu_executor() -> None:
    """Called from the FastAPI lifespan shutdown — mirrors queue.shutdown()."""
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=True, cancel_futures=False)
        _executor = None

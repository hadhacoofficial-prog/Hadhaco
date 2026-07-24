"""Event loop lag monitor — the general-purpose signal for "is the event
loop currently blocked", independent of any one code path. Schedules a wake
every _INTERVAL_SECONDS and measures how late it actually fired; a
synchronous call anywhere in the process (a blocking Pillow op, a bad
`requests.get`, anything) delays every pending callback including this one,
so lag here is a direct read of loop responsiveness regardless of cause.

Started/stopped from the FastAPI lifespan (app/main.py), same pattern as
the cache warmer and pubsub listener.
"""

from __future__ import annotations

import asyncio
from typing import Any

try:
    from prometheus_client import Gauge

    event_loop_lag_seconds: Any = Gauge(
        "event_loop_lag_seconds",
        "How much longer than expected the last event-loop tick took to fire",
    )
    _METRICS_ENABLED = True
except ImportError:  # pragma: no cover - prometheus_client not installed

    class _NoOpMetric:
        def set(self, *args: Any, **kwargs: Any) -> None:
            pass

    event_loop_lag_seconds = _NoOpMetric()
    _METRICS_ENABLED = False

_INTERVAL_SECONDS = 0.5
_monitor_task: asyncio.Task[None] | None = None


async def _monitor_loop() -> None:
    loop = asyncio.get_running_loop()
    next_expected = loop.time() + _INTERVAL_SECONDS
    while True:
        await asyncio.sleep(_INTERVAL_SECONDS)
        now = loop.time()
        lag = max(0.0, now - next_expected)
        event_loop_lag_seconds.set(lag)
        next_expected = now + _INTERVAL_SECONDS


def start_event_loop_monitor() -> None:
    global _monitor_task
    if _monitor_task is None:
        _monitor_task = asyncio.create_task(_monitor_loop())


async def stop_event_loop_monitor() -> None:
    global _monitor_task
    if _monitor_task is not None:
        _monitor_task.cancel()
        try:
            await _monitor_task
        except asyncio.CancelledError:
            pass
        _monitor_task = None

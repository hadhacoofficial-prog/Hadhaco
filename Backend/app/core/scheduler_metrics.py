"""Generic periodic-job metrics — every job registered via
app/workers/queue.py's QueueService gets timed the same way, labeled by
job_id. Same optional-import no-op pattern as the other metrics modules."""

from __future__ import annotations

from typing import Any

try:
    from prometheus_client import Histogram

    scheduler_job_duration_seconds: Any = Histogram(
        "scheduler_job_duration_seconds",
        "Duration of one periodic background job tick",
        ["job_id"],
    )
    _METRICS_ENABLED = True
except ImportError:  # pragma: no cover - prometheus_client not installed

    class _NoOpMetric:
        def labels(self, *args: Any, **kwargs: Any) -> _NoOpMetric:
            return self

        def observe(self, *args: Any, **kwargs: Any) -> None:
            pass

    scheduler_job_duration_seconds = _NoOpMetric()
    _METRICS_ENABLED = False

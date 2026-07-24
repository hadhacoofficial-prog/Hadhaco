"""Image-pipeline metrics — registers on the default prometheus_client
registry, served at the existing /metrics endpoint (app/main.py), same
optional-import no-op pattern as app/modules/inventory/metrics.py.

Metric semantics:
  - image_processing_duration_seconds{preset,stage}: wall-clock time of one
    CPU-bound stage of the image pipeline, run on the dedicated executor
    (app/core/cpu_executor.py). `stage` is "validate" (upload/replace's
    validate_upload decode+verify), "probe" (the post-validation
    PILImage.open(...).size call), or "generate" (background.py's full
    decode->rotate->crop->mask->resize->encode pass for one image across
    all its breakpoints).
    (scheduler-wide job duration lives in app/core/scheduler_metrics.py,
    since it's not media-specific — every registered job gets it.)
"""

from __future__ import annotations

from typing import Any

try:
    from prometheus_client import Histogram

    image_processing_duration_seconds: Any = Histogram(
        "image_processing_duration_seconds",
        "CPU-bound image pipeline stage duration",
        ["preset", "stage"],
    )
    _METRICS_ENABLED = True
except ImportError:  # pragma: no cover - prometheus_client not installed

    class _NoOpMetric:
        def labels(self, *args: Any, **kwargs: Any) -> _NoOpMetric:
            return self

        def observe(self, *args: Any, **kwargs: Any) -> None:
            pass

    image_processing_duration_seconds = _NoOpMetric()
    _METRICS_ENABLED = False

"""Business metrics for the reservation/inventory domain.

Registers on the default prometheus_client registry, so these are
automatically served at the existing /metrics endpoint that
prometheus_fastapi_instrumentator already exposes (app/main.py) — no new
endpoint needed. Follows the same optional-import, no-op-if-unavailable
pattern used there, since prometheus_client is only a transitive dependency
(of prometheus_fastapi_instrumentator) rather than a direct one.

Metric semantics:
  - reservation_created_total: incremented once per genuinely NEW reservation
    row created by reserve_items (not reuse/quantity-delta updates).
  - reservation_released_total{reason}: incremented per reservation row
    released by release_order_reservations, labeled with the terminal status
    written (RELEASED/CANCELLED/PAYMENT_FAILED — EXPIRED is tracked
    separately below since it's worker-driven, not request-driven).
  - reservation_expired_total{was_checkout}: incremented per reservation
    reclaimed by the expiry worker, labeled by whether it was mid-checkout
    (CHECKOUT_IN_PROGRESS) or just an abandoned cart (ACTIVE) at expiry time.
  - checkout_started_total: incremented when a reservation enters
    CHECKOUT_IN_PROGRESS (Razorpay order accepted).
  - checkout_completed_total: incremented when complete_reservations_for_order
    resolves "fulfilled" (payment verified against a still-live reservation).
  - checkout_failed_total{reason}: incremented for the subset of
    release_order_reservations calls that represent a checkout not reaching
    fulfilment (PAYMENT_FAILED, CANCELLED) — narrower than
    reservation_released_total, which also counts pre-checkout/system-cleanup
    releases (RELEASED).
  - oversell_prevented_total: incremented every time reserve_items rejects a
    request because insufficient stock is available — a healthy nonzero rate
    under contention means the lock is doing its job, not a bug.
  - worker_duration_seconds / worker_failures_total: wrap the
    reservation_expiry background worker's tick.
  - inventory_adjustments_total{type}: incremented by InventoryService for
    manual restocks/adjustments.
"""

from __future__ import annotations

from typing import Any

try:
    from prometheus_client import Counter, Histogram

    # Explicit `Any` annotations: these names are reassigned to _NoOpMetric
    # instances in the except branch below when prometheus_client isn't
    # installed — the dual-mode (real metric | no-op) pattern is
    # intentional, so mypy is told the true type up front rather than
    # inferring the concrete Counter/Histogram type from this branch alone.
    reservation_created_total: Any = Counter(
        "reservation_created_total",
        "Reservations created via reserve_items",
    )
    reservation_released_total: Any = Counter(
        "reservation_released_total",
        "Reservations released via release_order_reservations",
        ["reason"],
    )
    reservation_expired_total: Any = Counter(
        "reservation_expired_total",
        "Reservations reclaimed by the expiry worker",
        ["was_checkout"],
    )
    checkout_started_total: Any = Counter(
        "checkout_started_total",
        "Reservations that entered CHECKOUT_IN_PROGRESS",
    )
    checkout_completed_total: Any = Counter(
        "checkout_completed_total",
        "Orders whose reservations completed (reserved -> sold) via payment verification",
    )
    checkout_failed_total: Any = Counter(
        "checkout_failed_total",
        "Checkouts that did not reach fulfilment",
        ["reason"],
    )
    oversell_prevented_total: Any = Counter(
        "oversell_prevented_total",
        "Reservation requests rejected due to insufficient available stock",
    )
    worker_duration_seconds: Any = Histogram(
        "reservation_worker_duration_seconds",
        "Duration of a single reservation_expiry worker tick",
    )
    worker_failures_total: Any = Counter(
        "reservation_worker_failures_total",
        "Reservation expiry worker ticks that raised an exception",
    )
    inventory_adjustments_total: Any = Counter(
        "inventory_adjustments_total",
        "Manual inventory adjustments/restocks recorded by InventoryService",
        ["type"],
    )
    _METRICS_ENABLED = True
except ImportError:  # pragma: no cover - prometheus_client not installed

    class _NoOpMetric:
        def labels(self, *args: Any, **kwargs: Any) -> _NoOpMetric:
            return self

        def inc(self, *args: Any, **kwargs: Any) -> None:
            pass

        def observe(self, *args: Any, **kwargs: Any) -> None:
            pass

        def time(self) -> Any:
            import contextlib

            return contextlib.nullcontext()

    reservation_created_total = _NoOpMetric()
    reservation_released_total = _NoOpMetric()
    reservation_expired_total = _NoOpMetric()
    checkout_started_total = _NoOpMetric()
    checkout_completed_total = _NoOpMetric()
    checkout_failed_total = _NoOpMetric()
    oversell_prevented_total = _NoOpMetric()
    worker_duration_seconds = _NoOpMetric()
    worker_failures_total = _NoOpMetric()
    inventory_adjustments_total = _NoOpMetric()
    _METRICS_ENABLED = False

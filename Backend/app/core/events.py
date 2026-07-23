"""
Internal event bus -- publish/subscribe for cross-module communication.

Business modules publish domain events; listener modules subscribe.
No module calls another module's service methods directly across boundaries.

Events are dispatched to:
  1. In-process listeners (notifications, analytics, etc.)
  2. Redis pub/sub (for SSE -> frontend synchronization)

Usage:
    # Publishing
    from app.core.events import event_bus
    await event_bus.publish(OrderCreatedEvent(order_id=..., user_id=...))

    # Subscribing (at module init time)
    from app.core.events import event_bus, BaseEvent
    @event_bus.subscribe(OrderCreatedEvent)
    async def on_order_created(event: OrderCreatedEvent) -> None:
        ...
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog

log = structlog.get_logger(__name__)


@dataclass
class BaseEvent:
    event_type: str = field(init=False)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        self.event_type = type(self).__name__


# ── Concrete domain events ─────────────────────────────────────────────────────


@dataclass
class UserRegisteredEvent(BaseEvent):
    user_id: str = ""
    email: str = ""
    full_name: str = ""


@dataclass
class OrderCreatedEvent(BaseEvent):
    order_id: str = ""
    user_id: str = ""
    order_number: str = ""
    total_amount: float = 0.0
    customer_email: str = ""
    customer_phone: str = ""


@dataclass
class PaymentCapturedEvent(BaseEvent):
    payment_id: str = ""
    order_id: str = ""
    user_id: str = ""
    amount: float = 0.0
    order_number: str = ""
    customer_email: str = ""
    customer_phone: str = ""


@dataclass
class PaymentFailedEvent(BaseEvent):
    payment_id: str = ""
    order_id: str = ""
    user_id: str = ""
    reason: str = ""


@dataclass
class OrderStatusChangedEvent(BaseEvent):
    order_id: str = ""
    user_id: str = ""
    old_status: str = ""
    new_status: str = ""
    order_number: str = ""


@dataclass
class OrderShippedEvent(BaseEvent):
    order_id: str = ""
    user_id: str = ""
    shipment_id: str = ""
    tracking_number: str = ""
    tracking_url: str = ""
    awb: str = ""
    order_number: str = ""
    customer_email: str = ""
    customer_phone: str = ""


@dataclass
class OrderDeliveredEvent(BaseEvent):
    order_id: str = ""
    user_id: str = ""
    order_number: str = ""
    customer_email: str = ""


@dataclass
class RefundCreatedEvent(BaseEvent):
    refund_id: str = ""
    order_id: str = ""
    user_id: str = ""
    amount: float = 0.0
    order_number: str = ""
    customer_email: str = ""


@dataclass
class RefundProcessedEvent(BaseEvent):
    refund_id: str = ""
    order_id: str = ""
    user_id: str = ""
    amount: float = 0.0
    order_number: str = ""
    customer_email: str = ""


@dataclass
class RefundFailedEvent(BaseEvent):
    refund_id: str = ""
    order_id: str = ""
    user_id: str = ""
    amount: float = 0.0
    order_number: str = ""
    reason: str = ""


@dataclass
class ReviewRequestEvent(BaseEvent):
    order_id: str = ""
    user_id: str = ""
    user_email: str = ""
    customer_email: str = ""
    order_number: str = ""


# -- New events for frontend synchronization -----------------------------------
# These events are published to Redis pub/sub for SSE -> frontend delivery.


@dataclass
class InventoryChangedEvent(BaseEvent):
    """Published when stock quantities change (purchase, reservation, admin update, refund)."""

    product_ids: list[str] = field(default_factory=list)


@dataclass
class ReservationCreatedEvent(BaseEvent):
    """Published when a checkout reservation is created."""

    reservation_id: str = ""
    user_id: str = ""


@dataclass
class ReservationExpiredEvent(BaseEvent):
    """Published when a reservation expires (background worker)."""

    reservation_id: str = ""
    user_ids: list[str] = field(default_factory=list)
    product_ids: list[str] = field(default_factory=list)


@dataclass
class ProductUpdatedEvent(BaseEvent):
    """Published when a product is updated (admin)."""

    product_id: str = ""


@dataclass
class PriceChangedEvent(BaseEvent):
    """Published when a product price changes."""

    product_id: str = ""
    old_price: float = 0.0
    new_price: float = 0.0


@dataclass
class CollectionUpdatedEvent(BaseEvent):
    """Published when a collection is updated (admin)."""

    collection_id: str = ""


@dataclass
class CmsPublishedEvent(BaseEvent):
    """Published when CMS content is published."""

    section_key: str = ""


# ── Event -> SSE event type mapping ────────────────────────────────────────────

_SSE_EVENT_MAP: dict[str, str] = {
    "InventoryChangedEvent": "inventory_changed",
    "OrderCreatedEvent": "order_created",
    "OrderStatusChangedEvent": "order_status_changed",
    "ReservationCreatedEvent": "reservation_created",
    "ReservationExpiredEvent": "reservation_expired",
    "ProductUpdatedEvent": "product_updated",
    "PriceChangedEvent": "price_changed",
    "CollectionUpdatedEvent": "collection_updated",
    "CmsPublishedEvent": "cms_published",
}


def _event_to_sse_payload(event: BaseEvent) -> dict[str, Any] | None:
    """Convert a domain event to an SSE-friendly payload."""
    sse_type = _SSE_EVENT_MAP.get(event.event_type)
    if not sse_type:
        return None
    payload: dict[str, Any] = {}
    for k, v in event.__dict__.items():
        if k in ("event_type", "occurred_at"):
            continue
        if v is not None and v != "" and v != [] and v != 0.0:
            payload[k] = v
    return {"event": sse_type, "payload": payload}


# ── Event bus ─────────────────────────────────────────────────────────────────

AsyncListener = Callable[[Any], Coroutine[Any, Any, None]]


class EventBus:
    def __init__(self) -> None:
        self._listeners: dict[type[BaseEvent], list[AsyncListener]] = defaultdict(list)

    def subscribe(self, event_class: type[BaseEvent]) -> Callable:
        """Decorator to register an async listener for an event type."""

        def decorator(fn: AsyncListener) -> AsyncListener:
            self._listeners[event_class].append(fn)
            return fn

        return decorator

    def on(self, event_class: type[BaseEvent], listener: AsyncListener) -> None:
        """Register a listener imperatively."""
        self._listeners[event_class].append(listener)

    async def publish(self, event: BaseEvent) -> None:
        """
        Schedule listeners as fire-and-forget background tasks.

        The caller does NOT wait for listeners to finish.  This is intentional:
        - The HTTP response returns immediately.
        - Email / shipment / analytics run in the background.
        - Each listener opens its own DB session, so there is no shared state.

        IMPORTANT: commit your DB session BEFORE calling publish() if listeners
        need to read data you just wrote, because they open fresh sessions and
        will only see committed rows.

        Additionally, frontend-relevant events are published to Redis pub/sub
        for SSE delivery to connected clients.
        """
        listeners = self._listeners.get(type(event), [])
        if listeners:
            for listener in listeners:
                asyncio.create_task(self._safe_call(listener, event))

        # Publish to Redis pub/sub for SSE -> frontend sync
        sse_payload = _event_to_sse_payload(event)
        if sse_payload:
            asyncio.create_task(self._publish_to_sse(sse_payload))

    @staticmethod
    async def _safe_call(listener: AsyncListener, event: BaseEvent) -> None:
        try:
            await listener(event)
        except Exception as exc:
            log.error(
                "event_listener_failed",
                event_type=event.event_type,
                listener=getattr(listener, "__qualname__", repr(listener)),
                error=str(exc),
            )

    @staticmethod
    async def _publish_to_sse(payload: dict[str, Any]) -> None:
        """Publish an event to Redis pub/sub for SSE delivery."""
        try:
            from app.core.pubsub import publish_sync_event

            await publish_sync_event(
                event_type=payload["event"],
                payload=payload.get("payload", {}),
            )
        except Exception as exc:
            log.error("sse_publish_failed", event=payload.get("event"), error=str(exc))


event_bus = EventBus()

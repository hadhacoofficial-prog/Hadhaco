"""
Internal event bus — publish/subscribe for cross-module communication.

Business modules publish domain events; listener modules subscribe.
No module calls another module's service methods directly across boundaries.

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
class LowInventoryAlertEvent(BaseEvent):
    product_id: str = ""
    product_name: str = ""
    sku: str = ""
    current_qty: int = 0
    quantity_after: int = 0
    threshold: int = 0


@dataclass
class ReviewRequestEvent(BaseEvent):
    order_id: str = ""
    user_id: str = ""
    user_email: str = ""
    customer_email: str = ""
    order_number: str = ""


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
        """
        listeners = self._listeners.get(type(event), [])
        if not listeners:
            return

        for listener in listeners:
            asyncio.create_task(self._safe_call(listener, event))

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


event_bus = EventBus()

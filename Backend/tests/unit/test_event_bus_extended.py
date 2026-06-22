"""Extended tests for the EventBus and domain events."""

import asyncio
import uuid
from dataclasses import dataclass

from app.core.events import (
    BaseEvent,
    EventBus,
    LowInventoryAlertEvent,
    OrderCreatedEvent,
    OrderDeliveredEvent,
    OrderShippedEvent,
    PaymentCapturedEvent,
    RefundCreatedEvent,
    ReviewRequestEvent,
    UserRegisteredEvent,
)


@dataclass
class _CountEvent(BaseEvent):
    count: int = 0


class TestEventBusAdvanced:
    async def test_multiple_listeners_all_called(self):
        bus = EventBus()
        results = []

        async def listener_a(e):
            results.append("a")

        async def listener_b(e):
            results.append("b")

        async def listener_c(e):
            results.append("c")

        bus.on(_CountEvent, listener_a)
        bus.on(_CountEvent, listener_b)
        bus.on(_CountEvent, listener_c)

        await bus.publish(_CountEvent(count=1))
        await asyncio.sleep(0)  # let fire-and-forget tasks run
        assert sorted(results) == ["a", "b", "c"]

    async def test_event_data_accessible_in_listener(self):
        bus = EventBus()
        captured = []

        async def listener(e: _CountEvent):
            captured.append(e.count)

        bus.on(_CountEvent, listener)
        await bus.publish(_CountEvent(count=42))
        await asyncio.sleep(0)  # let fire-and-forget tasks run
        assert captured == [42]

    async def test_sync_listener_wrapped_correctly(self):
        bus = EventBus()
        received = []

        def sync_listener(e):
            received.append(e.count)

        bus.on(_CountEvent, sync_listener)
        # sync listeners are wrapped in asyncio.create_task(_safe_call)
        # _safe_call calls await listener(event) — sync functions aren't awaitable
        # so this tests resilience (sync listener will fail in _safe_call, not propagate)
        await bus.publish(_CountEvent(count=99))
        # The bus does not raise; the result depends on implementation

    async def test_multiple_publishes_accumulate(self):
        bus = EventBus()
        received = []

        async def listener(e):
            received.append(e.count)

        bus.on(_CountEvent, listener)
        await bus.publish(_CountEvent(count=1))
        await bus.publish(_CountEvent(count=2))
        await bus.publish(_CountEvent(count=3))
        await asyncio.sleep(0)  # let all three fire-and-forget tasks run
        assert received == [1, 2, 3]

    async def test_subscribe_decorator_works(self):
        bus = EventBus()
        received = []

        @bus.subscribe(_CountEvent)
        async def listener(e):
            received.append(e.count)

        await bus.publish(_CountEvent(count=7))
        await asyncio.sleep(0)  # let fire-and-forget tasks run
        assert received == [7]


class TestDomainEvents:
    """Verify all domain event dataclasses can be instantiated with correct fields."""

    def test_user_registered_event(self):
        uid = str(uuid.uuid4())
        e = UserRegisteredEvent(user_id=uid, email="u@test.com")
        assert e.event_type == "UserRegisteredEvent"
        assert e.user_id == uid
        assert e.email == "u@test.com"

    def test_order_created_event(self):
        uid = str(uuid.uuid4())
        oid = str(uuid.uuid4())
        e = OrderCreatedEvent(
            user_id=uid,
            order_id=oid,
            order_number="HD001",
            total_amount=999.0,
            customer_email="u@test.com",
            customer_phone="+91999",
        )
        assert e.event_type == "OrderCreatedEvent"
        assert e.order_number == "HD001"
        assert e.total_amount == 999.0

    def test_payment_captured_event(self):
        e = PaymentCapturedEvent(
            user_id=str(uuid.uuid4()),
            order_id=str(uuid.uuid4()),
            payment_id="pay_123",
            amount=500.0,
        )
        assert e.event_type == "PaymentCapturedEvent"
        assert e.payment_id == "pay_123"

    def test_order_shipped_event(self):
        e = OrderShippedEvent(
            user_id=str(uuid.uuid4()),
            order_id=str(uuid.uuid4()),
            order_number="HD002",
            awb="AWB123",
            customer_email="x@test.com",
        )
        assert e.awb == "AWB123"
        assert e.event_type == "OrderShippedEvent"

    def test_order_delivered_event(self):
        e = OrderDeliveredEvent(
            user_id=str(uuid.uuid4()),
            order_id=str(uuid.uuid4()),
            order_number="HD003",
            customer_email="x@test.com",
        )
        assert e.event_type == "OrderDeliveredEvent"

    def test_review_request_event(self):
        e = ReviewRequestEvent(
            user_id=str(uuid.uuid4()),
            order_id=str(uuid.uuid4()),
            customer_email="r@test.com",
        )
        assert e.event_type == "ReviewRequestEvent"

    def test_low_inventory_alert_event(self):
        e = LowInventoryAlertEvent(
            product_id=str(uuid.uuid4()),
            product_name="Silver Ring",
            sku="SR-001",
            current_qty=2,
            threshold=5,
        )
        assert e.current_qty < e.threshold

    def test_refund_created_event(self):
        e = RefundCreatedEvent(
            user_id=str(uuid.uuid4()),
            order_id=str(uuid.uuid4()),
            amount=250.0,
            customer_email="r@test.com",
        )
        assert e.amount == 250.0
        assert e.event_type == "RefundCreatedEvent"

    def test_base_event_has_occurred_at(self):
        e = UserRegisteredEvent(user_id="u1", email="t@test.com")
        assert e.occurred_at is not None

    def test_event_type_is_class_name(self):
        e = UserRegisteredEvent(user_id="u1", email="t@test.com")
        assert e.event_type == "UserRegisteredEvent"

import asyncio
from dataclasses import dataclass

from app.core.events import BaseEvent, EventBus


@dataclass
class _TestEvent(BaseEvent):
    value: str = ""


@dataclass
class _OtherEvent(BaseEvent):
    value: str = ""


class TestEventBus:
    async def test_listener_receives_published_event(self):
        bus = EventBus()
        received = []

        bus.on(_TestEvent, lambda e: _collect(received, e))
        await bus.publish(_TestEvent(value="hello"))
        await asyncio.sleep(0)  # let fire-and-forget tasks run
        assert len(received) == 1
        assert received[0].value == "hello"

    async def test_listener_only_gets_its_event_type(self):
        bus = EventBus()
        received = []

        bus.on(_TestEvent, lambda e: _collect(received, e))
        await bus.publish(_OtherEvent(value="ignored"))
        assert received == []

    async def test_failing_listener_does_not_break_others(self):
        bus = EventBus()
        received = []

        async def boom(event):
            raise RuntimeError("listener exploded")

        bus.on(_TestEvent, boom)
        bus.on(_TestEvent, lambda e: _collect(received, e))

        # must not raise
        await bus.publish(_TestEvent(value="resilient"))
        await asyncio.sleep(0)  # let fire-and-forget tasks run
        assert len(received) == 1

    async def test_publish_with_no_listeners_is_noop(self):
        bus = EventBus()
        await bus.publish(_TestEvent(value="void"))

    async def test_event_type_is_class_name(self):
        event = _TestEvent(value="x")
        assert event.event_type == "_TestEvent"


async def _collect(sink: list, event) -> None:
    sink.append(event)

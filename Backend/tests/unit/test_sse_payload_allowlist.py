"""The public SSE stream must never carry customer contact data."""

from app.core.events import (
    OrderCreatedEvent,
    OrderStatusChangedEvent,
    PriceChangedEvent,
    _event_to_sse_payload,
)

_PII_KEYS = {"customer_email", "customer_phone", "order_number", "total_amount"}


def test_order_created_payload_excludes_contact_data():
    event = OrderCreatedEvent(
        order_id="o1",
        user_id="u1",
        order_number="ORD-1",
        total_amount=1999.0,
        customer_email="buyer@example.com",
        customer_phone="9999999999",
    )
    out = _event_to_sse_payload(event)
    assert out is not None and out["event"] == "order_created"
    assert out["payload"] == {"order_id": "o1", "user_id": "u1"}
    assert not (_PII_KEYS & set(out["payload"]))


def test_order_status_changed_payload_is_allowlisted():
    event = OrderStatusChangedEvent(
        order_id="o1",
        user_id="u1",
        old_status="confirmed",
        new_status="cancelled",
        order_number="ORD-1",
    )
    out = _event_to_sse_payload(event)
    assert out is not None
    assert out["payload"] == {
        "order_id": "o1",
        "user_id": "u1",
        "new_status": "cancelled",
    }


def test_public_catalog_event_keeps_its_fields():
    out = _event_to_sse_payload(
        PriceChangedEvent(product_id="p1", old_price=10.0, new_price=8.0)
    )
    assert out is not None
    assert out["payload"] == {"product_id": "p1", "old_price": 10.0, "new_price": 8.0}

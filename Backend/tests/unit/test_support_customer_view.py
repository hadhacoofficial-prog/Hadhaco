import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from app.modules.support.schemas import customer_view


def _msg(body: str, internal: bool):
    return SimpleNamespace(
        id=uuid.uuid4(),
        sender_id=uuid.uuid4(),
        body=body,
        is_internal=internal,
        created_at=datetime.now(UTC),
    )


def test_customer_view_strips_internal_notes():
    ticket = SimpleNamespace(
        id=uuid.uuid4(),
        ticket_number="T-1",
        subject="s",
        category="c",
        status="open",
        priority="normal",
        created_at=datetime.now(UTC),
        messages=[_msg("public reply", False), _msg("staff only note", True)],
    )
    out = customer_view(ticket)
    assert [m.body for m in out.messages] == ["public reply"]


def test_analytics_event_payload_is_bounded():
    import pytest
    from pydantic import ValidationError

    from app.modules.analytics.schemas import TrackEventRequest

    TrackEventRequest(event_type="page_view", metadata={"k": "v"})
    with pytest.raises(ValidationError):
        TrackEventRequest(event_type="x" * 65)
    with pytest.raises(ValidationError):
        TrackEventRequest(event_type="page_view", session_id="s" * 129)
    with pytest.raises(ValidationError):
        TrackEventRequest(event_type="page_view", metadata={"k": "v" * 5000})
    with pytest.raises(ValidationError):
        TrackEventRequest(
            event_type="page_view", metadata={str(i): 1 for i in range(51)}
        )

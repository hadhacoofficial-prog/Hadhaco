from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class TicketCreate(BaseModel):
    order_id: uuid.UUID | None = None
    subject: str
    category: str
    body: str


class MessageCreate(BaseModel):
    body: str
    is_internal: bool = False


class MessageOut(BaseModel):
    id: uuid.UUID
    sender_id: uuid.UUID
    body: str
    is_internal: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class TicketOut(BaseModel):
    id: uuid.UUID
    ticket_number: str
    subject: str
    category: str
    status: str
    priority: str
    created_at: datetime
    messages: list[MessageOut] = []
    model_config = {"from_attributes": True}


class AdminTicketUpdate(BaseModel):
    status: str | None = None
    priority: str | None = None
    assigned_to: uuid.UUID | None = None

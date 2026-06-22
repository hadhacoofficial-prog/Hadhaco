from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ReturnItemCreate(BaseModel):
    order_item_id: uuid.UUID
    quantity: int = Field(..., ge=1)
    reason: str | None = None


class ReturnCreate(BaseModel):
    order_id: uuid.UUID
    reason: str
    items: list[ReturnItemCreate]


class ReturnItemOut(BaseModel):
    id: uuid.UUID
    order_item_id: uuid.UUID
    quantity: int
    reason: str | None
    condition: str | None
    model_config = {"from_attributes": True}


class ReturnOut(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    status: str
    reason: str
    created_at: datetime
    items: list[ReturnItemOut] = []
    model_config = {"from_attributes": True}


class AdminReturnStatusUpdate(BaseModel):
    status: str
    admin_notes: str | None = None

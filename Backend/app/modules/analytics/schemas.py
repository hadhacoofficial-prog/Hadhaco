from __future__ import annotations
import uuid
from datetime import date
from typing import Any
from pydantic import BaseModel


class TrackEventRequest(BaseModel):
    event_type: str
    product_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    session_id: str | None = None
    metadata: dict[str, Any] = {}


class DashboardStats(BaseModel):
    revenue: dict[str, Any]
    orders: dict[str, Any]
    aov: dict[str, Any]
    conversion_rate: float
    top_products: list[dict[str, Any]]
    revenue_by_day: list[dict[str, Any]]
    orders_by_status: dict[str, int]

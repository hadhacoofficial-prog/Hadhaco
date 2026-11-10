from __future__ import annotations

import json
import uuid
from typing import Any

from pydantic import BaseModel, Field, field_validator

_MAX_METADATA_BYTES = 4096
_MAX_METADATA_KEYS = 50


class TrackEventRequest(BaseModel):
    """Anonymous, high-volume endpoint: every field is length/size bounded."""

    event_type: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")
    product_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    session_id: str | None = Field(default=None, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def _bound_metadata(cls, v: dict[str, Any]) -> dict[str, Any]:
        if len(v) > _MAX_METADATA_KEYS:
            raise ValueError(f"metadata may have at most {_MAX_METADATA_KEYS} keys")
        try:
            size = len(json.dumps(v, separators=(",", ":")).encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise ValueError("metadata must be JSON-serialisable") from exc
        if size > _MAX_METADATA_BYTES:
            raise ValueError(f"metadata exceeds {_MAX_METADATA_BYTES} bytes")
        return v


class DashboardStats(BaseModel):
    revenue: dict[str, Any]
    orders: dict[str, Any]
    aov: dict[str, Any]
    conversion_rate: float
    top_products: list[dict[str, Any]]
    revenue_by_day: list[dict[str, Any]]
    orders_by_status: dict[str, int]

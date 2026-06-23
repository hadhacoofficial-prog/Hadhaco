import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class ShipmentEventResponse(BaseModel):
    id: uuid.UUID
    status: str
    description: str | None
    location: str | None
    occurred_at: datetime

    model_config = {"from_attributes": True}


class ShipmentResponse(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    provider: str
    awb_number: str | None
    tracking_url: str | None
    status: str
    estimated_delivery: date | None
    delivered_at: datetime | None
    created_at: datetime
    updated_at: datetime
    events: list[ShipmentEventResponse] = []

    model_config = {"from_attributes": True}


class CreateShipmentRequest(BaseModel):
    courier: str = Field(..., min_length=1, max_length=100)
    tracking_number: str | None = Field(None, max_length=200)
    tracking_url: str | None = Field(None, max_length=500)
    estimated_delivery: date | None = None


class UpdateShipmentRequest(BaseModel):
    courier: str | None = Field(None, min_length=1, max_length=100)
    tracking_number: str | None = Field(None, max_length=200)
    tracking_url: str | None = Field(None, max_length=500)
    status: str | None = Field(
        None,
        pattern="^(created|picked_up|in_transit|out_for_delivery|delivered|cancelled|failed)$",
    )
    estimated_delivery: date | None = None


class ShippingRateResponse(BaseModel):
    provider: str
    service_name: str
    estimated_days: int
    charge: float
    is_recommended: bool


class TrackingResponse(BaseModel):
    courier: str | None
    tracking_number: str | None
    tracking_url: str | None
    status: str
    estimated_delivery: date | None
    created_at: datetime

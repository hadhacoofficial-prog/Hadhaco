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
    label_url: str | None
    status: str
    weight_grams: int | None
    estimated_delivery: date | None
    pickup_scheduled_at: datetime | None
    delivered_at: datetime | None
    created_at: datetime
    updated_at: datetime
    events: list[ShipmentEventResponse] = []

    model_config = {"from_attributes": True}


class CreateShipmentRequest(BaseModel):
    order_id: uuid.UUID
    weight_grams: int | None = Field(None, gt=0)
    length_cm: float | None = None
    width_cm: float | None = None
    height_cm: float | None = None


class ShippingRateResponse(BaseModel):
    provider: str
    service_name: str
    estimated_days: int
    charge: float
    is_recommended: bool


class TrackingResponse(BaseModel):
    awb_number: str
    status: str
    estimated_delivery: date | None
    events: list[ShipmentEventResponse]

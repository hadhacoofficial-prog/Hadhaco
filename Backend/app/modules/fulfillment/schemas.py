import uuid
from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ShippingProviderEnum(StrEnum):
    INDIA_POST = "india_post"
    DTDC = "dtdc"
    DELHIVERY = "delhivery"
    BLUE_DART = "blue_dart"
    XPRESSBEES = "xpressbees"
    SHADOWFAX = "shadowfax"
    EKART = "ekart"
    OTHER = "other"


class FulfillmentTimelineResponse(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    action: str
    actor_id: uuid.UUID | None
    admin_name: str | None
    details: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


class FulfillmentTimelineListResponse(BaseModel):
    timeline: list[FulfillmentTimelineResponse]


class ConfirmPaymentRequest(BaseModel):
    pass


class GenerateShippingLabelRequest(BaseModel):
    pass


class GeneratePackingSlipRequest(BaseModel):
    pass


class DispatchOrderRequest(BaseModel):
    shipping_provider: ShippingProviderEnum = Field(
        default=ShippingProviderEnum.INDIA_POST,
        description="Shipping provider for this dispatch",
    )
    tracking_number: str = Field(
        ..., min_length=1, max_length=100, description="AWB or tracking number"
    )
    dispatch_date: datetime | None = Field(
        None, description="When the package was dispatched (default: now)"
    )
    expected_delivery_date: date | None = Field(
        None, description="Expected delivery date (optional)"
    )
    dispatch_notes: str | None = Field(
        None, max_length=500, description="Optional dispatch notes"
    )


class UpdateFulfillmentStatusRequest(BaseModel):
    fulfillment_status: str = Field(
        ...,
        pattern="^(pending|packing|label_generated|dispatched|in_transit|delivered|cancelled|returned|refunded)$",
    )
    notes: str | None = None

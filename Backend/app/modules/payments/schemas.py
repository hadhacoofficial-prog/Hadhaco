import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PaymentResponse(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    razorpay_order_id: str
    razorpay_payment_id: str | None
    amount: float
    currency: str
    method: str | None
    status: str
    captured_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RefundRequest(BaseModel):
    amount: float | None = Field(
        None, gt=0, description="Partial refund amount. Omit for full refund."
    )
    reason: str | None = Field(None, max_length=500)


class RefundResponse(BaseModel):
    id: uuid.UUID
    payment_id: uuid.UUID
    order_id: uuid.UUID
    razorpay_refund_id: str | None
    amount: float
    reason: str | None
    status: str
    processed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}

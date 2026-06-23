import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class OrderItemResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID | None
    variant_id: uuid.UUID | None
    product_name: str
    product_sku: str
    variant_name: str | None
    unit_price: float
    quantity: int
    tax_rate: float
    tax_amount: float
    line_total: float

    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    id: uuid.UUID
    order_number: str
    user_id: uuid.UUID
    status: str
    payment_status: str
    shipping_full_name: str
    shipping_phone: str | None
    shipping_line1: str
    shipping_line2: str | None
    shipping_city: str
    shipping_state: str
    shipping_postal: str
    shipping_country: str
    billing_full_name: str | None
    billing_line1: str | None
    billing_city: str | None
    billing_state: str | None
    billing_postal: str | None
    subtotal: float
    tax_amount: float
    shipping_charge: float
    discount: float
    total: float
    coupon_code: str | None
    payment_method: str | None
    razorpay_order_id: str | None
    tracking_number: str | None
    estimated_delivery: date | None
    notes: str | None
    cancellation_reason: str | None
    cancelled_at: datetime | None
    delivered_at: datetime | None
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemResponse] = []

    model_config = {"from_attributes": True}


class OrderListItem(BaseModel):
    id: uuid.UUID
    order_number: str
    status: str
    payment_status: str
    total: float
    item_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderListResponse(BaseModel):
    items: list[OrderListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class CreateOrderRequest(BaseModel):
    shipping_address_id: uuid.UUID
    billing_address_id: uuid.UUID | None = None
    payment_method: str = Field(default="razorpay", pattern="^(razorpay|cod)$")
    coupon_code: str | None = None
    notes: str | None = Field(None, max_length=500)


class UpdateOrderStatusRequest(BaseModel):
    status: str = Field(
        ...,
        pattern="^(confirmed|processing|packed|shipped|delivered|cancelled|"
        "payment_failed|payment_expired|return_requested|returned|refunded)$",
    )
    cancellation_reason: str | None = None
    tracking_number: str | None = None
    shipping_provider: str | None = None
    estimated_delivery: date | None = None


class CancelOrderRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


# ── Razorpay direct checkout ──────────────────────────────────────────────────


class CreatePaymentIntentRequest(BaseModel):
    shipping_address_id: uuid.UUID
    billing_address_id: uuid.UUID | None = None
    coupon_code: str | None = None
    notes: str | None = Field(None, max_length=500)


class CreatePaymentIntentResponse(BaseModel):
    order_id: str
    razorpay_order_id: str
    amount: int  # paise (INR × 100)
    currency: str
    key: str


class VerifyOrderPaymentRequest(BaseModel):
    order_id: uuid.UUID
    razorpay_payment_id: str
    razorpay_order_id: str
    razorpay_signature: str


class VerifyOrderPaymentResponse(BaseModel):
    success: bool
    order_id: str
    order_number: str

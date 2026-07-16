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
    image_url: str | None
    unit_price: float
    quantity: int
    tax_rate: float
    tax_amount: float
    line_total: float
    # Post-delivery review reminder state — filled by OrderService.get_order
    # for customer views of DELIVERED orders only; None everywhere else.
    product_slug: str | None = None
    is_reviewed: bool | None = None
    review_id: uuid.UUID | None = None
    review_rating: int | None = None

    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    id: uuid.UUID
    order_number: str
    user_id: uuid.UUID
    status: str
    payment_status: str
    fulfillment_status: str
    shipping_full_name: str
    shipping_phone: str | None
    shipping_alternate_phone: str | None
    shipping_line1: str
    shipping_line2: str | None
    shipping_landmark: str | None
    shipping_city: str
    shipping_state: str
    shipping_postal: str
    shipping_country: str
    billing_full_name: str | None
    billing_phone: str | None
    billing_alternate_phone: str | None
    billing_line1: str | None
    billing_line2: str | None
    billing_landmark: str | None
    billing_city: str | None
    billing_state: str | None
    billing_postal: str | None
    billing_country: str | None
    subtotal: float
    tax_amount: float
    shipping_charge: float
    discount: float
    total: float
    coupon_code: str | None
    payment_method: str | None
    razorpay_order_id: str | None
    razorpay_payment_id: str | None
    shipping_provider: str | None
    tracking_number: str | None
    estimated_delivery: date | None
    complimentary_gift: str | None
    notes: str | None
    cancellation_reason: str | None
    cancelled_at: datetime | None
    delivered_at: datetime | None
    packed_at: datetime | None
    shipping_label_generated_at: datetime | None
    dispatched_at: datetime | None
    shipment_notes: str | None
    fulfilled_by: uuid.UUID | None
    last_fulfillment_action: str | None
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemResponse] = []

    model_config = {"from_attributes": True}


class OrderListItem(BaseModel):
    id: uuid.UUID
    order_number: str
    status: str
    payment_status: str
    fulfillment_status: str
    total: float
    item_count: int
    complimentary_gift: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderListResponse(BaseModel):
    items: list[OrderListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


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


COMPLIMENTARY_GIFT_VALUES = ("Traditional Sweet", "Traditional Hot Snack")


class SetComplimentaryGiftRequest(BaseModel):
    gift: str = Field(..., pattern="^(Traditional Sweet|Traditional Hot Snack)$")


# ── Active reservations (storefront) ─────────────────────────────────────────


class ActiveReservationItem(BaseModel):
    reservation_number: str
    product_id: uuid.UUID
    variant_id: uuid.UUID | None
    product_name: str
    variant_name: str | None
    quantity: int
    expires_at: datetime

    model_config = {"from_attributes": True}


class ActiveReservationResponse(BaseModel):
    items: list[ActiveReservationItem]

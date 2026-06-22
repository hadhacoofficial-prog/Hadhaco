import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CartItemResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    variant_id: uuid.UUID | None
    quantity: int
    unit_price: float
    line_total: float

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_with_total(cls, item) -> "CartItemResponse":
        return cls(
            id=item.id,
            product_id=item.product_id,
            variant_id=item.variant_id,
            quantity=item.quantity,
            unit_price=float(item.unit_price),
            line_total=round(float(item.unit_price) * item.quantity, 2),
        )


class CartSummary(BaseModel):
    id: uuid.UUID
    items: list[CartItemResponse]
    item_count: int
    subtotal: float
    tax_amount: float       # flat 3% GST — refined per-item in orders phase
    discount: float
    total: float
    coupon_code: str | None
    expires_at: datetime


class AddToCartRequest(BaseModel):
    product_id: uuid.UUID
    variant_id: uuid.UUID | None = None
    quantity: int = Field(default=1, ge=1, le=100)


class UpdateCartItemRequest(BaseModel):
    quantity: int = Field(..., ge=1, le=100)


class ApplyCouponRequest(BaseModel):
    coupon_code: str = Field(..., min_length=1, max_length=50)

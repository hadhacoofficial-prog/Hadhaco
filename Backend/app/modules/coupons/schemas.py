import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class CouponCreateRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    description: str | None = None
    coupon_type: str = Field(
        default="percentage", pattern="^(percentage|fixed_amount|free_shipping)$"
    )
    value: float = Field(..., gt=0)
    min_order_amount: float = Field(default=0.0, ge=0)
    max_discount: float | None = Field(None, gt=0)
    usage_limit: int | None = Field(None, gt=0)
    per_user_limit: int = Field(default=1, ge=1)
    is_active: bool = True
    valid_from: datetime | None = None
    valid_until: datetime | None = None

    @field_validator("code")
    @classmethod
    def upper_code(cls, v: str) -> str:
        return v.upper().strip()

    @field_validator("value")
    @classmethod
    def validate_percentage(cls, v: float, info) -> float:
        if info.data.get("coupon_type") == "percentage" and v > 100:
            raise ValueError("Percentage discount cannot exceed 100")
        return v


class CouponUpdateRequest(BaseModel):
    description: str | None = None
    value: float | None = Field(None, gt=0)
    min_order_amount: float | None = Field(None, ge=0)
    max_discount: float | None = None
    usage_limit: int | None = None
    per_user_limit: int | None = Field(None, ge=1)
    is_active: bool | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None


class CouponResponse(BaseModel):
    id: uuid.UUID
    code: str
    description: str | None
    coupon_type: str
    value: float
    min_order_amount: float
    max_discount: float | None
    usage_limit: int | None
    usage_count: int
    per_user_limit: int
    is_active: bool
    valid_from: datetime
    valid_until: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CouponValidateRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    order_subtotal: float = Field(..., gt=0)


class CouponValidateResponse(BaseModel):
    valid: bool
    discount_amount: float
    message: str
    coupon: CouponResponse | None = None

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

_STATUS_PATTERN = "^(active|inactive|draft)$"
_TYPE_PATTERN = "^(percentage|fixed_amount|free_shipping)$"


class CouponCreateRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    description: str | None = None
    coupon_type: str = Field(default="percentage", pattern=_TYPE_PATTERN)
    value: float = Field(..., gt=0)
    status: str = Field(default="active", pattern=_STATUS_PATTERN)

    # Validity
    valid_from: datetime | None = None
    valid_until: datetime | None = None

    # Order value
    min_order_amount: float = Field(default=0.0, ge=0)
    max_order_amount: float | None = Field(None, gt=0)
    max_discount: float | None = Field(None, gt=0)

    # Usage limits
    usage_limit: int | None = Field(None, gt=0)
    per_user_limit: int = Field(default=1, ge=1)
    one_time_per_customer: bool = False

    # Customer eligibility
    first_order_only: bool = False
    new_customer_only: bool = False
    returning_customer_only: bool = False

    # Product / category restrictions
    eligible_product_ids: list[str] | None = None
    eligible_collection_ids: list[str] | None = None
    eligible_category_slugs: list[str] | None = None
    excluded_product_ids: list[str] | None = None
    excluded_category_slugs: list[str] | None = None

    # Audience restrictions
    allowed_emails: list[str] | None = None
    allowed_phone_numbers: list[str] | None = None
    customer_groups: list[str] | None = None

    # Region restrictions
    allowed_states: list[str] | None = None
    allowed_cities: list[str] | None = None
    allowed_pincodes: list[str] | None = None

    # Method restrictions
    allowed_payment_methods: list[str] | None = None
    allowed_shipping_methods: list[str] | None = None

    # Campaign & stacking
    stackable: bool = True
    campaign_name: str | None = None

    # Backward-compat (derived from status)
    is_active: bool | None = None

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
    status: str | None = Field(None, pattern=_STATUS_PATTERN)
    is_active: bool | None = None
    value: float | None = Field(None, gt=0)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    min_order_amount: float | None = Field(None, ge=0)
    max_order_amount: float | None = None
    max_discount: float | None = None
    usage_limit: int | None = None
    per_user_limit: int | None = Field(None, ge=1)
    one_time_per_customer: bool | None = None
    first_order_only: bool | None = None
    new_customer_only: bool | None = None
    returning_customer_only: bool | None = None
    eligible_product_ids: list[str] | None = None
    eligible_collection_ids: list[str] | None = None
    eligible_category_slugs: list[str] | None = None
    excluded_product_ids: list[str] | None = None
    excluded_category_slugs: list[str] | None = None
    allowed_emails: list[str] | None = None
    allowed_phone_numbers: list[str] | None = None
    customer_groups: list[str] | None = None
    allowed_states: list[str] | None = None
    allowed_cities: list[str] | None = None
    allowed_pincodes: list[str] | None = None
    allowed_payment_methods: list[str] | None = None
    allowed_shipping_methods: list[str] | None = None
    stackable: bool | None = None
    campaign_name: str | None = None


class CouponResponse(BaseModel):
    id: uuid.UUID
    code: str
    description: str | None
    coupon_type: str
    value: float
    status: str
    is_active: bool
    valid_from: datetime
    valid_until: datetime | None
    min_order_amount: float
    max_order_amount: float | None
    max_discount: float | None
    usage_limit: int | None
    usage_count: int
    per_user_limit: int
    one_time_per_customer: bool
    first_order_only: bool
    new_customer_only: bool
    returning_customer_only: bool
    eligible_product_ids: list[str] | None
    eligible_collection_ids: list[str] | None
    eligible_category_slugs: list[str] | None
    excluded_product_ids: list[str] | None
    excluded_category_slugs: list[str] | None
    allowed_emails: list[str] | None
    allowed_phone_numbers: list[str] | None
    customer_groups: list[str] | None
    allowed_states: list[str] | None
    allowed_cities: list[str] | None
    allowed_pincodes: list[str] | None
    allowed_payment_methods: list[str] | None
    allowed_shipping_methods: list[str] | None
    stackable: bool
    campaign_name: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CouponValidateRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    order_subtotal: float = Field(..., gt=0)
    # Cart context for product/category restriction checks
    cart_product_ids: list[str] = Field(default_factory=list)
    cart_category_slugs: list[str] = Field(default_factory=list)
    # Checkout context for method/region checks
    payment_method: str | None = None
    shipping_method: str | None = None
    delivery_state: str | None = None
    delivery_city: str | None = None
    delivery_pincode: str | None = None


class CouponValidateResponse(BaseModel):
    valid: bool
    discount_amount: float
    message: str
    coupon: CouponResponse | None = None
    # Whether the coupon can be stacked with others
    stackable: bool = True

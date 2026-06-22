import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# ---------- Sub-schemas ----------


class ProductImageResponse(BaseModel):
    id: uuid.UUID
    url: str
    thumbnail_url: str | None
    medium_url: str | None
    alt_text: str | None
    is_primary: bool
    sort_order: int

    model_config = {"from_attributes": True}


class ProductVariantResponse(BaseModel):
    id: uuid.UUID
    sku: str
    name: str
    price_adjustment: float
    stock_quantity: int
    weight_grams: float | None
    is_active: bool
    sort_order: int

    model_config = {"from_attributes": True}


class ProductAttributeResponse(BaseModel):
    id: uuid.UUID
    name: str
    value: str
    sort_order: int

    model_config = {"from_attributes": True}


class ProductVariantCreateRequest(BaseModel):
    sku: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    price_adjustment: float = Field(default=0.0)
    stock_quantity: int = Field(default=0, ge=0)
    weight_grams: float | None = None
    is_active: bool = True
    sort_order: int = 0


class ProductAttributeCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    value: str = Field(..., min_length=1, max_length=500)
    sort_order: int = 0


# ---------- Product ----------


class ProductCreateRequest(BaseModel):
    sku: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    short_description: str | None = Field(None, max_length=500)

    category_id: uuid.UUID | None = None

    metal_type: str | None = None
    purity: str | None = None
    hallmark_number: str | None = None
    weight_grams: float | None = Field(None, gt=0)
    making_charges: float | None = Field(None, ge=0)
    wastage_percent: float | None = Field(None, ge=0, le=100)
    gender: str | None = None

    base_price: float = Field(..., gt=0)
    compare_at_price: float | None = Field(None, gt=0)
    cost_price: float | None = Field(None, gt=0)
    tax_rate: float = Field(default=3.0, ge=0, le=100)
    hsn_code: str | None = None

    track_inventory: bool = True
    allow_backorder: bool = False
    low_stock_threshold: int = Field(default=5, ge=0)
    stock_quantity: int = Field(default=0, ge=0)

    status: str = "draft"
    is_featured: bool = False
    is_new_arrival: bool = False
    is_best_seller: bool = False
    is_customizable: bool = False
    requires_shipping: bool = True

    length_cm: float | None = None
    width_cm: float | None = None
    height_cm: float | None = None

    meta_title: str | None = Field(None, max_length=255)
    meta_description: str | None = Field(None, max_length=500)
    meta_keywords: str | None = None

    variants: list[ProductVariantCreateRequest] = []
    attributes: list[ProductAttributeCreateRequest] = []

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        import re

        if not re.match(r"^[a-z0-9-]+$", v):
            raise ValueError(
                "slug must contain only lowercase letters, numbers, and hyphens"
            )
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"draft", "active", "archived"}
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}")
        return v


class ProductUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    slug: str | None = None
    description: str | None = None
    short_description: str | None = Field(None, max_length=500)
    category_id: uuid.UUID | None = None
    metal_type: str | None = None
    purity: str | None = None
    hallmark_number: str | None = None
    weight_grams: float | None = Field(None, gt=0)
    making_charges: float | None = Field(None, ge=0)
    wastage_percent: float | None = Field(None, ge=0, le=100)
    gender: str | None = None
    base_price: float | None = Field(None, gt=0)
    compare_at_price: float | None = None
    cost_price: float | None = None
    tax_rate: float | None = Field(None, ge=0, le=100)
    hsn_code: str | None = None
    track_inventory: bool | None = None
    allow_backorder: bool | None = None
    low_stock_threshold: int | None = Field(None, ge=0)
    status: str | None = None
    is_featured: bool | None = None
    is_new_arrival: bool | None = None
    is_best_seller: bool | None = None
    is_customizable: bool | None = None
    requires_shipping: bool | None = None
    length_cm: float | None = None
    width_cm: float | None = None
    height_cm: float | None = None
    meta_title: str | None = Field(None, max_length=255)
    meta_description: str | None = Field(None, max_length=500)
    meta_keywords: str | None = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str | None) -> str | None:
        if v is None:
            return v
        import re

        if not re.match(r"^[a-z0-9-]+$", v):
            raise ValueError(
                "slug must contain only lowercase letters, numbers, and hyphens"
            )
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is None:
            return v
        allowed = {"draft", "active", "archived"}
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}")
        return v


class ProductResponse(BaseModel):
    id: uuid.UUID
    sku: str
    name: str
    slug: str
    description: str | None
    short_description: str | None
    category_id: uuid.UUID | None
    metal_type: str | None
    purity: str | None
    hallmark_number: str | None
    weight_grams: float | None
    making_charges: float | None
    wastage_percent: float | None
    gender: str | None
    base_price: float
    compare_at_price: float | None
    cost_price: float | None
    tax_rate: float
    hsn_code: str | None
    track_inventory: bool
    allow_backorder: bool
    low_stock_threshold: int
    stock_quantity: int
    status: str
    is_featured: bool
    is_new_arrival: bool
    is_best_seller: bool
    is_customizable: bool
    requires_shipping: bool
    length_cm: float | None
    width_cm: float | None
    height_cm: float | None
    meta_title: str | None
    meta_description: str | None
    meta_keywords: str | None
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
    images: list[ProductImageResponse] = []
    variants: list[ProductVariantResponse] = []
    attributes: list[ProductAttributeResponse] = []

    model_config = {"from_attributes": True}


class ProductListItem(BaseModel):
    id: uuid.UUID
    sku: str
    name: str
    slug: str
    short_description: str | None
    category_id: uuid.UUID | None
    metal_type: str | None
    base_price: float
    compare_at_price: float | None
    stock_quantity: int
    status: str
    is_featured: bool
    is_new_arrival: bool
    is_best_seller: bool
    created_at: datetime
    primary_image: str | None = None

    model_config = {"from_attributes": True}


class ProductListResponse(BaseModel):
    items: list[ProductListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


# ---------- Stock adjustment ----------


class StockAdjustRequest(BaseModel):
    delta: int = Field(..., description="Positive to add, negative to subtract")
    reason: str | None = None


# ---------- Variant update ----------


class ProductVariantUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    price_adjustment: float | None = None
    stock_quantity: int | None = Field(None, ge=0)
    weight_grams: float | None = None
    is_active: bool | None = None
    sort_order: int | None = None

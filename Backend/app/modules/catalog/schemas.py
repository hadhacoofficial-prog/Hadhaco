import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.modules.media import storage
from app.modules.media.schemas import ImageVariantOut

# ---------- Sub-schemas ----------


class ProductCollectionRef(BaseModel):
    id: uuid.UUID
    name: str
    slug: str

    model_config = {"from_attributes": True}


def cache_busted_url(url: str | None, updated_at: datetime) -> str | None:
    """
    Append a `?v=<updated_at>` query param to *url*.

    Crop and replace overwrite the same R2 object key in place (by design,
    so re-cropping and re-editing always work from a stable path), which
    means the URL string never changes even though the underlying bytes
    do. Browsers and CDNs cache by URL, so without this every crop/replace
    would keep serving the stale, previously-cached image until a hard
    refresh. Tagging the URL with the row's `updated_at` makes it change
    exactly when the content does, with no effect on the stored object key.
    """
    if not url:
        return url
    version = int(updated_at.timestamp())
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}v={version}"


class ProductImageResponse(BaseModel):
    """
    Built from an app.modules.media.models.Image row (module='product') plus
    its variants — product images are no longer a bespoke table, they're
    `images`/`image_variants` rows like every other module. See
    docs/architecture/Universal_Responsive_Image_System_Design.md §9.
    """

    id: uuid.UUID
    url: str
    # The untouched original upload — the crop editor must reopen against
    # this, never a generated variant (closes the "Edit Crop shows the
    # already-cropped image" bug).
    original_url: str
    thumbnail_url: str | None
    medium_url: str | None
    large_url: str | None = None
    alt_text: str | None
    is_primary: bool
    sort_order: int
    crop_x: float | None = None
    crop_y: float | None = None
    crop_width: float | None = None
    crop_height: float | None = None
    crop_zoom: float | None = None
    crop_rotation: float | None = None
    updated_at: datetime
    # Every ready variant across every breakpoint (not just desktop) — lets
    # the storefront render a real responsive <picture>/srcset instead of
    # always downloading the desktop `large` file regardless of viewport.
    # `product.images` is already fully relationship-loaded per product
    # (see CatalogService.list_products), so this costs no extra query.
    variants: list[ImageVariantOut] = Field(default_factory=list)
    focus_point: dict[str, float] | None = None

    @classmethod
    def from_image(cls, image: Any) -> "ProductImageResponse":
        variants_by_name = {
            v.variant_name: v
            for v in image.variants
            if v.breakpoint == "desktop" and v.dpr == 1 and v.status == "ready"
        }
        original_variant = variants_by_name.get("large") or variants_by_name.get(
            "medium"
        )
        url = (
            original_variant.url
            if original_variant
            else storage.public_url(image.original_key)
        )
        thumbnail = variants_by_name.get("thumbnail")
        medium = variants_by_name.get("medium")
        large = variants_by_name.get("large")

        crop_box = (
            image.metadata_.get("crops", {}).get("desktop") if image.metadata_ else None
        )
        focus_point = image.metadata_.get("focus_point") if image.metadata_ else None

        return cls(
            id=image.id,
            url=cache_busted_url(url, image.updated_at) or url,
            original_url=storage.public_url(image.original_key),
            thumbnail_url=(
                cache_busted_url(thumbnail.url, image.updated_at) if thumbnail else None
            ),
            medium_url=(
                cache_busted_url(medium.url, image.updated_at) if medium else None
            ),
            large_url=cache_busted_url(large.url, image.updated_at) if large else None,
            alt_text=image.alt_text,
            is_primary=image.is_primary,
            sort_order=image.sort_order,
            crop_x=crop_box["box"]["x"] if crop_box else None,
            crop_y=crop_box["box"]["y"] if crop_box else None,
            crop_width=crop_box["box"]["width"] if crop_box else None,
            crop_height=crop_box["box"]["height"] if crop_box else None,
            crop_zoom=crop_box["zoom"] if crop_box else None,
            crop_rotation=crop_box["rotation"] if crop_box else None,
            updated_at=image.updated_at,
            variants=[
                ImageVariantOut(
                    id=v.id,
                    breakpoint=v.breakpoint,
                    variant_name=v.variant_name,
                    dpr=v.dpr,
                    format=v.format,
                    url=cache_busted_url(v.url, image.updated_at) or v.url,
                    width=v.width,
                    height=v.height,
                    status=v.status,
                    error_message=v.error_message,
                )
                for v in image.variants
                if v.status == "ready"
            ],
            focus_point=focus_point,
        )


class ProductVariantResponse(BaseModel):
    id: uuid.UUID
    sku: str
    name: str
    price_adjustment: float
    stock_quantity: int
    reserved_quantity: int
    sold_quantity: int
    available_stock: int
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
    max_order_quantity: int = Field(default=0, ge=0)

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
    collection_ids: list[uuid.UUID] = []

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
    max_order_quantity: int | None = Field(None, ge=0)
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
    collection_ids: list[uuid.UUID] | None = None

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
    reserved_quantity: int
    sold_quantity: int
    available_stock: int
    max_order_quantity: int
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
    average_rating: float | None = None
    review_count: int = 0
    images: list[ProductImageResponse] = []
    variants: list[ProductVariantResponse] = []
    attributes: list[ProductAttributeResponse] = []
    collections: list[ProductCollectionRef] = []

    model_config = {"from_attributes": True}

    @field_validator("images", mode="before")
    @classmethod
    def _build_images(cls, v: Any) -> Any:
        """
        `Product.images` (the ORM relationship) yields raw
        app.modules.media.models.Image rows, not dicts/ProductImageResponse
        instances — convert via from_image() before pydantic's normal
        from_attributes coercion runs, since Image's shape doesn't match
        ProductImageResponse's flat fields directly (variants live in a
        separate `variants` relationship, crop data in `metadata_` JSONB).
        """
        if v and hasattr(v[0], "variants") and hasattr(v[0], "metadata_"):
            return [ProductImageResponse.from_image(img) for img in v]
        return v


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
    available_stock: int
    status: str
    is_featured: bool
    is_new_arrival: bool
    is_best_seller: bool
    created_at: datetime
    primary_image: str | None = None
    secondary_image: str | None = None
    # Full responsive variant set (every breakpoint) for the primary image —
    # additive alongside `primary_image` (kept for any other existing
    # consumer) so the storefront grid can render a real srcset instead of
    # always downloading the desktop `large` file on every viewport
    # (docs audit HP-4/MP-1).
    primary_image_variants: list[ImageVariantOut] = Field(default_factory=list)
    primary_image_focus_point: dict[str, float] | None = None
    average_rating: float | None = None
    review_count: int = 0
    collections: list[ProductCollectionRef] = []

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
    variant_id: uuid.UUID | None = None
    reason: str | None = None


# ---------- Variant update ----------


class ProductVariantUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    price_adjustment: float | None = None
    stock_quantity: int | None = Field(None, ge=0)
    weight_grams: float | None = None
    is_active: bool | None = None
    sort_order: int | None = None

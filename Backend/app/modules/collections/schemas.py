import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CollectionCreateRequest(BaseModel):
    name: str = Field(max_length=200)
    slug: str | None = Field(default=None, max_length=200)
    description: str | None = None
    image_url: str | None = None
    is_active: bool = True
    is_featured: bool = False
    sort_order: int = 0
    seo_title: str | None = None
    seo_description: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class CollectionUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    slug: str | None = Field(default=None, max_length=200)
    description: str | None = None
    image_url: str | None = None
    is_active: bool | None = None
    is_featured: bool | None = None
    sort_order: int | None = None
    seo_title: str | None = None
    seo_description: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class CollectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    image_url: str | None
    is_active: bool
    is_featured: bool
    sort_order: int
    seo_title: str | None
    seo_description: str | None
    starts_at: datetime | None
    ends_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CollectionDetailResponse(CollectionResponse):
    product_count: int = 0


class CollectionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    image_url: str | None
    is_active: bool
    is_featured: bool
    sort_order: int
    product_count: int = 0
    updated_at: datetime


class CollectionListResponse(BaseModel):
    items: list[CollectionListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class AddProductsToCollectionRequest(BaseModel):
    product_ids: list[uuid.UUID]


class ReorderProductsRequest(BaseModel):
    product_ids: list[uuid.UUID]


class CollectionProductItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sku: str
    name: str
    slug: str
    category_id: uuid.UUID | None
    base_price: float
    stock_quantity: int
    status: str
    is_featured: bool
    primary_image: str | None = None
    sort_order: int = 0


class BulkActionRequest(BaseModel):
    ids: list[uuid.UUID]
    action: str = Field(pattern="^(delete|activate|deactivate|feature|unfeature)$")

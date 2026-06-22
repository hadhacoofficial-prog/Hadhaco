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


class AddProductsToCollectionRequest(BaseModel):
    product_ids: list[uuid.UUID]

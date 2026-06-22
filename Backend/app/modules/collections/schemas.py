import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CollectionCreateRequest(BaseModel):
    name: str = Field(max_length=200)
    slug: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = None
    image_url: Optional[str] = None
    is_active: bool = True
    is_featured: bool = False
    sort_order: int = 0
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None


class CollectionUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    slug: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = None
    image_url: Optional[str] = None
    is_active: Optional[bool] = None
    is_featured: Optional[bool] = None
    sort_order: Optional[int] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None


class CollectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    description: Optional[str]
    image_url: Optional[str]
    is_active: bool
    is_featured: bool
    sort_order: int
    seo_title: Optional[str]
    seo_description: Optional[str]
    starts_at: Optional[datetime]
    ends_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class AddProductsToCollectionRequest(BaseModel):
    product_ids: list[uuid.UUID]

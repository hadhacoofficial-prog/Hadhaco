import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CategoryBase(BaseModel):
    name: str = Field(max_length=200)
    slug: str = Field(max_length=200)
    description: str | None = None
    image_url: str | None = None
    sort_order: int = 0
    is_active: bool = True
    seo_title: str | None = None
    seo_description: str | None = None
    parent_id: uuid.UUID | None = None


class CategoryCreateRequest(CategoryBase):
    pass


class CategoryUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    slug: str | None = Field(default=None, max_length=200)
    description: str | None = None
    image_url: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None
    seo_title: str | None = None
    seo_description: str | None = None
    parent_id: uuid.UUID | None = None


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    slug: str
    description: str | None
    image_url: str | None
    sort_order: int
    is_active: bool
    seo_title: str | None
    seo_description: str | None
    created_at: datetime
    updated_at: datetime


class CategoryTreeNode(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    slug: str
    image_url: str | None
    sort_order: int
    product_count: int = 0
    children: list["CategoryTreeNode"] = []


class NavbarCategoriesResponse(BaseModel):
    """Navbar-optimised response: categories pre-grouped by gender slug."""

    women: list[CategoryTreeNode] = []
    men: list[CategoryTreeNode] = []
    unisex: list[CategoryTreeNode] = []
    kids: list[CategoryTreeNode] = []


class NavCategoryItem(BaseModel):
    """Lean, flat category item for the navigation endpoint."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    image_url: str | None = None


class NavigationCategoriesResponse(BaseModel):
    """Response for GET /categories/navigation.

    Only active categories that have at least one active product are included,
    grouped by their parent gender slug.
    """

    women: list[NavCategoryItem] = []
    men: list[NavCategoryItem] = []
    unisex: list[NavCategoryItem] = []
    kids: list[NavCategoryItem] = []

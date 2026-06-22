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
    slug: str | None = Field(default=None, max_length=200)  # type: ignore[assignment]


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


class CategoryDetailResponse(CategoryResponse):
    product_count: int = 0
    children_count: int = 0


class CategoryAdminListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    slug: str
    image_url: str | None
    sort_order: int
    is_active: bool
    product_count: int = 0
    children_count: int = 0
    updated_at: datetime


class CategoryAdminListResponse(BaseModel):
    items: list[CategoryAdminListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


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


class CategoryProductItem(BaseModel):
    id: uuid.UUID
    sku: str
    name: str
    slug: str
    base_price: float
    stock_quantity: int
    status: str
    is_featured: bool
    primary_image: str | None = None


class CategoryProductsResponse(BaseModel):
    items: list[CategoryProductItem]
    total: int
    page: int
    page_size: int
    total_pages: int


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


class GenderMeta(BaseModel):
    """Metadata for a top-level gender category (Women / Men / Unisex / Kids)."""

    id: uuid.UUID
    name: str
    slug: str
    image_url: str | None = None
    sort_order: int = 0


class NavigationCategoriesResponse(BaseModel):
    """Response for GET /categories/navigation."""

    women: list[NavCategoryItem] = []
    men: list[NavCategoryItem] = []
    unisex: list[NavCategoryItem] = []
    kids: list[NavCategoryItem] = []
    # Top-level gender category metadata (id, slug, image_url, sort_order)
    gender_meta: dict[str, GenderMeta] = {}


class BulkCategoryActionRequest(BaseModel):
    ids: list[uuid.UUID]
    action: str = Field(pattern="^(delete|activate|deactivate)$")

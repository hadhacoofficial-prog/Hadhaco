import uuid
from typing import Any

from slugify import slugify
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.modules.categories.models import Category
from app.modules.categories.repository import CategoryRepository
from app.modules.categories.schemas import (
    CategoryCreateRequest,
    CategoryTreeNode,
    CategoryUpdateRequest,
    NavbarCategoriesResponse,
    NavCategoryItem,
    NavigationCategoriesResponse,
)

# Maps the parent-category slug in the DB to the gender key used in the API response.
# Add "shop-unisex": "unisex" here once that parent category is seeded.
_GENDER_SLUG_MAP: dict[str, str] = {
    "shop-women": "women",
    "shop-men": "men",
    "shop-unisex": "unisex",
    "shop-kids": "kids",
}


class CategoryService:
    def __init__(self) -> None:
        self._repo = CategoryRepository()

    async def get_tree(self, db: AsyncSession) -> list[CategoryTreeNode]:
        all_cats = await self._repo.list_all_active(db)
        return _build_tree(all_cats, parent_id=None)

    async def get_navbar(self, db: AsyncSession) -> NavbarCategoriesResponse:
        """Return categories pre-grouped by gender slug for the navbar endpoint."""
        all_cats = await self._repo.list_all_active(db)
        tree = _build_tree(all_cats, parent_id=None)

        buckets: dict[str, list[CategoryTreeNode]] = {
            "women": [],
            "men": [],
            "unisex": [],
            "kids": [],
        }
        for node in tree:
            gender = _GENDER_SLUG_MAP.get(node.slug)
            if gender:
                buckets[gender] = node.children

        return NavbarCategoriesResponse(**buckets)

    async def get_navigation(self, db: AsyncSession) -> NavigationCategoriesResponse:
        """Return lean categories grouped by gender for GET /categories/navigation.

        All active child categories are included. The product-count filter is
        intentionally omitted here so the nav works during catalogue setup — once
        products exist, inactive/empty categories will be removed via is_active instead.
        Cached in Redis for 24 h by the router.
        """
        all_cats = await self._repo.list_all_active(db)
        tree = _build_tree(all_cats, parent_id=None)

        buckets: dict[str, list[NavCategoryItem]] = {
            "women": [],
            "men": [],
            "unisex": [],
            "kids": [],
        }
        for node in tree:
            gender = _GENDER_SLUG_MAP.get(node.slug)
            if gender:
                buckets[gender] = [
                    NavCategoryItem(
                        id=child.id,
                        name=child.name,
                        slug=child.slug,
                        image_url=child.image_url,
                    )
                    for child in node.children
                ]

        return NavigationCategoriesResponse(**buckets)

    async def get_by_slug(self, db: AsyncSession, slug: str) -> Category:
        cat = await self._repo.get_by_slug(db, slug)
        if not cat:
            raise NotFoundError(f"Category '{slug}' not found")
        return cat

    async def create(
        self, db: AsyncSession, data: CategoryCreateRequest, actor_id: str
    ) -> Category:
        slug = data.slug or slugify(data.name)
        existing = await self._repo.get_by_slug(db, slug)
        if existing:
            raise ConflictError(f"Category slug '{slug}' already exists")
        payload: dict[str, Any] = {**data.model_dump(exclude_none=True), "slug": slug}
        return await self._repo.create(db, payload)

    async def update(
        self, db: AsyncSession, cat_id: str | uuid.UUID, data: CategoryUpdateRequest
    ) -> Category:
        cat = await self._repo.get_by_id(db, cat_id)
        if not cat:
            raise NotFoundError("Category not found")
        payload = data.model_dump(exclude_none=True)
        if "name" in payload and "slug" not in payload:
            payload["slug"] = slugify(payload["name"])
        if "slug" in payload:
            existing = await self._repo.get_by_slug(db, payload["slug"])
            if existing and str(existing.id) != str(cat_id):
                raise ConflictError(f"Slug '{payload['slug']}' already taken")
        return await self._repo.update(db, cat_id, payload)  # type: ignore[return-value]

    async def delete(self, db: AsyncSession, cat_id: str | uuid.UUID) -> None:
        cat = await self._repo.get_by_id(db, cat_id)
        if not cat:
            raise NotFoundError("Category not found")
        if await self._repo.has_active_products(db, cat_id):
            raise ConflictError("Cannot delete a category that has active products")
        await self._repo.soft_delete(db, cat_id)


def _build_tree(
    cats: list[Category], parent_id: uuid.UUID | None
) -> list[CategoryTreeNode]:
    nodes = []
    for c in cats:
        if c.parent_id == parent_id:
            node = CategoryTreeNode(
                id=c.id,
                parent_id=c.parent_id,
                name=c.name,
                slug=c.slug,
                image_url=c.image_url,
                sort_order=c.sort_order,
            )
            node.children = _build_tree(cats, parent_id=c.id)
            nodes.append(node)
    return sorted(nodes, key=lambda n: n.sort_order)

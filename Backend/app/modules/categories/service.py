import uuid
from typing import Any

from slugify import slugify
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.modules.categories.models import Category
from app.modules.categories.repository import CategoryRepository
from app.modules.categories.schemas import (
    BulkCategoryActionRequest,
    CategoryAdminListResponse,
    CategoryAdminListItem,
    CategoryCreateRequest,
    CategoryDetailResponse,
    CategoryProductItem,
    CategoryProductsResponse,
    CategoryResponse,
    CategoryTreeNode,
    CategoryUpdateRequest,
    GenderMeta,
    NavbarCategoriesResponse,
    NavCategoryItem,
    NavigationCategoriesResponse,
)

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
        all_cats = await self._repo.list_all_active(db)
        tree = _build_tree(all_cats, parent_id=None)

        buckets: dict[str, list[NavCategoryItem]] = {
            "women": [],
            "men": [],
            "unisex": [],
            "kids": [],
        }
        gender_meta: dict[str, GenderMeta] = {}

        for node in tree:
            gender = _GENDER_SLUG_MAP.get(node.slug)
            if gender:
                gender_meta[gender] = GenderMeta(
                    id=node.id,
                    name=node.name,
                    slug=node.slug,
                    image_url=node.image_url,
                    sort_order=node.sort_order,
                )
                buckets[gender] = [
                    NavCategoryItem(
                        id=child.id,
                        name=child.name,
                        slug=child.slug,
                        image_url=child.image_url,
                    )
                    for child in node.children
                ]

        return NavigationCategoriesResponse(**buckets, gender_meta=gender_meta)

    async def get_by_slug(self, db: AsyncSession, slug: str) -> Category:
        cat = await self._repo.get_by_slug(db, slug)
        if not cat:
            raise NotFoundError(f"Category '{slug}' not found")
        return cat

    async def get_detail(
        self, db: AsyncSession, cat_id: str | uuid.UUID
    ) -> CategoryDetailResponse:
        cat = await self._repo.get_by_id(db, cat_id)
        if not cat:
            raise NotFoundError("Category not found")
        product_count = await self._repo.get_product_count(db, cat_id)
        children_count = await self._repo.get_children_count(db, cat_id)
        result = CategoryDetailResponse.model_validate(cat)
        result.product_count = product_count
        result.children_count = children_count
        return result

    async def list_admin(
        self,
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 50,
        search: str | None = None,
        parent_id: uuid.UUID | None = None,
        is_active: bool | None = None,
    ) -> CategoryAdminListResponse:
        rows, total = await self._repo.list_admin(
            db,
            page=page,
            page_size=page_size,
            search=search,
            parent_id=parent_id,
            is_active=is_active,
        )
        items = [CategoryAdminListItem.model_validate(dict(r)) for r in rows]
        return CategoryAdminListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=max(1, (total + page_size - 1) // page_size),
        )

    async def get_products(
        self,
        db: AsyncSession,
        cat_id: str | uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> CategoryProductsResponse:
        cat = await self._repo.get_by_id(db, cat_id)
        if not cat:
            raise NotFoundError("Category not found")
        rows, total = await self._repo.get_products(
            db, cat_id, page=page, page_size=page_size
        )
        items = [CategoryProductItem.model_validate(dict(r)) for r in rows]
        return CategoryProductsResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=max(1, (total + page_size - 1) // page_size),
        )

    async def move_product(
        self,
        db: AsyncSession,
        product_id: uuid.UUID,
        category_id: uuid.UUID,
    ) -> None:
        cat = await self._repo.get_by_id(db, category_id)
        if not cat:
            raise NotFoundError("Target category not found")
        await self._repo.move_product_to_category(db, product_id, category_id)

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
        if await self._repo.has_children(db, cat_id):
            raise ConflictError(
                "Cannot delete a category that has subcategories. Delete subcategories first."
            )
        await self._repo.soft_delete(db, cat_id)

    async def bulk_action(
        self, db: AsyncSession, payload: BulkCategoryActionRequest
    ) -> None:
        if payload.action == "delete":
            await self._repo.bulk_soft_delete(db, payload.ids)
        elif payload.action == "activate":
            await self._repo.bulk_set_active(db, payload.ids, True)
        elif payload.action == "deactivate":
            await self._repo.bulk_set_active(db, payload.ids, False)


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

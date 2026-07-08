import uuid
from collections.abc import Sequence

from slugify import slugify
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.modules.collections.repository import CollectionRepository
from app.modules.collections.schemas import (
    AddProductsToCollectionRequest,
    BulkActionRequest,
    CollectionCreateRequest,
    CollectionDetailResponse,
    CollectionListItem,
    CollectionListResponse,
    CollectionProductItem,
    CollectionResponse,
    CollectionUpdateRequest,
    ReorderProductsRequest,
)
from app.modules.media.repository import ImageRepository

_repo = CollectionRepository()
_image_repo = ImageRepository()


async def _attach_image_urls(
    db: AsyncSession, items: Sequence[CollectionResponse | CollectionListItem]
) -> None:
    """Resolve each collection's primary image into a cache-busted `image_url`
    — replaces the plain `image_url` column dropped in the Phase 3 cutover.
    get_primary_variant_urls looks up by owner_id (the collection's own id),
    not by primary_image_id (which is the Image row's id)."""
    ids = [i.id for i in items if i.primary_image_id]
    if not ids:
        return
    urls = await _image_repo.get_primary_variant_urls(db, "collection", ids)
    for item in items:
        if item.primary_image_id:
            item.image_url = urls.get(item.id)


class CollectionService:
    async def list_active(self, db: AsyncSession) -> list[CollectionResponse]:
        cols = await _repo.list_active(db)
        results = [CollectionResponse.model_validate(c) for c in cols]
        await _attach_image_urls(db, results)
        return results

    async def list_admin(
        self,
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        is_active: bool | None = None,
        is_featured: bool | None = None,
        sort_by: str = "sort_order",
        sort_dir: str = "asc",
    ) -> CollectionListResponse:
        rows, total = await _repo.list_admin(
            db,
            page=page,
            page_size=page_size,
            search=search,
            is_active=is_active,
            is_featured=is_featured,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        items = [CollectionListItem.model_validate(r) for r in rows]
        await _attach_image_urls(db, items)
        return CollectionListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=max(1, (total + page_size - 1) // page_size),
        )

    async def get_by_slug(self, db: AsyncSession, slug: str) -> CollectionResponse:
        col = await _repo.get_by_slug(db, slug)
        if not col:
            raise NotFoundError("Collection not found")
        result = CollectionResponse.model_validate(col)
        await _attach_image_urls(db, [result])
        return result

    async def get_detail(
        self, db: AsyncSession, col_id: uuid.UUID
    ) -> CollectionDetailResponse:
        col = await _repo.get_by_id(db, col_id)
        if not col:
            raise NotFoundError("Collection not found")
        count = await _repo.get_product_count(db, col_id)
        data = CollectionDetailResponse.model_validate(col)
        data.product_count = count
        await _attach_image_urls(db, [data])
        return data

    async def create(
        self, db: AsyncSession, payload: CollectionCreateRequest
    ) -> CollectionDetailResponse:
        slug = payload.slug or slugify(payload.name)
        existing = await _repo.get_by_slug(db, slug)
        if existing:
            raise ConflictError("Collection with this slug already exists")
        data = payload.model_dump()
        data["slug"] = slug
        col = await _repo.create(db, data)
        result = CollectionDetailResponse.model_validate(col)
        result.product_count = 0
        return result

    async def update(
        self,
        db: AsyncSession,
        col_id: uuid.UUID,
        payload: CollectionUpdateRequest,
    ) -> CollectionDetailResponse:
        existing = await _repo.get_by_id(db, col_id)
        if not existing:
            raise NotFoundError("Collection not found")

        data = payload.model_dump(exclude_unset=True)

        if "name" in data and "slug" not in data:
            data["slug"] = slugify(data["name"])

        if "slug" in data and data["slug"] != existing.slug:
            slug_conflict = await _repo.get_by_slug(db, data["slug"])
            if slug_conflict:
                raise ConflictError("Collection with this slug already exists")

        col = await _repo.update(db, col_id, data)
        count = await _repo.get_product_count(db, col_id)
        result = CollectionDetailResponse.model_validate(col)
        result.product_count = count
        await _attach_image_urls(db, [result])
        return result

    async def delete(self, db: AsyncSession, col_id: uuid.UUID) -> None:
        existing = await _repo.get_by_id(db, col_id)
        if not existing:
            raise NotFoundError("Collection not found")
        await _repo.soft_delete(db, col_id)

    async def bulk_action(self, db: AsyncSession, payload: BulkActionRequest) -> None:
        if payload.action == "delete":
            await _repo.bulk_soft_delete(db, payload.ids)
        elif payload.action == "activate":
            await _repo.bulk_set_active(db, payload.ids, True)
        elif payload.action == "deactivate":
            await _repo.bulk_set_active(db, payload.ids, False)
        elif payload.action == "feature":
            await _repo.bulk_set_featured(db, payload.ids, True)
        elif payload.action == "unfeature":
            await _repo.bulk_set_featured(db, payload.ids, False)

    async def add_products(
        self,
        db: AsyncSession,
        col_id: uuid.UUID,
        payload: AddProductsToCollectionRequest,
    ) -> None:
        existing = await _repo.get_by_id(db, col_id)
        if not existing:
            raise NotFoundError("Collection not found")
        await _repo.add_products(db, col_id, payload.product_ids)

    async def remove_product(
        self, db: AsyncSession, col_id: uuid.UUID, product_id: uuid.UUID
    ) -> None:
        existing = await _repo.get_by_id(db, col_id)
        if not existing:
            raise NotFoundError("Collection not found")
        await _repo.remove_product(db, col_id, product_id)

    async def reorder_products(
        self,
        db: AsyncSession,
        col_id: uuid.UUID,
        payload: ReorderProductsRequest,
    ) -> None:
        existing = await _repo.get_by_id(db, col_id)
        if not existing:
            raise NotFoundError("Collection not found")
        await _repo.reorder_products(db, col_id, payload.product_ids)

    async def get_products(
        self,
        db: AsyncSession,
        col_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[CollectionProductItem], int]:
        existing = await _repo.get_by_id(db, col_id)
        if not existing:
            raise NotFoundError("Collection not found")
        rows, total = await _repo.get_products_in_collection(
            db, col_id, page=page, page_size=page_size
        )
        items = [CollectionProductItem.model_validate(dict(r)) for r in rows]
        return items, total

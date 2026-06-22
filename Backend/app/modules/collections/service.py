import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.modules.collections.repository import CollectionRepository
from app.modules.collections.schemas import (
    AddProductsToCollectionRequest,
    CollectionCreateRequest,
    CollectionResponse,
    CollectionUpdateRequest,
)

_repo = CollectionRepository()


class CollectionService:

    async def list_active(self, db: AsyncSession) -> list[CollectionResponse]:
        cols = await _repo.list_active(db)
        return [CollectionResponse.model_validate(c) for c in cols]

    async def get_by_slug(self, db: AsyncSession, slug: str) -> CollectionResponse:
        col = await _repo.get_by_slug(db, slug)
        if not col:
            raise NotFoundError("Collection not found")
        return CollectionResponse.model_validate(col)

    async def create(
        self, db: AsyncSession, payload: CollectionCreateRequest
    ) -> CollectionResponse:
        existing = await _repo.get_by_slug(db, payload.slug)
        if existing:
            raise ConflictError("Collection with this slug already exists")
        col = await _repo.create(db, payload.model_dump())
        return CollectionResponse.model_validate(col)

    async def update(
        self,
        db: AsyncSession,
        col_id: uuid.UUID,
        payload: CollectionUpdateRequest,
    ) -> CollectionResponse:
        existing = await _repo.get_by_id(db, col_id)
        if not existing:
            raise NotFoundError("Collection not found")

        data = payload.model_dump(exclude_unset=True)

        if "slug" in data and data["slug"] != existing.slug:
            slug_conflict = await _repo.get_by_slug(db, data["slug"])
            if slug_conflict:
                raise ConflictError("Collection with this slug already exists")

        col = await _repo.update(db, col_id, data)
        return CollectionResponse.model_validate(col)

    async def delete(self, db: AsyncSession, col_id: uuid.UUID) -> None:
        existing = await _repo.get_by_id(db, col_id)
        if not existing:
            raise NotFoundError("Collection not found")
        await _repo.soft_delete(db, col_id)

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

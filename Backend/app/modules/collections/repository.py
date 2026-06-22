import uuid
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.collections.models import Collection, ProductCollection


class CollectionRepository:

    async def get_by_id(self, db: AsyncSession, col_id: str | uuid.UUID) -> Collection | None:
        result = await db.execute(
            select(Collection).where(Collection.id == col_id, Collection.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, db: AsyncSession, slug: str) -> Collection | None:
        result = await db.execute(
            select(Collection).where(Collection.slug == slug, Collection.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list_active(self, db: AsyncSession) -> list[Collection]:
        result = await db.execute(
            select(Collection)
            .where(Collection.is_active.is_(True), Collection.deleted_at.is_(None))
            .order_by(Collection.sort_order.asc(), Collection.name.asc())
        )
        return list(result.scalars().all())

    async def create(self, db: AsyncSession, data: dict[str, Any]) -> Collection:
        col = Collection(**data)
        db.add(col)
        await db.flush()
        await db.refresh(col)
        return col

    async def update(self, db: AsyncSession, col_id: str | uuid.UUID, data: dict[str, Any]) -> Collection | None:
        await db.execute(update(Collection).where(Collection.id == col_id).values(**data))
        return await self.get_by_id(db, col_id)

    async def soft_delete(self, db: AsyncSession, col_id: str | uuid.UUID) -> None:
        from datetime import UTC, datetime, timezone
        await db.execute(
            update(Collection).where(Collection.id == col_id)
            .values(deleted_at=datetime.now(UTC), is_active=False)
        )

    async def add_products(self, db: AsyncSession, col_id: uuid.UUID, product_ids: list[uuid.UUID]) -> None:
        for pid in product_ids:
            # Upsert via INSERT ... ON CONFLICT DO NOTHING
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = pg_insert(ProductCollection).values(
                product_id=pid, collection_id=col_id, sort_order=0
            ).on_conflict_do_nothing()
            await db.execute(stmt)

    async def remove_product(self, db: AsyncSession, col_id: uuid.UUID, product_id: uuid.UUID) -> None:
        await db.execute(
            delete(ProductCollection).where(
                ProductCollection.collection_id == col_id,
                ProductCollection.product_id == product_id,
            )
        )

    async def get_product_ids(self, db: AsyncSession, col_id: uuid.UUID) -> list[uuid.UUID]:
        result = await db.execute(
            select(ProductCollection.product_id)
            .where(ProductCollection.collection_id == col_id)
            .order_by(ProductCollection.sort_order.asc())
        )
        return list(result.scalars().all())

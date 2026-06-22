import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.categories.models import Category


class CategoryRepository:
    async def get_by_id(self, db: AsyncSession, cat_id: str | uuid.UUID) -> Category | None:
        result = await db.execute(
            select(Category).where(Category.id == cat_id, Category.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, db: AsyncSession, slug: str) -> Category | None:
        result = await db.execute(
            select(Category).where(Category.slug == slug, Category.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list_all_active(self, db: AsyncSession) -> list[Category]:
        result = await db.execute(
            select(Category)
            .where(Category.is_active.is_(True), Category.deleted_at.is_(None))
            .order_by(Category.sort_order.asc(), Category.name.asc())
        )
        return list(result.scalars().all())

    async def create(self, db: AsyncSession, data: dict[str, Any]) -> Category:
        cat = Category(**data)
        db.add(cat)
        await db.flush()
        await db.refresh(cat)
        return cat

    async def update(
        self, db: AsyncSession, cat_id: str | uuid.UUID, data: dict[str, Any]
    ) -> Category | None:
        await db.execute(update(Category).where(Category.id == cat_id).values(**data))
        return await self.get_by_id(db, cat_id)

    async def soft_delete(self, db: AsyncSession, cat_id: str | uuid.UUID) -> None:
        from datetime import UTC, datetime

        await db.execute(
            update(Category)
            .where(Category.id == cat_id)
            .values(deleted_at=datetime.now(UTC), is_active=False)
        )

    async def has_active_products(self, db: AsyncSession, cat_id: str | uuid.UUID) -> bool:
        # Avoid circular import — use raw SQL text
        from sqlalchemy import text

        result = await db.execute(
            text(
                "SELECT 1 FROM products WHERE category_id = :cid AND deleted_at IS NULL AND status = 'active' LIMIT 1"
            ),
            {"cid": str(cat_id)},
        )
        return result.first() is not None

    async def get_category_ids_with_products(self, db: AsyncSession) -> set[str]:
        """Return the set of category IDs (as str) that have at least one active product.
        Single query — avoids N+1 when building the navigation tree.
        Uses raw SQL to avoid a circular import with the catalog module.
        """
        from sqlalchemy import text

        result = await db.execute(
            text(
                "SELECT DISTINCT category_id::text FROM products "
                "WHERE deleted_at IS NULL AND status = 'active' AND category_id IS NOT NULL"
            )
        )
        return {row[0] for row in result.fetchall()}

import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.categories.models import Category


class CategoryRepository:
    async def get_by_id(
        self, db: AsyncSession, cat_id: str | uuid.UUID
    ) -> Category | None:
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

    async def list_admin(
        self,
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 50,
        search: str | None = None,
        parent_id: uuid.UUID | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return flat list of all categories (for admin), with product/children counts."""
        from sqlalchemy import text

        filter_clauses = ["c.deleted_at IS NULL"]
        params: dict[str, Any] = {
            "limit": page_size,
            "offset": (page - 1) * page_size,
        }

        if search:
            filter_clauses.append("(c.name ILIKE :search OR c.slug ILIKE :search)")
            params["search"] = f"%{search}%"
        if parent_id is not None:
            filter_clauses.append("c.parent_id = :parent_id")
            params["parent_id"] = str(parent_id)
        if is_active is not None:
            filter_clauses.append("c.is_active = :is_active")
            params["is_active"] = is_active

        where = " AND ".join(filter_clauses)

        count_result = await db.execute(
            text(f"SELECT COUNT(*) FROM categories c WHERE {where}"),
            {k: v for k, v in params.items() if k not in ("limit", "offset")},
        )
        total = count_result.scalar_one()

        rows_result = await db.execute(
            text(f"""
                SELECT
                    c.id, c.parent_id, c.name, c.slug, c.image_url,
                    c.sort_order, c.is_active, c.updated_at,
                    COALESCE(pc.product_count, 0) AS product_count,
                    COALESCE(cc.children_count, 0) AS children_count
                FROM categories c
                LEFT JOIN (
                    SELECT category_id, COUNT(*) AS product_count
                    FROM products
                    WHERE deleted_at IS NULL
                    GROUP BY category_id
                ) pc ON pc.category_id = c.id
                LEFT JOIN (
                    SELECT parent_id, COUNT(*) AS children_count
                    FROM categories
                    WHERE deleted_at IS NULL
                    GROUP BY parent_id
                ) cc ON cc.parent_id = c.id
                WHERE {where}
                ORDER BY c.sort_order ASC, c.name ASC
                LIMIT :limit OFFSET :offset
            """),
            params,
        )
        rows = rows_result.mappings().all()
        return list(rows), total

    async def get_product_count(self, db: AsyncSession, cat_id: str | uuid.UUID) -> int:
        from sqlalchemy import text

        result = await db.execute(
            text(
                "SELECT COUNT(*) FROM products WHERE category_id = :cid AND deleted_at IS NULL"
            ),
            {"cid": str(cat_id)},
        )
        return result.scalar_one()

    async def get_children_count(
        self, db: AsyncSession, cat_id: str | uuid.UUID
    ) -> int:
        result = await db.execute(
            select(func.count(Category.id)).where(
                Category.parent_id == cat_id, Category.deleted_at.is_(None)
            )
        )
        return result.scalar_one()

    async def has_children(self, db: AsyncSession, cat_id: str | uuid.UUID) -> bool:
        result = await db.execute(
            select(func.count(Category.id)).where(
                Category.parent_id == cat_id, Category.deleted_at.is_(None)
            )
        )
        return result.scalar_one() > 0

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

    async def bulk_soft_delete(
        self, db: AsyncSession, cat_ids: list[uuid.UUID]
    ) -> None:
        from datetime import UTC, datetime

        await db.execute(
            update(Category)
            .where(Category.id.in_(cat_ids), Category.deleted_at.is_(None))
            .values(deleted_at=datetime.now(UTC), is_active=False)
        )

    async def bulk_set_active(
        self, db: AsyncSession, cat_ids: list[uuid.UUID], is_active: bool
    ) -> None:
        await db.execute(
            update(Category)
            .where(Category.id.in_(cat_ids), Category.deleted_at.is_(None))
            .values(is_active=is_active)
        )

    async def has_active_products(
        self, db: AsyncSession, cat_id: str | uuid.UUID
    ) -> bool:
        from sqlalchemy import text

        result = await db.execute(
            text(
                "SELECT 1 FROM products WHERE category_id = :cid AND deleted_at IS NULL AND status = 'active' LIMIT 1"
            ),
            {"cid": str(cat_id)},
        )
        return result.first() is not None

    async def get_category_ids_with_products(self, db: AsyncSession) -> set[str]:
        from sqlalchemy import text

        result = await db.execute(
            text(
                "SELECT DISTINCT category_id::text FROM products "
                "WHERE deleted_at IS NULL AND status = 'active' AND category_id IS NOT NULL"
            )
        )
        return {row[0] for row in result.fetchall()}

    async def get_products(
        self,
        db: AsyncSession,
        cat_id: str | uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Any], int]:
        from sqlalchemy import text

        count_result = await db.execute(
            text(
                "SELECT COUNT(*) FROM products WHERE category_id = :cid AND deleted_at IS NULL"
            ),
            {"cid": str(cat_id)},
        )
        total = count_result.scalar_one()

        rows_result = await db.execute(
            text("""
                SELECT
                    p.id, p.sku, p.name, p.slug,
                    p.base_price, p.stock_quantity, p.status, p.is_featured,
                    (SELECT pi.url FROM product_images pi
                     WHERE pi.product_id = p.id AND pi.is_primary = TRUE
                     LIMIT 1) AS primary_image
                FROM products p
                WHERE p.category_id = :cid AND p.deleted_at IS NULL
                ORDER BY p.created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            {
                "cid": str(cat_id),
                "limit": page_size,
                "offset": (page - 1) * page_size,
            },
        )
        rows = rows_result.mappings().all()
        return list(rows), total

    async def move_product_to_category(
        self,
        db: AsyncSession,
        product_id: uuid.UUID,
        category_id: uuid.UUID | None,
    ) -> None:
        from sqlalchemy import text

        await db.execute(
            text(
                "UPDATE products SET category_id = :cat_id WHERE id = :pid AND deleted_at IS NULL"
            ),
            {
                "cat_id": str(category_id) if category_id else None,
                "pid": str(product_id),
            },
        )

import uuid
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.collections.models import Collection, ProductCollection


class CollectionRepository:
    async def get_by_id(
        self, db: AsyncSession, col_id: str | uuid.UUID
    ) -> Collection | None:
        result = await db.execute(
            select(Collection).where(
                Collection.id == col_id, Collection.deleted_at.is_(None)
            )
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, db: AsyncSession, slug: str) -> Collection | None:
        result = await db.execute(
            select(Collection).where(
                Collection.slug == slug, Collection.deleted_at.is_(None)
            )
        )
        return result.scalar_one_or_none()

    async def list_active(self, db: AsyncSession) -> list[Collection]:
        result = await db.execute(
            select(Collection)
            .where(Collection.is_active.is_(True), Collection.deleted_at.is_(None))
            .order_by(Collection.sort_order.asc(), Collection.name.asc())
        )
        return list(result.scalars().all())

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
    ) -> tuple[list[dict[str, Any]], int]:
        """Return paginated list with product_count."""
        from sqlalchemy import case, cast, Integer, literal_column

        pc_subq = (
            select(
                ProductCollection.collection_id,
                func.count(ProductCollection.product_id).label("cnt"),
            )
            .group_by(ProductCollection.collection_id)
            .subquery()
        )

        filters = [Collection.deleted_at.is_(None)]
        if search:
            term = f"%{search}%"
            filters.append(
                Collection.name.ilike(term)
                | Collection.slug.ilike(term)
                | Collection.description.ilike(term)
                | Collection.seo_title.ilike(term)
            )
        if is_active is not None:
            filters.append(Collection.is_active == is_active)
        if is_featured is not None:
            filters.append(Collection.is_featured == is_featured)

        col_map = {
            "sort_order": Collection.sort_order,
            "name": Collection.name,
            "updated_at": Collection.updated_at,
            "created_at": Collection.created_at,
        }
        order_col = col_map.get(sort_by, Collection.sort_order)
        order_expr = order_col.asc() if sort_dir == "asc" else order_col.desc()

        count_q = select(func.count()).select_from(Collection).where(*filters)
        total = (await db.execute(count_q)).scalar_one()

        q = (
            select(
                Collection,
                func.coalesce(pc_subq.c.cnt, 0).label("product_count"),
            )
            .outerjoin(pc_subq, pc_subq.c.collection_id == Collection.id)
            .where(*filters)
            .order_by(order_expr)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await db.execute(q)).all()
        return (
            [
                {
                    **{
                        c.key: getattr(row.Collection, c.key)
                        for c in Collection.__table__.columns
                    },
                    "product_count": row.product_count,
                }
                for row in rows
            ],
            total,
        )

    async def get_product_count(self, db: AsyncSession, col_id: uuid.UUID) -> int:
        result = await db.execute(
            select(func.count(ProductCollection.product_id)).where(
                ProductCollection.collection_id == col_id
            )
        )
        return result.scalar_one()

    async def create(self, db: AsyncSession, data: dict[str, Any]) -> Collection:
        col = Collection(**data)
        db.add(col)
        await db.flush()
        await db.refresh(col)
        return col

    async def update(
        self, db: AsyncSession, col_id: str | uuid.UUID, data: dict[str, Any]
    ) -> Collection | None:
        await db.execute(
            update(Collection).where(Collection.id == col_id).values(**data)
        )
        return await self.get_by_id(db, col_id)

    async def soft_delete(self, db: AsyncSession, col_id: str | uuid.UUID) -> None:
        from datetime import UTC, datetime

        await db.execute(
            update(Collection)
            .where(Collection.id == col_id)
            .values(deleted_at=datetime.now(UTC), is_active=False)
        )

    async def bulk_soft_delete(
        self, db: AsyncSession, col_ids: list[uuid.UUID]
    ) -> None:
        from datetime import UTC, datetime

        await db.execute(
            update(Collection)
            .where(Collection.id.in_(col_ids), Collection.deleted_at.is_(None))
            .values(deleted_at=datetime.now(UTC), is_active=False)
        )

    async def bulk_set_active(
        self, db: AsyncSession, col_ids: list[uuid.UUID], is_active: bool
    ) -> None:
        await db.execute(
            update(Collection)
            .where(Collection.id.in_(col_ids), Collection.deleted_at.is_(None))
            .values(is_active=is_active)
        )

    async def bulk_set_featured(
        self, db: AsyncSession, col_ids: list[uuid.UUID], is_featured: bool
    ) -> None:
        await db.execute(
            update(Collection)
            .where(Collection.id.in_(col_ids), Collection.deleted_at.is_(None))
            .values(is_featured=is_featured)
        )

    async def add_products(
        self, db: AsyncSession, col_id: uuid.UUID, product_ids: list[uuid.UUID]
    ) -> None:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        # Determine starting sort_order
        max_order_result = await db.execute(
            select(func.coalesce(func.max(ProductCollection.sort_order), -1)).where(
                ProductCollection.collection_id == col_id
            )
        )
        base_order = max_order_result.scalar_one() + 1

        for i, pid in enumerate(product_ids):
            stmt = (
                pg_insert(ProductCollection)
                .values(
                    product_id=pid, collection_id=col_id, sort_order=base_order + i
                )
                .on_conflict_do_nothing()
            )
            await db.execute(stmt)

    async def remove_product(
        self, db: AsyncSession, col_id: uuid.UUID, product_id: uuid.UUID
    ) -> None:
        await db.execute(
            delete(ProductCollection).where(
                ProductCollection.collection_id == col_id,
                ProductCollection.product_id == product_id,
            )
        )

    async def reorder_products(
        self, db: AsyncSession, col_id: uuid.UUID, product_ids: list[uuid.UUID]
    ) -> None:
        for i, pid in enumerate(product_ids):
            await db.execute(
                update(ProductCollection)
                .where(
                    ProductCollection.collection_id == col_id,
                    ProductCollection.product_id == pid,
                )
                .values(sort_order=i)
            )

    async def get_product_ids(
        self, db: AsyncSession, col_id: uuid.UUID
    ) -> list[uuid.UUID]:
        result = await db.execute(
            select(ProductCollection.product_id)
            .where(ProductCollection.collection_id == col_id)
            .order_by(ProductCollection.sort_order.asc())
        )
        return list(result.scalars().all())

    async def get_products_in_collection(
        self,
        db: AsyncSession,
        col_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Any], int]:
        """Return paginated products in a collection with sort_order."""
        from sqlalchemy import text

        count_result = await db.execute(
            select(func.count(ProductCollection.product_id)).where(
                ProductCollection.collection_id == col_id
            )
        )
        total = count_result.scalar_one()

        q = await db.execute(
            text("""
                SELECT
                    p.id, p.sku, p.name, p.slug, p.category_id,
                    p.base_price, p.stock_quantity, p.status, p.is_featured,
                    pc.sort_order,
                    (SELECT pi.url FROM product_images pi
                     WHERE pi.product_id = p.id AND pi.is_primary = TRUE
                     LIMIT 1) AS primary_image
                FROM product_collections pc
                JOIN products p ON p.id = pc.product_id
                WHERE pc.collection_id = :col_id AND p.deleted_at IS NULL
                ORDER BY pc.sort_order ASC
                LIMIT :limit OFFSET :offset
            """),
            {
                "col_id": str(col_id),
                "limit": page_size,
                "offset": (page - 1) * page_size,
            },
        )
        rows = q.mappings().all()
        return list(rows), total

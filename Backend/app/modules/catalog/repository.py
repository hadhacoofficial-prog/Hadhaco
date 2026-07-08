import uuid
from typing import Any

from sqlalchemy import ColumnElement, and_, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.catalog.models import (
    Product,
    ProductAttribute,
    ProductVariant,
)
from app.modules.media.models import Image


class ProductRepository:
    def _base_query(self, include_deleted: bool = False):
        q = select(Product).options(
            selectinload(Product.images).selectinload(Image.variants),
            selectinload(Product.variants),
            selectinload(Product.attributes),
        )
        if not include_deleted:
            q = q.where(Product.deleted_at.is_(None))
        return q

    async def get_by_id(
        self, db: AsyncSession, product_id: uuid.UUID, include_deleted: bool = False
    ) -> Product | None:
        q = self._base_query(include_deleted).where(Product.id == product_id)
        result = await db.execute(q)
        return result.scalar_one_or_none()

    async def get_by_slug(self, db: AsyncSession, slug: str) -> Product | None:
        q = self._base_query().where(Product.slug == slug)
        result = await db.execute(q)
        return result.scalar_one_or_none()

    async def get_by_sku(self, db: AsyncSession, sku: str) -> Product | None:
        result = await db.execute(
            select(Product).where(Product.sku == sku, Product.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_collections_for_product(
        self, db: AsyncSession, product_id: uuid.UUID
    ) -> list:
        from app.modules.collections.models import Collection, ProductCollection

        result = await db.execute(
            select(Collection)
            .join(ProductCollection, ProductCollection.collection_id == Collection.id)
            .where(
                ProductCollection.product_id == product_id,
                Collection.deleted_at.is_(None),
            )
            .order_by(ProductCollection.sort_order)
        )
        return list(result.scalars().all())

    async def get_collections_for_products(
        self, db: AsyncSession, product_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list]:
        if not product_ids:
            return {}
        from app.modules.collections.models import Collection, ProductCollection

        result = await db.execute(
            select(ProductCollection.product_id, Collection)
            .join(Collection, ProductCollection.collection_id == Collection.id)
            .where(
                ProductCollection.product_id.in_(product_ids),
                Collection.deleted_at.is_(None),
            )
            .order_by(ProductCollection.product_id, ProductCollection.sort_order)
        )
        mapping: dict[uuid.UUID, list] = {}
        for pid, col in result.all():
            mapping.setdefault(pid, []).append(col)
        return mapping

    async def list_paginated(
        self,
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        category_id: uuid.UUID | None = None,
        collection_id: uuid.UUID | None = None,
        metal_type: str | None = None,
        gender: str | None = None,
        is_featured: bool | None = None,
        is_new_arrival: bool | None = None,
        is_best_seller: bool | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        search: str | None = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        include_deleted: bool = False,
    ) -> tuple[list[Product], int]:
        filters: list[ColumnElement[bool]] = []
        if not include_deleted:
            filters.append(Product.deleted_at.is_(None))
        if status:
            filters.append(Product.status == status)
        if category_id:
            filters.append(Product.category_id == category_id)
        if collection_id:
            from app.modules.collections.models import ProductCollection

            filters.append(
                Product.id.in_(
                    select(ProductCollection.product_id).where(
                        ProductCollection.collection_id == collection_id
                    )
                )
            )
        if metal_type:
            filters.append(Product.metal_type == metal_type)
        if gender:
            filters.append(Product.gender == gender)
        if is_featured is not None:
            filters.append(Product.is_featured == is_featured)
        if is_new_arrival is not None:
            filters.append(Product.is_new_arrival == is_new_arrival)
        if is_best_seller is not None:
            filters.append(Product.is_best_seller == is_best_seller)
        if min_price is not None:
            filters.append(Product.base_price >= min_price)
        if max_price is not None:
            filters.append(Product.base_price <= max_price)
        if search:
            # search_vector (GIN-indexed, trigger-maintained from name/
            # short_description/description/metal_type/purity/meta_keywords)
            # replaces leading-wildcard ILIKE on name/description, which
            # can't use any index. sku is NOT part of the tsvector — it's
            # a short, separately-indexed code, so it keeps its own ILIKE.
            filters.append(
                or_(
                    Product.search_vector.op("@@")(
                        func.plainto_tsquery("english", search)
                    ),
                    Product.sku.ilike(f"%{search}%"),
                )
            )

        base_q = select(Product).where(and_(*filters)) if filters else select(Product)

        count_q = (
            select(func.count(Product.id)).where(and_(*filters))
            if filters
            else select(func.count(Product.id))
        )
        total_result = await db.execute(count_q)
        total: int = total_result.scalar_one()

        sort_col = getattr(Product, sort_by, Product.created_at)
        order = sort_col.desc() if sort_dir == "desc" else sort_col.asc()

        list_q = (
            base_q.options(
                selectinload(Product.images).selectinload(Image.variants),
                selectinload(Product.variants),
            )
            .order_by(order)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(list_q)
        return list(result.scalars().all()), total

    async def create(self, db: AsyncSession, data: dict[str, Any]) -> Product:
        product = Product(**data)
        db.add(product)
        await db.flush()
        await db.refresh(product)
        return product

    async def update(
        self, db: AsyncSession, product_id: uuid.UUID, data: dict[str, Any]
    ) -> Product | None:
        await db.execute(update(Product).where(Product.id == product_id).values(**data))
        return await self.get_by_id(db, product_id)

    async def soft_delete(self, db: AsyncSession, product_id: uuid.UUID) -> None:
        from datetime import UTC, datetime

        await db.execute(
            update(Product)
            .where(Product.id == product_id)
            .values(deleted_at=datetime.now(UTC), status="archived")
        )

    # Image CRUD is no longer owned by this repository — every image
    # operation (upload/crop/replace/reorder/delete/set-primary) goes
    # through ImageRepository / UniversalImageService
    # (app.modules.media), which own the universal images/image_variants
    # tables. `Product.images` above remains available read-only for
    # convenience in list/detail queries.

    # ---------- Variants ----------

    async def add_variant(
        self, db: AsyncSession, data: dict[str, Any]
    ) -> ProductVariant:
        variant = ProductVariant(**data)
        db.add(variant)
        await db.flush()
        await db.refresh(variant)
        return variant

    async def get_variant(
        self, db: AsyncSession, variant_id: uuid.UUID
    ) -> ProductVariant | None:
        result = await db.execute(
            select(ProductVariant).where(ProductVariant.id == variant_id)
        )
        return result.scalar_one_or_none()

    async def update_variant(
        self, db: AsyncSession, variant_id: uuid.UUID, data: dict[str, Any]
    ) -> ProductVariant | None:
        await db.execute(
            update(ProductVariant).where(ProductVariant.id == variant_id).values(**data)
        )
        return await self.get_variant(db, variant_id)

    async def delete_variant(self, db: AsyncSession, variant_id: uuid.UUID) -> bool:
        result = await db.execute(
            select(ProductVariant).where(ProductVariant.id == variant_id)
        )
        v = result.scalar_one_or_none()
        if not v:
            return False
        await db.delete(v)
        return True

    # ---------- Attributes ----------

    async def upsert_attribute(
        self,
        db: AsyncSession,
        product_id: uuid.UUID,
        name: str,
        value: str,
        sort_order: int = 0,
    ) -> ProductAttribute:
        result = await db.execute(
            select(ProductAttribute).where(
                ProductAttribute.product_id == product_id,
                ProductAttribute.name == name,
            )
        )
        attr = result.scalar_one_or_none()
        if attr:
            attr.value = value
            attr.sort_order = sort_order
        else:
            attr = ProductAttribute(
                id=uuid.uuid4(),
                product_id=product_id,
                name=name,
                value=value,
                sort_order=sort_order,
            )
            db.add(attr)
        await db.flush()
        return attr

    async def delete_attribute(
        self, db: AsyncSession, product_id: uuid.UUID, name: str
    ) -> bool:
        result = await db.execute(
            select(ProductAttribute).where(
                ProductAttribute.product_id == product_id,
                ProductAttribute.name == name,
            )
        )
        attr = result.scalar_one_or_none()
        if not attr:
            return False
        await db.delete(attr)
        return True

    # ---------- Stock ----------

    async def adjust_stock(
        self, db: AsyncSession, product_id: uuid.UUID, delta: int
    ) -> int:
        """Atomically adjusts stock. Returns new quantity."""
        result = await db.execute(
            text(
                "UPDATE products SET stock_quantity = stock_quantity + :delta "
                "WHERE id = :id AND deleted_at IS NULL "
                "RETURNING stock_quantity"
            ),
            {"delta": delta, "id": str(product_id)},
        )
        row = result.fetchone()
        return row[0] if row else 0

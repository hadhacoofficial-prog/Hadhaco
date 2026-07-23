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
        """Return paginated products with total count.

        Uses COUNT(*) OVER() window function so count + data are fetched in a
        single round-trip (saves one DB round-trip vs the previous separate
        count query).  Relationship eager-loads (images / variants) are NOT
        applied here — call ``get_images_for_products`` and
        ``get_image_variants_for_images`` for list-view image hydration, which
        fetches only the 2 images per product that the UI actually renders.
        """
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

        where_clause = and_(*filters) if filters else None
        count_window = func.count().over().label("_total_count")

        sort_col = getattr(Product, sort_by, Product.created_at)
        order = sort_col.desc() if sort_dir == "desc" else sort_col.asc()

        list_q = (
            select(Product, count_window)
            .options(selectinload(Product.variants))
            .order_by(order)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        if where_clause is not None:
            list_q = list_q.where(where_clause)
        result = await db.execute(list_q)
        rows = result.unique().all()
        if not rows:
            return [], 0
        total: int = rows[0][1]
        items = [row[0] for row in rows]
        return items, total

    # ------------------------------------------------------------------ #
    #  List-view image hydration — replaces heavy selectinload(Product.images
    #  ).selectinload(Image.variants) which loaded ALL images for ALL products.
    #  Instead, we fetch exactly 2 images per product (primary + first
    #  secondary) in a single batch query, then fetch image_variants only for
    #  the primary images.
    # ------------------------------------------------------------------ #

    async def get_images_for_products(
        self, db: AsyncSession, product_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list]:
        """Fetch exactly 2 images (primary + secondary) per product.

        Returns ``{product_id: [primary_img, secondary_img]}`` — each img
        has its ``.variants`` relationship populated (via selectinload in the
        calling batch query).
        """
        if not product_ids:
            return {}

        from sqlalchemy.orm import selectinload as _sel

        from app.modules.media.models import Image

        # Step 1: CTE ranks images per product (only ID + owner_id + rn)
        # — avoids the JSONB-hashing issue with .unique() on full Image rows.
        ranked_q = (
            select(
                Image.id.label("_image_id"),
                Image.owner_id.label("_owner_id"),
                func.row_number()
                .over(
                    partition_by=Image.owner_id,
                    order_by=(
                        Image.is_primary.desc(),
                        Image.sort_order.asc(),
                        Image.created_at.asc(),
                    ),
                )
                .label("_rn"),
            )
            .where(
                Image.owner_type == "product",
                Image.deleted_at.is_(None),
                Image.owner_id.in_(product_ids),
            )
            .subquery()
        )

        ids_q = select(ranked_q.c._image_id, ranked_q.c._owner_id).where(
            ranked_q.c._rn <= 2
        )
        result = await db.execute(ids_q)
        id_rows = result.all()
        if not id_rows:
            return {}

        image_ids = [row[0] for row in id_rows]
        owner_map: dict[uuid.UUID, uuid.UUID] = {row[0]: row[1] for row in id_rows}

        # Step 2: batch-load full Image objects (with selectinload for variants)
        imgs_result = await db.execute(
            select(Image).where(Image.id.in_(image_ids)).options(_sel(Image.variants))
        )
        images = imgs_result.scalars().all()

        # Step 3: build {product_id: [img, ...]} preserving sort order from CTE
        id_order: dict[uuid.UUID, int] = {
            row[0]: idx for idx, row in enumerate(id_rows)
        }
        mapping: dict[uuid.UUID, list] = {}
        for img in images:
            pid = owner_map.get(img.id)
            if pid is not None:
                mapping.setdefault(pid, []).append(img)
        # Sort each product's images by the CTE row number
        for pid in mapping:
            mapping[pid].sort(key=lambda i: id_order.get(i.id, 999))
        return mapping

    async def get_image_variants_for_images(
        self, db: AsyncSession, image_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list]:
        """Fetch ImageVariant rows for the given image IDs.

        Returns ``{image_id: [ImageVariant, ...]}``.
        """
        if not image_ids:
            return {}

        from app.modules.media.models import ImageVariant

        result = await db.execute(
            select(ImageVariant).where(ImageVariant.image_id.in_(image_ids))
        )
        mapping: dict[uuid.UUID, list] = {}
        for iv in result.scalars().all():
            mapping.setdefault(iv.image_id, []).append(iv)
        return mapping

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
        # The raw UPDATE bypasses the ORM identity map so the cached
        # instance is stale.  Expire it so the re-fetch hits the DB.
        instance = db.get(Product, product_id)
        if instance is not None:
            db.expire(instance)
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
        # The raw UPDATE bypasses the ORM identity map so the cached
        # instance is stale.  Expire it so the re-fetch hits the DB.
        instance = db.get(ProductVariant, variant_id)
        if instance is not None:
            db.expire(instance)
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

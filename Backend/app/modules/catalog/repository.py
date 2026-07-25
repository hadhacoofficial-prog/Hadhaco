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
from app.modules.inventory.reservation_service import ACTIVE_OR_CHECKOUT_STATUSES
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
        instance = await db.get(Product, product_id)
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

    async def resolve_default_variant_id(
        self, db: AsyncSession, product_id: uuid.UUID
    ) -> uuid.UUID | None:
        """The variant an admin operation targeting "the product" (no
        explicit variant chosen) resolves to — mirrors CartService.
        _resolve_default_variant_id's rule (earliest active variant by
        sort_order/created_at), so admin stock adjustments never silently
        fall through to the vestigial Product.stock_quantity column."""
        result = await db.execute(
            select(ProductVariant.id)
            .where(
                ProductVariant.product_id == product_id,
                ProductVariant.is_active.is_(True),
            )
            .order_by(ProductVariant.sort_order.asc(), ProductVariant.created_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_variant_by_sku(
        self, db: AsyncSession, sku: str
    ) -> ProductVariant | None:
        """Look up a variant by its (globally unique) SKU.

        Variant SKUs are enforced unique by ``product_variants_sku_key`` on the
        ``product_variants`` table — distinct from ``Product.sku`` — so callers
        checking a *variant* SKU must use this, not ``get_by_sku``.
        """
        result = await db.execute(
            select(ProductVariant).where(ProductVariant.sku == sku)
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
        instance = await db.get(ProductVariant, variant_id)
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
        """Atomically adjusts stock. Returns new quantity.

        WARNING: not on the enriched inventory pipeline — no row lock beyond
        the UPDATE itself, no InventoryChangedEvent, no cache invalidation,
        no transaction log. CatalogService.adjust_stock deliberately calls
        ReservationService.record_adjustment instead of this method; real
        callers should do the same. Kept only for existing repository-level
        tests — do not call this from new code."""
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

    # ---------- Variant-level inventory listing (admin) ----------

    _VARIANT_SORT_COLUMNS: dict[str, str] = {
        "updated_at": "v.updated_at",
        "available_stock": "available_stock",
        "stock_quantity": "v.stock_quantity",
        "product_name": "p.name",
        "sku": "v.sku",
    }

    async def list_variants_paginated(
        self,
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        sort_by: str = "updated_at",
        sort_dir: str = "desc",
        variant_status: str | None = None,
        has_reservations: bool | None = None,
        recently_updated_hours: int | None = None,
        category_id: uuid.UUID | None = None,
        collection_id: uuid.UUID | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Single-query, variant-level inventory listing for the admin page.

        One row per ProductVariant, joined to Product/Category (for display
        + filters) and LEFT JOIN LATERAL'd against InventoryTransaction (last
        adjustment) and InventoryReservation (has_reservations filter) so the
        whole page renders from one round-trip — no N+1, no per-row follow-up
        calls. Uses COUNT(*) OVER() to fetch total alongside the page.
        """
        params: dict[str, Any] = {
            "limit": page_size,
            "offset": (page - 1) * page_size,
        }
        where: list[str] = ["p.deleted_at IS NULL"]

        if variant_status == "active":
            where.append("v.is_active = true")
        elif variant_status == "inactive":
            where.append("v.is_active = false")
        elif variant_status == "out_of_stock":
            where.append(
                "GREATEST(v.stock_quantity - v.reserved_quantity - v.sold_quantity, 0) = 0"
            )

        if has_reservations is not None:
            exists_clause = (
                "EXISTS (SELECT 1 FROM inventory_reservations r "
                "WHERE r.variant_id = v.id "
                f"AND r.status IN {ACTIVE_OR_CHECKOUT_STATUSES})"  # nosec B608
            )
            where.append(exists_clause if has_reservations else f"NOT {exists_clause}")

        if recently_updated_hours is not None:
            where.append("v.updated_at >= now() - make_interval(hours => :hours)")
            params["hours"] = recently_updated_hours

        if category_id is not None:
            where.append("p.category_id = :category_id")
            params["category_id"] = str(category_id)

        if collection_id is not None:
            where.append(
                "EXISTS (SELECT 1 FROM product_collections pc "
                "WHERE pc.product_id = p.id AND pc.collection_id = :collection_id)"
            )
            params["collection_id"] = str(collection_id)

        search_rank_sql = "6"
        if search:
            term = search.strip()[:200]
            params["exact"] = term
            params["prefix"] = f"{term}%"
            params["partial"] = f"%{term}%"
            where.append(
                "("
                "v.sku ILIKE :partial OR p.sku ILIKE :partial OR p.name ILIKE :partial "
                "OR v.name ILIKE :partial OR c.name ILIKE :partial "
                "OR EXISTS (SELECT 1 FROM product_collections pc2 "
                "JOIN collections col2 ON col2.id = pc2.collection_id "
                "WHERE pc2.product_id = p.id "
                "AND (col2.name ILIKE :partial OR col2.slug ILIKE :partial))"
                ")"
            )
            search_rank_sql = """
                CASE
                    WHEN v.sku ILIKE :exact THEN 0
                    WHEN p.sku ILIKE :exact THEN 1
                    WHEN p.name ILIKE :exact THEN 2
                    WHEN v.name ILIKE :exact THEN 3
                    WHEN c.name ILIKE :exact THEN 4
                    WHEN v.sku ILIKE :prefix THEN 5
                    ELSE 6
                END
            """

        where_sql = " AND ".join(where)
        sort_col = self._VARIANT_SORT_COLUMNS.get(sort_by, "v.updated_at")
        sort_dir_sql = "ASC" if sort_dir == "asc" else "DESC"

        query = text(f"""
            SELECT
                v.id AS variant_id,
                v.product_id,
                p.name AS product_name,
                v.name AS variant_name,
                v.sku,
                c.name AS category_name,
                (SELECT iv.url FROM images i
                 JOIN image_variants iv ON iv.image_id = i.id
                 WHERE i.owner_type = 'product' AND i.owner_id = p.id
                   AND i.is_primary = TRUE AND i.deleted_at IS NULL
                   AND iv.variant_name = 'medium' AND iv.breakpoint = 'desktop'
                   AND iv.status = 'ready'
                 LIMIT 1) AS primary_image,
                v.stock_quantity,
                v.reserved_quantity,
                v.sold_quantity,
                GREATEST(v.stock_quantity - v.reserved_quantity - v.sold_quantity, 0)
                    AS available_stock,  -- mirrors compute_available_stock()
                p.low_stock_threshold,
                p.track_inventory,
                p.allow_backorder,
                v.is_active,
                p.status AS product_status,
                v.updated_at,
                la.quantity AS last_adjustment_quantity,
                la.adjustment_mode AS last_adjustment_mode,
                la.reason AS last_adjustment_reason,
                la.created_at AS last_adjustment_at,
                prof.full_name AS last_adjustment_by_name,
                {search_rank_sql} AS search_rank,
                COUNT(*) OVER() AS _total_count
            FROM product_variants v
            JOIN products p ON p.id = v.product_id
            LEFT JOIN categories c ON c.id = p.category_id
            LEFT JOIN LATERAL (
                SELECT t.quantity, t.adjustment_mode, t.reason, t.created_at,
                       t.performed_by
                FROM inventory_transactions t
                WHERE t.variant_id = v.id
                ORDER BY t.created_at DESC
                LIMIT 1
            ) la ON true
            LEFT JOIN profiles prof ON prof.id = la.performed_by
            WHERE {where_sql}  -- nosec B608
            ORDER BY search_rank ASC, {sort_col} {sort_dir_sql}, v.id ASC
            LIMIT :limit OFFSET :offset
        """)  # nosec B608 — where_sql/sort_col/sort_dir_sql built from a fixed
        # whitelist + bound params only, never raw user input.

        result = await db.execute(query, params)
        rows = [dict(r._mapping) for r in result.fetchall()]
        total = rows[0]["_total_count"] if rows else 0
        for row in rows:
            row.pop("_total_count", None)
            row.pop("search_rank", None)
        return rows, total

    async def list_orders_for_variant(
        self,
        db: AsyncSession,
        variant_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """Paginated order history for a variant's expandable admin row."""
        result = await db.execute(
            text("""
                SELECT
                    o.id AS order_id,
                    o.order_number,
                    o.status,
                    o.created_at,
                    oi.quantity,
                    oi.line_total,
                    COUNT(*) OVER() AS _total_count
                FROM order_items oi
                JOIN orders o ON o.id = oi.order_id
                WHERE oi.variant_id = :variant_id
                ORDER BY o.created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            {
                "variant_id": str(variant_id),
                "limit": page_size,
                "offset": (page - 1) * page_size,
            },
        )
        rows = [dict(r._mapping) for r in result.fetchall()]
        total = rows[0]["_total_count"] if rows else 0
        for row in rows:
            row.pop("_total_count", None)
        return rows, total

    async def get_variant_inventory_summary(self, db: AsyncSession) -> dict[str, int]:
        """Global (unfiltered) KPI rollup for the admin inventory page header."""
        result = await db.execute(text("""
                SELECT
                    COUNT(*) AS total_variants,
                    COUNT(*) FILTER (
                        WHERE GREATEST(v.stock_quantity - v.reserved_quantity
                            - v.sold_quantity, 0) <= p.low_stock_threshold
                            AND p.track_inventory = true
                    ) AS low_stock_variants,
                    COUNT(*) FILTER (
                        WHERE GREATEST(v.stock_quantity - v.reserved_quantity
                            - v.sold_quantity, 0) = 0
                    ) AS out_of_stock_variants,
                    COALESCE(SUM(v.reserved_quantity), 0) AS reserved_units,
                    COALESCE(SUM(GREATEST(v.stock_quantity - v.reserved_quantity
                        - v.sold_quantity, 0)), 0) AS available_units,
                    COALESCE(SUM(v.stock_quantity), 0) AS total_inventory_units
                FROM product_variants v
                JOIN products p ON p.id = v.product_id
                WHERE p.deleted_at IS NULL AND v.is_active = true
            """))
        row = result.fetchone()
        return dict(row._mapping) if row else {}

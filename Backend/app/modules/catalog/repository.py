import uuid
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import (
    ColumnElement,
    and_,
    case,
    exists,
    false,
    func,
    literal_column,
    or_,
    select,
    text,
    true,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.catalog.models import (
    Product,
    ProductAttribute,
    ProductVariant,
)
from app.modules.inventory.reservation_service import ACTIVE_OR_CHECKOUT_STATUSES
from app.modules.media.models import Image

# ── Product list filtering / sorting ────────────────────────────────────────
#
# Sort keys are an allowlist — the router regex-validates `sort_by` and this
# map is the only place a key becomes SQL, so user input can never name an
# arbitrary column.

PRODUCT_SORT_KEYS: tuple[str, ...] = (
    "created_at",
    "updated_at",
    "base_price",
    "name",
    "stock_quantity",
    "status",
    "average_rating",
    "sold_quantity",
    "discount",
    "featured",
    "relevance",
)


@dataclass(frozen=True)
class ProductFilterSpec:
    status: str | None = None
    category_id: uuid.UUID | None = None
    # Already expanded to include sub-categories by the caller. An empty list
    # means "a category filter was requested but matched nothing" → no rows.
    category_ids: list[uuid.UUID] | None = None
    collection_id: uuid.UUID | None = None
    metal_type: str | None = None
    metal_types: list[str] | None = None
    purities: list[str] | None = None
    gender: str | None = None
    genders: list[str] | None = None
    is_featured: bool | None = None
    is_new_arrival: bool | None = None
    is_best_seller: bool | None = None
    min_price: float | None = None
    max_price: float | None = None
    search: str | None = None
    in_stock: bool | None = None
    on_sale: bool | None = None
    min_rating: float | None = None
    stock_status: str | None = None
    include_deleted: bool = False

    def cache_params(self) -> dict[str, Any]:
        """JSON-stable dict for Redis cache keys (router + cache warmer)."""
        d = asdict(self)
        if d["category_ids"] is not None:
            d["category_ids"] = sorted(str(c) for c in d["category_ids"])
        return d


def _available_stock_expr() -> ColumnElement[int]:
    """SQL mirror of ``Product.available_stock`` (sum of active variants'
    availability when the product has any, else the product-level counters)."""
    v = ProductVariant
    has_active = (
        exists()
        .where(v.product_id == Product.id, v.is_active.is_(True))
        .correlate(Product)
    )
    variant_sum = (
        select(
            func.coalesce(
                func.sum(
                    func.greatest(
                        v.stock_quantity - v.reserved_quantity - v.sold_quantity, 0
                    )
                ),
                0,
            )
        )
        .where(v.product_id == Product.id, v.is_active.is_(True))
        .correlate(Product)
        .scalar_subquery()
    )
    product_level = func.greatest(
        Product.stock_quantity - Product.reserved_quantity - Product.sold_quantity, 0
    )
    return case((has_active, variant_sum), else_=product_level)


def _purchasable_clause() -> ColumnElement[bool]:
    """Matches ``compute_inventory_status(...)[1]`` (can_purchase)."""
    return or_(
        Product.track_inventory.is_(False),
        Product.allow_backorder.is_(True),
        _available_stock_expr() > 0,
    )


def _on_sale_clause() -> ColumnElement[bool]:
    return and_(
        Product.compare_at_price.is_not(None),
        Product.compare_at_price > Product.base_price,
    )


def _stock_status_clause(stock_status: str) -> ColumnElement[bool] | None:
    available = _available_stock_expr()
    tracked = Product.track_inventory.is_(True)
    if stock_status == "out_of_stock":
        return and_(tracked, available <= 0)
    if stock_status == "low_stock":
        return and_(tracked, available > 0, available <= Product.low_stock_threshold)
    if stock_status == "in_stock":
        return or_(
            Product.track_inventory.is_(False),
            available > Product.low_stock_threshold,
        )
    return None


def _filter_clauses(spec: ProductFilterSpec) -> dict[str, ColumnElement[bool]]:
    """Build WHERE clauses keyed by facet group.

    Keying lets the facets query drop exactly one group at a time
    (disjunctive faceting) while the list query simply ANDs them all.
    """
    c: dict[str, ColumnElement[bool]] = {}
    if not spec.include_deleted:
        c["deleted"] = Product.deleted_at.is_(None)
    if spec.status:
        # The storefront's fixed "active" is inlined as a SQL literal (not a
        # bind param) so the planner can match the partial
        # ``WHERE deleted_at IS NULL AND status = 'active'`` indexes
        # (migration 0066) even under generic prepared-statement plans.
        # Any other value (admin filter, user-supplied) stays a bind param.
        c["status"] = (
            Product.status == literal_column("'active'")
            if spec.status == "active"
            else Product.status == spec.status
        )
    if spec.category_ids is not None:
        c["category"] = (
            Product.category_id.in_(spec.category_ids) if spec.category_ids else false()
        )
    elif spec.category_id:
        c["category"] = Product.category_id == spec.category_id
    if spec.collection_id:
        from app.modules.collections.models import ProductCollection

        c["collection"] = Product.id.in_(
            select(ProductCollection.product_id).where(
                ProductCollection.collection_id == spec.collection_id
            )
        )
    metals = spec.metal_types or ([spec.metal_type] if spec.metal_type else [])
    if metals:
        c["metal"] = Product.metal_type.in_(metals)
    if spec.purities:
        c["purity"] = Product.purity.in_(spec.purities)
    genders = spec.genders or ([spec.gender] if spec.gender else [])
    if genders:
        c["gender"] = Product.gender.in_(genders)
    if spec.is_featured is not None:
        c["featured"] = Product.is_featured == spec.is_featured
    if spec.is_new_arrival is not None:
        c["new"] = Product.is_new_arrival == spec.is_new_arrival
    if spec.is_best_seller is not None:
        c["bestseller"] = Product.is_best_seller == spec.is_best_seller
    price: list[ColumnElement[bool]] = []
    if spec.min_price is not None:
        price.append(Product.base_price >= spec.min_price)
    if spec.max_price is not None:
        price.append(Product.base_price <= spec.max_price)
    if price:
        c["price"] = and_(*price)
    if spec.search:
        # search_vector (GIN-indexed, trigger-maintained from name/
        # short_description/description/metal_type/purity/meta_keywords)
        # replaces leading-wildcard ILIKE on name/description, which
        # can't use any index. sku is NOT part of the tsvector — it's
        # a short, separately-indexed code, so it keeps its own ILIKE.
        c["search"] = or_(
            Product.search_vector.op("@@")(
                func.plainto_tsquery("english", spec.search)
            ),
            Product.sku.ilike(f"%{spec.search}%"),
        )
    if spec.in_stock:
        c["in_stock"] = _purchasable_clause()
    if spec.on_sale:
        c["on_sale"] = _on_sale_clause()
    if spec.min_rating is not None:
        c["rating"] = Product.average_rating >= spec.min_rating
    if spec.stock_status:
        clause = _stock_status_clause(spec.stock_status)
        if clause is not None:
            c["stock_status"] = clause
    return c


def _product_order_by(sort_by: str, sort_dir: str, search: str | None) -> list[Any]:
    desc = sort_dir == "desc"

    def directed(col: Any) -> Any:
        return col.desc().nulls_last() if desc else col.asc().nulls_last()

    if sort_by == "relevance":
        if search:
            rank = func.ts_rank(
                Product.search_vector, func.plainto_tsquery("english", search)
            )
            # Exact SKU hits outrank text matches; ties fall back to newest.
            return [
                (Product.sku.ilike(search)).desc(),
                rank.desc(),
                Product.created_at.desc(),
                Product.id,
            ]
        # No query → relevance degenerates to the storefront default.
        sort_by, desc = "featured", True
    if sort_by == "featured":
        return [
            Product.is_featured.desc(),
            Product.is_best_seller.desc(),
            Product.created_at.desc(),
            Product.id,
        ]
    if sort_by == "average_rating":
        return [
            directed(Product.average_rating),
            directed(Product.review_count),
            Product.id,
        ]
    if sort_by == "discount":
        pct = case(
            (
                _on_sale_clause(),
                (Product.compare_at_price - Product.base_price)
                / Product.compare_at_price,
            ),
            else_=0,
        )
        return [directed(pct), Product.id]
    column_map: dict[str, Any] = {
        "created_at": Product.created_at,
        "updated_at": Product.updated_at,
        "base_price": Product.base_price,
        "name": func.lower(Product.name),
        "stock_quantity": Product.stock_quantity,
        "status": Product.status,
        "sold_quantity": Product.sold_quantity,
    }
    return [directed(column_map.get(sort_by, Product.created_at)), Product.id]


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

    async def sku_exists(self, db: AsyncSession, sku: str) -> bool:
        """Whether `sku` is taken — across *all* rows, deleted or not.

        `sku`/`slug` are globally unique at the DB level (not scoped to
        `deleted_at IS NULL`), so a soft-deleted product still reserves its
        sku/slug forever. Conflict pre-checks must use this instead of
        `get_by_sku`/`get_by_slug` (which are deleted-filtered, for public
        lookups) or a duplicate reused by a deleted row slips past the
        check and blows up as an unhandled IntegrityError at insert time.
        """
        result = await db.execute(select(Product.id).where(Product.sku == sku))
        return result.first() is not None

    async def slug_exists(self, db: AsyncSession, slug: str) -> bool:
        """Whether `slug` is taken — across *all* rows, deleted or not. See `sku_exists`."""
        result = await db.execute(select(Product.id).where(Product.slug == slug))
        return result.first() is not None

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
        category_ids: list[uuid.UUID] | None = None,
        metal_types: list[str] | None = None,
        purities: list[str] | None = None,
        genders: list[str] | None = None,
        in_stock: bool | None = None,
        on_sale: bool | None = None,
        min_rating: float | None = None,
        stock_status: str | None = None,
        load_variants: bool = True,
    ) -> tuple[list[Product], int]:
        """Return paginated products with total count.

        ``load_variants=False`` skips the ``Product.variants`` selectinload (one
        whole extra round trip) and instead computes availability in the same
        statement via ``_available_stock_expr()``, exposing it as
        ``product.list_available_stock``. ``Product.available_stock`` must not
        be read on such items (the relationship is not loaded) - use
        ``list_available_stock``. List views need only that number.

        Uses COUNT(*) OVER() window function so count + data are fetched in a
        single round-trip (saves one DB round-trip vs the previous separate
        count query).  Relationship eager-loads (images / variants) are NOT
        applied here — call ``get_images_for_products`` for list-view image
        hydration, which fetches only the 2 images per product that the UI
        actually renders (with their ``Image.variants`` selectinloaded).

        Filtering always happens before OFFSET/LIMIT and every ordering ends
        with ``Product.id`` so offset pages are stable (no row can appear on
        two pages, or on none, when the primary sort key has ties).
        """
        spec = ProductFilterSpec(
            status=status,
            category_id=category_id,
            category_ids=category_ids,
            collection_id=collection_id,
            metal_type=metal_type,
            metal_types=metal_types,
            purities=purities,
            gender=gender,
            genders=genders,
            is_featured=is_featured,
            is_new_arrival=is_new_arrival,
            is_best_seller=is_best_seller,
            min_price=min_price,
            max_price=max_price,
            search=search,
            in_stock=in_stock,
            on_sale=on_sale,
            min_rating=min_rating,
            stock_status=stock_status,
            include_deleted=include_deleted,
        )
        filters = list(_filter_clauses(spec).values())
        count_window = func.count().over().label("_total_count")

        columns: list[Any] = [Product, count_window]
        if not load_variants:
            columns.append(_available_stock_expr().label("_avail"))
        list_q = (
            select(*columns)
            .order_by(*_product_order_by(sort_by, sort_dir, search))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        if load_variants:
            list_q = list_q.options(selectinload(Product.variants))
        if filters:
            list_q = list_q.where(and_(*filters))
        result = await db.execute(list_q)
        rows = result.unique().all()
        if not rows:
            # COUNT(*) OVER() rides on the returned rows, so a page past the end
            # would report total=0. Only in that case pay for a plain count, so
            # callers can tell "page too far" from "no results".
            if page <= 1:
                return [], 0
            count_q = select(func.count()).select_from(Product)
            if filters:
                count_q = count_q.where(and_(*filters))
            return [], int((await db.execute(count_q)).scalar_one())
        total: int = rows[0][1]
        items = [row[0] for row in rows]
        if not load_variants:
            for row in rows:
                row[0].list_available_stock = int(row[2])
        return items, total

    async def get_facets(
        self, db: AsyncSession, spec: "ProductFilterSpec"
    ) -> dict[str, Any]:
        """Disjunctive facet counts for the storefront filter panel.

        Each facet is counted under every *other* active filter but not its
        own, so selecting "Women" still shows how many "Men" pieces exist
        (multi-select within a group widens; across groups narrows).

        Every scalar facet (total, price bounds, rating buckets, flag counts)
        comes from ONE scan using per-aggregate ``FILTER (WHERE ...)``
        clauses; only the value-grouped facets need their own GROUP BY. The
        router Redis-caches the result alongside the product lists.
        """
        clauses = _filter_clauses(spec)

        def where_except(*groups: str) -> list[ColumnElement[bool]]:
            return [c for k, c in clauses.items() if k not in groups]

        def matching(*groups: str, extra: ColumnElement[bool] | None = None) -> Any:
            parts = where_except(*groups) + ([extra] if extra is not None else [])
            return and_(true(), *parts)

        rating_thresholds = (4, 3, 2, 1)
        summary = (
            await db.execute(
                select(
                    func.count().filter(matching()),
                    func.min(Product.base_price).filter(matching("price")),
                    func.max(Product.base_price).filter(matching("price")),
                    *[
                        func.count().filter(
                            matching("rating", extra=Product.average_rating >= t)
                        )
                        for t in rating_thresholds
                    ],
                    func.count().filter(
                        matching("in_stock", extra=_purchasable_clause())
                    ),
                    func.count().filter(matching("on_sale", extra=_on_sale_clause())),
                    func.count().filter(
                        matching("new", extra=Product.is_new_arrival.is_(True))
                    ),
                    func.count().filter(
                        matching("bestseller", extra=Product.is_best_seller.is_(True))
                    ),
                    func.count().filter(matching(extra=Product.sold_quantity > 0)),
                ).select_from(Product)
            )
        ).one()
        total, price_min, price_max = summary[0], summary[1], summary[2]
        ratings = summary[3 : 3 + len(rating_thresholds)]
        in_stock, on_sale, new_arrival, best_seller, with_sales = summary[
            3 + len(rating_thresholds) :
        ]

        async def grouped(col: Any, group: str) -> list[dict[str, Any]]:
            q = (
                select(col, func.count())
                .select_from(Product)
                .where(*where_except(group), col.is_not(None))
                .group_by(col)
                .order_by(func.count().desc(), col)
            )
            return [
                {"value": v, "count": int(n)}
                for v, n in (await db.execute(q)).all()
                if v
            ]

        cat_rows = (
            await db.execute(
                select(Product.category_id, func.count())
                .select_from(Product)
                .where(*where_except("category"), Product.category_id.is_not(None))
                .group_by(Product.category_id)
            )
        ).all()

        return {
            "total": int(total),
            "category_counts": {cid: int(n) for cid, n in cat_rows},
            "genders": await grouped(Product.gender, "gender"),
            "metal_types": await grouped(Product.metal_type, "metal"),
            "purities": await grouped(Product.purity, "purity"),
            "price_min": float(price_min) if price_min is not None else None,
            "price_max": float(price_max) if price_max is not None else None,
            "ratings": [
                {"min_rating": t, "count": int(n)}
                for t, n in zip(rating_thresholds, ratings, strict=True)
            ],
            "in_stock": int(in_stock),
            "on_sale": int(on_sale),
            "new_arrival": int(new_arrival),
            "best_seller": int(best_seller),
            "has_sales": int(with_sales) > 0,
        }

    # ------------------------------------------------------------------ #
    #  List-view image hydration — replaces heavy selectinload(Product.images
    #  ).selectinload(Image.variants) which loaded ALL images for ALL products.
    #  Instead, we fetch exactly 2 images per product (primary + first
    #  secondary) in a single statement, with Image.variants joined-loaded
    #  for those images only.
    # ------------------------------------------------------------------ #

    async def get_images_for_products(
        self, db: AsyncSession, product_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list]:
        """Fetch exactly 2 images (primary + secondary) per product.

        Returns ``{product_id: [primary_img, secondary_img]}`` — each img
        has its ``.variants`` relationship populated (joined-loaded in the
        same single statement).
        """
        if not product_ids:
            return {}

        from sqlalchemy.orm import joinedload

        from app.modules.media.models import Image

        # One statement: rank images per product in a subquery (primary first,
        # then sort_order, then age) and keep the top two, joining each
        # image's variants in the same round trip. This used to be three
        # statements (rank ids, load images, selectinload variants).
        ranked = (
            select(
                Image.id.label("_image_id"),
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

        q = (
            select(Image)
            .join(ranked, ranked.c._image_id == Image.id)
            .where(ranked.c._rn <= 2)
            .options(joinedload(Image.variants))
            .order_by(Image.owner_id, ranked.c._rn)
        )
        images = (await db.execute(q)).unique().scalars().all()

        mapping: dict[uuid.UUID, list] = {}
        for img in images:
            if img.owner_id is not None:
                mapping.setdefault(img.owner_id, []).append(img)
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
        # UPDATE ... RETURNING returns the fresh row in one round-trip
        # (previously: UPDATE, then re-read via db.get + expire + SELECT).
        result = await db.execute(
            update(ProductVariant)
            .where(ProductVariant.id == variant_id)
            .values(**data)
            .returning(ProductVariant)
        )
        return result.scalar_one_or_none()

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
        if not rows and page > 1:
            # COUNT(*) OVER() rides on the returned rows, so a page past the
            # end would report total=0; count the same FROM/WHERE instead.
            count_sql = text(f"""
                SELECT COUNT(*)
                FROM product_variants v
                JOIN products p ON p.id = v.product_id
                LEFT JOIN categories c ON c.id = p.category_id
                WHERE {where_sql}  -- nosec B608
            """)  # nosec B608 — same whitelisted where_sql as above.
            count_params = {
                k: v for k, v in params.items() if k not in ("limit", "offset")
            }
            total = int((await db.execute(count_sql, count_params)).scalar_one())
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

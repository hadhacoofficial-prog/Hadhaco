import math
import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictError,
    InventoryError,
    NotFoundError,
    ValidationError,
)
from app.modules.catalog.models import ProductVariant
from app.modules.catalog.repository import ProductRepository
from app.modules.catalog.schemas import (
    LastAdjustmentInfo,
    ProductAttributeCreateRequest,
    ProductCollectionRef,
    ProductCreateRequest,
    ProductImageResponse,
    ProductListItem,
    ProductListResponse,
    ProductResponse,
    ProductUpdateRequest,
    ProductVariantCreateRequest,
    ProductVariantUpdateRequest,
    StockAdjustRequest,
    VariantInventoryListResponse,
    VariantInventoryRow,
    VariantInventorySummary,
    VariantOrderHistoryItem,
    VariantOrderHistoryResponse,
)
from app.modules.inventory.reservation_service import ReservationService
from app.modules.inventory.status import compute_inventory_status

_repo = ProductRepository()
_reservation_svc = ReservationService()


def _pick_image_url(
    image: ProductImageResponse, variant: Literal["medium", "thumbnail"]
) -> str:
    """Resolve a list-item image URL for *variant*, falling back down the
    chain to whichever size actually exists (medium -> thumbnail -> original,
    or thumbnail -> medium -> original)."""
    if variant == "thumbnail":
        return image.thumbnail_url or image.medium_url or image.url
    return image.medium_url or image.thumbnail_url or image.url


class CatalogService:
    async def get_by_id(
        self, db: AsyncSession, product_id: uuid.UUID
    ) -> ProductResponse:
        product = await _repo.get_by_id(db, product_id)
        if not product:
            raise NotFoundError("Product not found")
        response = ProductResponse.model_validate(product)
        cols = await _repo.get_collections_for_product(db, product_id)
        response.collections = [ProductCollectionRef.model_validate(c) for c in cols]
        return response

    async def get_by_slug(self, db: AsyncSession, slug: str) -> ProductResponse:
        product = await _repo.get_by_slug(db, slug)
        if not product:
            raise NotFoundError("Product not found")
        response = ProductResponse.model_validate(product)
        cols = await _repo.get_collections_for_product(db, product.id)
        response.collections = [ProductCollectionRef.model_validate(c) for c in cols]
        return response

    async def list_products(
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
        include_collections: bool = True,
        image_variant: Literal["medium", "thumbnail"] = "medium",
    ) -> ProductListResponse:
        items, total = await _repo.list_paginated(
            db,
            page=page,
            page_size=page_size,
            status=status,
            category_id=category_id,
            collection_id=collection_id,
            metal_type=metal_type,
            gender=gender,
            is_featured=is_featured,
            is_new_arrival=is_new_arrival,
            is_best_seller=is_best_seller,
            min_price=min_price,
            max_price=max_price,
            search=search,
            sort_by=sort_by,
            sort_dir=sort_dir,
            include_deleted=include_deleted,
        )

        product_ids = [p.id for p in items]

        # Batch-load exactly 2 images per product (primary + secondary)
        # instead of selectinload which loaded ALL images for ALL products.
        images_map = await _repo.get_images_for_products(db, product_ids)

        # Collect ALL image IDs (both primary + secondary) for variant loading
        all_image_ids: list[uuid.UUID] = []
        for imgs in images_map.values():
            all_image_ids.extend(img.id for img in imgs)

        # Batch-load image variants only for the fetched images (not ALL
        # images for ALL products as selectinload did before).
        variants_map = await _repo.get_image_variants_for_images(db, all_image_ids)

        # Attach variants to images in-memory
        for imgs in images_map.values():
            for img in imgs:
                img.variants = variants_map.get(img.id, [])

        # Skip the collections join entirely for callers that never render
        # collection badges (e.g. homepage rails) — pass
        # include_collections=false to opt out.
        col_map = (
            await _repo.get_collections_for_products(db, product_ids)
            if include_collections
            else {}
        )

        list_items = []
        for p in items:
            imgs = images_map.get(p.id, [])
            primary = next((img for img in imgs if img.is_primary), None)
            if primary is None and imgs:
                primary = imgs[0]
            secondary = next((img for img in imgs if img is not primary), None)

            sorted_primary_variants = (
                sorted(
                    primary.variants,
                    key=lambda v: (v.breakpoint, v.variant_name, v.dpr),
                )
                if primary
                else []
            )
            primary_img = (
                _pick_image_url(ProductImageResponse.from_image(primary), image_variant)
                if primary
                else None
            )
            secondary_img = (
                _pick_image_url(
                    ProductImageResponse.from_image(secondary), image_variant
                )
                if secondary
                else None
            )
            cols = [
                ProductCollectionRef.model_validate(c) for c in col_map.get(p.id, [])
            ]
            inventory_status, can_purchase = compute_inventory_status(
                p.available_stock,
                p.low_stock_threshold,
                p.track_inventory,
                p.allow_backorder,
            )
            list_items.append(
                ProductListItem(
                    id=p.id,
                    sku=p.sku,
                    name=p.name,
                    slug=p.slug,
                    short_description=p.short_description,
                    category_id=p.category_id,
                    metal_type=p.metal_type,
                    base_price=p.base_price,
                    compare_at_price=p.compare_at_price,
                    stock_quantity=p.stock_quantity,
                    available_stock=p.available_stock,
                    inventory_status=inventory_status,
                    can_purchase=can_purchase,
                    status=p.status,
                    is_featured=p.is_featured,
                    is_new_arrival=p.is_new_arrival,
                    is_best_seller=p.is_best_seller,
                    created_at=p.created_at,
                    average_rating=p.average_rating,
                    review_count=p.review_count,
                    primary_image=primary_img,
                    secondary_image=secondary_img,
                    primary_image_variants=sorted_primary_variants,
                    primary_image_focus_point=(
                        ProductImageResponse.from_image(primary).focus_point
                        if primary
                        else None
                    ),
                    collections=cols,
                )
            )

        return ProductListResponse(
            items=list_items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=math.ceil(total / page_size) if total else 0,
        )

    async def create(
        self, db: AsyncSession, payload: ProductCreateRequest
    ) -> ProductResponse:
        if await _repo.get_by_sku(db, payload.sku):
            raise ConflictError("Product with this SKU already exists")
        if await _repo.get_by_slug(db, payload.slug):
            raise ConflictError("Product with this slug already exists")

        variants_data = payload.variants
        attributes_data = payload.attributes
        collection_ids = payload.collection_ids
        data = payload.model_dump(exclude={"variants", "attributes", "collection_ids"})

        if data.get("status") == "active":
            data["published_at"] = datetime.now(UTC)

        product = await _repo.create(db, data)

        for v in variants_data:
            # Variant SKU uniqueness lives on product_variants, not products.
            if await _repo.get_variant_by_sku(db, v.sku):
                raise ConflictError(f"Variant SKU '{v.sku}' already exists")
            vdata = v.model_dump()
            vdata["product_id"] = product.id
            await _repo.add_variant(db, vdata)

        if not variants_data:
            # Every product must have >=1 variant (variant-first inventory —
            # see migration 0060_backfill_default_variants, which backfilled
            # this invariant for pre-existing data but does not cover
            # products created afterwards). Mirror its logic: a synthetic
            # "Default" variant reusing the product's own sku (falling back
            # to a suffixed sku on collision) inherits the product's
            # stock/reserved/sold counters given at creation time.
            default_sku = product.sku
            if await _repo.get_variant_by_sku(db, default_sku):
                default_sku = f"{product.sku}-DEFAULT"
            await _repo.add_variant(
                db,
                {
                    "product_id": product.id,
                    "sku": default_sku,
                    "name": "Default",
                    "price_adjustment": 0,
                    "stock_quantity": data.get("stock_quantity", 0),
                    "reserved_quantity": data.get("reserved_quantity", 0),
                    "sold_quantity": data.get("sold_quantity", 0),
                    "weight_grams": data.get("weight_grams"),
                    "is_active": True,
                    "sort_order": 0,
                },
            )

        for a in attributes_data:
            await _repo.upsert_attribute(db, product.id, a.name, a.value, a.sort_order)

        if collection_ids:
            from app.modules.collections.repository import CollectionRepository

            col_repo = CollectionRepository()
            for col_id in collection_ids:
                await col_repo.add_products(db, col_id, [product.id])

        # Reload with relations
        product = await _repo.get_by_id(db, product.id)  # type: ignore[assignment]
        assert product is not None
        response = ProductResponse.model_validate(product)
        if collection_ids:
            cols = await _repo.get_collections_for_product(db, product.id)
            response.collections = [
                ProductCollectionRef.model_validate(c) for c in cols
            ]
        return response

    async def update(
        self, db: AsyncSession, product_id: uuid.UUID, payload: ProductUpdateRequest
    ) -> ProductResponse:
        product = await _repo.get_by_id(db, product_id)
        if not product:
            raise NotFoundError("Product not found")

        data = payload.model_dump(exclude_unset=True)
        new_collection_ids: list[uuid.UUID] | None = data.pop("collection_ids", None)

        if "slug" in data and data["slug"] != product.slug:
            if await _repo.get_by_slug(db, data["slug"]):
                raise ConflictError("Product with this slug already exists")

        if data.get("status") == "active" and product.status != "active":
            data["published_at"] = datetime.now(UTC)

        updated = await _repo.update(db, product_id, data)

        if new_collection_ids is not None:
            from sqlalchemy import delete as sa_delete

            from app.modules.collections.models import ProductCollection
            from app.modules.collections.repository import CollectionRepository

            col_repo = CollectionRepository()
            # Remove all existing memberships for this product
            await db.execute(
                sa_delete(ProductCollection).where(
                    ProductCollection.product_id == product_id
                )
            )
            # Add the new memberships
            for col_id in new_collection_ids:
                await col_repo.add_products(db, col_id, [product_id])

        response = ProductResponse.model_validate(updated)
        cols = await _repo.get_collections_for_product(db, product_id)
        response.collections = [ProductCollectionRef.model_validate(c) for c in cols]
        return response

    async def delete(self, db: AsyncSession, product_id: uuid.UUID) -> None:
        product = await _repo.get_by_id(db, product_id)
        if not product:
            raise NotFoundError("Product not found")
        await _repo.soft_delete(db, product_id)

    # ---------- Variants ----------

    async def add_variant(
        self,
        db: AsyncSession,
        product_id: uuid.UUID,
        payload: ProductVariantCreateRequest,
    ):
        product = await _repo.get_by_id(db, product_id)
        if not product:
            raise NotFoundError("Product not found")
        # Variant SKUs are unique on the product_variants table, NOT products —
        # check the right table, or a duplicate variant SKU slips past this
        # guard and blows up as an unhandled IntegrityError (500) at flush time.
        if await _repo.get_variant_by_sku(db, payload.sku):
            raise ConflictError(f"Variant SKU '{payload.sku}' already exists")
        data = payload.model_dump()
        data["product_id"] = product_id
        try:
            variant = await _repo.add_variant(db, data)
        except IntegrityError as exc:
            # Safety net for the check-then-insert race (two concurrent adds of
            # the same SKU both pass the guard above).
            raise ConflictError(f"Variant SKU '{payload.sku}' already exists") from exc

        # New variant may be added to an already-live product page — tell
        # any connected SSE subscribers so its stock isn't invisible until
        # an unrelated refetch happens to pick it up. Mirrors the publish
        # pattern in InventoryService.record_movement (the other
        # cross-module publisher outside ReservationService itself).
        try:
            from app.core.events import InventoryChangedEvent, event_bus
            from app.modules.inventory.reservation_service import (
                invalidate_inventory_cache,
            )

            await event_bus.publish(
                InventoryChangedEvent(
                    product_ids=[str(product_id)],
                    available_by_product={str(product_id): variant.stock_quantity},
                )
            )
            await invalidate_inventory_cache([(product_id, variant.id)])
        except Exception:
            pass  # Event publishing / cache invalidation is best-effort.
        return variant

    async def update_variant(
        self,
        db: AsyncSession,
        variant_id: uuid.UUID,
        payload: ProductVariantUpdateRequest,
    ):
        variant = await _repo.get_variant(db, variant_id)
        if not variant:
            raise NotFoundError("Variant not found")

        data = payload.model_dump(exclude_unset=True)
        # stock_quantity must go through ReservationService.record_adjustment
        # (row lock + InventoryChangedEvent + cache bust), not a raw column
        # write — a direct update here previously left every real-time
        # subscriber (SSE-driven product cards/PDP/cart) showing a stale
        # number until their next unrelated refetch.
        new_stock = data.pop("stock_quantity", None)
        updated: ProductVariant | None = variant
        if data:
            updated = await _repo.update_variant(db, variant_id, data)
        if new_stock is not None and new_stock != variant.stock_quantity:
            # target_quantity (not delta) so record_adjustment computes the
            # actual delta from the value it reads INSIDE its row lock, not
            # from the variant.stock_quantity snapshot read above — two
            # concurrent edits racing to "set" the same field must not step
            # on each other (same race class the Set Exact Quantity admin
            # dialog guards against; this is a second entry point to it).
            await _reservation_svc.record_adjustment(
                db,
                product_id=variant.product_id,
                variant_id=variant.id,
                target_quantity=new_stock,
                reference=f"variant_edit:{variant_id}",
            )
            updated = await _repo.get_variant(db, variant_id)
        return updated

    async def delete_variant(
        self, db: AsyncSession, variant_id: uuid.UUID
    ) -> uuid.UUID | None:
        """Delete a variant. Returns the parent product_id if found, else None."""
        variant = await _repo.get_variant(db, variant_id)
        if not variant:
            return None
        product_id = variant.product_id
        await _repo.delete_variant(db, variant_id)
        return product_id

    # ---------- Attributes ----------

    async def upsert_attribute(
        self,
        db: AsyncSession,
        product_id: uuid.UUID,
        payload: ProductAttributeCreateRequest,
    ):
        product = await _repo.get_by_id(db, product_id)
        if not product:
            raise NotFoundError("Product not found")
        return await _repo.upsert_attribute(
            db, product_id, payload.name, payload.value, payload.sort_order
        )

    async def delete_attribute(
        self, db: AsyncSession, product_id: uuid.UUID, name: str
    ) -> None:
        if not await _repo.delete_attribute(db, product_id, name):
            raise NotFoundError("Attribute not found")

    # ---------- Stock ----------

    async def adjust_stock(
        self,
        db: AsyncSession,
        product_id: uuid.UUID,
        payload: StockAdjustRequest,
        *,
        performed_by: uuid.UUID | None = None,
        request_id: str | None = None,
    ) -> int:
        product = await _repo.get_by_id(db, product_id)
        if not product:
            raise NotFoundError("Product not found")

        variant_id = payload.variant_id
        if variant_id is None:
            # Every product has >=1 variant (migration 0060_backfill_default_
            # variants + CatalogService.create's default-variant fallback).
            # Resolving here instead of falling through to the vestigial
            # Product.stock_quantity column means "adjust this product's
            # stock" always affects real, purchasable inventory.
            variant_id = await _repo.resolve_default_variant_id(db, product_id)
            if variant_id is None:
                raise NotFoundError("Product has no active variant to adjust")

        delta = None
        target_quantity = None
        if payload.mode == "add":
            delta = payload.quantity
        elif payload.mode == "remove":
            delta = -payload.quantity
        else:
            target_quantity = payload.quantity
        try:
            return await _reservation_svc.record_adjustment(
                db,
                product_id=product_id,
                variant_id=variant_id,
                delta=delta,
                target_quantity=target_quantity,
                reference=payload.notes,
                performed_by=performed_by,
                request_id=request_id,
                adjustment_mode=payload.mode.upper(),
                reason=payload.reason,
                notes=payload.notes,
            )
        except InventoryError as exc:
            raise ValidationError(str(exc)) from exc

    # ---------- Variant-level admin inventory listing ----------

    async def list_variant_inventory(
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
    ) -> VariantInventoryListResponse:
        rows, total = await _repo.list_variants_paginated(
            db,
            page=page,
            page_size=page_size,
            search=search,
            sort_by=sort_by,
            sort_dir=sort_dir,
            variant_status=variant_status,
            has_reservations=has_reservations,
            recently_updated_hours=recently_updated_hours,
            category_id=category_id,
            collection_id=collection_id,
        )
        summary_data = await _repo.get_variant_inventory_summary(db)

        items = []
        for row in rows:
            last_adjustment = None
            if row.get("last_adjustment_at") is not None:
                last_adjustment = LastAdjustmentInfo(
                    quantity=row["last_adjustment_quantity"],
                    mode=row["last_adjustment_mode"],
                    reason=row["last_adjustment_reason"],
                    at=row["last_adjustment_at"],
                    by_name=row["last_adjustment_by_name"],
                )
            is_low_stock = (
                row["track_inventory"]
                and row["available_stock"] <= row["low_stock_threshold"]
            )
            items.append(
                VariantInventoryRow(
                    variant_id=row["variant_id"],
                    product_id=row["product_id"],
                    product_name=row["product_name"],
                    variant_name=row["variant_name"],
                    sku=row["sku"],
                    category_name=row["category_name"],
                    primary_image=row["primary_image"],
                    stock_quantity=row["stock_quantity"],
                    reserved_quantity=row["reserved_quantity"],
                    sold_quantity=row["sold_quantity"],
                    available_stock=row["available_stock"],
                    low_stock_threshold=row["low_stock_threshold"],
                    track_inventory=row["track_inventory"],
                    allow_backorder=row["allow_backorder"],
                    is_active=row["is_active"],
                    product_status=row["product_status"],
                    is_low_stock=is_low_stock,
                    updated_at=row["updated_at"],
                    last_adjustment=last_adjustment,
                )
            )

        return VariantInventoryListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=math.ceil(total / page_size) if total else 0,
            summary=VariantInventorySummary(**summary_data),
        )

    async def list_orders_for_variant(
        self,
        db: AsyncSession,
        variant_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> VariantOrderHistoryResponse:
        rows, total = await _repo.list_orders_for_variant(
            db, variant_id, page=page, page_size=page_size
        )
        return VariantOrderHistoryResponse(
            items=[VariantOrderHistoryItem(**row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=math.ceil(total / page_size) if total else 0,
        )

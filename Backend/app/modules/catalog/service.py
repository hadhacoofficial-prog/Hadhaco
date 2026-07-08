import math
import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictError,
    InventoryError,
    NotFoundError,
    ValidationError,
)
from app.modules.catalog.repository import ProductRepository
from app.modules.catalog.schemas import (
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
)
from app.modules.inventory.reservation_service import ReservationService

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
            sorted_imgs = [
                ProductImageResponse.from_image(img)
                for img in sorted(p.images, key=lambda i: i.sort_order)
            ]
            primary = next((img for img in sorted_imgs if img.is_primary), None)
            if primary is None and sorted_imgs:
                primary = sorted_imgs[0]
            secondary_imgs = [img for img in sorted_imgs if img is not primary]
            secondary = secondary_imgs[0] if secondary_imgs else None
            # Storefront listing contexts (cards, collections, search,
            # wishlist) default to the medium variant so grid cards aren't
            # upscaled from the tiny 200x200 thumbnail; admin tables render
            # much smaller previews and opt into thumbnail_url via
            # image_variant="thumbnail". Either way, falls back down the
            # chain to whichever variant actually exists. Cache-busting
            # already happened inside ProductImageResponse.from_image().
            primary_img = _pick_image_url(primary, image_variant) if primary else None
            secondary_img = (
                _pick_image_url(secondary, image_variant) if secondary else None
            )
            cols = [
                ProductCollectionRef.model_validate(c) for c in col_map.get(p.id, [])
            ]
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
                    status=p.status,
                    is_featured=p.is_featured,
                    is_new_arrival=p.is_new_arrival,
                    is_best_seller=p.is_best_seller,
                    created_at=p.created_at,
                    primary_image=primary_img,
                    secondary_image=secondary_img,
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
            if await _repo.get_by_sku(db, v.sku):
                raise ConflictError(f"Variant SKU '{v.sku}' already exists")
            vdata = v.model_dump()
            vdata["product_id"] = product.id
            await _repo.add_variant(db, vdata)

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
        if await _repo.get_by_sku(db, payload.sku):
            raise ConflictError(f"SKU '{payload.sku}' already exists")
        data = payload.model_dump()
        data["product_id"] = product_id
        return await _repo.add_variant(db, data)

    async def update_variant(
        self,
        db: AsyncSession,
        variant_id: uuid.UUID,
        payload: ProductVariantUpdateRequest,
    ):
        variant = await _repo.get_variant(db, variant_id)
        if not variant:
            raise NotFoundError("Variant not found")
        return await _repo.update_variant(
            db, variant_id, payload.model_dump(exclude_unset=True)
        )

    async def delete_variant(self, db: AsyncSession, variant_id: uuid.UUID) -> None:
        if not await _repo.delete_variant(db, variant_id):
            raise NotFoundError("Variant not found")

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
        self, db: AsyncSession, product_id: uuid.UUID, payload: StockAdjustRequest
    ) -> int:
        product = await _repo.get_by_id(db, product_id)
        if not product:
            raise NotFoundError("Product not found")
        try:
            return await _reservation_svc.record_adjustment(
                db,
                product_id=product_id,
                variant_id=payload.variant_id,
                delta=payload.delta,
                reference=payload.reason,
            )
        except InventoryError as exc:
            raise ValidationError(str(exc)) from exc

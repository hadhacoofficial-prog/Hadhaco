import hashlib
import json
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, deleted, ok
from app.core.database import get_db
from app.core.dependencies import require_admin
from app.core.redis import get_redis, safe_redis_get, safe_redis_setex
from app.modules.catalog.schemas import (
    ProductAttributeCreateRequest,
    ProductCreateRequest,
    ProductListResponse,
    ProductResponse,
    ProductUpdateRequest,
    ProductVariantCreateRequest,
    ProductVariantResponse,
    ProductVariantUpdateRequest,
    StockAdjustRequest,
)
from app.modules.catalog.service import CatalogService

router = APIRouter()
_service = CatalogService()

_PRODUCT_LIST_TTL = 300  # 5 minutes — catalog changes via admin only


def _product_list_cache_key(**params) -> str:
    h = hashlib.sha256(
        json.dumps(params, sort_keys=True, default=str).encode()
    ).hexdigest()[:12]
    return f"products:list:v1:{h}"


async def _bust_product_list_cache(redis: aioredis.Redis) -> None:
    """Delete all cached product list pages after any catalog mutation."""
    from app.core.redis import redis_available

    if not redis_available():
        return
    try:
        import asyncio

        keys = await asyncio.wait_for(redis.keys("products:list:v1:*"), timeout=0.3)
        if keys:
            from app.core.redis import safe_redis_delete

            await safe_redis_delete(redis, *keys)
    except Exception:
        from app.core.redis import mark_redis_error

        mark_redis_error()


# ---------- Public ----------


@router.get("/products", response_model=BaseSuccessResponse[ProductListResponse])
async def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category_id: uuid.UUID | None = None,
    category_slug: str | None = Query(None, max_length=200),
    collection_id: uuid.UUID | None = None,
    collection_slug: str | None = Query(None, max_length=200),
    metal_type: str | None = None,
    gender: str | None = None,
    is_featured: bool | None = None,
    is_new_arrival: bool | None = None,
    is_best_seller: bool | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    search: str | None = Query(None, max_length=200),
    sort_by: str = Query(
        "created_at", pattern="^(created_at|base_price|name|stock_quantity)$"
    ),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    # Resolve category_slug → category_id
    resolved_category_id = category_id
    if category_slug and not category_id:
        from app.modules.categories.repository import CategoryRepository

        cat = await CategoryRepository().get_by_slug(db, category_slug)
        if cat:
            resolved_category_id = cat.id

    # Resolve collection_slug → collection_id
    resolved_collection_id = collection_id
    if collection_slug and not collection_id:
        from app.modules.collections.repository import CollectionRepository

        col = await CollectionRepository().get_by_slug(db, collection_slug)
        if col:
            resolved_collection_id = col.id

    cache_key = _product_list_cache_key(
        page=page,
        page_size=page_size,
        category_id=resolved_category_id,
        collection_id=resolved_collection_id,
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
    )
    cached = await safe_redis_get(redis, cache_key)
    if cached:
        return ok(
            ProductListResponse.model_validate_json(cached),
            ResponseCode.PRODUCT_LISTED,
            "Products listed successfully",
        )

    result = await _service.list_products(
        db,
        page=page,
        page_size=page_size,
        status="active",
        category_id=resolved_category_id,
        collection_id=resolved_collection_id,
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
    )
    await safe_redis_setex(
        redis, cache_key, _PRODUCT_LIST_TTL, result.model_dump_json()
    )
    return ok(result, ResponseCode.PRODUCT_LISTED, "Products listed successfully")


@router.get("/products/{slug}", response_model=BaseSuccessResponse[ProductResponse])
async def get_product_by_slug(slug: str, db: AsyncSession = Depends(get_db)):
    result = await _service.get_by_slug(db, slug)
    return ok(result, ResponseCode.PRODUCT_FETCHED, "Product fetched successfully")


# ---------- Admin ----------


@router.get(
    "/admin/products",
    response_model=BaseSuccessResponse[ProductListResponse],
    dependencies=[Depends(require_admin)],
)
async def admin_list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    category_id: uuid.UUID | None = None,
    collection_id: uuid.UUID | None = None,
    metal_type: str | None = None,
    gender: str | None = None,
    search: str | None = Query(None, max_length=200),
    sort_by: str = Query(
        "created_at", pattern="^(created_at|base_price|name|stock_quantity|status)$"
    ),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
):
    result = await _service.list_products(
        db,
        page=page,
        page_size=page_size,
        status=status,
        category_id=category_id,
        collection_id=collection_id,
        metal_type=metal_type,
        gender=gender,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    return ok(result, ResponseCode.PRODUCT_LISTED, "Products listed successfully")


@router.post(
    "/admin/products",
    response_model=BaseSuccessResponse[ProductResponse],
    status_code=201,
    dependencies=[Depends(require_admin)],
)
async def create_product(
    payload: ProductCreateRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    from app.common.responses import created

    result = await _service.create(db, payload)
    await _bust_product_list_cache(redis)
    return created(result, ResponseCode.PRODUCT_CREATED, "Product created successfully")


@router.get(
    "/admin/products/generate-sku",
    response_model=BaseSuccessResponse[dict],
    dependencies=[Depends(require_admin)],
)
async def generate_sku(
    prefix: str = Query("XX", max_length=4),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func
    from sqlalchemy import select as sa_select

    from app.modules.catalog.models import Product

    count_result = await db.execute(
        sa_select(func.count(Product.id)).where(Product.deleted_at.is_(None))
    )
    count = (count_result.scalar_one() or 0) + 1
    clean = "".join(c for c in prefix.upper() if c.isalpha())[:2] or "XX"
    sku = f"HDH-{clean}-{count:06d}"
    return ok({"sku": sku}, ResponseCode.PRODUCT_FETCHED, "SKU generated")


@router.get(
    "/admin/products/{product_id}",
    response_model=BaseSuccessResponse[ProductResponse],
    dependencies=[Depends(require_admin)],
)
async def admin_get_product(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await _service.get_by_id(db, product_id)
    return ok(result, ResponseCode.PRODUCT_FETCHED, "Product fetched successfully")


@router.patch(
    "/admin/products/{product_id}",
    response_model=BaseSuccessResponse[ProductResponse],
    dependencies=[Depends(require_admin)],
)
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdateRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    result = await _service.update(db, product_id, payload)
    await _bust_product_list_cache(redis)
    return ok(result, ResponseCode.PRODUCT_UPDATED, "Product updated successfully")


@router.delete(
    "/admin/products/{product_id}",
    response_model=BaseSuccessResponse[None],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def delete_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    await _service.delete(db, product_id)
    await _bust_product_list_cache(redis)
    return deleted(ResponseCode.PRODUCT_DELETED, "Product deleted successfully")


# ---------- Variants ----------


@router.post(
    "/admin/products/{product_id}/variants",
    response_model=BaseSuccessResponse[ProductVariantResponse],
    status_code=201,
    dependencies=[Depends(require_admin)],
)
async def add_variant(
    product_id: uuid.UUID,
    payload: ProductVariantCreateRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    from app.common.responses import created

    variant = await _service.add_variant(db, product_id, payload)
    await _bust_product_list_cache(redis)
    return created(
        ProductVariantResponse.model_validate(variant),
        ResponseCode.PRODUCT_VARIANT_CREATED,
        "Variant created successfully",
    )


@router.patch(
    "/admin/products/variants/{variant_id}",
    response_model=BaseSuccessResponse[ProductVariantResponse],
    dependencies=[Depends(require_admin)],
)
async def update_variant(
    variant_id: uuid.UUID,
    payload: ProductVariantUpdateRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    variant = await _service.update_variant(db, variant_id, payload)
    await _bust_product_list_cache(redis)
    return ok(
        ProductVariantResponse.model_validate(variant),
        ResponseCode.PRODUCT_VARIANT_UPDATED,
        "Variant updated successfully",
    )


@router.delete(
    "/admin/products/variants/{variant_id}",
    response_model=BaseSuccessResponse[None],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def delete_variant(
    variant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    await _service.delete_variant(db, variant_id)
    await _bust_product_list_cache(redis)
    return deleted(ResponseCode.PRODUCT_VARIANT_DELETED, "Variant deleted successfully")


# ---------- Attributes ----------


@router.put(
    "/admin/products/{product_id}/attributes",
    response_model=BaseSuccessResponse[None],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def upsert_attribute(
    product_id: uuid.UUID,
    payload: ProductAttributeCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    await _service.upsert_attribute(db, product_id, payload)
    return ok(
        None, ResponseCode.PRODUCT_ATTRIBUTE_UPSERTED, "Attribute upserted successfully"
    )


@router.delete(
    "/admin/products/{product_id}/attributes/{attr_name}",
    response_model=BaseSuccessResponse[None],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def delete_attribute(
    product_id: uuid.UUID,
    attr_name: str,
    db: AsyncSession = Depends(get_db),
):
    await _service.delete_attribute(db, product_id, attr_name)
    return deleted(
        ResponseCode.PRODUCT_ATTRIBUTE_DELETED, "Attribute deleted successfully"
    )


# ---------- Stock ----------


@router.get(
    "/admin/products/{product_id}/collections",
    response_model=BaseSuccessResponse[list],
    dependencies=[Depends(require_admin)],
)
async def get_product_collections(
    product_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import select as sa_select

    from app.modules.collections.models import Collection, ProductCollection
    from app.modules.collections.schemas import CollectionResponse as CR

    result = await db.execute(
        sa_select(Collection)
        .join(ProductCollection, ProductCollection.collection_id == Collection.id)
        .where(
            ProductCollection.product_id == product_id, Collection.deleted_at.is_(None)
        )
    )
    cols = list(result.scalars().all())
    return ok(
        [CR.model_validate(c) for c in cols],
        ResponseCode.COLLECTION_LISTED,
        "Product collections",
    )


@router.post(
    "/admin/products/{product_id}/stock/adjust",
    response_model=BaseSuccessResponse[dict],
    dependencies=[Depends(require_admin)],
)
async def adjust_stock(
    product_id: uuid.UUID,
    payload: StockAdjustRequest,
    db: AsyncSession = Depends(get_db),
):
    new_qty = await _service.adjust_stock(db, product_id, payload)
    return ok(
        {"stock_quantity": new_qty},
        ResponseCode.PRODUCT_STOCK_ADJUSTED,
        "Stock adjusted successfully",
    )

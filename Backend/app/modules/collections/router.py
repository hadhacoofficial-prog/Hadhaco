import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, deleted, ok
from app.core.cache import (
    PREFIX_COLLECTION_DETAIL,
    TTL_COLLECTION_DETAIL,
    TTL_COLLECTION_LIST,
    add_cache_headers,
    bust_collection_detail_cache,
    bust_sitemap_cache,
    cache_swr,
    check_not_modified,
    make_etag,
    not_modified_response,
)
from app.core.database import AsyncSessionLocal, get_db
from app.core.dependencies import require_admin
from app.core.redis import (
    get_redis,
    safe_redis_delete,
)
from app.modules.collections.schemas import (
    AddProductsToCollectionRequest,
    BulkActionRequest,
    CollectionCreateRequest,
    CollectionDetailResponse,
    CollectionListResponse,
    CollectionResponse,
    CollectionUpdateRequest,
    ReorderProductsRequest,
)
from app.modules.collections.service import CollectionService

router = APIRouter()
_service = CollectionService()

_LIST_CACHE_KEY = "collections:list:v1"
_LIST_CACHE_TTL = 15 * 60


async def _bust_list_cache(redis: aioredis.Redis) -> None:
    await safe_redis_delete(redis, _LIST_CACHE_KEY)


# ── Public ──────────────────────────────────────────────────────────────────


@router.get(
    "/collections", response_model=BaseSuccessResponse[list[CollectionResponse]]
)
async def list_collections(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    # Runs on a fresh worker (NullPool) session, never the request session:
    # cache_swr may invoke this from a detached background SWR-refresh task
    # after the request has already committed/closed its session.
    async def _fetch():
        async with AsyncSessionLocal() as s:
            result = await _service.list_active(s)
            return [c.model_dump(mode="json") for c in result]

    data = await cache_swr(
        redis,
        _LIST_CACHE_KEY,
        ttl=TTL_COLLECTION_LIST,
        swr_window=TTL_COLLECTION_LIST,
        fetch_fn=_fetch,
    )

    import json as _json

    serialized = _json.dumps(
        ok(
            data,
            ResponseCode.COLLECTION_LISTED,
            "Collections listed successfully",
        ).model_dump(mode="json"),
        default=str,
    )
    etag = make_etag(serialized)
    if check_not_modified(request, etag):
        return not_modified_response()

    response = JSONResponse(content=_json.loads(serialized))
    add_cache_headers(
        response,
        TTL_COLLECTION_LIST,
        stale_while_revalidate=TTL_COLLECTION_LIST,
        etag=etag,
    )
    return response


@router.get(
    "/collections/{slug}", response_model=BaseSuccessResponse[CollectionResponse]
)
async def get_collection(
    slug: str,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    cache_key = f"{PREFIX_COLLECTION_DETAIL}:{slug}"

    async def _fetch():
        async with AsyncSessionLocal() as s:
            result = await _service.get_by_slug(s, slug)
            return result.model_dump(mode="json")

    data = await cache_swr(
        redis,
        cache_key,
        ttl=TTL_COLLECTION_DETAIL,
        swr_window=TTL_COLLECTION_DETAIL,
        fetch_fn=_fetch,
    )
    response = JSONResponse(
        content=ok(
            data,
            ResponseCode.COLLECTION_FETCHED,
            "Collection fetched successfully",
        ).model_dump(mode="json")
    )
    add_cache_headers(
        response,
        TTL_COLLECTION_DETAIL,
        stale_while_revalidate=TTL_COLLECTION_DETAIL,
    )
    return response


# ── Admin ────────────────────────────────────────────────────────────────────


@router.get(
    "/admin/collections",
    response_model=BaseSuccessResponse[CollectionListResponse],
    dependencies=[Depends(require_admin)],
)
async def admin_list_collections(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    search: str | None = Query(None, max_length=200),
    is_active: bool | None = None,
    is_featured: bool | None = None,
    sort_by: str = Query(
        "sort_order", pattern="^(sort_order|name|updated_at|created_at)$"
    ),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
):
    result = await _service.list_admin(
        db,
        page=page,
        page_size=page_size,
        search=search,
        is_active=is_active,
        is_featured=is_featured,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    return ok(result, ResponseCode.COLLECTION_LISTED, "Collections listed successfully")


@router.get(
    "/admin/collections/{col_id}",
    response_model=BaseSuccessResponse[CollectionDetailResponse],
    dependencies=[Depends(require_admin)],
)
async def admin_get_collection(col_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await _service.get_detail(db, col_id)
    return ok(
        result, ResponseCode.COLLECTION_FETCHED, "Collection fetched successfully"
    )


@router.post(
    "/admin/collections",
    response_model=BaseSuccessResponse[CollectionDetailResponse],
    status_code=201,
    dependencies=[Depends(require_admin)],
)
async def create_collection(
    payload: CollectionCreateRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    from app.common.responses import created

    result = await _service.create(db, payload)
    await _bust_list_cache(redis)
    await bust_collection_detail_cache(redis, slug=result.slug)
    await bust_sitemap_cache(redis)
    return created(
        result, ResponseCode.COLLECTION_CREATED, "Collection created successfully"
    )


@router.patch(
    "/admin/collections/{col_id}",
    response_model=BaseSuccessResponse[CollectionDetailResponse],
    dependencies=[Depends(require_admin)],
)
async def update_collection(
    col_id: uuid.UUID,
    payload: CollectionUpdateRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    result = await _service.update(db, col_id, payload)
    await _bust_list_cache(redis)
    await bust_collection_detail_cache(redis, slug=result.slug)
    return ok(
        result, ResponseCode.COLLECTION_UPDATED, "Collection updated successfully"
    )


@router.delete(
    "/admin/collections/{col_id}",
    response_model=BaseSuccessResponse[None],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def delete_collection(
    col_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    slug = await _service.delete(db, col_id)
    await _bust_list_cache(redis)
    await bust_collection_detail_cache(redis, slug=slug)
    await bust_sitemap_cache(redis)
    return deleted(ResponseCode.COLLECTION_DELETED, "Collection deleted successfully")


@router.post(
    "/admin/collections/bulk",
    response_model=BaseSuccessResponse[None],
    dependencies=[Depends(require_admin)],
)
async def bulk_action_collections(
    payload: BulkActionRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    await _service.bulk_action(db, payload)
    await _bust_list_cache(redis)
    return ok(None, ResponseCode.COLLECTION_UPDATED, "Bulk action applied")


@router.get(
    "/admin/collections/{col_id}/products",
    response_model=BaseSuccessResponse[dict],
    dependencies=[Depends(require_admin)],
)
async def admin_get_collection_products(
    col_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    items, total = await _service.get_products(
        db, col_id, page=page, page_size=page_size
    )
    return ok(
        {
            "items": [i.model_dump() for i in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        },
        ResponseCode.PRODUCT_LISTED,
        "Collection products listed",
    )


@router.post(
    "/admin/collections/{col_id}/products",
    response_model=BaseSuccessResponse[None],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def add_products_to_collection(
    col_id: uuid.UUID,
    payload: AddProductsToCollectionRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    await _service.add_products(db, col_id, payload)
    await _bust_list_cache(redis)
    return ok(
        None, ResponseCode.COLLECTION_PRODUCTS_ADDED, "Products added to collection"
    )


@router.delete(
    "/admin/collections/{col_id}/products/{product_id}",
    response_model=BaseSuccessResponse[None],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def remove_product_from_collection(
    col_id: uuid.UUID,
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    await _service.remove_product(db, col_id, product_id)
    await _bust_list_cache(redis)
    return deleted(
        ResponseCode.COLLECTION_PRODUCT_REMOVED, "Product removed from collection"
    )


@router.patch(
    "/admin/collections/{col_id}/products/reorder",
    response_model=BaseSuccessResponse[None],
    dependencies=[Depends(require_admin)],
)
async def reorder_collection_products(
    col_id: uuid.UUID,
    payload: ReorderProductsRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    await _service.reorder_products(db, col_id, payload)
    await _bust_list_cache(redis)
    return ok(None, ResponseCode.COLLECTION_UPDATED, "Products reordered")

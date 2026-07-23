import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, deleted, ok
from app.core.cache import (
    PREFIX_CATEGORY_TREE,
    TTL_CATEGORY_TREE,
    add_cache_headers,
    bust_category_tree_cache,
    cache_swr,
    check_not_modified,
    make_etag,
    not_modified_response,
)
from app.core.database import AsyncWorkerSessionLocal, get_db
from app.core.dependencies import require_admin
from app.core.redis import (
    get_redis,
    safe_redis_delete,
)
from app.modules.categories.schemas import (
    BulkCategoryActionRequest,
    CategoryAdminListResponse,
    CategoryCreateRequest,
    CategoryDetailResponse,
    CategoryProductsResponse,
    CategoryResponse,
    CategoryTreeNode,
    CategoryUpdateRequest,
    NavbarCategoriesResponse,
    NavigationCategoriesResponse,
)
from app.modules.categories.service import CategoryService
from app.modules.profiles.models import Profile

router = APIRouter(tags=["categories"])
_svc = CategoryService()

_NAVBAR_CACHE_KEY = "categories:navbar:v1"
_NAVBAR_TTL = 24 * 60 * 60
_NAV_CACHE_KEY = "navigation:categories:v2"
_NAV_TTL = 24 * 60 * 60


async def _bust_all_nav_caches(redis: aioredis.Redis) -> None:
    await safe_redis_delete(redis, _NAVBAR_CACHE_KEY, _NAV_CACHE_KEY)
    await bust_category_tree_cache(redis)


# ── Public endpoints ──────────────────────────────────────────────────────────


@router.get("/categories", response_model=BaseSuccessResponse[list[CategoryTreeNode]])
async def list_categories(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    cache_key = f"{PREFIX_CATEGORY_TREE}:all"

    # Fresh worker session — cache_swr may re-run this from a detached
    # background refresh task after the request session is gone.
    async def _fetch_tree():
        async with AsyncWorkerSessionLocal() as s:
            result = await _svc.get_tree(s)
            return [n.model_dump(mode="json") for n in result]

    data = await cache_swr(
        redis,
        cache_key,
        ttl=TTL_CATEGORY_TREE,
        swr_window=TTL_CATEGORY_TREE,
        fetch_fn=_fetch_tree,
    )

    import json as _json

    serialized = _json.dumps(
        ok(
            data,
            ResponseCode.CATEGORY_LISTED,
            "Categories fetched successfully",
        ).model_dump(mode="json"),
        default=str,
    )
    etag = make_etag(serialized)
    if check_not_modified(request, etag):
        return not_modified_response()

    response = JSONResponse(content=_json.loads(serialized))
    add_cache_headers(
        response,
        TTL_CATEGORY_TREE,
        stale_while_revalidate=TTL_CATEGORY_TREE,
        etag=etag,
    )
    return response


@router.get(
    "/categories/navbar", response_model=BaseSuccessResponse[NavbarCategoriesResponse]
)
async def navbar_categories(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    async def _fetch_navbar():
        async with AsyncWorkerSessionLocal() as s:
            result = await _svc.get_navbar(s)
            return result.model_dump()

    data = await cache_swr(
        redis,
        _NAVBAR_CACHE_KEY,
        ttl=_NAVBAR_TTL,
        swr_window=_NAVBAR_TTL,
        fetch_fn=_fetch_navbar,
    )
    response = JSONResponse(
        content=ok(
            data,
            ResponseCode.CATEGORY_LISTED,
            "Categories fetched successfully",
        ).model_dump(mode="json")
    )
    add_cache_headers(
        response, _NAVBAR_TTL, stale_while_revalidate=_NAVBAR_TTL, immutable=True
    )
    return response


@router.get(
    "/categories/navigation",
    response_model=BaseSuccessResponse[NavigationCategoriesResponse],
)
async def navigation_categories(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    async def _fetch_navigation():
        async with AsyncWorkerSessionLocal() as s:
            result = await _svc.get_navigation(s)
            return result.model_dump()

    data = await cache_swr(
        redis,
        _NAV_CACHE_KEY,
        ttl=_NAV_TTL,
        swr_window=_NAV_TTL,
        fetch_fn=_fetch_navigation,
    )
    response = JSONResponse(
        content=ok(
            data,
            ResponseCode.CATEGORY_LISTED,
            "Navigation categories fetched successfully",
        ).model_dump(mode="json")
    )
    add_cache_headers(
        response, _NAV_TTL, stale_while_revalidate=_NAV_TTL, immutable=True
    )
    return response


# ── Admin endpoints ───────────────────────────────────────────────────────────


@router.get(
    "/admin/categories",
    response_model=BaseSuccessResponse[CategoryAdminListResponse],
)
async def admin_list_categories(
    _: Profile = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: str | None = Query(None, max_length=200),
    parent_id: uuid.UUID | None = None,
    is_active: bool | None = None,
):
    result = await _svc.list_admin(
        db,
        page=page,
        page_size=page_size,
        search=search,
        parent_id=parent_id,
        is_active=is_active,
    )
    return ok(result, ResponseCode.CATEGORY_LISTED, "Categories listed successfully")


@router.get(
    "/admin/categories/{cat_id}",
    response_model=BaseSuccessResponse[CategoryDetailResponse],
)
async def admin_get_category(
    cat_id: uuid.UUID,
    _: Profile = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await _svc.get_detail(db, cat_id)
    return ok(result, ResponseCode.CATEGORY_LISTED, "Category fetched successfully")


@router.post(
    "/admin/categories",
    response_model=BaseSuccessResponse[CategoryResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_category(
    data: CategoryCreateRequest,
    current_user: Profile = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    from app.common.responses import created

    cat = await _svc.create(db, data, str(current_user.id))
    await _bust_all_nav_caches(redis)
    return created(
        CategoryResponse.model_validate(cat),
        ResponseCode.CATEGORY_CREATED,
        "Category created successfully",
    )


@router.patch(
    "/admin/categories/{cat_id}", response_model=BaseSuccessResponse[CategoryResponse]
)
async def update_category(
    cat_id: uuid.UUID,
    data: CategoryUpdateRequest,
    _: Profile = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    cat = await _svc.update(db, cat_id, data)
    await _bust_all_nav_caches(redis)
    return ok(
        CategoryResponse.model_validate(cat),
        ResponseCode.CATEGORY_UPDATED,
        "Category updated successfully",
    )


@router.delete(
    "/admin/categories/{cat_id}",
    response_model=BaseSuccessResponse[None],
    status_code=200,
)
async def delete_category(
    cat_id: uuid.UUID,
    _: Profile = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    await _svc.delete(db, cat_id)
    await _bust_all_nav_caches(redis)
    return deleted(ResponseCode.CATEGORY_DELETED, "Category deleted successfully")


@router.post(
    "/admin/categories/bulk",
    response_model=BaseSuccessResponse[None],
)
async def bulk_action_categories(
    payload: BulkCategoryActionRequest,
    _: Profile = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    await _svc.bulk_action(db, payload)
    await _bust_all_nav_caches(redis)
    return ok(None, ResponseCode.CATEGORY_UPDATED, "Bulk action applied")


@router.get(
    "/admin/categories/{cat_id}/products",
    response_model=BaseSuccessResponse[CategoryProductsResponse],
)
async def admin_get_category_products(
    cat_id: uuid.UUID,
    _: Profile = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    result = await _svc.get_products(db, cat_id, page=page, page_size=page_size)
    return ok(result, ResponseCode.PRODUCT_LISTED, "Category products listed")


@router.patch(
    "/admin/categories/{cat_id}/products/{product_id}",
    response_model=BaseSuccessResponse[None],
)
async def move_product_to_category(
    cat_id: uuid.UUID,
    product_id: uuid.UUID,
    _: Profile = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    await _svc.move_product(db, product_id, cat_id)
    return ok(None, ResponseCode.PRODUCT_UPDATED, "Product moved to category")

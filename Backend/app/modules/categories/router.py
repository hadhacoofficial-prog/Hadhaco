import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, deleted, ok
from app.core.database import get_db
from app.core.dependencies import require_admin
from app.core.redis import get_redis, safe_redis_delete, safe_redis_get, safe_redis_setex
from app.modules.categories.schemas import (
    CategoryCreateRequest,
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
_NAVBAR_TTL = 24 * 60 * 60  # 24 hours

_NAV_CACHE_KEY = "navigation:categories:v1"
_NAV_TTL = 24 * 60 * 60  # 24 hours


async def _bust_all_nav_caches(redis: aioredis.Redis) -> None:
    """Invalidate both navigation cache keys on any admin category change."""
    await safe_redis_delete(redis, _NAVBAR_CACHE_KEY, _NAV_CACHE_KEY)


# ── Public endpoints ──────────────────────────────────────────────────────────

@router.get("/categories", response_model=BaseSuccessResponse[list[CategoryTreeNode]])
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await _svc.get_tree(db)
    return ok(result, ResponseCode.CATEGORY_LISTED, "Categories fetched successfully")


@router.get("/categories/navbar", response_model=BaseSuccessResponse[NavbarCategoriesResponse])
async def navbar_categories(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Navbar-optimised endpoint: categories pre-grouped by gender (women/men/unisex/kids).

    Cached in Redis for 24 hours. Invalidated automatically when any admin
    creates, updates, or deletes a category.
    """
    cached = await safe_redis_get(redis, _NAVBAR_CACHE_KEY)
    if cached:
        return ok(
            NavbarCategoriesResponse.model_validate_json(cached),
            ResponseCode.CATEGORY_LISTED,
            "Categories fetched successfully",
        )

    result = await _svc.get_navbar(db)
    await safe_redis_setex(redis, _NAVBAR_CACHE_KEY, _NAVBAR_TTL, result.model_dump_json())
    return ok(result, ResponseCode.CATEGORY_LISTED, "Categories fetched successfully")


@router.get("/categories/navigation", response_model=BaseSuccessResponse[NavigationCategoriesResponse])
async def navigation_categories(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Main navigation endpoint: lean categories grouped by gender (women/men/unisex/kids).

    Only active categories with at least one active product are returned.
    Cached in Redis for 24 hours under key 'navigation:categories:v1'.
    Invalidated automatically when any admin creates, updates, or deletes a category.
    """
    cached = await safe_redis_get(redis, _NAV_CACHE_KEY)
    if cached:
        return ok(
            NavigationCategoriesResponse.model_validate_json(cached),
            ResponseCode.CATEGORY_LISTED,
            "Navigation categories fetched successfully",
        )

    result = await _svc.get_navigation(db)
    await safe_redis_setex(redis, _NAV_CACHE_KEY, _NAV_TTL, result.model_dump_json())
    return ok(result, ResponseCode.CATEGORY_LISTED, "Navigation categories fetched successfully")


# ── Admin endpoints ───────────────────────────────────────────────────────────

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


@router.patch("/admin/categories/{cat_id}", response_model=BaseSuccessResponse[CategoryResponse])
async def update_category(
    cat_id: str,
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
    cat_id: str,
    _: Profile = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    await _svc.delete(db, cat_id)
    await _bust_all_nav_caches(redis)
    return deleted(ResponseCode.CATEGORY_DELETED, "Category deleted successfully")

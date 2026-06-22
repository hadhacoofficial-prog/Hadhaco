from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, ok
from app.core.database import get_db
from app.core.dependencies import (
    get_current_user,
    profile_cache_key,
    require_admin,
    require_super_admin,
)
from app.core.redis import get_redis, safe_redis_delete
from app.modules.profiles.models import Profile
from app.modules.profiles.schemas import (
    AdminUserListResponse,
    AdminUserRoleUpdateRequest,
    AdminUserStatusUpdateRequest,
    ProfileResponse,
    ProfileUpdateRequest,
)
from app.modules.media.service import MediaService
from app.modules.profiles.service import ProfileService

router = APIRouter()
_svc = ProfileService()
_media_svc = MediaService()


async def _invalidate(redis: aioredis.Redis, user_id: str) -> None:
    await safe_redis_delete(redis, profile_cache_key(user_id))


# ── Customer profile endpoints ────────────────────────────────────────────────

@router.get("/me", response_model=BaseSuccessResponse[ProfileResponse])
async def get_my_profile(
    current_user: Profile = Depends(get_current_user),
) -> BaseSuccessResponse[ProfileResponse]:
    return ok(
        ProfileResponse.model_validate(current_user),
        ResponseCode.USER_PROFILE_FETCHED,
        "Profile fetched successfully",
    )


@router.patch("/me", response_model=BaseSuccessResponse[ProfileResponse])
async def update_my_profile(
    data: ProfileUpdateRequest,
    current_user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> BaseSuccessResponse[ProfileResponse]:
    profile = await _svc.update_profile(db, current_user.id, data)
    await _invalidate(redis, str(current_user.id))
    return ok(
        ProfileResponse.model_validate(profile),
        ResponseCode.USER_PROFILE_UPDATED,
        "Profile updated successfully",
    )


@router.patch("/me/avatar", response_model=BaseSuccessResponse[ProfileResponse])
async def update_avatar(
    file: UploadFile = File(...),
    current_user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> BaseSuccessResponse[ProfileResponse]:
    file_bytes = await file.read()
    avatar_url = _media_svc.upload_avatar(file_bytes, str(current_user.id))
    profile = await _svc.update_avatar(db, current_user.id, avatar_url)
    await _invalidate(redis, str(current_user.id))
    return ok(
        ProfileResponse.model_validate(profile),
        ResponseCode.USER_AVATAR_UPDATED,
        "Avatar updated successfully",
    )


# ── Admin user management endpoints ──────────────────────────────────────────

@router.get("/admin/users", response_model=BaseSuccessResponse[AdminUserListResponse])
async def list_users(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    role: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    sort_by: str = Query(default="created_at"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    _admin: Profile = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> BaseSuccessResponse[AdminUserListResponse]:
    result = await _svc.list_users(
        db,
        page=page,
        page_size=page_size,
        role=role,
        is_active=is_active,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    return ok(result, ResponseCode.USER_LISTED, "Users listed successfully")


@router.patch("/admin/users/{user_id}/role", response_model=BaseSuccessResponse[ProfileResponse])
async def change_user_role(
    user_id: str,
    data: AdminUserRoleUpdateRequest,
    current_user: Profile = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> BaseSuccessResponse[ProfileResponse]:
    profile = await _svc.change_role(db, user_id, data.role, current_user.id)
    await _invalidate(redis, user_id)
    return ok(
        ProfileResponse.model_validate(profile),
        ResponseCode.USER_ROLE_CHANGED,
        "User role updated successfully",
    )


@router.patch("/admin/users/{user_id}/status", response_model=BaseSuccessResponse[ProfileResponse])
async def set_user_status(
    user_id: str,
    data: AdminUserStatusUpdateRequest,
    current_user: Profile = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> BaseSuccessResponse[ProfileResponse]:
    profile = await _svc.set_status(db, user_id, data.is_active, current_user.id)
    await _invalidate(redis, user_id)
    return ok(
        ProfileResponse.model_validate(profile),
        ResponseCode.USER_STATUS_CHANGED,
        "User status updated successfully",
    )

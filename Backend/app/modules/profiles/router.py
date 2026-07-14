from typing import Annotated

import redis.asyncio as aioredis
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, ok
from app.core.database import get_db
from app.core.dependencies import (
    get_current_user,
    profile_cache_key,
    require_2fa_verified,
    require_admin,
    require_super_admin,
)
from app.core.redis import get_redis, safe_redis_delete
from app.modules.media.repository import ImageRepository
from app.modules.media.universal_service import (
    UniversalImageService,
    UniversalImageServiceError,
)
from app.modules.profiles.models import Profile
from app.modules.profiles.schemas import (
    AdminUserListResponse,
    AdminUserRoleUpdateRequest,
    AdminUserStatusUpdateRequest,
    ProfileResponse,
    ProfileUpdateRequest,
)
from app.modules.profiles.service import ProfileService

router = APIRouter()
_svc = ProfileService()
_universal = UniversalImageService()
_image_repo = ImageRepository()


async def _invalidate(redis: aioredis.Redis, user_id: str) -> None:
    await safe_redis_delete(redis, profile_cache_key(user_id))


async def _to_profile_response(db: AsyncSession, profile: Profile) -> ProfileResponse:
    result = ProfileResponse.model_validate(profile)
    if result.primary_image_id:
        # get_primary_variant_urls looks up by owner_id (the profile's own
        # id), not by primary_image_id (the Image row's own id).
        urls = await _image_repo.get_primary_variant_urls(
            db,
            "user",
            [result.id],
            variant_name="avatar",
            breakpoint="all",
        )
        result.avatar_url = urls.get(result.id)
    return result


# ── Customer profile endpoints ────────────────────────────────────────────────


@router.get("/me", response_model=BaseSuccessResponse[ProfileResponse])
async def get_my_profile(
    current_user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BaseSuccessResponse[ProfileResponse]:
    return ok(
        await _to_profile_response(db, current_user),
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
        await _to_profile_response(db, profile),
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
    try:
        image = await _universal.upload(
            db,
            preset_id="avatar",
            file_bytes=file_bytes,
            filename=file.filename or "avatar.jpg",
            content_type=file.content_type or "image/jpeg",
            owner_type="user",
            owner_id=current_user.id,
            uploaded_by=current_user.id,
        )
    except UniversalImageServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    profile = await _svc.update_avatar(db, current_user.id, image.id)
    await _invalidate(redis, str(current_user.id))
    return ok(
        await _to_profile_response(db, profile),
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
    sort_by: str = Query(
        default="created_at",
        pattern="^(created_at|updated_at|email|full_name|role)$",
    ),
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


@router.patch(
    "/admin/users/{user_id}/role", response_model=BaseSuccessResponse[ProfileResponse]
)
async def change_user_role(
    user_id: str,
    data: AdminUserRoleUpdateRequest,
    current_user: Profile = Depends(require_2fa_verified),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> BaseSuccessResponse[ProfileResponse]:
    profile = await _svc.change_role(db, user_id, data.role, current_user.id)
    await _invalidate(redis, user_id)
    return ok(
        await _to_profile_response(db, profile),
        ResponseCode.USER_ROLE_CHANGED,
        "User role updated successfully",
    )


@router.patch(
    "/admin/users/{user_id}/status", response_model=BaseSuccessResponse[ProfileResponse]
)
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
        await _to_profile_response(db, profile),
        ResponseCode.USER_STATUS_CHANGED,
        "User status updated successfully",
    )


@router.post(
    "/admin/users/{user_id}/2fa/reset",
    response_model=BaseSuccessResponse[None],
    summary="Force reset 2FA for an admin user (super_admin only)",
)
async def force_reset_2fa(
    user_id: str,
    request: Request,
    actor: Profile = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> BaseSuccessResponse[None]:
    from app.modules.audit.service import AuditService
    from app.modules.auth.service import AuthService

    svc = AuthService()
    await svc.force_reset_2fa(db, user_id)
    await AuditService().log(
        db,
        actor_id=str(actor.id),
        actor_email=actor.email,
        actor_role=actor.role,
        action="2fa_force_reset",
        resource_type="admin_2fa",
        resource_id=user_id,
        ip_address=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent"),
    )
    return ok(None, ResponseCode.AUTH_2FA_VERIFIED, "2FA has been reset for this user")

import math
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import UserRole
from app.core.exceptions import NotFoundError
from app.modules.media.repository import ImageRepository
from app.modules.profiles.models import Admin2FA, Profile
from app.modules.profiles.repository import ProfileRepository
from app.modules.profiles.schemas import (
    AdminUserListItem,
    AdminUserListResponse,
    ProfileUpdateRequest,
)

_image_repo = ImageRepository()


class ProfileService:
    def __init__(self) -> None:
        self._repo = ProfileRepository()

    async def get_profile(self, db: AsyncSession, user_id: str | uuid.UUID) -> Profile:
        profile = await self._repo.get_by_id(db, user_id)
        if not profile:
            raise NotFoundError("Profile not found")
        return profile

    async def update_profile(
        self,
        db: AsyncSession,
        user_id: str | uuid.UUID,
        data: ProfileUpdateRequest,
    ) -> Profile:
        update_data = data.model_dump(exclude_none=True)
        if not update_data:
            return await self.get_profile(db, user_id)
        profile = await self._repo.update(db, user_id, update_data)
        if not profile:
            raise NotFoundError("Profile not found")
        return profile

    async def update_avatar(
        self,
        db: AsyncSession,
        user_id: str | uuid.UUID,
        image_id: uuid.UUID,
    ) -> Profile:
        profile = await self._repo.update(db, user_id, {"primary_image_id": image_id})
        if not profile:
            raise NotFoundError("Profile not found")
        return profile

    async def list_users(
        self,
        db: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 20,
        role: str | None = None,
        is_active: bool | None = None,
        search: str | None = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
    ) -> AdminUserListResponse:
        items, total = await self._repo.list_paginated(
            db,
            page=page,
            page_size=page_size,
            role=role,
            is_active=is_active,
            search=search,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        total_pages = math.ceil(total / page_size) if page_size else 1
        list_items = [AdminUserListItem.model_validate(p) for p in items]
        # get_primary_variant_urls looks up by owner_id (the profile's own
        # id), not by primary_image_id (the Image row's own id).
        ids = [i.id for i in list_items if i.primary_image_id]
        urls = await _image_repo.get_primary_variant_urls(
            db, "user", ids, variant_name="avatar", breakpoint="all"
        )
        for item in list_items:
            if item.primary_image_id:
                item.avatar_url = urls.get(item.id)

        # Fetch 2FA status for all listed users
        user_ids = [i.id for i in list_items]
        if user_ids:
            result = await db.execute(
                select(Admin2FA.user_id, Admin2FA.is_enabled).where(
                    Admin2FA.user_id.in_(user_ids)
                )
            )
            two_fa_map = {row[0]: row[1] for row in result.all()}
        else:
            two_fa_map = {}

        for item in list_items:
            item.two_factor_enabled = bool(two_fa_map.get(item.id, False))

        return AdminUserListResponse(
            items=list_items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    async def change_role(
        self,
        db: AsyncSession,
        target_user_id: str | uuid.UUID,
        new_role: UserRole,
        actor_id: str | uuid.UUID,
    ) -> Profile:
        profile = await self._repo.get_by_id(db, target_user_id)
        if not profile:
            raise NotFoundError("User not found")
        old_role = profile.role
        updated = await self._repo.update(db, target_user_id, {"role": new_role})

        # Audit log
        from app.modules.audit.service import AuditService

        audit = AuditService()
        await audit.log(
            db,
            actor_id=str(actor_id),
            action="role_change",
            resource_type="profile",
            resource_id=str(target_user_id),
            metadata={"old_role": old_role, "new_role": new_role},
        )

        return updated  # type: ignore[return-value]

    async def set_status(
        self,
        db: AsyncSession,
        target_user_id: str | uuid.UUID,
        is_active: bool,
        actor_id: str | uuid.UUID,
    ) -> Profile:
        profile = await self._repo.get_by_id(db, target_user_id)
        if not profile:
            raise NotFoundError("User not found")
        updated = await self._repo.update(db, target_user_id, {"is_active": is_active})

        from app.modules.audit.service import AuditService

        audit = AuditService()
        await audit.log(
            db,
            actor_id=str(actor_id),
            action="status_change",
            resource_type="profile",
            resource_id=str(target_user_id),
            metadata={"is_active": is_active},
        )

        return updated  # type: ignore[return-value]

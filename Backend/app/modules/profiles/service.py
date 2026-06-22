import math
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import UserRole
from app.core.exceptions import ConflictError, NotFoundError
from app.modules.profiles.models import Profile
from app.modules.profiles.repository import ProfileRepository
from app.modules.profiles.schemas import (
    AdminUserListResponse,
    AdminUserListItem,
    ProfileUpdateRequest,
)


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
        avatar_url: str,
    ) -> Profile:
        profile = await self._repo.update(db, user_id, {"avatar_url": avatar_url})
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
        return AdminUserListResponse(
            items=[AdminUserListItem.model_validate(p) for p in items],
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

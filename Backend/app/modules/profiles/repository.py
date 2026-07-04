import uuid
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.profiles.models import Profile


class ProfileRepository:
    async def get_by_id(
        self, db: AsyncSession, user_id: str | uuid.UUID
    ) -> Profile | None:
        result = await db.execute(
            select(Profile).where(
                Profile.id == user_id,
                Profile.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, db: AsyncSession, email: str) -> Profile | None:
        result = await db.execute(
            select(Profile).where(
                Profile.email == email,
                Profile.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, db: AsyncSession, data: dict[str, Any]) -> Profile:
        profile = Profile(**data)
        db.add(profile)
        await db.flush()
        await db.refresh(profile)
        return profile

    async def update(
        self,
        db: AsyncSession,
        user_id: str | uuid.UUID,
        data: dict[str, Any],
    ) -> Profile | None:
        # UPDATE ... RETURNING instead of UPDATE-then-reSELECT (Profile has
        # no relationships to eager-load). Keeps get_by_id's deleted_at
        # filter so a soft-deleted profile isn't "successfully" updated.
        result = await db.execute(
            update(Profile)
            .where(Profile.id == user_id, Profile.deleted_at.is_(None))
            .values(**data)
            .returning(Profile)
        )
        return result.scalar_one_or_none()

    async def list_paginated(
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
    ) -> tuple[list[Profile], int]:
        q = select(Profile).where(Profile.deleted_at.is_(None))

        if role:
            q = q.where(Profile.role == role)
        if is_active is not None:
            q = q.where(Profile.is_active == is_active)
        if search:
            term = f"%{search}%"
            q = q.where(
                or_(
                    Profile.email.ilike(term),
                    Profile.full_name.ilike(term),
                )
            )

        # Count
        count_q = select(func.count()).select_from(q.subquery())
        total_result = await db.execute(count_q)
        total: int = total_result.scalar_one()

        # Sort
        sort_col = getattr(Profile, sort_by, Profile.created_at)
        if sort_dir == "desc":
            q = q.order_by(sort_col.desc())
        else:
            q = q.order_by(sort_col.asc())

        # Paginate
        offset = (page - 1) * page_size
        q = q.offset(offset).limit(page_size)

        result = await db.execute(q)
        items = list(result.scalars().all())
        return items, total

    async def soft_delete(self, db: AsyncSession, user_id: str | uuid.UUID) -> None:
        from datetime import UTC, datetime

        await db.execute(
            update(Profile)
            .where(Profile.id == user_id)
            .values(deleted_at=datetime.now(UTC), is_active=False)
        )

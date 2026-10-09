import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, func, or_, select, update
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
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> tuple[list[Profile], int]:
        """Admin user list. Each returned Profile carries ``_order_count`` and
        ``_total_spent`` (paid orders) computed in the same query, so the
        table can show and sort by customer value with no per-row lookups."""
        from app.modules.orders.models import Order

        filters: list[ColumnElement[bool]] = [Profile.deleted_at.is_(None)]
        if role:
            filters.append(Profile.role == role)
        if is_active is not None:
            filters.append(Profile.is_active == is_active)
        if date_from is not None:
            filters.append(Profile.created_at >= date_from)
        if date_to is not None:
            filters.append(Profile.created_at < date_to)
        if search:
            term = f"%{search.strip()}%"
            filters.append(
                or_(
                    Profile.email.ilike(term),
                    Profile.full_name.ilike(term),
                    Profile.phone.ilike(term),
                )
            )

        total_result = await db.execute(
            select(func.count()).select_from(Profile).where(*filters)
        )
        total: int = total_result.scalar_one()

        order_count = (
            select(func.count(Order.id))
            .where(Order.user_id == Profile.id)
            .correlate(Profile)
            .scalar_subquery()
        )
        total_spent = (
            select(func.coalesce(func.sum(Order.total), 0))
            .where(Order.user_id == Profile.id, Order.payment_status == "paid")
            .correlate(Profile)
            .scalar_subquery()
        )

        # Allowlist — never getattr(Profile, user_input).
        sort_columns: dict[str, Any] = {
            "created_at": Profile.created_at,
            "updated_at": Profile.updated_at,
            "email": func.lower(Profile.email),
            "full_name": func.lower(Profile.full_name),
            "role": Profile.role,
            "order_count": order_count,
            "total_spent": total_spent,
        }
        sort_col = sort_columns.get(sort_by, Profile.created_at)
        order = sort_col.desc().nulls_last() if sort_dir == "desc" else sort_col.asc()

        q = (
            select(
                Profile,
                order_count.label("_order_count"),
                total_spent.label("_total_spent"),
            )
            .where(*filters)
            .order_by(order, Profile.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(q)
        items: list[Profile] = []
        for profile, n_orders, spent in result.all():
            profile._order_count = int(n_orders or 0)
            profile._total_spent = float(spent or 0)
            items.append(profile)
        return items, total

    async def soft_delete(self, db: AsyncSession, user_id: str | uuid.UUID) -> None:
        from datetime import UTC, datetime

        await db.execute(
            update(Profile)
            .where(Profile.id == user_id)
            .values(deleted_at=datetime.now(UTC), is_active=False)
        )

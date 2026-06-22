import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.addresses.models import UserAddress

_MAX_ADDRESSES = 10


class AddressRepository:
    async def list_for_user(self, db: AsyncSession, user_id: uuid.UUID) -> list[UserAddress]:
        result = await db.execute(
            select(UserAddress)
            .where(UserAddress.user_id == user_id, UserAddress.deleted_at.is_(None))
            .order_by(UserAddress.is_default.desc(), UserAddress.created_at.desc())
        )
        return list(result.scalars().all())

    async def get(
        self, db: AsyncSession, address_id: uuid.UUID, user_id: uuid.UUID
    ) -> UserAddress | None:
        result = await db.execute(
            select(UserAddress).where(
                UserAddress.id == address_id,
                UserAddress.user_id == user_id,
                UserAddress.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def count_for_user(self, db: AsyncSession, user_id: uuid.UUID) -> int:
        from sqlalchemy import func

        result = await db.execute(
            select(func.count())
            .select_from(UserAddress)
            .where(
                UserAddress.user_id == user_id,
                UserAddress.deleted_at.is_(None),
            )
        )
        return result.scalar_one()

    async def create(self, db: AsyncSession, data: dict[str, Any]) -> UserAddress:
        addr = UserAddress(**data)
        db.add(addr)
        await db.flush()
        await db.refresh(addr)
        return addr

    async def update(
        self, db: AsyncSession, address_id: uuid.UUID, data: dict[str, Any]
    ) -> UserAddress | None:
        await db.execute(update(UserAddress).where(UserAddress.id == address_id).values(**data))
        result = await db.execute(select(UserAddress).where(UserAddress.id == address_id))
        return result.scalar_one_or_none()

    async def clear_default(self, db: AsyncSession, user_id: uuid.UUID, address_type: str) -> None:
        """Remove is_default from all addresses of this type for the user."""
        await db.execute(
            update(UserAddress)
            .where(
                UserAddress.user_id == user_id,
                UserAddress.type == address_type,
                UserAddress.deleted_at.is_(None),
            )
            .values(is_default=False)
        )

    async def soft_delete(self, db: AsyncSession, address_id: uuid.UUID) -> None:
        from datetime import UTC, datetime

        await db.execute(
            update(UserAddress)
            .where(UserAddress.id == address_id)
            .values(deleted_at=datetime.now(UTC), is_default=False)
        )

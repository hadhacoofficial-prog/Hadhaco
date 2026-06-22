from __future__ import annotations
import uuid
from datetime import UTC, datetime, timezone
from typing import Any
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.settings.models import FeatureFlag


class SettingsRepository:
    async def get_flag(self, db: AsyncSession, key: str) -> FeatureFlag | None:
        result = await db.execute(select(FeatureFlag).where(FeatureFlag.key == key))
        return result.scalar_one_or_none()

    async def list_flags(self, db: AsyncSession) -> list[FeatureFlag]:
        result = await db.execute(select(FeatureFlag).order_by(FeatureFlag.key))
        return list(result.scalars().all())

    async def upsert_flag(self, db: AsyncSession, *, key: str, value: bool, description: str | None, updated_by: uuid.UUID | None) -> FeatureFlag:
        stmt = insert(FeatureFlag).values(
            key=key, value=value, description=description, updated_by=updated_by, updated_at=datetime.now(UTC)
        ).on_conflict_do_update(
            index_elements=["key"],
            set_={"value": value, "description": description, "updated_by": updated_by, "updated_at": datetime.now(UTC)},
        ).returning(FeatureFlag)
        result = await db.execute(stmt)
        await db.flush()
        return result.scalar_one()

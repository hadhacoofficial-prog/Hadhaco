from __future__ import annotations
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.settings.models import FeatureFlag
from app.modules.settings.repository import SettingsRepository
from app.modules.settings.schemas import FeatureFlagUpdate


_repo = SettingsRepository()


class SettingsService:
    async def list_flags(self, db: AsyncSession) -> list[FeatureFlag]:
        return await _repo.list_flags(db)

    async def set_flag(self, db: AsyncSession, *, key: str, data: FeatureFlagUpdate, updated_by: uuid.UUID) -> FeatureFlag:
        flag = await _repo.upsert_flag(db, key=key, value=data.value, description=data.description, updated_by=updated_by)
        await db.commit()
        return flag

    @staticmethod
    async def is_feature_enabled(db: AsyncSession, key: str) -> bool:
        flag = await _repo.get_flag(db, key)
        return flag.value if flag else False

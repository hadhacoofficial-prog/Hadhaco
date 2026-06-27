from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.company.models import CompanyConfig


class CompanyConfigRepository:
    async def get(self, db: AsyncSession) -> CompanyConfig | None:
        result = await db.execute(select(CompanyConfig).where(CompanyConfig.id == 1))
        return result.scalar_one_or_none()

    async def update(self, db: AsyncSession, data: dict) -> CompanyConfig:
        row = await self.get(db)
        if not row:
            row = CompanyConfig(id=1)
            db.add(row)
        for key, val in data.items():
            if hasattr(row, key):
                setattr(row, key, val)
        await db.flush()
        return row

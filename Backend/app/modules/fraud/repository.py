from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fraud.models import FraudSignal


class FraudRepository:
    async def create(self, db: AsyncSession, **kwargs: Any) -> FraudSignal:
        signal = FraudSignal(**kwargs)
        db.add(signal)
        await db.flush()
        return signal

    async def get(self, db: AsyncSession, signal_id: uuid.UUID) -> FraudSignal | None:
        result = await db.execute(select(FraudSignal).where(FraudSignal.id == signal_id))
        return result.scalar_one_or_none()

    async def list_unresolved(
        self, db: AsyncSession, offset: int = 0, limit: int = 50
    ) -> list[FraudSignal]:
        result = await db.execute(
            select(FraudSignal)
            .where(FraudSignal.is_resolved == False)
            .order_by(FraudSignal.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update(
        self, db: AsyncSession, signal: FraudSignal, data: dict[str, Any]
    ) -> FraudSignal:
        for k, v in data.items():
            setattr(signal, k, v)
        db.add(signal)
        await db.flush()
        return signal

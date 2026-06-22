from __future__ import annotations
import uuid
from datetime import UTC, datetime, timezone
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.fraud.models import FraudSignal
from app.modules.fraud.repository import FraudRepository
from app.modules.fraud.schemas import FraudResolveRequest, FraudSignalCreate


class FraudService:
    def __init__(self) -> None:
        self._repo = FraudRepository()

    async def record_signal(self, db: AsyncSession, data: FraudSignalCreate) -> FraudSignal:
        signal = await self._repo.create(
            db,
            user_id=data.user_id,
            ip_address=data.ip_address,
            signal_type=data.signal_type,
            severity=data.severity,
            description=data.description,
            metadata_=data.metadata,
        )
        await db.commit()
        await db.refresh(signal)
        return signal

    async def list_signals(self, db: AsyncSession, *, offset: int, limit: int) -> list[FraudSignal]:
        return await self._repo.list_unresolved(db, offset=offset, limit=limit)

    async def resolve_signal(self, db: AsyncSession, *, signal_id: uuid.UUID, resolver_id: uuid.UUID, data: FraudResolveRequest) -> FraudSignal:
        signal = await self._repo.get(db, signal_id)
        if not signal:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Signal not found")
        signal = await self._repo.update(
            db, signal, {"is_resolved": data.is_resolved, "resolved_by": resolver_id, "resolved_at": datetime.now(UTC)}
        )
        await db.commit()
        await db.refresh(signal)
        return signal

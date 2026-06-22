from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.support.models import SupportMessage, SupportTicket


class SupportRepository:
    async def create_ticket(self, db: AsyncSession, **kwargs: Any) -> SupportTicket:
        t = SupportTicket(**kwargs)
        db.add(t)
        await db.flush()
        return t

    async def add_message(self, db: AsyncSession, **kwargs: Any) -> SupportMessage:
        m = SupportMessage(**kwargs)
        db.add(m)
        await db.flush()
        return m

    async def get_ticket(self, db: AsyncSession, ticket_id: uuid.UUID) -> SupportTicket | None:
        result = await db.execute(select(SupportTicket).where(SupportTicket.id == ticket_id))
        return result.scalar_one_or_none()

    async def list_for_customer(
        self, db: AsyncSession, customer_id: uuid.UUID
    ) -> list[SupportTicket]:
        result = await db.execute(
            select(SupportTicket)
            .where(SupportTicket.customer_id == customer_id)
            .order_by(SupportTicket.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_all(
        self, db: AsyncSession, *, status: str | None = None, offset: int = 0, limit: int = 50
    ) -> list[SupportTicket]:
        q = select(SupportTicket).order_by(SupportTicket.created_at.desc())
        if status:
            q = q.where(SupportTicket.status == status)
        result = await db.execute(q.offset(offset).limit(limit))
        return list(result.scalars().all())

    async def update_ticket(
        self, db: AsyncSession, ticket: SupportTicket, data: dict[str, Any]
    ) -> SupportTicket:
        for k, v in data.items():
            setattr(ticket, k, v)
        db.add(ticket)
        await db.flush()
        return ticket

    async def next_ticket_number(self, db: AsyncSession) -> str:
        from sqlalchemy import text

        result = await db.execute(text("SELECT COUNT(*) FROM support_tickets"))
        count = result.scalar() or 0
        year = datetime.now(UTC).year
        return f"SUP-{year}-{str(count + 1).zfill(4)}"

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.support.models import SupportMessage, SupportTicket
from app.modules.support.repository import SupportRepository
from app.modules.support.schemas import AdminTicketUpdate, MessageCreate, TicketCreate


class SupportService:
    def __init__(self) -> None:
        self._repo = SupportRepository()

    async def create_ticket(
        self, db: AsyncSession, *, customer_id: uuid.UUID, data: TicketCreate
    ) -> SupportTicket:
        ticket_number = await self._repo.next_ticket_number(db)
        ticket = await self._repo.create_ticket(
            db,
            ticket_number=ticket_number,
            customer_id=customer_id,
            order_id=data.order_id,
            subject=data.subject,
            category=data.category,
        )
        await self._repo.add_message(
            db, ticket_id=ticket.id, sender_id=customer_id, body=data.body
        )
        await db.commit()
        await db.refresh(ticket)
        return ticket

    async def reply(
        self,
        db: AsyncSession,
        *,
        ticket_id: uuid.UUID,
        sender_id: uuid.UUID,
        data: MessageCreate,
        is_admin: bool = False,
    ) -> SupportMessage:
        ticket = await self._repo.get_ticket(db, ticket_id)
        if not ticket:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
        if not is_admin and ticket.customer_id != sender_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your ticket")
        msg = await self._repo.add_message(
            db,
            ticket_id=ticket_id,
            sender_id=sender_id,
            body=data.body,
            is_internal=data.is_internal and is_admin,
        )
        if ticket.status == "resolved":
            await self._repo.update_ticket(db, ticket, {"status": "open"})
        await db.commit()
        await db.refresh(msg)
        return msg

    async def list_customer_tickets(
        self, db: AsyncSession, customer_id: uuid.UUID
    ) -> list[SupportTicket]:
        return await self._repo.list_for_customer(db, customer_id)

    async def get_ticket(
        self,
        db: AsyncSession,
        ticket_id: uuid.UUID,
        *,
        viewer_id: uuid.UUID,
        is_admin: bool,
    ) -> SupportTicket:
        ticket = await self._repo.get_ticket(db, ticket_id)
        if not ticket:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
        if not is_admin and ticket.customer_id != viewer_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your ticket")
        return ticket

    async def admin_list(
        self, db: AsyncSession, *, status_filter: str | None, offset: int, limit: int
    ) -> list[SupportTicket]:
        return await self._repo.list_all(
            db, status=status_filter, offset=offset, limit=limit
        )

    async def admin_update(
        self, db: AsyncSession, *, ticket_id: uuid.UUID, data: AdminTicketUpdate
    ) -> SupportTicket:
        ticket = await self._repo.get_ticket(db, ticket_id)
        if not ticket:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
        updates = data.model_dump(exclude_unset=True)
        ticket = await self._repo.update_ticket(db, ticket, updates)
        await db.commit()
        await db.refresh(ticket)
        return ticket

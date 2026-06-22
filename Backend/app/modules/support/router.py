from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, ok
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.modules.support.schemas import AdminTicketUpdate, MessageCreate, TicketCreate, TicketOut
from app.modules.support.service import SupportService

router = APIRouter(prefix="/support", tags=["support"])
_svc = SupportService()


@router.post("/tickets", response_model=BaseSuccessResponse[TicketOut], status_code=201)
async def create_ticket(
    data: TicketCreate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    from app.common.responses import created

    result = await _svc.create_ticket(db, customer_id=user.id, data=data)
    return created(
        result, ResponseCode.SUPPORT_TICKET_CREATED, "Support ticket created successfully"
    )


@router.get("/tickets", response_model=BaseSuccessResponse[list[TicketOut]])
async def list_tickets(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    result = await _svc.list_customer_tickets(db, user.id)
    return ok(result, ResponseCode.SUPPORT_TICKET_LISTED, "Tickets listed successfully")


@router.get("/tickets/{ticket_id}", response_model=BaseSuccessResponse[TicketOut])
async def get_ticket(
    ticket_id: uuid.UUID, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    result = await _svc.get_ticket(db, ticket_id, viewer_id=user.id, is_admin=False)
    return ok(result, ResponseCode.SUPPORT_TICKET_FETCHED, "Ticket fetched successfully")


@router.post("/tickets/{ticket_id}/messages", response_model=BaseSuccessResponse[dict])
async def reply_ticket(
    ticket_id: uuid.UUID,
    data: MessageCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    result = await _svc.reply(db, ticket_id=ticket_id, sender_id=user.id, data=data)
    return ok(result, ResponseCode.SUPPORT_TICKET_REPLIED, "Reply sent successfully")


@router.get("/admin/tickets", response_model=BaseSuccessResponse[list[TicketOut]])
async def admin_list_tickets(
    status: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await _svc.admin_list(db, status_filter=status, offset=offset, limit=limit)
    return ok(result, ResponseCode.SUPPORT_TICKET_LISTED, "Tickets listed successfully")


@router.patch("/admin/tickets/{ticket_id}", response_model=BaseSuccessResponse[TicketOut])
async def admin_update_ticket(
    ticket_id: uuid.UUID,
    data: AdminTicketUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await _svc.admin_update(db, ticket_id=ticket_id, data=data)
    return ok(result, ResponseCode.SUPPORT_TICKET_UPDATED, "Ticket updated successfully")


@router.post("/admin/tickets/{ticket_id}/messages", response_model=BaseSuccessResponse[dict])
async def admin_reply_ticket(
    ticket_id: uuid.UUID,
    data: MessageCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
    result = await _svc.reply(db, ticket_id=ticket_id, sender_id=admin.id, data=data, is_admin=True)
    return ok(result, ResponseCode.SUPPORT_TICKET_REPLIED, "Reply sent successfully")

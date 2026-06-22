from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, ok
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.modules.returns.schemas import AdminReturnStatusUpdate, ReturnCreate, ReturnOut
from app.modules.returns.service import ReturnService

router = APIRouter(prefix="/returns", tags=["returns"])
_svc = ReturnService()


@router.post("", response_model=BaseSuccessResponse[ReturnOut], status_code=201)
async def create_return(
    data: ReturnCreate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    from app.common.responses import created

    result = await _svc.create_return(db, customer_id=user.id, data=data)
    return created(result, ResponseCode.RETURN_CREATED, "Return request created successfully")


@router.get("", response_model=BaseSuccessResponse[list[ReturnOut]])
async def list_returns(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    result = await _svc.list_customer_returns(db, user.id)
    return ok(result, ResponseCode.RETURN_LISTED, "Returns listed successfully")


@router.get("/admin/returns", response_model=BaseSuccessResponse[list[ReturnOut]])
async def admin_list_returns(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await _svc.list_all(db, offset=offset, limit=limit)
    return ok(result, ResponseCode.RETURN_LISTED, "Returns listed successfully")


@router.patch("/admin/returns/{return_id}/status", response_model=BaseSuccessResponse[ReturnOut])
async def admin_update_return_status(
    return_id: uuid.UUID,
    data: AdminReturnStatusUpdate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
    result = await _svc.admin_update_status(
        db, return_id=return_id, admin_id=uuid.UUID(admin["sub"]), data=data
    )
    return ok(result, ResponseCode.RETURN_STATUS_UPDATED, "Return status updated successfully")

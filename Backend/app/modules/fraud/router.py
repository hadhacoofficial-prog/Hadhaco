from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, ok
from app.core.database import get_db
from app.core.dependencies import require_admin
from app.modules.fraud.schemas import FraudResolveRequest, FraudSignalCreate, FraudSignalOut
from app.modules.fraud.service import FraudService

router = APIRouter(prefix="/admin/fraud", tags=["fraud"])
_svc = FraudService()


@router.get("/signals", response_model=BaseSuccessResponse[list[FraudSignalOut]])
async def list_signals(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await _svc.list_signals(db, offset=offset, limit=limit)
    return ok(result, ResponseCode.FRAUD_SIGNALS_LISTED, "Fraud signals listed successfully")


@router.post("/signals", response_model=BaseSuccessResponse[FraudSignalOut], status_code=201)
async def create_signal(
    data: FraudSignalCreate, db: AsyncSession = Depends(get_db), _=Depends(require_admin)
):
    from app.common.responses import created

    result = await _svc.record_signal(db, data)
    return created(result, ResponseCode.FRAUD_SIGNAL_CREATED, "Fraud signal recorded successfully")


@router.patch("/signals/{signal_id}", response_model=BaseSuccessResponse[FraudSignalOut])
async def resolve_signal(
    signal_id: uuid.UUID,
    data: FraudResolveRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
    result = await _svc.resolve_signal(
        db, signal_id=signal_id, resolver_id=uuid.UUID(admin["sub"]), data=data
    )
    return ok(result, ResponseCode.FRAUD_SIGNAL_RESOLVED, "Fraud signal resolved successfully")

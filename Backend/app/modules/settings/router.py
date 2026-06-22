from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, ok
from app.core.database import get_db
from app.core.dependencies import require_admin
from app.modules.settings.schemas import FeatureFlagOut, FeatureFlagUpdate
from app.modules.settings.service import SettingsService

router = APIRouter(prefix="/admin/settings", tags=["settings"])
_svc = SettingsService()


@router.get("/flags", response_model=BaseSuccessResponse[list[FeatureFlagOut]])
async def list_flags(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await _svc.list_flags(db)
    return ok(result, ResponseCode.SETTINGS_FLAGS_LISTED, "Feature flags listed successfully")


@router.put("/flags/{key}", response_model=BaseSuccessResponse[FeatureFlagOut])
async def set_flag(
    key: str,
    data: FeatureFlagUpdate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
    result = await _svc.set_flag(db, key=key, data=data, updated_by=uuid.UUID(admin["sub"]))
    return ok(result, ResponseCode.SETTINGS_FLAG_UPDATED, "Feature flag updated successfully")

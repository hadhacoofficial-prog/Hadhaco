from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, ok
from app.core.database import get_db
from app.core.dependencies import require_2fa_verified, require_admin
from app.modules.company.repository import CompanyConfigRepository
from app.modules.company.schemas import CompanyConfigOut, CompanyConfigUpdate

router = APIRouter(prefix="/admin/company", tags=["company"])
_repo = CompanyConfigRepository()


@router.get("", response_model=BaseSuccessResponse[CompanyConfigOut])
async def get_company_config(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    config = await _repo.get(db)
    if config is None:
        config = await _repo.update(db, {})
        await db.commit()
    return ok(config, ResponseCode.COMPANY_CONFIG_RETRIEVED, "Company config retrieved")


@router.patch("", response_model=BaseSuccessResponse[CompanyConfigOut])
async def update_company_config(
    data: CompanyConfigUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_2fa_verified),
):
    payload = {k: v for k, v in data.model_dump().items() if v is not None}
    config = await _repo.update(db, payload)
    await db.commit()
    await db.refresh(config)
    return ok(config, ResponseCode.COMPANY_CONFIG_UPDATED, "Company config updated")

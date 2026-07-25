from __future__ import annotations

import json

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, ok
from app.core.cache import add_cache_headers, cache_swr
from app.core.database import AsyncSessionLocal, get_db
from app.core.dependencies import require_2fa_verified, require_admin
from app.core.redis import get_redis, safe_redis_delete
from app.modules.company.repository import CompanyConfigRepository
from app.modules.company.schemas import CompanyConfigOut, CompanyConfigUpdate

_TTL_COMPANY_CONFIG = 3600  # 1 hour
_COMPANY_CACHE_KEY = "company:config"

router = APIRouter(prefix="/admin/company", tags=["company"])
public_router = APIRouter(prefix="/company", tags=["company"])
_repo = CompanyConfigRepository()


# ── Public endpoint (no auth, cached) ────────────────────────────────────────


@public_router.get("")
async def get_company_config_public(
    redis: aioredis.Redis = Depends(get_redis),
):
    async def _fetch() -> dict:
        async with AsyncSessionLocal() as s:
            config = await _repo.get(s)
            if config is None:
                config = await _repo.update(s, {})
                await s.commit()
        payload = ok(
            CompanyConfigOut.model_validate(config),
            ResponseCode.COMPANY_CONFIG_RETRIEVED,
            "Company config retrieved",
        )
        return json.loads(payload.model_dump_json())

    result = await cache_swr(
        redis,
        _COMPANY_CACHE_KEY,
        ttl=_TTL_COMPANY_CONFIG,
        swr_window=_TTL_COMPANY_CONFIG,
        fetch_fn=_fetch,
    )
    response = JSONResponse(content=result)
    add_cache_headers(
        response, _TTL_COMPANY_CONFIG, stale_while_revalidate=_TTL_COMPANY_CONFIG
    )
    return response


# ── Admin endpoints (auth required) ─────────────────────────────────────────


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
    redis: aioredis.Redis = Depends(get_redis),
    _=Depends(require_2fa_verified),
):
    payload = {k: v for k, v in data.model_dump().items() if v is not None}
    config = await _repo.update(db, payload)
    await db.commit()
    await db.refresh(config)
    # Invalidate the public cache so storefront picks up new values
    await safe_redis_delete(redis, _COMPANY_CACHE_KEY)
    return ok(config, ResponseCode.COMPANY_CONFIG_UPDATED, "Company config updated")

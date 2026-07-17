from __future__ import annotations

from datetime import UTC, datetime

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, ok
from app.core.cache import (
    PREFIX_FEATURE_FLAG,
    TTL_FEATURE_FLAG,
    add_cache_headers,
    bust_feature_flag_cache,
)
from app.core.database import get_db
from app.core.dependencies import require_2fa_verified, require_admin
from app.core.redis import get_redis, safe_redis_get, safe_redis_setex
from app.modules.settings.schemas import (
    FeatureFlagOut,
    FeatureFlagUpdate,
    ProviderHealthOut,
    ProviderSettingsOut,
    ProviderSettingsUpdate,
    ProviderTestResult,
    WhatsAppMessageTemplateOut,
)
from app.modules.settings.service import SettingsService

router = APIRouter(prefix="/admin/settings", tags=["settings"])
public_router = APIRouter(prefix="/settings", tags=["settings"])
_svc = SettingsService()

_VALID_PROVIDERS = {"email", "whatsapp"}


def _validate_provider(provider: str) -> None:
    if provider not in _VALID_PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")


@router.get("/flags", response_model=BaseSuccessResponse[list[FeatureFlagOut]])
async def list_flags(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await _svc.list_flags(db)
    return ok(
        result, ResponseCode.SETTINGS_FLAGS_LISTED, "Feature flags listed successfully"
    )


@router.put("/flags/{key}", response_model=BaseSuccessResponse[FeatureFlagOut])
async def set_flag(
    key: str,
    data: FeatureFlagUpdate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_2fa_verified),
):
    result = await _svc.set_flag(db, key=key, data=data, updated_by=admin.id)
    from app.core.redis import get_redis_pool

    redis = get_redis_pool()
    await bust_feature_flag_cache(redis, key)
    return ok(
        result, ResponseCode.SETTINGS_FLAG_UPDATED, "Feature flag updated successfully"
    )


@router.get(
    "/notification-providers/{provider}",
    response_model=BaseSuccessResponse[ProviderSettingsOut],
)
async def get_provider_settings(
    provider: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    _validate_provider(provider)
    values = await _svc.get_provider_settings(db, provider=provider)
    return ok(
        ProviderSettingsOut(provider=provider, settings=values),
        ResponseCode.SETTINGS_PROVIDER_FETCHED,
        "Provider settings fetched successfully",
    )


@router.put(
    "/notification-providers/{provider}",
    response_model=BaseSuccessResponse[ProviderSettingsOut],
)
async def update_provider_settings(
    provider: str,
    data: ProviderSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_2fa_verified),
):
    _validate_provider(provider)
    values = await _svc.update_provider_settings(
        db, provider=provider, data=data.values, updated_by=admin.id
    )
    return ok(
        ProviderSettingsOut(provider=provider, settings=values),
        ResponseCode.SETTINGS_PROVIDER_UPDATED,
        "Provider settings updated successfully",
    )


@router.get(
    "/notification-providers/{provider}/health",
    response_model=BaseSuccessResponse[ProviderHealthOut],
)
async def get_provider_health(
    provider: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    _validate_provider(provider)
    health = await _svc.get_provider_health(db, provider=provider)
    return ok(
        ProviderHealthOut(**health),
        ResponseCode.SETTINGS_PROVIDER_FETCHED,
        "Provider health fetched successfully",
    )


@router.get(
    "/notification-providers/whatsapp/templates",
    response_model=BaseSuccessResponse[list[WhatsAppMessageTemplateOut]],
)
async def list_whatsapp_templates(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    templates = await _svc.list_whatsapp_templates(db)
    return ok(
        templates,
        ResponseCode.SETTINGS_PROVIDER_TEMPLATES_LISTED,
        "WhatsApp templates listed successfully",
    )


@router.post(
    "/notification-providers/email/test",
    response_model=BaseSuccessResponse[ProviderTestResult],
)
async def test_email_provider(
    to: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    from app.modules.notifications.dispatcher import dispatcher

    try:
        msg_id = await dispatcher.send_email(
            db,
            to=to,
            subject="Test notification from Hadha.co",
            html="<p>This is a test email from the Hadha.co notification system.</p>",
        )
        result = ProviderTestResult(
            success=True, message="Test email sent", message_id=msg_id
        )
    except Exception as exc:
        result = ProviderTestResult(success=False, message=str(exc))
    return ok(
        result, ResponseCode.SETTINGS_PROVIDER_TESTED, "Email provider test completed"
    )


@router.post(
    "/notification-providers/whatsapp/test",
    response_model=BaseSuccessResponse[ProviderTestResult],
)
async def test_whatsapp_provider(
    to: str,
    template_name: str,
    language: str = "en_US",
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    from app.modules.notifications.providers.registry import registry

    try:
        provider = registry.get_whatsapp_provider()
        msg_id = await provider.send_whatsapp(
            db, to=to, template_name=template_name, language=language, components=[]
        )
        result = ProviderTestResult(
            success=True, message="Test WhatsApp message sent", message_id=msg_id
        )
    except Exception as exc:
        result = ProviderTestResult(success=False, message=str(exc))
    return ok(
        result,
        ResponseCode.SETTINGS_PROVIDER_TESTED,
        "WhatsApp provider test completed",
    )


@public_router.get("/flags/{key}", response_model=BaseSuccessResponse[FeatureFlagOut])
async def get_public_flag(
    key: str,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    cache_key = f"{PREFIX_FEATURE_FLAG}:{key}"
    cached = await safe_redis_get(redis, cache_key)
    if cached:
        import json as _json

        from fastapi.responses import JSONResponse

        content = _json.loads(cached)
        response = JSONResponse(content=content)
        add_cache_headers(response, TTL_FEATURE_FLAG)
        return response

    flag = await _svc.get_flag(db, key=key)
    result = (
        FeatureFlagOut.model_validate(flag)
        if flag
        else FeatureFlagOut(
            key=key, value=False, description=None, updated_at=datetime.now(UTC)
        )
    )
    response_data = ok(
        result, ResponseCode.SETTINGS_FLAGS_LISTED, "Feature flag fetched successfully"
    )
    import json as _json

    from fastapi.responses import JSONResponse

    serialized = _json.dumps(_json.loads(response_data.model_dump_json()), default=str)
    await safe_redis_setex(redis, cache_key, TTL_FEATURE_FLAG, serialized)
    content = _json.loads(serialized)
    response = JSONResponse(content=content)
    add_cache_headers(response, TTL_FEATURE_FLAG)
    return response

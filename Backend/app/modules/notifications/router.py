from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, ok
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.modules.notifications.schemas import (
    DailyTotalOut,
    NotificationAnalyticsOut,
    NotificationLogOut,
    NotificationPreferenceOut,
    NotificationPreferenceUpdate,
    NotificationRuleOut,
    NotificationRuleUpdate,
    NotificationTemplateOut,
    NotificationTemplateUpdate,
    NotificationTemplateVersionOut,
    ProviderSuccessRateOut,
    TopTemplateOut,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


# ── User preference endpoints ─────────────────────────────────────────────────


@router.get(
    "/preferences",
    response_model=BaseSuccessResponse[list[NotificationPreferenceOut]],
)
async def get_preferences(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    from app.modules.notifications.repository import NotificationRepository

    repo = NotificationRepository()
    pref = await repo.get_preferences(db, user.id)
    return ok(
        [pref] if pref else [],
        ResponseCode.NOTIFICATION_PREFERENCES_FETCHED,
        "Preferences fetched successfully",
    )


@router.put(
    "/preferences",
    response_model=BaseSuccessResponse[NotificationPreferenceOut],
)
async def upsert_preference(
    data: NotificationPreferenceUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    from app.modules.notifications.repository import NotificationRepository

    repo = NotificationRepository()
    update_data = data.model_dump(exclude_unset=True)
    pref = await repo.upsert_preferences(db, user.id, update_data)
    return ok(
        pref,
        ResponseCode.NOTIFICATION_PREFERENCE_UPSERTED,
        "Preference updated successfully",
    )


# ── Admin: Notification logs ─────────────────────────────────────────────────


@router.get(
    "/admin/logs",
    response_model=BaseSuccessResponse[dict],
)
async def list_logs(
    status: str | None = None,
    channel: str | None = None,
    event_type: str | None = None,
    category: str | None = None,
    provider: str | None = None,
    search: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    from app.modules.notifications.repository import NotificationRepository

    repo = NotificationRepository()
    logs, total = await repo.list_logs(
        db,
        status=status,
        channel=channel,
        event_type=event_type,
        category=category,
        provider=provider,
        search=search,
        date_from=date_from,
        date_to=date_to,
        offset=offset,
        limit=limit,
    )
    return ok(
        {
            "items": [NotificationLogOut.model_validate(log) for log in logs],
            "total": total,
            "offset": offset,
            "limit": limit,
        },
        ResponseCode.NOTIFICATION_LOGS_LISTED,
        "Notification logs listed successfully",
    )


# ── Admin: Retry failed notifications ────────────────────────────────────────


class RetryLogsRequest(BaseModel):
    log_ids: list[uuid.UUID]


@router.post("/admin/logs/retry", response_model=BaseSuccessResponse[dict])
async def retry_logs_by_id(
    data: RetryLogsRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Explicit admin retry of one or more specific logs (individual or bulk),
    regardless of their current retry-delay gate."""
    from app.modules.notifications.service import NotificationService

    svc = NotificationService()
    retried = 0
    for log_id in data.log_ids:
        if await svc.retry_log_by_id(db, log_id):
            retried += 1
    return ok(
        {"retried": retried, "requested": len(data.log_ids)},
        ResponseCode.NOTIFICATION_LOG_RETRIED,
        f"Retried {retried} of {len(data.log_ids)} notification(s)",
    )


@router.post("/admin/retry", response_model=BaseSuccessResponse[dict])
async def retry_pending_notifications(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    from app.modules.notifications.repository import NotificationRepository
    from app.modules.notifications.service import NotificationService

    repo = NotificationRepository()
    pending = await repo.get_pending_retries(db)
    count = len(pending)
    svc = NotificationService()
    await svc.retry_pending(db)
    return ok(
        {"retried": count},
        ResponseCode.NOTIFICATIONS_RETRIED,
        f"Retried {count} pending notification(s)",
    )


# ── Admin: Analytics ─────────────────────────────────────────────────────────


@router.get(
    "/admin/analytics",
    response_model=BaseSuccessResponse[NotificationAnalyticsOut],
)
async def get_analytics(
    hours: int = Query(24, ge=1, le=2160),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    from app.modules.notifications.repository import NotificationRepository

    repo = NotificationRepository()
    data = await repo.get_analytics(db, hours=hours)
    daily_totals = [
        DailyTotalOut(**row)
        for row in await repo.get_daily_totals(db, days=max(hours // 24, 1))
    ]
    top_templates = [TopTemplateOut(**row) for row in await repo.get_top_templates(db)]
    provider_success_rate = {
        provider: ProviderSuccessRateOut(**rate)
        for provider, rate in (await repo.get_provider_success_rate(db)).items()
    }
    avg_delivery_seconds = await repo.get_average_delivery_seconds(db)
    return ok(
        NotificationAnalyticsOut(
            **data,
            daily_totals=daily_totals,
            top_templates=top_templates,
            provider_success_rate=provider_success_rate,
            avg_delivery_seconds=avg_delivery_seconds,
        ),
        ResponseCode.NOTIFICATION_ANALYTICS_FETCHED,
        "Notification analytics fetched successfully",
    )


# ── Admin: Notification rules (matrix) ───────────────────────────────────────


@router.get(
    "/admin/rules",
    response_model=BaseSuccessResponse[list[NotificationRuleOut]],
)
async def list_rules(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    from app.modules.notifications.repository import NotificationRepository

    repo = NotificationRepository()
    rules = await repo.list_rules(db)
    return ok(
        rules,
        ResponseCode.NOTIFICATION_RULES_LISTED,
        "Notification rules listed successfully",
    )


@router.put(
    "/admin/rules/{event_type}",
    response_model=BaseSuccessResponse[NotificationRuleOut],
)
async def update_rule(
    event_type: str,
    data: NotificationRuleUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    from app.modules.notifications.repository import NotificationRepository

    repo = NotificationRepository()
    update_data = data.model_dump(exclude_unset=True)
    rule = await repo.upsert_rule(db, event_type=event_type, **update_data)
    return ok(
        rule,
        ResponseCode.NOTIFICATION_RULE_UPDATED,
        "Notification rule updated successfully",
    )


# ── Admin: Template management ───────────────────────────────────────────────


@router.get(
    "/admin/templates",
    response_model=BaseSuccessResponse[list[NotificationTemplateOut]],
)
async def list_templates(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    from app.modules.notifications.repository import NotificationRepository

    repo = NotificationRepository()
    templates = await repo.list_templates(db)
    return ok(
        templates,
        ResponseCode.NOTIFICATION_TEMPLATES_LISTED,
        "Notification templates listed successfully",
    )


@router.put(
    "/admin/templates/{template_id}",
    response_model=BaseSuccessResponse[NotificationTemplateOut],
)
async def update_template(
    template_id: uuid.UUID,
    data: NotificationTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
    from app.modules.notifications.repository import NotificationRepository

    repo = NotificationRepository()
    update_data = data.model_dump(exclude_unset=True)
    template = await repo.update_template(
        db, template_id, update_data, updated_by=admin.id
    )
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return ok(
        template,
        ResponseCode.NOTIFICATION_TEMPLATE_UPDATED,
        "Notification template updated successfully",
    )


@router.get(
    "/admin/templates/{template_id}/versions",
    response_model=BaseSuccessResponse[list[NotificationTemplateVersionOut]],
)
async def list_template_versions(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    from app.modules.notifications.repository import NotificationRepository

    repo = NotificationRepository()
    versions = await repo.list_template_versions(db, template_id)
    return ok(
        versions,
        ResponseCode.NOTIFICATION_TEMPLATES_LISTED,
        "Notification template versions listed successfully",
    )


@router.post(
    "/admin/templates/{template_id}/versions/{version}/restore",
    response_model=BaseSuccessResponse[NotificationTemplateOut],
)
async def restore_template_version(
    template_id: uuid.UUID,
    version: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
    from app.modules.notifications.repository import NotificationRepository

    repo = NotificationRepository()
    snapshot = await repo.get_template_version(db, template_id, version)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Template version not found")

    template = await repo.update_template(
        db,
        template_id,
        {
            "subject": snapshot.subject,
            "template_body": snapshot.template_body,
            "variables": snapshot.variables,
        },
        updated_by=admin.id,
    )
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return ok(
        template,
        ResponseCode.NOTIFICATION_TEMPLATE_RESTORED,
        f"Template restored to version {version}",
    )


@router.post(
    "/admin/templates/{template_id}/duplicate",
    response_model=BaseSuccessResponse[NotificationTemplateOut],
)
async def duplicate_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    from app.modules.notifications.repository import NotificationRepository

    repo = NotificationRepository()
    copy = await repo.duplicate_template(db, template_id)
    if not copy:
        raise HTTPException(status_code=404, detail="Template not found")
    return ok(
        copy,
        ResponseCode.NOTIFICATION_TEMPLATE_DUPLICATED,
        "Template duplicated successfully",
    )


# ── Admin: Test notifications ────────────────────────────────────────────────
# Moved to app.modules.settings.router — POST /admin/settings/notification-
# providers/{email,whatsapp}/test — so test-sends go through the same
# dispatcher + provider-settings resolution as real notifications.

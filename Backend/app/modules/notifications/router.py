from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, ok
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.modules.notifications.models import NotificationLog, NotificationPreference

router = APIRouter(prefix="/notifications", tags=["notifications"])


class PreferenceIn(BaseModel):
    channel: str
    event_type: str
    enabled: bool


class PreferenceOut(BaseModel):
    channel: str
    event_type: str
    enabled: bool
    model_config = {"from_attributes": True}


class NotificationLogOut(BaseModel):
    id: uuid.UUID
    channel: str
    recipient: str
    subject: str | None
    status: str
    created_at: datetime
    model_config = {"from_attributes": True}


@router.get("/preferences", response_model=BaseSuccessResponse[list[PreferenceOut]])
async def get_preferences(
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    result = await db.execute(
        select(NotificationPreference).where(NotificationPreference.user_id == user.id)
    )
    prefs = list(result.scalars().all())
    return ok(
        prefs,
        ResponseCode.NOTIFICATION_PREFERENCES_FETCHED,
        "Preferences fetched successfully",
    )


@router.put("/preferences", response_model=BaseSuccessResponse[PreferenceOut])
async def upsert_preference(
    data: PreferenceIn,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    stmt = (
        insert(NotificationPreference)
        .values(
            user_id=user.id,
            channel=data.channel,
            event_type=data.event_type,
            enabled=data.enabled,
        )
        .on_conflict_do_update(
            index_elements=["user_id", "channel", "event_type"],
            set_={"enabled": data.enabled},
        )
        .returning(NotificationPreference)
    )
    result = await db.execute(stmt)
    await db.commit()
    pref = result.scalar_one()
    return ok(
        pref,
        ResponseCode.NOTIFICATION_PREFERENCE_UPSERTED,
        "Preference updated successfully",
    )


@router.get("/admin/logs", response_model=BaseSuccessResponse[list[NotificationLogOut]])
async def list_logs(
    status: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    q = select(NotificationLog).order_by(NotificationLog.created_at.desc())
    if status:
        q = q.where(NotificationLog.status == status)
    result = await db.execute(q.offset(offset).limit(limit))
    logs = list(result.scalars().all())
    return ok(
        logs,
        ResponseCode.NOTIFICATION_LOGS_LISTED,
        "Notification logs listed successfully",
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

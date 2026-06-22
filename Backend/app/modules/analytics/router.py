from __future__ import annotations
import uuid
from datetime import date, timedelta
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, accepted, ok
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.modules.analytics.schemas import DashboardStats, TrackEventRequest
from app.modules.analytics.service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])
_svc = AnalyticsService()


@router.post("/events", response_model=BaseSuccessResponse[None], status_code=202)
async def track_event(
    body: TrackEventRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user_id: str | None = None
    try:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            from app.core.security import verify_supabase_jwt
            payload = await verify_supabase_jwt(auth[7:])
            user_id = payload.sub
    except Exception:
        pass
    ip = request.client.host if request.client else None
    ua = request.headers.get("User-Agent")
    await _svc.track(db, request=body, user_id=user_id, ip_address=ip, user_agent=ua)
    return accepted(None, ResponseCode.ANALYTICS_EVENT_TRACKED, "Event tracked successfully")


@router.get("/admin/dashboard", response_model=BaseSuccessResponse[dict])
async def admin_dashboard(
    from_date: date | None = None,
    to_date: date | None = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    today = date.today()
    fd = from_date or (today - timedelta(days=30))
    td = to_date or today
    result = await _svc.get_dashboard(db, from_date=fd, to_date=td)
    return ok(result, ResponseCode.ANALYTICS_DASHBOARD_FETCHED, "Dashboard data fetched successfully")

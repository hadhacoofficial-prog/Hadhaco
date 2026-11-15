from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, accepted, ok
from app.core.database import get_db
from app.core.dependencies import require_admin
from app.modules.analytics.schemas import TrackEventRequest
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
        from app.core.auth_cookies import read_access_cookie
        from app.core.security import verify_access_token

        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else read_access_cookie(request)
        if token:
            # Read-only attribution of the event: no CSRF/revocation needed, and
            # any failure just records the event as anonymous.
            user_id = verify_access_token(token).sub
    except Exception:
        pass
    ip = request.client.host if request.client else None
    ua = request.headers.get("User-Agent")
    await _svc.track(db, request=body, user_id=user_id, ip_address=ip, user_agent=ua)
    return accepted(
        None, ResponseCode.ANALYTICS_EVENT_TRACKED, "Event tracked successfully"
    )


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
    return ok(
        result,
        ResponseCode.ANALYTICS_DASHBOARD_FETCHED,
        "Dashboard data fetched successfully",
    )

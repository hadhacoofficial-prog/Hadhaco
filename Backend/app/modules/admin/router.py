from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, ok
from app.core.database import get_db
from app.core.dependencies import require_admin
from app.modules.admin.schemas import KPIStats
from app.modules.audit.repository import AuditRepository
from app.modules.audit.schemas import AuditLogEntry, AuditLogPage

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/dashboard", response_model=BaseSuccessResponse[KPIStats])
async def dashboard(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    today = date.today()
    today_start = datetime(today.year, today.month, today.day, tzinfo=UTC)
    tomorrow_start = today_start + timedelta(days=1)

    rows = await db.execute(
        text("""
        SELECT
            (SELECT COUNT(*) FROM orders WHERE created_at >= :ts AND created_at < :te)               AS today_orders,
            (SELECT COALESCE(SUM(total),0) FROM orders WHERE created_at >= :ts AND created_at < :te) AS today_revenue,
            (SELECT COUNT(*) FROM profiles WHERE role = 'customer' AND created_at >= :ts AND created_at < :te) AS new_customers_today,
            (SELECT COUNT(*) FROM orders WHERE status = 'pending')                                    AS pending_orders,
            (SELECT COUNT(*) FROM support_tickets WHERE status IN ('open','in_progress'))             AS open_support_tickets,
            (SELECT COUNT(*) FROM fraud_signals WHERE is_resolved = FALSE)                            AS unresolved_fraud_signals,
            (SELECT COUNT(*) FROM products WHERE track_inventory = TRUE AND deleted_at IS NULL
                AND stock_quantity <= low_stock_threshold)                                            AS low_stock_products
        """),
        {"ts": today_start, "te": tomorrow_start},
    )
    row = rows.mappings().one()
    stats = KPIStats(
        today_orders=row["today_orders"],
        today_revenue=float(row["today_revenue"]),
        new_customers_today=row["new_customers_today"],
        pending_orders=row["pending_orders"],
        open_support_tickets=row["open_support_tickets"],
        unresolved_fraud_signals=row["unresolved_fraud_signals"],
        low_stock_products=row["low_stock_products"],
    )
    return ok(stats, ResponseCode.ADMIN_DASHBOARD_FETCHED, "Dashboard stats fetched successfully")


@router.get("/audit-logs", response_model=BaseSuccessResponse[AuditLogPage])
async def list_audit_logs(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    actor_id: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
):
    items, total = await AuditRepository().list_paginated(
        db,
        page=page,
        page_size=page_size,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        date_from=date_from,
        date_to=date_to,
    )
    result = AuditLogPage(
        items=[AuditLogEntry.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )
    return ok(result, ResponseCode.ADMIN_AUDIT_LOGS_FETCHED, "Audit logs fetched successfully")

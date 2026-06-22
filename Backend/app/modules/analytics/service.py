from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.repository import AnalyticsRepository
from app.modules.analytics.schemas import TrackEventRequest


class AnalyticsService:
    def __init__(self) -> None:
        self._repo = AnalyticsRepository()

    async def track(
        self,
        db: AsyncSession,
        *,
        request: TrackEventRequest,
        user_id: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        await self._repo.record(
            db,
            event_type=request.event_type,
            user_id=user_id,
            session_id=request.session_id,
            product_id=request.product_id,
            category_id=request.category_id,
            event_metadata=request.metadata,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.commit()

    async def get_dashboard(
        self, db: AsyncSession, *, from_date: date, to_date: date
    ) -> dict[str, Any]:
        summary = await self._repo.get_dashboard(
            db, from_date=from_date, to_date=to_date
        )
        by_day = await self._repo.get_revenue_by_day(
            db, from_date=from_date, to_date=to_date
        )
        by_status = await self._repo.get_orders_by_status(
            db, from_date=from_date, to_date=to_date
        )
        top = await self._repo.get_top_products(
            db, from_date=from_date, to_date=to_date
        )
        return {
            "revenue": {"total": float(summary.get("revenue", 0))},
            "orders": {"total": int(summary.get("total_orders", 0))},
            "aov": {"value": float(summary.get("aov", 0))},
            "conversion_rate": 0.0,
            "top_products": [
                {
                    "product_id": str(r["product_id"]),
                    "product_name": r["name"],
                    "total_quantity": int(r["units_sold"]),
                    "total_revenue": float(r["revenue"]),
                }
                for r in top
            ],
            "revenue_by_day": [
                {"date": str(r["date"]), "total": float(r["revenue"])} for r in by_day
            ],
            "orders_by_status": by_status,
        }

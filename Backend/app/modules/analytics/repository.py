from __future__ import annotations
import uuid
from datetime import date, datetime, timezone
from typing import Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.analytics.models import AnalyticsEvent


class AnalyticsRepository:
    async def record(self, db: AsyncSession, **kwargs: Any) -> None:
        event = AnalyticsEvent(**kwargs)
        db.add(event)
        await db.flush()

    async def get_dashboard(
        self, db: AsyncSession, *, from_date: date, to_date: date
    ) -> dict[str, Any]:
        result = await db.execute(
            text("""
                SELECT
                    COALESCE(SUM(total) FILTER (WHERE status NOT IN ('cancelled','pending')), 0) AS revenue,
                    COUNT(*) FILTER (WHERE status NOT IN ('cancelled')) AS total_orders,
                    COALESCE(ROUND(AVG(total) FILTER (WHERE status NOT IN ('cancelled','pending')), 2), 0) AS aov
                FROM orders
                WHERE created_at::date BETWEEN :from_date AND :to_date
            """),
            {"from_date": from_date, "to_date": to_date},
        )
        row = result.fetchone()
        return dict(row._mapping) if row else {}

    async def get_revenue_by_day(
        self, db: AsyncSession, *, from_date: date, to_date: date
    ) -> list[dict[str, Any]]:
        result = await db.execute(
            text("""
                SELECT
                    created_at::date AS date,
                    COALESCE(SUM(total) FILTER (WHERE status NOT IN ('cancelled','pending')), 0) AS revenue,
                    COUNT(*) FILTER (WHERE status NOT IN ('cancelled')) AS orders
                FROM orders
                WHERE created_at::date BETWEEN :from_date AND :to_date
                GROUP BY created_at::date
                ORDER BY date
            """),
            {"from_date": from_date, "to_date": to_date},
        )
        return [dict(r._mapping) for r in result.fetchall()]

    async def get_orders_by_status(
        self, db: AsyncSession, *, from_date: date, to_date: date
    ) -> dict[str, int]:
        result = await db.execute(
            text("""
                SELECT status, COUNT(*) AS cnt
                FROM orders
                WHERE created_at::date BETWEEN :from_date AND :to_date
                GROUP BY status
            """),
            {"from_date": from_date, "to_date": to_date},
        )
        return {r.status: r.cnt for r in result.fetchall()}

    async def get_top_products(
        self, db: AsyncSession, *, from_date: date, to_date: date, limit: int = 10
    ) -> list[dict[str, Any]]:
        result = await db.execute(
            text("""
                SELECT
                    oi.product_id,
                    p.name,
                    p.slug,
                    SUM(oi.quantity) AS units_sold,
                    SUM(oi.line_total) AS revenue
                FROM order_items oi
                JOIN orders o ON o.id = oi.order_id
                JOIN products p ON p.id = oi.product_id
                WHERE o.created_at::date BETWEEN :from_date AND :to_date
                  AND o.status NOT IN ('cancelled','pending')
                GROUP BY oi.product_id, p.name, p.slug
                ORDER BY revenue DESC
                LIMIT :limit
            """),
            {"from_date": from_date, "to_date": to_date, "limit": limit},
        )
        return [dict(r._mapping) for r in result.fetchall()]

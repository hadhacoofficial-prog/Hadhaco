"""
Create next-month partitions for analytics_events and audit_logs.
Run first day of each month.
"""

from __future__ import annotations

import time
from datetime import date, timedelta

import structlog
from sqlalchemy import text

from app.core.database import AsyncSessionLocal

log = structlog.get_logger(__name__)


async def run() -> None:
    t0 = time.perf_counter()
    next_month = date.today().replace(day=1) + timedelta(days=32)
    next_month = next_month.replace(day=1)
    log.info("partition_manager_started", target_month=str(next_month))
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(
                text("SELECT create_analytics_partition(:d)"), {"d": next_month}
            )
            start = next_month
            end = (start + timedelta(days=32)).replace(day=1)
            partition_name = f"audit_logs_{start.strftime('%Y_%m')}"
            await db.execute(text(f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = '{partition_name}') THEN
                        CREATE TABLE {partition_name} PARTITION OF audit_logs
                        FOR VALUES FROM ('{start}') TO ('{end}');
                    END IF;
                END;
                $$
            """))
            await db.commit()
        duration_ms = round((time.perf_counter() - t0) * 1000)
        log.info(
            "partition_manager_completed",
            month=str(next_month),
            duration_ms=duration_ms,
        )
    except Exception:
        duration_ms = round((time.perf_counter() - t0) * 1000)
        log.exception(
            "partition_manager_failed", month=str(next_month), duration_ms=duration_ms
        )


if __name__ == "__main__":
    import asyncio

    asyncio.run(run())

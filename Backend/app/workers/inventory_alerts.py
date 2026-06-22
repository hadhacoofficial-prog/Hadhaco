"""
Scan products for low stock and emit LowInventoryAlertEvent.
Run every INVENTORY_ALERT_INTERVAL seconds.
"""
from __future__ import annotations

import time

import structlog
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.events import LowInventoryAlertEvent, event_bus

log = structlog.get_logger(__name__)


async def run() -> None:
    t0 = time.perf_counter()
    log.info("inventory_alerts_started")
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(text("""
                SELECT id, name, sku, stock_quantity, low_stock_threshold
                FROM   products
                WHERE  track_inventory = TRUE
                  AND  deleted_at IS NULL
                  AND  status = 'active'
                  AND  stock_quantity <= low_stock_threshold
            """))
            rows = result.mappings().all()
            for row in rows:
                await event_bus.publish(LowInventoryAlertEvent(
                    product_id=str(row["id"]),
                    product_name=row["name"],
                    sku=row["sku"] or "",
                    current_qty=row["stock_quantity"],
                    quantity_after=row["stock_quantity"],
                    threshold=row["low_stock_threshold"],
                ))
        duration_ms = round((time.perf_counter() - t0) * 1000)
        log.info("inventory_alerts_completed", alerts_sent=len(rows), duration_ms=duration_ms)
    except Exception:
        duration_ms = round((time.perf_counter() - t0) * 1000)
        log.exception("inventory_alerts_failed", duration_ms=duration_ms)


if __name__ == "__main__":
    import asyncio
    asyncio.run(run())

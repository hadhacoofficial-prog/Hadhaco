"""
Poll Delivery One for in-transit shipments and update order status.
Run every 15 minutes via APScheduler.
"""
from __future__ import annotations

import time

import structlog
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.modules.orders.models import Order
from app.modules.shipping.service import ShippingService

log = structlog.get_logger(__name__)
_shipping = ShippingService()


async def run() -> None:
    t0 = time.perf_counter()
    log.info("shipment_sync_started")
    errors = 0
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Order).where(Order.status == "shipped"))
            orders = result.scalars().all()
            for order in orders:
                try:
                    await _shipping.sync_shipment_status(db, order_id=order.id)
                except Exception:
                    errors += 1
                    log.exception("shipment_sync_order_failed", order_id=str(order.id))
        duration_ms = round((time.perf_counter() - t0) * 1000)
        log.info("shipment_sync_completed", total=len(orders), errors=errors, duration_ms=duration_ms)
    except Exception:
        duration_ms = round((time.perf_counter() - t0) * 1000)
        log.exception("shipment_sync_failed", duration_ms=duration_ms)


if __name__ == "__main__":
    import asyncio
    asyncio.run(run())

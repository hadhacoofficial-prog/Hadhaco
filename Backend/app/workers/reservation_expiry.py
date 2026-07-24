"""
Reservation expiry worker — runs every 60 seconds.

Finds all ACTIVE inventory reservations that have passed their expires_at
(i.e. the customer did not complete payment within the 10-minute window),
releases the reserved stock back to available, marks the reservation EXPIRED,
and transitions the associated order to payment_expired.

After the inventory module completes its work, this worker orchestrates
downstream side-effects (coupon restoration) via the Orders domain.

Uses SKIP LOCKED on reservation rows so multiple scheduler instances (if any)
never race on the same row.
"""

import structlog

from app.workers.base import run_with_session

log = structlog.get_logger(__name__)


async def run() -> None:
    await run_with_session(_expire_reservations)


async def _expire_reservations(db) -> None:
    from app.modules.inventory.reservation_service import ReservationService
    from app.modules.orders.service import OrderService

    svc = ReservationService()
    # Publishes its own (product-scoped, available-stock-carrying)
    # ReservationExpiredEvent right after committing the release, so
    # connected clients see accurate availability with no further round
    # trip needed for the common case.
    expired_order_ids = await svc.expire_stale_reservations(db)

    if expired_order_ids:
        log.info("reservations_expired_batch", count=len(expired_order_ids))
        order_svc = OrderService()
        await order_svc.handle_expired_order_side_effects(db, expired_order_ids)
        await db.commit()
    else:
        log.debug("reservation_expiry_run_no_expired")

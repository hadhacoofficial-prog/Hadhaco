"""
Reservation expiry worker — runs every 60 seconds.

Finds all ACTIVE inventory reservations that have passed their expires_at
(i.e. the customer did not complete payment within the 10-minute window),
releases the reserved stock back to available, marks the reservation EXPIRED,
and transitions the associated order to payment_expired.

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

    svc = ReservationService()
    expired = await svc.expire_stale_reservations(db)

    if expired:
        log.info("reservations_expired_batch", count=expired)
    else:
        log.debug("reservation_expiry_run_no_expired")

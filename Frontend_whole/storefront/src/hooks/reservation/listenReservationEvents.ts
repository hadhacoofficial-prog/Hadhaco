/**
 * listenReservationEvents — subscribes to SyncBus and updates the reservation store.
 *
 * Single responsibility: react to SyncBus events and update Zustand.
 * Does NOT invalidate React Query.
 *
 * Returns an unsubscribe function for cleanup.
 */

import { getBus, SyncEventType } from "@hadha/shared-api";
import { useReservationStore } from "@/stores/reservation";

/**
 * Subscribe to reservation-related SyncBus events and update the Zustand store.
 *
 * - RESERVATION_EXPIRED: If it's our reservation, expire it.
 * - ORDER_CREATED: If we have a reservation, mark it as converted.
 * - RESERVATION_CREATED: If we had an old reservation that wasn't
 *   converted/expired, clear it (superseded by a new one).
 */
export function listenReservationEvents(): () => void {
  const bus = getBus();

  const unsubExpired = bus.subscribe(SyncEventType.RESERVATION_EXPIRED, (event) => {
    const current = useReservationStore.getState().reservation;
    if (current && event.payload?.reservationId === current.reservationId) {
      useReservationStore.getState().expire();
    }
  });

  const unsubOrder = bus.subscribe(SyncEventType.ORDER_CREATED, () => {
    const current = useReservationStore.getState().reservation;
    if (current) {
      useReservationStore.getState().markConverted();
    }
  });

  const unsubCreated = bus.subscribe(SyncEventType.RESERVATION_CREATED, () => {
    const current = useReservationStore.getState().reservation;
    if (current && current.status !== "converted" && current.status !== "expired") {
      useReservationStore.getState().clear();
    }
  });

  return () => {
    unsubExpired();
    unsubOrder();
    unsubCreated();
  };
}

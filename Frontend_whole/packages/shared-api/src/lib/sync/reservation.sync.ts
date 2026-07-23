/**
 * Reservation Sync Module
 *
 * Owns: reservation-related queries and checkout store state.
 * Subscribes to: RESERVATION_CREATED, RESERVATION_EXPIRED, PAYMENT_FAILED.
 *
 * When a reservation is created, inventory availability changes across
 * all product pages. When it expires, everything reverts.
 */
import { queryKeys } from "../api/queryKeys";
import { SyncEventType, type SyncEvent } from "./events";
import type { SyncBus } from "./SyncBus";

export function registerReservationSync(bus: SyncBus): void {
  const qc = bus.queryClient;

  bus.subscribe(SyncEventType.RESERVATION_CREATED, () => {
    // Reservation holds stock — update everywhere
    qc.invalidateQueries({ queryKey: queryKeys.products.all });
    qc.invalidateQueries({ queryKey: queryKeys.inventory.cartStock([]) });
    qc.invalidateQueries({ queryKey: queryKeys.collections.all });
    qc.invalidateQueries({ queryKey: queryKeys.search.all });
    qc.invalidateQueries({ queryKey: queryKeys.cms.homepage });
    qc.invalidateQueries({ queryKey: queryKeys.orders.activeReservations });
  });

  bus.subscribe(SyncEventType.RESERVATION_EXPIRED, () => {
    // Reservation released — stock restored
    qc.invalidateQueries({ queryKey: queryKeys.products.all });
    qc.invalidateQueries({ queryKey: queryKeys.inventory.cartStock([]) });
    qc.invalidateQueries({ queryKey: queryKeys.collections.all });
    qc.invalidateQueries({ queryKey: queryKeys.search.all });
    qc.invalidateQueries({ queryKey: queryKeys.cms.homepage });
    qc.invalidateQueries({ queryKey: queryKeys.orders.all });
    qc.invalidateQueries({ queryKey: queryKeys.orders.activeReservations });
  });
}

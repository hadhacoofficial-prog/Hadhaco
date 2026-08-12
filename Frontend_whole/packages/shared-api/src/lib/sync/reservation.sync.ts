/**
 * Reservation Sync Module
 *
 * Owns: user-scoped reservation/order/cart queries on reservation events.
 * Subscribes to: RESERVATION_CREATED, RESERVATION_EXPIRED, PAYMENT_FAILED.
 *
 * Stock/list invalidation for reservation events lives in inventory.sync.ts
 * (targeted per `productIds`). This module only invalidates the OWNING user's
 * queries — a reservation created/expired by someone else must not touch this
 * tab's cart/orders (P1-4 per-user scoping).
 */
import { queryKeys } from "../api/queryKeys";
import { SyncEventType } from "./events";
import type { SyncBus } from "./SyncBus";
import { isEventForCurrentUser } from "./userScope";

export function registerReservationSync(bus: SyncBus): void {
  const qc = bus.queryClient;

  bus.subscribe(SyncEventType.RESERVATION_CREATED, async (event) => {
    // Reservation holds stock — refresh the OWNER's reservation badges.
    if (!(await isEventForCurrentUser(event.payload?.userId))) return;
    qc.invalidateQueries({ queryKey: queryKeys.orders.activeReservations });
  });

  bus.subscribe(SyncEventType.RESERVATION_EXPIRED, async (event) => {
    // Reservation released — refresh only the affected users' queries.
    if (!(await isEventForCurrentUser(event.payload?.userIds))) return;
    qc.invalidateQueries({ queryKey: queryKeys.orders.all });
    qc.invalidateQueries({ queryKey: queryKeys.orders.activeReservations });
    qc.invalidateQueries({ queryKey: queryKeys.cart.all });
  });
}

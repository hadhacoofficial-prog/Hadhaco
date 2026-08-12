/**
 * Checkout Sync Module
 *
 * Owns: checkout store state, reservation countdown, payment state.
 * Subscribes to: ORDER_CREATED, RESERVATION_EXPIRED, CART_CHANGED.
 *
 * Ensures checkout state is always consistent with backend state.
 * Order/reservation queries are user-scoped — foreign users' events are
 * skipped (P1-4 per-user scoping).
 */
import { queryKeys } from "../api/queryKeys";
import { SyncEventType } from "./events";
import type { SyncBus } from "./SyncBus";
import { isEventForCurrentUser } from "./userScope";

export function registerCheckoutSync(bus: SyncBus): void {
  const qc = bus.queryClient;

  bus.subscribe(SyncEventType.ORDER_CREATED, async (event) => {
    // Order placed — cart cleared, orders refreshed (owning user only).
    if (!(await isEventForCurrentUser(event.payload?.userId))) return;
    qc.invalidateQueries({ queryKey: queryKeys.orders.all });
    qc.invalidateQueries({ queryKey: queryKeys.orders.activeReservations });
    qc.invalidateQueries({ queryKey: queryKeys.cart.all });
  });

  bus.subscribe(SyncEventType.RESERVATION_EXPIRED, async (event) => {
    // Reservation expired — checkout should reset. The checkout store handles
    // its own reset via Zustand; refresh queries only for affected users.
    if (!(await isEventForCurrentUser(event.payload?.userIds))) return;
    qc.invalidateQueries({ queryKey: queryKeys.orders.all });
    qc.invalidateQueries({ queryKey: queryKeys.orders.activeReservations });
    qc.invalidateQueries({ queryKey: queryKeys.cart.all });
  });

  bus.subscribe(SyncEventType.CART_CHANGED, () => {
    // Cart modified — if checkout is open, revalidate cart stock
    qc.invalidateQueries({ queryKey: queryKeys.cart.all });
  });
}

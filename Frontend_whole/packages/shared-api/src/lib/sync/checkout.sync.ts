/**
 * Checkout Sync Module
 *
 * Owns: checkout store state, reservation countdown, payment state.
 * Subscribes to: ORDER_CREATED, RESERVATION_EXPIRED, CART_CHANGED.
 *
 * Ensures checkout state is always consistent with backend state.
 */
import { queryKeys } from "../api/queryKeys";
import { SyncEventType } from "./events";
import type { SyncBus } from "./SyncBus";

export function registerCheckoutSync(bus: SyncBus): void {
  const qc = bus.queryClient;

  bus.subscribe(SyncEventType.ORDER_CREATED, () => {
    // Order placed — cart cleared, orders refreshed
    qc.invalidateQueries({ queryKey: queryKeys.orders.all });
    qc.invalidateQueries({ queryKey: queryKeys.orders.activeReservations });
    qc.invalidateQueries({ queryKey: queryKeys.cart.all });
  });

  bus.subscribe(SyncEventType.RESERVATION_EXPIRED, () => {
    // Reservation expired — checkout should reset
    // The checkout store handles its own reset via Zustand;
    // we just ensure queries are fresh.
    qc.invalidateQueries({ queryKey: queryKeys.orders.all });
    qc.invalidateQueries({ queryKey: queryKeys.orders.activeReservations });
    qc.invalidateQueries({ queryKey: queryKeys.cart.all });
  });

  bus.subscribe(SyncEventType.CART_CHANGED, () => {
    // Cart modified — if checkout is open, revalidate cart stock
    qc.invalidateQueries({ queryKey: queryKeys.cart.all });
  });
}

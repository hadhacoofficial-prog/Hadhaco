/**
 * Cart Sync Module
 *
 * Owns: cart query keys, cart Zustand store cross-tab sync.
 * Subscribes to: CART_CHANGED, ORDER_CREATED, RESERVATION_EXPIRED, LOGIN, LOGOUT.
 * Broadcasts: cart-changed (via SyncBus).
 */
import { queryKeys } from "../api/queryKeys";
import { SyncEventType, type SyncEvent } from "./events";
import type { SyncBus } from "./SyncBus";

export function registerCartSync(bus: SyncBus): void {
  const qc = bus.queryClient;

  bus.subscribe(SyncEventType.CART_CHANGED, () => {
    qc.invalidateQueries({ queryKey: queryKeys.cart.all });
  });

  bus.subscribe(SyncEventType.ORDER_CREATED, () => {
    // Cart is cleared after order — invalidate so UI reflects empty cart
    qc.invalidateQueries({ queryKey: queryKeys.cart.all });
  });

  bus.subscribe(SyncEventType.RESERVATION_EXPIRED, () => {
    // Reservation expired — cart items may have changed
    qc.invalidateQueries({ queryKey: queryKeys.cart.all });
  });

  bus.subscribe(SyncEventType.LOGIN, () => {
    // On login, server cart may differ from local — refresh
    qc.invalidateQueries({ queryKey: queryKeys.cart.all });
    qc.invalidateQueries({ queryKey: queryKeys.orders.activeReservations });
  });

  bus.subscribe(SyncEventType.LOGOUT, () => {
    qc.invalidateQueries({ queryKey: queryKeys.cart.all });
    qc.invalidateQueries({ queryKey: queryKeys.orders.activeReservations });
  });
}

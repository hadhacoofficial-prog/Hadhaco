/**
 * Cart Sync Module
 *
 * Owns: cart query keys, cart Zustand store cross-tab sync.
 * Subscribes to: CART_CHANGED, ORDER_CREATED, RESERVATION_EXPIRED, LOGIN, LOGOUT.
 * Broadcasts: cart-changed (via SyncBus).
 */
import { queryKeys } from "../api/queryKeys";
import { SyncEventType } from "./events";
import type { SyncBus } from "./SyncBus";
import { isEventForCurrentUser } from "./userScope";

export function registerCartSync(bus: SyncBus): void {
  const qc = bus.queryClient;

  bus.subscribe(SyncEventType.CART_CHANGED, () => {
    qc.invalidateQueries({ queryKey: queryKeys.cart.all });
  });

  bus.subscribe(SyncEventType.ORDER_CREATED, async (event) => {
    // Cart is cleared after order — but only for the OWNING user.
    if (!(await isEventForCurrentUser(event.payload?.userId))) return;
    qc.invalidateQueries({ queryKey: queryKeys.cart.all });
  });

  bus.subscribe(SyncEventType.RESERVATION_EXPIRED, async (event) => {
    // Reservation expired — only the affected users' cart items may change.
    if (!(await isEventForCurrentUser(event.payload?.userIds))) return;
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

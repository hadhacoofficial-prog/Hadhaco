/**
 * Order Sync Module
 *
 * Owns: order queries (list, detail, payment, shipment, invoice).
 * Subscribes to: ORDER_CREATED, ORDER_CANCELLED, ORDER_STATUS_CHANGED.
 *
 * Order queries are user-scoped — events belonging to other users are skipped
 * (P1-4 per-user scoping). ORDER_CANCELLED is local/cross-tab only (no user
 * scope), so it always applies.
 */
import { queryKeys } from "../api/queryKeys";
import { SyncEventType } from "./events";
import type { SyncBus } from "./SyncBus";
import { isEventForCurrentUser } from "./userScope";

export function registerOrderSync(bus: SyncBus): void {
  const qc = bus.queryClient;

  bus.subscribe(SyncEventType.ORDER_CREATED, async (event) => {
    if (!(await isEventForCurrentUser(event.payload?.userId))) return;
    qc.invalidateQueries({ queryKey: queryKeys.orders.all });
    qc.invalidateQueries({ queryKey: queryKeys.orders.activeReservations });
  });

  bus.subscribe(SyncEventType.ORDER_CANCELLED, () => {
    qc.invalidateQueries({ queryKey: queryKeys.orders.all });
    qc.invalidateQueries({ queryKey: queryKeys.orders.activeReservations });
  });

  bus.subscribe(SyncEventType.ORDER_STATUS_CHANGED, async (event) => {
    if (!(await isEventForCurrentUser(event.payload?.userId))) return;
    qc.invalidateQueries({ queryKey: queryKeys.orders.all });
    if (event.payload?.orderId) {
      qc.invalidateQueries({
        queryKey: queryKeys.orders.detail(event.payload.orderId),
      });
    }
  });
}

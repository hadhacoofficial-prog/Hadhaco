/**
 * Order Sync Module
 *
 * Owns: order queries (list, detail, payment, shipment, invoice).
 * Subscribes to: ORDER_CREATED, ORDER_CANCELLED, ORDER_STATUS_CHANGED.
 */
import { queryKeys } from "../api/queryKeys";
import { SyncEventType } from "./events";
import type { SyncBus } from "./SyncBus";

export function registerOrderSync(bus: SyncBus): void {
  const qc = bus.queryClient;

  bus.subscribe(SyncEventType.ORDER_CREATED, () => {
    qc.invalidateQueries({ queryKey: queryKeys.orders.all });
  });

  bus.subscribe(SyncEventType.ORDER_CANCELLED, () => {
    qc.invalidateQueries({ queryKey: queryKeys.orders.all });
  });

  bus.subscribe(SyncEventType.ORDER_STATUS_CHANGED, (event) => {
    qc.invalidateQueries({ queryKey: queryKeys.orders.all });
    if (event.payload?.orderId) {
      qc.invalidateQueries({ queryKey: queryKeys.orders.detail(event.payload.orderId) });
    }
  });
}

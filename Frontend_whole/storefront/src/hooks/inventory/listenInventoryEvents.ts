/**
 * listenInventoryEvents — subscribes to SyncBus and updates the inventory store.
 *
 * Single responsibility: react to SyncBus events and update Zustand.
 * Does NOT invalidate React Query — that's a separate concern.
 *
 * Returns an unsubscribe function for cleanup.
 */

import { getBus, SyncEventType } from "@hadha/shared-api";
import { useInventoryStore, inventoryKey } from "@/stores/inventory";

/**
 * Subscribe to inventory-related SyncBus events and update the Zustand store.
 *
 * - INVENTORY_CHANGED: If productIds provided, mark those entries as needing
 *   reconciliation (confidence drops to "medium"). The next API fetch will
 *   reconcile. If no productIds, all entries get marked.
 * - PRODUCT_UPDATED: Same as INVENTORY_CHANGED for the specific product.
 * - RESERVATION_CREATED/EXPIRED: Mark entries as needing reconciliation.
 * - ORDER_CREATED/CANCELLED: Mark all entries as needing reconciliation.
 *
 * The actual stock reconciliation happens when React Query refetches and
 * hydrateInventoryFromProduct is called. This listener just flags staleness.
 */
export function listenInventoryEvents(): () => void {
  const bus = getBus();

  /** Mark entries as needing reconciliation after an event. */
  function flagStale(productIds?: string[]): void {
    const store = useInventoryStore.getState();
    if (productIds?.length) {
      for (const id of productIds) {
        // Flag base product and all its variants
        const baseKey = inventoryKey(id);
        if (store.entries[baseKey]) {
          store.upsert(id, { source: "sse", confidence: "medium" });
        }
      }
    } else {
      // No specific IDs — flag everything
      for (const [key, entry] of Object.entries(store.entries)) {
        if (key.includes("::")) continue; // Skip variants, only update base
        useInventoryStore.getState().upsert(entry.productId, {
          source: "sse",
          confidence: "medium",
        });
      }
    }
  }

  const unsubs = [
    bus.subscribe(SyncEventType.INVENTORY_CHANGED, (event) => {
      flagStale(event.payload?.productIds);
    }),

    bus.subscribe(SyncEventType.PRODUCT_UPDATED, (event) => {
      flagStale(event.payload?.productId ? [event.payload.productId] : undefined);
    }),

    bus.subscribe(SyncEventType.RESERVATION_CREATED, () => {
      flagStale();
    }),

    bus.subscribe(SyncEventType.RESERVATION_EXPIRED, () => {
      flagStale();
    }),

    bus.subscribe(SyncEventType.ORDER_CREATED, () => {
      flagStale();
    }),

    bus.subscribe(SyncEventType.ORDER_CANCELLED, () => {
      flagStale();
    }),
  ];

  return () => unsubs.forEach((u) => u());
}

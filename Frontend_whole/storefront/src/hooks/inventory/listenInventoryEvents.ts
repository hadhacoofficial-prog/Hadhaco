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
 * - INVENTORY_CHANGED / RESERVATION_CREATED / RESERVATION_EXPIRED now carry
 *   {productIds, availableByProduct} from the backend (see
 *   Backend/app/core/events.py) — when a product's new number is attached,
 *   it's written straight into the store at "high" confidence, so a product
 *   card / PDP / cart line reflects someone else's reservation the instant
 *   the event arrives, with no refetch round trip. Only entries already
 *   present in the store are touched (nothing to reconcile for a product no
 *   component has loaded yet).
 * - If an event carries productIds but no number for one of them (shouldn't
 *   happen for the events above, but kept as a safe fallback), that entry is
 *   just flagged "medium" confidence so the next fetch reconciles it.
 * - PRODUCT_UPDATED / ORDER_CREATED / ORDER_CANCELLED don't carry stock
 *   numbers (different concern — content/lifecycle, not quantity) and keep
 *   the coarser flag-and-refetch behavior.
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

  /** Apply a pushed available-stock number where we have one; otherwise fall
   * back to flagging for reconciliation on the next fetch. */
  function applyAvailable(
    productIds?: string[],
    availableByProduct?: Record<string, number>,
  ): void {
    if (!productIds?.length) {
      flagStale();
      return;
    }
    const store = useInventoryStore.getState();
    for (const id of productIds) {
      const baseKey = inventoryKey(id);
      if (!store.entries[baseKey]) continue; // nothing loaded to reconcile
      const availableStock = availableByProduct?.[id];
      if (availableStock !== undefined) {
        store.upsert(id, { availableStock, source: "sse", confidence: "high" });
      } else {
        store.upsert(id, { source: "sse", confidence: "medium" });
      }
    }
  }

  const unsubs = [
    bus.subscribe(SyncEventType.INVENTORY_CHANGED, (event) => {
      applyAvailable(event.payload?.productIds, event.payload?.availableByProduct);
    }),

    bus.subscribe(SyncEventType.PRODUCT_UPDATED, (event) => {
      flagStale(event.payload?.productId ? [event.payload.productId] : undefined);
    }),

    bus.subscribe(SyncEventType.RESERVATION_CREATED, (event) => {
      applyAvailable(event.payload?.productIds, event.payload?.availableByProduct);
    }),

    bus.subscribe(SyncEventType.RESERVATION_EXPIRED, (event) => {
      applyAvailable(event.payload?.productIds, event.payload?.availableByProduct);
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

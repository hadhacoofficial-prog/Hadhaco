/**
 * Collection Sync Module
 *
 * Owns: collection list, detail, products-in-collection.
 * Subscribes to: COLLECTION_UPDATED, PRODUCT_UPDATED, INVENTORY_CHANGED.
 */
import { queryKeys } from "../api/queryKeys";
import { SyncEventType } from "./events";
import type { SyncBus } from "./SyncBus";

export function registerCollectionSync(bus: SyncBus): void {
  const qc = bus.queryClient;

  bus.subscribe(SyncEventType.COLLECTION_UPDATED, () => {
    qc.invalidateQueries({ queryKey: queryKeys.collections.all });
  });

  bus.subscribe(SyncEventType.PRODUCT_UPDATED, () => {
    // Product changes may affect collection listings (featured, etc.)
    qc.invalidateQueries({ queryKey: queryKeys.collections.all });
  });

  bus.subscribe(SyncEventType.INVENTORY_CHANGED, () => {
    qc.invalidateQueries({ queryKey: queryKeys.collections.all });
  });
}

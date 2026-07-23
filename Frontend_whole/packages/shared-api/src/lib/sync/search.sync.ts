/**
 * Search Sync Module
 *
 * Owns: search results, autocomplete, trending.
 * Subscribes to: PRODUCT_UPDATED, INVENTORY_CHANGED, COLLECTION_UPDATED.
 */
import { queryKeys } from "../api/queryKeys";
import { SyncEventType } from "./events";
import type { SyncBus } from "./SyncBus";

export function registerSearchSync(bus: SyncBus): void {
  const qc = bus.queryClient;

  bus.subscribe(SyncEventType.PRODUCT_UPDATED, () => {
    qc.invalidateQueries({ queryKey: queryKeys.search.all });
  });

  bus.subscribe(SyncEventType.INVENTORY_CHANGED, () => {
    qc.invalidateQueries({ queryKey: queryKeys.search.all });
  });

  bus.subscribe(SyncEventType.COLLECTION_UPDATED, () => {
    qc.invalidateQueries({ queryKey: queryKeys.search.all });
  });

  bus.subscribe(SyncEventType.CMS_PUBLISHED, () => {
    qc.invalidateQueries({ queryKey: queryKeys.search.trending });
  });
}

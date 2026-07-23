/**
 * Homepage Sync Module
 *
 * Owns: CMS homepage, featured products, trending.
 * Subscribes to: INVENTORY_CHANGED, PRODUCT_UPDATED, CMS_PUBLISHED,
 *                COLLECTION_UPDATED.
 */
import { queryKeys } from "../api/queryKeys";
import { SyncEventType } from "./events";
import type { SyncBus } from "./SyncBus";

export function registerHomepageSync(bus: SyncBus): void {
  const qc = bus.queryClient;

  bus.subscribe(SyncEventType.INVENTORY_CHANGED, () => {
    qc.invalidateQueries({ queryKey: queryKeys.cms.homepage });
  });

  bus.subscribe(SyncEventType.PRODUCT_UPDATED, () => {
    qc.invalidateQueries({ queryKey: queryKeys.cms.homepage });
  });

  bus.subscribe(SyncEventType.CMS_PUBLISHED, () => {
    qc.invalidateQueries({ queryKey: queryKeys.cms.homepage });
  });

  bus.subscribe(SyncEventType.COLLECTION_UPDATED, () => {
    qc.invalidateQueries({ queryKey: queryKeys.cms.homepage });
  });

  bus.subscribe(SyncEventType.PRICE_CHANGED, () => {
    qc.invalidateQueries({ queryKey: queryKeys.cms.homepage });
  });
}

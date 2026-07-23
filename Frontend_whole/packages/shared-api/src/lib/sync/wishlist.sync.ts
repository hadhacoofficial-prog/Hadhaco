/**
 * Wishlist Sync Module
 *
 * Owns: wishlist query keys.
 * Subscribes to: WISHLIST_CHANGED.
 */
import { queryKeys } from "../api/queryKeys";
import { SyncEventType } from "./events";
import type { SyncBus } from "./SyncBus";

export function registerWishlistSync(bus: SyncBus): void {
  const qc = bus.queryClient;

  bus.subscribe(SyncEventType.WISHLIST_CHANGED, () => {
    qc.invalidateQueries({ queryKey: queryKeys.wishlist.all });
  });
}

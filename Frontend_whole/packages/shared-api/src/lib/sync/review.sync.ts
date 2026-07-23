/**
 * Review Sync Module
 *
 * Owns: review queries (forProduct, summary, myStatus).
 * Subscribes to: REVIEW_SUBMITTED.
 */
import { queryKeys } from "../api/queryKeys";
import { SyncEventType } from "./events";
import type { SyncBus } from "./SyncBus";

export function registerReviewSync(bus: SyncBus): void {
  const qc = bus.queryClient;

  bus.subscribe(SyncEventType.REVIEW_SUBMITTED, (event) => {
    const productId = event.payload?.productId;
    if (!productId) return;
    qc.invalidateQueries({ queryKey: queryKeys.reviews.forProduct(productId) });
    qc.invalidateQueries({ queryKey: queryKeys.reviews.summary(productId) });
    qc.invalidateQueries({ queryKey: queryKeys.reviews.myStatus(productId) });
  });
}

/**
 * useInventorySync — thin orchestrator for inventory state synchronization.
 *
 * Responsibilities (and ONLY this):
 *   1. Call hydrateInventoryFromProduct when React Query data changes.
 *
 * The SyncBus event listener (listenInventoryEvents) is mounted once,
 * globally, in router.tsx — not here — so real-time pushes apply on every
 * route, not just while a product detail page happens to be mounted.
 *
 * Does NOT:
 *   - Import or use queryClient
 *   - Call invalidateQueries
 *   - Subscribe to events directly (delegated to listenInventoryEvents)
 *   - Derive business logic (delegated to selectors)
 */

import { useEffect } from "react";
import { hydrateInventoryFromProduct } from "@/hooks/inventory/hydrateInventory";
import type { ProductDetail } from "@/types/public";

/**
 * Sync a product's raw inventory data from React Query into the Zustand store.
 *
 * Must be called with the raw `ProductDetail` (not the mapped `Product`)
 * because the mapped type drops the stock fields the store needs.
 */
export function useInventorySync(slug: string, rawProduct: ProductDetail | undefined): void {
  useEffect(() => {
    if (!rawProduct?.id) return;
    hydrateInventoryFromProduct(rawProduct);
  }, [rawProduct]);
}

// Re-export selectors for convenience
export {
  selectAvailableStock,
  selectStockStatus,
  selectIsLowStock,
  selectIsSoldOut,
  selectCanAdd,
  selectBadgeStock,
  selectBadgeStatus,
  selectInventoryVersion,
} from "@/stores/inventory";

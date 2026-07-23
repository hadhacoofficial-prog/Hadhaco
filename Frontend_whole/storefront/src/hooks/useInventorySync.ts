/**
 * useInventorySync — thin orchestrator for inventory state synchronization.
 *
 * Responsibilities (and ONLY these):
 *   1. Call hydrateInventoryFromProduct when React Query data changes.
 *   2. Mount the SyncBus event listener on mount.
 *
 * Does NOT:
 *   - Import or use queryClient
 *   - Call invalidateQueries
 *   - Subscribe to events directly (delegated to listenInventoryEvents)
 *   - Derive business logic (delegated to selectors)
 */

import { useEffect, useRef } from "react";
import { useInventoryStore } from "@/stores/inventory";
import { hydrateInventoryFromProduct } from "@/hooks/inventory/hydrateInventory";
import { listenInventoryEvents } from "@/hooks/inventory/listenInventoryEvents";
import type { ProductDetail } from "@/types/public";

/**
 * Sync a product's raw inventory data from React Query into the Zustand store,
 * and subscribe to SyncBus events for real-time updates.
 *
 * Must be called with the raw `ProductDetail` (not the mapped `Product`)
 * because the mapped type drops the stock fields the store needs.
 */
export function useInventorySync(slug: string, rawProduct: ProductDetail | undefined): void {
  // Hydrate store on data change
  useEffect(() => {
    if (!rawProduct?.id) return;
    hydrateInventoryFromProduct(rawProduct);
  }, [rawProduct]);

  // Mount the SyncBus event listener once
  const listenerRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!listenerRef.current) {
      listenerRef.current = listenInventoryEvents();
    }
    return () => {
      listenerRef.current?.();
      listenerRef.current = null;
    };
  }, []);
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

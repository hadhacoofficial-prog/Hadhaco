/**
 * Inventory Sync Module
 *
 * Owns: server-paginated list invalidation for inventory-affecting events.
 *
 * Product detail and stock state are now managed by the inventory Zustand store
 * (via listenInventoryEvents + hydrateInventoryFromProduct). This module only
 * handles invalidation of server-driven list/catalog/search queries that cannot
 * be stored locally.
 *
 * Subscribes to: INVENTORY_CHANGED, ORDER_CREATED, RESERVATION_CREATED,
 *                RESERVATION_EXPIRED, PRODUCT_UPDATED, PRICE_CHANGED,
 *                ORDER_CANCELLED.
 */
import { queryKeys } from "../api/queryKeys";
import { SyncEventType } from "./events";
import type { SyncBus } from "./SyncBus";

/**
 * Invalidate server-paginated list queries that display stock information.
 *
 * Product detail queries are NOT invalidated here — they're managed by
 * the Zustand inventory store + React Query hydration.
 */
function invalidateServerLists(bus: SyncBus, productIds?: string[]): void {
  const qc = bus.queryClient;

  // Product lists (they display stock badges in grid)
  qc.invalidateQueries({ queryKey: queryKeys.products.all });

  // Cart stock validation
  qc.invalidateQueries({ queryKey: queryKeys.inventory.cartStock([]) });

  // Collections contain products with stock info
  qc.invalidateQueries({ queryKey: queryKeys.collections.all });

  // Search results display stock
  qc.invalidateQueries({ queryKey: queryKeys.search.all });

  // Homepage featured/trending products
  qc.invalidateQueries({ queryKey: queryKeys.cms.homepage });

  // Categories (product counts may change)
  qc.invalidateQueries({ queryKey: queryKeys.categories.all });
}

export function registerInventorySync(bus: SyncBus): void {
  bus.subscribe(SyncEventType.INVENTORY_CHANGED, () => {
    invalidateServerLists(bus);
  });

  bus.subscribe(SyncEventType.ORDER_CREATED, () => {
    invalidateServerLists(bus);
    bus.queryClient.invalidateQueries({
      queryKey: queryKeys.orders.activeReservations,
    });
  });

  bus.subscribe(SyncEventType.RESERVATION_CREATED, () => {
    invalidateServerLists(bus);
    bus.queryClient.invalidateQueries({
      queryKey: queryKeys.orders.activeReservations,
    });
  });

  bus.subscribe(SyncEventType.RESERVATION_EXPIRED, () => {
    invalidateServerLists(bus);
    bus.queryClient.invalidateQueries({
      queryKey: queryKeys.orders.activeReservations,
    });
  });

  bus.subscribe(SyncEventType.PRODUCT_UPDATED, (event) => {
    invalidateServerLists(bus);
    const id = event.payload?.productId;
    if (id) {
      bus.queryClient.invalidateQueries({
        queryKey: queryKeys.products.related(id),
      });
    }
  });

  bus.subscribe(SyncEventType.PRICE_CHANGED, (event) => {
    invalidateServerLists(bus);
    const id = event.payload?.productId;
    if (id) {
      bus.queryClient.invalidateQueries({
        queryKey: queryKeys.products.related(id),
      });
    }
  });

  bus.subscribe(SyncEventType.ORDER_CANCELLED, () => {
    invalidateServerLists(bus);
  });
}

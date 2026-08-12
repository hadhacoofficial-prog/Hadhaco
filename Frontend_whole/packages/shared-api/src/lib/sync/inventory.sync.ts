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
 * Scoping (P1-4): stock-affecting events carry `productIds` in their payload,
 * so instead of blasting every catalog query we invalidate ONLY the queries
 * whose cached data references one of those products (PDP stock/detail, list
 * pages that contain the product). The coarse catalog bust (collections, search,
 * homepage, categories, all products) is reserved for events that actually
 * change list membership — PRODUCT_UPDATED / PRICE_CHANGED (name, status,
 * featured, price).
 *
 * Subscribes to: INVENTORY_CHANGED, ORDER_CREATED, RESERVATION_CREATED,
 *                RESERVATION_EXPIRED, PRODUCT_UPDATED, PRICE_CHANGED,
 *                ORDER_CANCELLED.
 */
import type { Query } from "@tanstack/react-query";

import { queryKeys } from "../api/queryKeys";
import { SyncEventType } from "./events";
import type { SyncBus } from "./SyncBus";

/** True when `data` (or any product nested inside it) has one of `ids`. */
function containsAnyProduct(data: unknown, ids: ReadonlySet<string>): boolean {
  if (Array.isArray(data)) {
    return data.some((item) => containsAnyProduct(item, ids));
  }
  if (!data || typeof data !== "object") return false;
  const obj = data as Record<string, unknown>;
  if (typeof obj.id === "string" && ids.has(obj.id)) return true;
  if (Array.isArray(obj.items)) {
    return obj.items.some((item) => containsAnyProduct(item, ids));
  }
  return false;
}

/**
 * Invalidate only the product queries whose cached data references one of
 * `productIds` (PDP `products.stock(slug)` / `products.detail(slug)` /
 * `products.byId(id)`, and list/infinite pages that contain the product).
 * Queries for other products are untouched.
 */
function invalidateProductsTargeted(bus: SyncBus, productIds: string[]): void {
  const ids = new Set(productIds);
  bus.queryClient.invalidateQueries({
    predicate: (query: Query) => {
      const key = query.queryKey as readonly unknown[];
      if (key[0] !== "products") return false;
      return containsAnyProduct(query.state.data, ids);
    },
  });
}

/** Invalidate the tab's cart stock validation queries (small, user-scoped). */
function invalidateCartStock(bus: SyncBus): void {
  bus.queryClient.invalidateQueries({
    queryKey: queryKeys.inventory.cartStock([]),
  });
}

/**
 * Invalidate stock-affected queries. When the event carries product ids we
 * refetch only those products; otherwise fall back to a coarse `products.all`
 * bust (no collections/search/homepage/categories — stock changes do not alter
 * list membership).
 */
function invalidateStockQueries(bus: SyncBus, productIds?: string[]): void {
  const ids = (productIds ?? []).filter((id) => id.length > 0);
  if (ids.length > 0) {
    invalidateProductsTargeted(bus, ids);
  } else {
    bus.queryClient.invalidateQueries({ queryKey: queryKeys.products.all });
  }
  invalidateCartStock(bus);
}

/**
 * Full catalog bust — only for events that can change list membership
 * (product name/status/featured/price). Refetches products, collections,
 * search, homepage and categories.
 */
function invalidateCatalogBroad(bus: SyncBus): void {
  const qc = bus.queryClient;
  qc.invalidateQueries({ queryKey: queryKeys.products.all });
  qc.invalidateQueries({ queryKey: queryKeys.collections.all });
  qc.invalidateQueries({ queryKey: queryKeys.search.all });
  qc.invalidateQueries({ queryKey: queryKeys.cms.homepage });
  qc.invalidateQueries({ queryKey: queryKeys.categories.all });
  invalidateCartStock(bus);
}

export function registerInventorySync(bus: SyncBus): void {
  bus.subscribe(SyncEventType.INVENTORY_CHANGED, (event) => {
    invalidateStockQueries(bus, event.payload?.productIds);
  });

  bus.subscribe(SyncEventType.ORDER_CREATED, () => {
    // Rare (per purchase); stock refetch itself is covered by the paired
    // INVENTORY_CHANGED, but keep a coarse fallback for safety.
    invalidateStockQueries(bus);
  });

  bus.subscribe(SyncEventType.RESERVATION_CREATED, (event) => {
    invalidateStockQueries(bus, event.payload?.productIds);
  });

  bus.subscribe(SyncEventType.RESERVATION_EXPIRED, (event) => {
    invalidateStockQueries(bus, event.payload?.productIds);
  });

  bus.subscribe(SyncEventType.PRODUCT_UPDATED, (event) => {
    invalidateCatalogBroad(bus);
    const id = event.payload?.productId;
    if (id) {
      bus.queryClient.invalidateQueries({
        queryKey: queryKeys.products.related(id),
      });
    }
  });

  bus.subscribe(SyncEventType.PRICE_CHANGED, (event) => {
    invalidateCatalogBroad(bus);
    const id = event.payload?.productId;
    if (id) {
      bus.queryClient.invalidateQueries({
        queryKey: queryKeys.products.related(id),
      });
    }
  });

  bus.subscribe(SyncEventType.ORDER_CANCELLED, () => {
    // Local/cross-tab only (not SSE-delivered); stock release also publishes
    // a targeted INVENTORY_CHANGED. Coarse fallback for safety.
    invalidateStockQueries(bus);
  });
}

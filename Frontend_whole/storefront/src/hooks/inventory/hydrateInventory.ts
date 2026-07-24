/**
 * hydrateInventory — pure function that writes API data into the Zustand store.
 *
 * Single responsibility: transform ProductDetail → InventoryEntry and upsert.
 * No side effects, no subscriptions, no React Query dependency.
 */

import { useInventoryStore } from "@/stores/inventory";
import type { ProductDetail, ProductListItem } from "@/types/public";

/**
 * Hydrate the inventory Zustand store from a raw ProductDetail API response.
 * Called once per API fetch — the store is the source of truth after this.
 */
export function hydrateInventoryFromProduct(raw: ProductDetail): void {
  if (!raw.id) return;

  useInventoryStore.getState().upsertProduct(raw.id, {
    stock_quantity: raw.stock_quantity,
    available_stock: raw.available_stock ?? raw.stock_quantity,
    reserved_quantity: raw.reserved_quantity ?? 0,
    sold_quantity: raw.sold_quantity ?? 0,
    low_stock_threshold: raw.low_stock_threshold,
    max_order_quantity: raw.max_order_quantity ?? 0,
    track_inventory: raw.track_inventory,
    allow_backorder: raw.allow_backorder,
    base_price: raw.base_price,
    compare_at_price: raw.compare_at_price ?? null,
    variants: raw.variants?.map((v) => ({
      id: v.id,
      stock_quantity: v.stock_quantity,
      available_stock: v.available_stock ?? v.stock_quantity,
      price_adjustment: v.price_adjustment,
    })),
  });
}

/**
 * Hydrate inventory from a batch of products (e.g., product list response).
 */
export function hydrateInventoryFromProducts(products: ProductDetail[]): void {
  for (const raw of products) {
    hydrateInventoryFromProduct(raw);
  }
}

/**
 * Hydrate inventory from list/grid/search results — these only carry the
 * slim `ProductListItem` shape (no reserved/sold/threshold/variants), unlike
 * the full `ProductDetail` a PDP fetches. Writes only the fields we actually
 * have via `upsert` (not `upsertProduct`, which requires the full shape) so
 * every product card/grid can still read a real-time `availableStock` out of
 * the store instead of only ever showing the number from its one-time list
 * fetch.
 */
export function hydrateInventoryFromListItems(items: ProductListItem[]): void {
  const store = useInventoryStore.getState();
  for (const item of items) {
    if (!item.id) continue;
    store.upsert(item.id, {
      variantId: null,
      stockQuantity: item.stock_quantity,
      availableStock: item.available_stock ?? item.stock_quantity,
      price: item.base_price,
      compareAtPrice: item.compare_at_price ?? null,
      source: "api",
      confidence: "high",
    });
  }
}

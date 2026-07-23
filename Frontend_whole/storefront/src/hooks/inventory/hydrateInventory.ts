/**
 * hydrateInventory — pure function that writes API data into the Zustand store.
 *
 * Single responsibility: transform ProductDetail → InventoryEntry and upsert.
 * No side effects, no subscriptions, no React Query dependency.
 */

import { useInventoryStore } from "@/stores/inventory";
import type { ProductDetail } from "@/types/public";

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

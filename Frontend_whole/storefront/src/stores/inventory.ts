/**
 * Inventory Store — first-class business state for stock management.
 *
 * Architecture:
 *   - Zustand owns the inventory state (source of truth)
 *   - React Query fetches from API and hydrates this store
 *   - SyncBus events update this store from other tabs/users
 *   - Mutations update this store optimistically
 *   - Components read from this store via memoized selectors
 *
 * Every product/variant has its own inventory entry keyed by `productId::variantId`.
 * Reservation state lives in the reservation store, NOT here.
 */

import { create } from "zustand";
import { inventoryLog } from "@/lib/sync/syncLog";

// ── Types ─────────────────────────────────────────────────────────────────────

export type StockStatus = "in_stock" | "low_stock" | "sold_out" | "backorder";
export type InventorySource = "api" | "optimistic" | "sse" | "poll";
export type InventoryConfidence = "high" | "medium" | "low";

export interface InventoryEntry {
  /** Product ID. */
  productId: string;
  /** Variant ID (null for base product). */
  variantId: string | null;

  // ── Stock quantities ──────────────────────────────────────────────────────
  stockQuantity: number;
  availableStock: number;
  reservedQuantity: number;
  soldQuantity: number;

  // ── Thresholds ────────────────────────────────────────────────────────────
  lowStockThreshold: number;
  maxOrderQuantity: number;

  // ── Derived status ────────────────────────────────────────────────────────
  stockStatus: StockStatus;

  // ── Inventory policy ──────────────────────────────────────────────────────
  trackInventory: boolean;
  allowBackorder: boolean;

  // ── Price (cached for immediate display) ──────────────────────────────────
  price: number;
  compareAtPrice: number | null;

  // ── Synchronization metadata ──────────────────────────────────────────────
  lastUpdated: number;
  syncVersion: number;
  source: InventorySource;
  confidence: InventoryConfidence;
}

export type InventoryKey = string; // "productId" or "productId::variantId"

// ── Helpers ───────────────────────────────────────────────────────────────────

export function inventoryKey(productId: string, variantId?: string | null): InventoryKey {
  return variantId ? `${productId}::${variantId}` : productId;
}

function deriveStockStatus(entry: {
  availableStock: number;
  lowStockThreshold: number;
  trackInventory: boolean;
  allowBackorder: boolean;
  stockQuantity: number;
}): StockStatus {
  if (!entry.trackInventory) return "in_stock";
  if (entry.availableStock > 0) {
    if (entry.availableStock <= entry.lowStockThreshold) return "low_stock";
    return "in_stock";
  }
  if (entry.allowBackorder && entry.stockQuantity > 0) return "backorder";
  return "sold_out";
}

// ── Store ─────────────────────────────────────────────────────────────────────

interface InventoryState {
  /** Map of inventoryKey → InventoryEntry */
  entries: Record<InventoryKey, InventoryEntry>;

  /** Global sync version (incremented on every update for change detection) */
  version: number;

  // ── Actions ──────────────────────────────────────────────────────────────

  /** Set or merge inventory data for a product (from API response). */
  upsert: (
    productId: string,
    data: Partial<InventoryEntry> & { variantId?: string | null },
  ) => void;

  /** Set inventory for a product and all its variants at once. */
  upsertProduct: (
    productId: string,
    productData: {
      stock_quantity: number;
      available_stock?: number;
      reserved_quantity?: number;
      sold_quantity?: number;
      low_stock_threshold: number;
      max_order_quantity?: number;
      track_inventory: boolean;
      allow_backorder: boolean;
      base_price: number;
      compare_at_price?: number | null;
      variants?: Array<{
        id: string;
        stock_quantity: number;
        available_stock?: number;
        price_adjustment: number;
      }>;
    },
  ) => void;

  /** Optimistically decrement stock (on add-to-cart). */
  optimisticDecrement: (productId: string, variantId: string | null, quantity: number) => void;

  /** Optimistically increment stock (on remove-from-cart or reservation expiry). */
  optimisticIncrement: (productId: string, variantId: string | null, quantity: number) => void;

  /** Get inventory entry for a product/variant. */
  get: (productId: string, variantId?: string | null) => InventoryEntry | undefined;

  /** Get all entries (for iteration). */
  getAll: () => Record<InventoryKey, InventoryEntry>;

  /** Clear all entries (on logout). */
  clear: () => void;
}

export const useInventoryStore = create<InventoryState>()((set, get) => ({
  entries: {},
  version: 0,

  upsert: (productId, data) => {
    const key = inventoryKey(productId, data.variantId);
    set((state) => {
      const existing = state.entries[key];
      const merged = { ...existing, ...data, productId, variantId: data.variantId ?? null };
      const stockStatus = deriveStockStatus({
        availableStock: merged.availableStock ?? 0,
        lowStockThreshold: merged.lowStockThreshold ?? 5,
        trackInventory: merged.trackInventory ?? true,
        allowBackorder: merged.allowBackorder ?? false,
        stockQuantity: merged.stockQuantity ?? 0,
      });
      const source = data.source ?? "api";
      if (source !== "api" || !existing) {
        inventoryLog.upsert(key, source, merged.availableStock ?? 0, stockStatus);
      }
      return {
        entries: {
          ...state.entries,
          [key]: {
            ...merged,
            stockStatus,
            lastUpdated: Date.now(),
            syncVersion: state.version + 1,
            source: data.source ?? "api",
            confidence: data.confidence ?? "high",
          },
        },
        version: state.version + 1,
      };
    });
  },

  upsertProduct: (productId, productData) => {
    const baseEntry = {
      stockQuantity: productData.stock_quantity,
      availableStock: productData.available_stock ?? productData.stock_quantity,
      reservedQuantity: productData.reserved_quantity ?? 0,
      soldQuantity: productData.sold_quantity ?? 0,
      lowStockThreshold: productData.low_stock_threshold,
      maxOrderQuantity: productData.max_order_quantity ?? 0,
      trackInventory: productData.track_inventory,
      allowBackorder: productData.allow_backorder,
      price: productData.base_price,
      compareAtPrice: productData.compare_at_price ?? null,
      source: "api" as InventorySource,
      confidence: "high" as InventoryConfidence,
    };

    // Upsert base product
    get().upsert(productId, { ...baseEntry, variantId: null });

    // Upsert each variant
    if (productData.variants) {
      for (const v of productData.variants) {
        const vAvailable = v.available_stock ?? v.stock_quantity;
        get().upsert(productId, {
          ...baseEntry,
          variantId: v.id,
          stockQuantity: v.stock_quantity,
          availableStock: vAvailable,
          reservedQuantity: 0,
          price: productData.base_price + v.price_adjustment,
        });
      }
    }
  },

  optimisticDecrement: (productId, variantId, quantity) => {
    const key = inventoryKey(productId, variantId);
    const entry = get().entries[key];
    if (!entry) return;

    const newAvailable = Math.max(0, entry.availableStock - quantity);
    const newReserved = entry.reservedQuantity + quantity;
    const newStatus = deriveStockStatus({
      ...entry,
      availableStock: newAvailable,
    });

    set((state) => ({
      entries: {
        ...state.entries,
        [key]: {
          ...entry,
          availableStock: newAvailable,
          reservedQuantity: newReserved,
          stockStatus: newStatus,
          lastUpdated: Date.now(),
          source: "optimistic",
          confidence: "medium",
        },
      },
      version: state.version + 1,
    }));
  },

  optimisticIncrement: (productId, variantId, quantity) => {
    const key = inventoryKey(productId, variantId);
    const entry = get().entries[key];
    if (!entry) return;

    const newAvailable = entry.availableStock + quantity;
    const newReserved = Math.max(0, entry.reservedQuantity - quantity);
    const newStatus = deriveStockStatus({
      ...entry,
      availableStock: newAvailable,
    });

    set((state) => ({
      entries: {
        ...state.entries,
        [key]: {
          ...entry,
          availableStock: newAvailable,
          reservedQuantity: newReserved,
          stockStatus: newStatus,
          lastUpdated: Date.now(),
          source: "optimistic",
          confidence: "medium",
        },
      },
      version: state.version + 1,
    }));
  },

  get: (productId, variantId) => {
    const key = inventoryKey(productId, variantId);
    return get().entries[key];
  },

  getAll: () => get().entries,

  clear: () => set({ entries: {}, version: 0 }),
}));

// ── Memoized Selectors ──────────────────────────────────────────────────────
// Components should use these instead of raw store access.
// Each selector returns a stable reference when the underlying value hasn't changed.

/** Get available stock for a product/variant. Returns 0 if not found. */
export function selectAvailableStock(productId: string, variantId?: string | null) {
  const key = inventoryKey(productId, variantId);
  return (state: InventoryState): number => state.entries[key]?.availableStock ?? 0;
}

/** Get the full stock status for a product/variant. */
export function selectStockStatus(productId: string, variantId?: string | null) {
  const key = inventoryKey(productId, variantId);
  return (state: InventoryState): StockStatus => state.entries[key]?.stockStatus ?? "sold_out";
}

/** Check if a product is low stock (available ≤ threshold). */
export function selectIsLowStock(productId: string, variantId?: string | null) {
  const key = inventoryKey(productId, variantId);
  return (state: InventoryState): boolean => {
    const entry = state.entries[key];
    if (!entry) return false;
    return entry.stockStatus === "low_stock";
  };
}

/** Check if a product is sold out. */
export function selectIsSoldOut(productId: string, variantId?: string | null) {
  const key = inventoryKey(productId, variantId);
  return (state: InventoryState): boolean => {
    const entry = state.entries[key];
    if (!entry) return true;
    return entry.stockStatus === "sold_out";
  };
}

/** Check if user can add more of this product to cart. */
export function selectCanAdd(productId: string, variantId: string | null, currentCartQty: number) {
  const key = inventoryKey(productId, variantId);
  return (state: InventoryState): boolean => {
    const entry = state.entries[key];
    if (!entry) return false;
    if (entry.stockStatus === "sold_out") return false;
    const cap =
      entry.maxOrderQuantity > 0
        ? Math.min(entry.maxOrderQuantity, entry.availableStock)
        : entry.availableStock;
    return cap - currentCartQty > 0;
  };
}

/** Get available stock for the stock badge. Returns 0 if not found. */
export function selectBadgeStock(productId: string, variantId?: string | null) {
  const key = inventoryKey(productId, variantId);
  return (state: InventoryState): number => state.entries[key]?.availableStock ?? 0;
}

/** Get the stock status for the stock badge. */
export function selectBadgeStatus(productId: string, variantId?: string | null) {
  const key = inventoryKey(productId, variantId);
  return (state: InventoryState): StockStatus => state.entries[key]?.stockStatus ?? "sold_out";
}

/** Get the inventory store version. Used to detect any change. */
export function selectInventoryVersion() {
  return (state: InventoryState): number => state.version;
}

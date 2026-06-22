import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface WishlistItem {
  id: string;
  slug: string;
  name: string;
  image: string;
  price: number;
  sku: string;
  variantId?: string;
  variantName?: string;
}

// Unique key for a wishlist entry: same product + different variant = different entries
const itemKey = (id: string, variantId?: string) => `${id}::${variantId ?? ""}`;

interface WishlistState {
  items: WishlistItem[];
  toggle: (item: WishlistItem) => void;
  remove: (id: string, variantId?: string) => void;
  has: (id: string) => boolean;
  clear: () => void;
}

export const useWishlist = create<WishlistState>()(
  persist(
    (set, get) => ({
      items: [],
      toggle: (item) =>
        set((s) => ({
          items: s.items.some((x) => itemKey(x.id, x.variantId) === itemKey(item.id, item.variantId))
            ? s.items.filter((x) => itemKey(x.id, x.variantId) !== itemKey(item.id, item.variantId))
            : [...s.items, item],
        })),
      remove: (id, variantId) =>
        set((s) => ({
          items: s.items.filter((x) => itemKey(x.id, x.variantId) !== itemKey(id, variantId)),
        })),
      // has() is product-level — true if ANY variant of this product is wishlisted.
      // Use items.some() directly for variant-specific checks.
      has: (id) => get().items.some((x) => x.id === id),
      clear: () => set({ items: [] }),
    }),
    { name: "hadha-wishlist" },
  ),
);
